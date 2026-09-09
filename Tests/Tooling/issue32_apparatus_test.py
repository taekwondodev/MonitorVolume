import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "issue32_apparatus.py"
SPEC = importlib.util.spec_from_file_location("issue32_apparatus", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
apparatus = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apparatus)


class Issue32ApparatusTests(unittest.TestCase):
    def fixture(self) -> dict:
        samples = [
            {
                "sequence": 0,
                "status": "sampled",
                "uptimeNanoseconds": 110,
                "rssBytes": 1_024,
                "cumulativeCpuNanoseconds": 1_000,
                "cpuIntervalStartUptimeNanoseconds": None,
                "intervalCpuPercent": None,
            },
            {
                "sequence": 1,
                "status": "failed",
                "uptimeNanoseconds": 150,
                "reason": "fixtureFailure",
            },
            {
                "sequence": 2,
                "status": "sampled",
                "uptimeNanoseconds": 190,
                "rssBytes": 2_048,
                "cumulativeCpuNanoseconds": 1_020,
                "cpuIntervalStartUptimeNanoseconds": None,
                "intervalCpuPercent": None,
            },
            {
                "sequence": 3,
                "status": "censored",
                "uptimeNanoseconds": 210,
                "reason": "fixtureCensor",
            },
        ]
        boundaries = [
            {"phase": "normalUse", "boundary": "start", "uptimeNanoseconds": 100},
            {"phase": "normalUse", "boundary": "end", "uptimeNanoseconds": 200},
        ]
        child_boundaries = [
            {"phase": "normalUse", "boundary": "start", "uptimeNanoseconds": 10_000},
            {"phase": "normalUse", "boundary": "end", "uptimeNanoseconds": 20_000},
        ]
        observed_boundaries = [
            {
                "phase": "normalUse",
                "boundary": "start",
                "childUptimeNanoseconds": 10_000,
                "uptimeNanoseconds": 100,
            },
            {
                "phase": "normalUse",
                "boundary": "end",
                "childUptimeNanoseconds": 20_000,
                "uptimeNanoseconds": 200,
            },
        ]
        apparatus.derive_cpu_intervals(samples)
        report = {
            "candidate": "A",
            "sourceRef": "a" * 40,
            "binding": {"file": "hash"},
            "configurationDigest": "configuration",
            "driverSha256": "driver",
            "expectedScenariosSha256": "matrix",
            "collectionProtocolSha256": "protocol",
            "runnerSha256": "runner",
            "resourceClockSource": "parentObservedPythonMonotonicNanoseconds",
            "rawSamples": samples,
            "observedPhaseBoundaries": observed_boundaries,
            "resourceSummary": apparatus.summarize(samples),
            "phaseResourceSummaries": apparatus.summarize_by_phase(samples, boundaries),
            "failedPollCount": 1,
            "censoredCount": 1,
            "validationFailures": [],
            "childReport": {
                "schemaVersion": 2,
                "topology": ["mainActorBridge"],
                "scenarios": [{"name": "fixture", "values": {"result": "pass"}}],
                "failures": [],
                "apparatus": {
                    "capacity": 8,
                    "clockSource": "systemUptimeMonotonicNanoseconds",
                    "instrumentation": "full",
                    "workloadClass": "normal",
                    "phaseBoundaries": child_boundaries,
                    "phases": [{
                        "phase": "normalUse",
                        "inputEventCount": 1,
                        "passedThroughEventCount": 0,
                        "deliveredCommandCount": 1,
                        "admissionAttempted": 1,
                        "admitted": 1,
                        "rejected": 0,
                        "discarded": 0,
                        "overflow": 0,
                        "completed": 1,
                        "peakOutstanding": 1,
                        "pending": 0,
                    }],
                    "events": [{"kind": "fixture"}],
                    "availability": json.loads(json.dumps(apparatus.EXPECTED_AVAILABILITY)),
                    "failures": [],
                },
            },
        }
        report["behaviorFingerprint"] = apparatus.behavior_fingerprint(report)
        return report

    def test_raw_samples_reconstruct_every_summary_and_retain_missing_data(self) -> None:
        report = self.fixture()

        self.assertEqual(apparatus.validate_raw_report(report), [])
        self.assertEqual(report["resourceSummary"]["sampleCount"], 2)
        self.assertEqual(report["resourceSummary"]["failedPollCount"], 1)
        self.assertEqual(report["resourceSummary"]["censoredCount"], 1)
        self.assertEqual(report["resourceSummary"]["cpuIntervalCount"], 1)
        self.assertEqual(report["phaseResourceSummaries"]["normalUse"]["sampleCount"], 2)
        self.assertEqual(report["phaseResourceSummaries"]["normalUse"]["cpuIntervalCount"], 1)

    def test_cpu_interval_percent_uses_cumulative_rusage_deltas(self) -> None:
        samples = [
            {
                "status": "sampled",
                "uptimeNanoseconds": 1_000_000_000,
                "cumulativeCpuNanoseconds": 100_000_000,
            },
            {
                "status": "sampled",
                "uptimeNanoseconds": 1_100_000_000,
                "cumulativeCpuNanoseconds": 125_000_000,
            },
        ]

        apparatus.derive_cpu_intervals(samples)

        self.assertEqual(samples[1]["cpuIntervalStartUptimeNanoseconds"], 1_000_000_000)
        self.assertEqual(samples[1]["intervalCpuPercent"], 25.0)

    def test_dropped_raw_sample_invalidates_published_summary(self) -> None:
        report = self.fixture()
        report["rawSamples"].pop(0)

        failures = apparatus.validate_raw_report(report)

        self.assertIn("rawSampleSequenceMismatch", failures)
        self.assertIn("resourceSummaryNotReconstructable", failures)
        self.assertIn("phaseSummaryNotReconstructable", failures)

    def test_missing_binding_and_wrong_clock_are_rejected(self) -> None:
        report = self.fixture()
        del report["driverSha256"]
        report["childReport"]["apparatus"]["clockSource"] = "logicalSequence"

        failures = apparatus.validate_raw_report(report)

        self.assertIn("artifactBindingMissing", failures)
        self.assertIn("childClockSourceMismatch", failures)

    def test_missing_native_evidence_limit_is_rejected(self) -> None:
        report = self.fixture()
        report["childReport"]["apparatus"]["availability"].pop()

        self.assertIn("availabilityMismatch", apparatus.validate_raw_report(report))

    def test_missing_phase_rejection_accounting_is_rejected(self) -> None:
        report = self.fixture()
        del report["childReport"]["apparatus"]["phases"][0]["rejected"]

        self.assertIn("phaseAccountingMissing", apparatus.validate_raw_report(report))

    def test_prepared_executable_requires_canonical_path_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            worktree = Path(folder)
            binary = worktree / ".build" / "release" / apparatus.TARGET
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"prepared-release")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()

            resolved, build_command = apparatus.resolve_executable(worktree, binary, digest)

            self.assertEqual(resolved, binary.resolve())
            self.assertIsNone(build_command)
            with self.assertRaisesRegex(apparatus.GateFailure, "hash mismatch"):
                apparatus.resolve_executable(worktree, binary, "0" * 64)
            other = worktree / "other"
            other.write_bytes(binary.read_bytes())
            with self.assertRaisesRegex(apparatus.GateFailure, "Release product"):
                apparatus.resolve_executable(worktree, other, digest)

    def test_candidate_watchdog_kills_hung_process_and_preserves_output(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            phase_events = Path(folder) / "phase-events.jsonl"
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import signal, sys, time; "
                        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                        "print('watchdog-stdout', flush=True); "
                        "print('watchdog-stderr', file=sys.stderr, flush=True); "
                        "time.sleep(10)"
                    ),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )

            stdout, stderr, samples, boundaries, timed_out = apparatus.observe_candidate_process(
                process,
                phase_events,
                poll_interval_seconds=0.01,
                timeout_seconds=0.05,
                termination_grace_seconds=0.05,
            )

            self.assertTrue(timed_out)
            self.assertIsNotNone(process.returncode)
            self.assertIn("watchdog-stdout", stdout)
            self.assertIn("watchdog-stderr", stderr)
            self.assertEqual(boundaries, [])
            self.assertEqual(samples[-1]["reason"], "candidateProcessTimedOut")

    def test_bounded_command_timeout_terminates_its_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            identity = Path(folder) / "process-group.txt"
            command = [
                sys.executable,
                "-c",
                (
                    "import os, pathlib, signal, subprocess, sys, time; "
                    "child=subprocess.Popen([sys.executable, '-c', "
                    "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(10)'], "
                    "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                    f"pathlib.Path({str(identity)!r}).write_text(str(os.getpid()) + ':' + str(child.pid)); "
                    "time.sleep(10)"
                ),
            ]

            with self.assertRaises(subprocess.TimeoutExpired):
                apparatus.run_process(
                    command,
                    cwd=ROOT,
                    timeout_seconds=0.2,
                    termination_grace_seconds=0.05,
                )

            process_group, child_process = (int(value) for value in identity.read_text().split(":"))
            deadline = apparatus.time.monotonic() + 1
            while apparatus.time.monotonic() < deadline:
                status = subprocess.run(
                    ["ps", "-p", f"{process_group},{child_process}", "-o", "stat="],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                states = status.stdout.split()
                if not states or all(state.startswith("Z") for state in states):
                    break
                apparatus.time.sleep(0.01)
            else:
                self.fail("timed-out process group survived cleanup")

    def test_phase_summaries_do_not_merge_normal_and_stress_windows(self) -> None:
        samples = [
            {"sequence": 0, "status": "sampled", "uptimeNanoseconds": 110, "rssBytes": 1, "cpuPercent": 1.0},
            {"sequence": 1, "status": "sampled", "uptimeNanoseconds": 310, "rssBytes": 3, "cpuPercent": 3.0},
        ]
        boundaries = [
            {"phase": "normalUse", "boundary": "start", "uptimeNanoseconds": 100},
            {"phase": "normalUse", "boundary": "end", "uptimeNanoseconds": 200},
            {"phase": "stress", "boundary": "start", "uptimeNanoseconds": 300},
            {"phase": "stress", "boundary": "end", "uptimeNanoseconds": 400},
        ]

        summaries = apparatus.summarize_by_phase(samples, boundaries)

        self.assertEqual(summaries["normalUse"]["maximumRssBytes"], 1)
        self.assertEqual(summaries["stress"]["maximumRssBytes"], 3)

    def test_phase_observer_waits_for_a_complete_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "phases.jsonl"
            path.write_text('{"phase":"idle"')
            observations = []

            offset = apparatus.observe_phase_events(path, 0, observations)

            self.assertEqual(offset, 0)
            self.assertEqual(observations, [])
            path.write_text('{"phase":"idle","boundary":"start","uptimeNanoseconds":42}\n')
            offset = apparatus.observe_phase_events(path, offset, observations)
            self.assertEqual(offset, path.stat().st_size)
            self.assertEqual(observations[0]["childUptimeNanoseconds"], 42)

    def test_same_candidate_control_ignores_resource_and_timestamp_noise(self) -> None:
        left = self.fixture()
        right = json.loads(json.dumps(left))
        right["rawSamples"][0]["rssBytes"] = 999_999
        right["childReport"]["apparatus"]["phaseBoundaries"][0]["uptimeNanoseconds"] += 42

        self.assertEqual(apparatus.validate_control_pair(left, right), [])

    def test_control_rejects_candidate_source_and_behavior_drift(self) -> None:
        left = self.fixture()
        right = json.loads(json.dumps(left))
        right["candidate"] = "B"
        right["sourceRef"] = "b" * 40
        right["childReport"]["apparatus"]["phases"][0]["inputEventCount"] = 2

        failures = apparatus.validate_control_pair(left, right)

        self.assertEqual(
            failures,
            ["controlCandidateMismatch", "controlSourceRefMismatch", "controlBehaviorMismatch"],
        )

    def test_instrumentation_control_requires_full_and_none_with_identical_behavior(self) -> None:
        full = self.fixture()
        full["frozenProtocol"] = {"instrumentation": "full", "workloadClass": "normal"}
        none = json.loads(json.dumps(full))
        none["frozenProtocol"]["instrumentation"] = "none"
        none["childReport"]["apparatus"]["instrumentation"] = "none"
        none["childReport"]["apparatus"]["events"] = []

        self.assertEqual(apparatus.validate_instrumentation_pair(full, none), [])

        none["childReport"]["apparatus"]["phases"][0]["inputEventCount"] = 2
        self.assertIn(
            "instrumentationBehaviorMismatch",
            apparatus.validate_instrumentation_pair(full, none),
        )

    def test_gate_refuses_to_reuse_an_evidence_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing"
            output.mkdir()
            args = types.SimpleNamespace(
                worktree=ROOT,
                output_dir=output,
                candidate="A",
                source_ref="a" * 40,
                workload="normal",
                instrumentation="full",
                run_ordinal=1,
            )

            with self.assertRaisesRegex(apparatus.GateFailure, "already exists"):
                apparatus.gate(args)

    def test_cli_exposes_gate_and_control_but_no_comparative_collection(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("gate", result.stdout)
        self.assertIn("control", result.stdout)
        self.assertNotIn("compare", result.stdout)


if __name__ == "__main__":
    unittest.main()
