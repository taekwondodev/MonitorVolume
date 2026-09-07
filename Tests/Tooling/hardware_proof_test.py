import copy
import fcntl
import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
app_tool = importlib.import_module("app_tool")
validate_hardware_proof = importlib.import_module("hardware_proof").validate_hardware_proof

spec = importlib.util.spec_from_file_location(
    "proof_driver", ROOT / ".hermes/skills/verify-proart-volume/scripts/verify.py")
assert spec is not None and spec.loader is not None
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def confirmed(state, write=True):
    return {"confirmed": True, "writeAttempted": write, "observed": state, "elapsedNanoseconds": 1}


def report_at(volume=80):
    initial = {"volume": volume, "mute": "unmuted"}
    changed = {"volume": 99 if volume == 100 else volume + 1, "mute": "unmuted"}
    muted = {"volume": volume, "mute": "muted"}
    return {"status": "passed", "phases": [
        {"control": control, "initial": initial, "requested": requested,
         "transition": confirmed(requested), "restorationRequested": initial,
         "restoration": confirmed(initial)}
        for control, requested in [("volume", changed), ("mute", muted)]
    ], "final": confirmed(initial, write=False)}


class HardwareProofTests(unittest.TestCase):
    def test_spec_transitions(self):
        for volume in (80, 100):
            validate_hardware_proof(report_at(volume))

    def test_rejects_incomplete_or_fabricated_success(self):
        changes = [
            lambda r: r["phases"].clear(),
            lambda r: r["phases"][0].update(requested=r["phases"][0]["initial"]),
            lambda r: r["phases"][0]["transition"].pop("observed"),
            lambda r: r["phases"][0]["restoration"].update(observed={"volume": 81, "mute": "unmuted"}),
            lambda r: r["phases"][1].update(control="volume"),
            lambda r: r["final"].update(observed={"volume": True, "mute": "unmuted"}),
            lambda r: r["phases"][0]["transition"].update(elapsedNanoseconds=-1),
            lambda r: r["phases"][0]["restoration"].update(confirmed=False, error="writeFailure"),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                report = copy.deepcopy(report_at())
                change(report)
                with self.assertRaises(RuntimeError):
                    validate_hardware_proof(report)

    def test_failed_transition_and_stopped_restoration_are_valid_failures(self):
        failure = {"confirmed": False, "writeAttempted": True, "error": "writeFailure", "elapsedNanoseconds": 1}
        report = report_at()
        report["status"] = "failed"
        report["phases"][0]["transition"] = failure
        validate_hardware_proof(report)
        report["phases"][0]["restoration"] = failure
        report["phases"] = report["phases"][:1]
        report["final"] = {**failure, "writeAttempted": False}
        validate_hardware_proof(report)
        validate_hardware_proof({"status": "failed", "phases": [], "final": report["final"]})

    def test_probe_persists_nonzero_and_malformed_evidence(self):
        failed = report_at()
        failed["status"] = "failed"
        failed["phases"][0]["transition"] = {
            "confirmed": False, "writeAttempted": True,
            "error": "writeFailure", "elapsedNanoseconds": 1}
        for stdout, code in [(json.dumps(report_at()), 0), (json.dumps(failed), 5), ("broken JSON", 5),
                             (json.dumps(report_at()), 5)]:
            with self.subTest(code=code, stdout=stdout), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                executable = root / ".build/release/ProArtVolumeRuntimeProbe"
                executable.parent.mkdir(parents=True)
                executable.write_text("#!/bin/sh\nexit 0\n")
                executable.chmod(0o755)
                installed = root / "installed"
                installed.write_bytes(b"test-only executable binding")
                calls = []

                def execute(*args, **kwargs):
                    self.assertEqual(calls, ["stop"])
                    return subprocess.CompletedProcess(args[0], code, stdout, "diagnostic")

                with patch.object(app_tool, "ROOT", root), \
                     patch.object(app_tool, "INSTALLED_EXECUTABLE", installed), \
                     patch.object(app_tool, "build_release", return_value=installed), \
                     patch.object(app_tool, "stop_installed_app", side_effect=lambda: calls.append("stop")), \
                     patch.object(app_tool, "exact_processes", return_value=[]), \
                     patch.object(app_tool.subprocess, "run", side_effect=execute):
                    result = app_tool.probe_monitor_status()
                evidence = json.loads(Path(result["evidence"]).read_text())
                self.assertEqual(evidence["stdout"], stdout)
                self.assertEqual(evidence["returncode"], code)
                self.assertEqual(evidence["status"], "passed" if code == 0 else "failed")
                self.assertIn("installedExecutableSHA256", evidence)
                if stdout == json.dumps(failed):
                    self.assertEqual(evidence["report"], failed)
                    self.assertNotIn("error", evidence)

    def test_probe_lock_contention_starts_no_build_or_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lock_path = root / ".hermes/verification/hardware-proof.lock"
            lock_path.parent.mkdir(parents=True)
            with lock_path.open("a") as owner:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(app_tool, "ROOT", root), \
                     patch.object(app_tool, "build_release") as build, \
                     patch.object(app_tool, "stop_installed_app") as stop, \
                     patch.object(app_tool.subprocess, "run") as run:
                    with self.assertRaises(BlockingIOError):
                        app_tool.probe_monitor_status()
                    build.assert_not_called()
                    stop.assert_not_called()
                    run.assert_not_called()

    def test_driver_failure_preserves_evidence_and_owned_cleanup_scope(self):
        for failure in ("build-app.sh", "verify-installed-app.sh", "cleanup"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                calls = []

                def command(command, **kwargs):
                    name = Path(command[0]).name
                    cleanup = name == "stop-app.sh" and "probe-monitor-status.sh" in calls
                    calls.append(name)
                    failed = name == failure or (failure == "cleanup" and cleanup)
                    return subprocess.CompletedProcess(command, 1 if failed else 0,
                        json.dumps({"status": "failed" if failed else "passed"}),
                        "controlled failure" if failed else "")

                with patch.object(driver, "repository_root", return_value=root), \
                     patch.object(driver.subprocess, "run", side_effect=command):
                    result = driver.prove()
                saved = json.loads(Path(result["evidence"]).read_text())
                self.assertEqual(result["status"], "failed")
                self.assertEqual(saved["status"], "failed")
                if failure == "build-app.sh":
                    self.assertEqual(calls, ["build-app.sh"])
                    self.assertNotIn("cleanup", saved)
                elif failure == "verify-installed-app.sh":
                    self.assertEqual(calls, ["build-app.sh", "verify-installed-app.sh", "stop-app.sh"])
                    self.assertIn("cleanup", saved)
                    self.assertNotIn("hardware_proof", saved)
                else:
                    self.assertIn("hardware_proof", saved)
                    self.assertIn("cleanup_error", saved)

    def test_probe_refuses_surviving_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / ".build/release/ProArtVolumeRuntimeProbe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            executable.chmod(0o755)
            with patch.object(app_tool, "ROOT", root), \
                 patch.object(app_tool, "INSTALLED_EXECUTABLE", executable), \
                 patch.object(app_tool, "build_release", return_value=executable), \
                 patch.object(app_tool, "stop_installed_app"), \
                 patch.object(app_tool, "exact_processes", return_value=[123]), \
                 patch.object(app_tool.subprocess, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "owner"):
                    app_tool.probe_monitor_status()
                run.assert_not_called()

    def test_driver_stops_before_probe_and_persists_failure_before_cleanup(self):
        for passed in (True, False):
            with self.subTest(passed=passed), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                calls = []
                def command(command, cwd, text, capture_output):
                    name = Path(command[0]).name
                    if name == "probe-monitor-status.sh":
                        self.assertEqual(calls[-1], "stop-app.sh")
                    if name == "stop-app.sh" and "probe-monitor-status.sh" in calls:
                        saved = list(root.glob(".hermes/verification/evidence/*/launch.json"))
                        self.assertEqual(len(saved), 1)
                        self.assertIn("hardware_proof", json.loads(saved[0].read_text()))
                    calls.append(name)
                    success = passed or name != "probe-monitor-status.sh"
                    return subprocess.CompletedProcess(command, 0 if success else 1,
                        json.dumps({"status": "passed" if success else "failed", "phases": []}), "")
                with patch.object(driver, "repository_root", return_value=root), \
                     patch.object(driver.subprocess, "run", side_effect=command):
                    result = driver.prove()
                self.assertEqual(calls, ["build-app.sh", "verify-installed-app.sh", "stop-app.sh",
                                         "probe-monitor-status.sh", "stop-app.sh"])
                self.assertEqual(result["status"], "passed" if passed else "failed")
                self.assertTrue(Path(result["evidence"]).is_file())


if __name__ == "__main__":
    unittest.main()
