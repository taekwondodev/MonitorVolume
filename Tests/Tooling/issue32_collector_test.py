import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import issue32_apparatus as apparatus
from scripts import issue32_collection_protocol as protocol_module
from scripts import issue32_collector as collector


ROOT = Path(__file__).resolve().parents[2]


class Issue32CollectorTests(unittest.TestCase):
    def control_report(self, candidate: str, instrumentation: str, workload: str = "normal") -> dict:
        source_ref = protocol_module.load_protocol()["candidates"][candidate]["sourceRef"]
        report = {
            "candidate": candidate,
            "sourceRef": source_ref,
            "collectionProtocolSha256": collector.protocol_sha256(),
            "runnerSha256": collector.sha256_file(ROOT / "scripts" / "issue32_apparatus.py"),
            "expectedScenariosSha256": collector.sha256_file(apparatus.EXPECTED_SCENARIOS_PATH),
            "validationFailures": [],
            "exitCode": 0,
            "configurationDigest": f"{candidate}-{workload}-full-config",
            "frozenProtocol": {
                "workloadClass": workload,
                "instrumentation": instrumentation,
            },
            "executable": {"sha256": hashlib.sha256(candidate.encode()).hexdigest()},
            "childReport": {
                "scenarios": [{"name": "literal", "values": {"passed": True}}],
                "failures": [],
                "apparatus": {
                    "workloadClass": workload,
                    "instrumentation": instrumentation,
                    "phases": [{"phase": "literal", "inputEventCount": 1}],
                },
            },
        }
        report["behaviorFingerprint"] = apparatus.behavior_fingerprint(report)
        return report

    def write_control_reports(self, folder: Path) -> list[Path]:
        paths: list[Path] = []
        for candidate in ("A", "B"):
            for ordinal, instrumentation in enumerate(("full", "full", "none"), 1):
                path = folder / f"{candidate}-{instrumentation}-{ordinal}.json"
                path.write_text(json.dumps(self.control_report(candidate, instrumentation)))
                paths.append(path)
        return paths

    def test_schedule_materializes_168_runs_in_balanced_blocks(self) -> None:
        protocol = protocol_module.load_protocol()
        warmup, measured = collector.materialize_run_specs(protocol)
        warmup_blocks = collector.workload_blocks(warmup)
        measured_blocks = collector.workload_blocks(measured)

        self.assertEqual((len(warmup), len(measured)), (8, 160))
        self.assertEqual((len(warmup_blocks), len(measured_blocks)), (2, 40))
        self.assertEqual(
            {(item.candidate, item.instrumentation) for item in measured_blocks[0]},
            {("A", "full"), ("B", "full"), ("A", "none"), ("B", "none")},
        )

    def test_control_manifest_reconstructs_from_six_bound_reports(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            paths = self.write_control_reports(Path(folder))

            manifest = collector.control_manifest(paths)

            self.assertEqual(manifest["status"], "controlsValidated")
            self.assertEqual(len(manifest["reports"]), 6)
            collector.validate_control_manifest(manifest)
            paths[0].write_text("{}")
            with self.assertRaises(collector.CollectionError):
                collector.validate_control_manifest(manifest)

    def test_control_manifest_rejects_behavior_drift(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            paths = self.write_control_reports(Path(folder))
            report = json.loads(paths[1].read_text())
            report["childReport"]["apparatus"]["phases"][0]["inputEventCount"] = 2
            report["behaviorFingerprint"] = apparatus.behavior_fingerprint(report)
            paths[1].write_text(json.dumps(report))

            with self.assertRaisesRegex(collector.CollectionError, "repeatability"):
                collector.control_manifest(paths)

    def test_environment_parsers_require_ac_and_explicit_low_power_value(self) -> None:
        self.assertEqual(collector.parse_power_source("Now drawing from 'AC Power'\n"), "ac")
        self.assertFalse(collector.parse_ac_low_power_mode("Battery Power:\n lowpowermode 1\nAC Power:\n lowpowermode 0\n"))
        self.assertTrue(collector.parse_ac_low_power_mode("AC Power:\n lowpowermode 1\n"))
        with self.assertRaises(collector.CollectionError):
            collector.parse_power_source("unknown")
        with self.assertRaises(collector.CollectionError):
            collector.parse_ac_low_power_mode("AC Power:\n standby 1\n")

    def test_environment_validation_rejects_drift(self) -> None:
        baseline = {
            "powerSource": "ac",
            "lowPowerMode": False,
            "thermalState": "nominal",
            "logicalCpuCount": 10,
            "identity": {"swVers": "A", "machine": "arm64", "model": "Mac", "swift": "Swift"},
        }
        collector.validate_environment(baseline)
        drifted = json.loads(json.dumps(baseline))
        drifted["identity"]["swVers"] = "B"
        with self.assertRaisesRegex(collector.CollectionError, "identity changed"):
            collector.validate_environment(drifted, baseline)

    def test_timing_pairs_same_input_and_uses_final_return_for_drain(self) -> None:
        report = {
            "childReport": {"apparatus": {"events": [
                {"phase": "isolatedInput", "kind": "typedBridgeRequested", "input": "down", "uptimeNanoseconds": 10},
                {"phase": "isolatedInput", "kind": "typedBridgeReturned", "input": "down", "uptimeNanoseconds": 20},
                {"phase": "isolatedInput", "kind": "typedBridgeRequested", "input": "up", "uptimeNanoseconds": 25},
                {"phase": "isolatedInput", "kind": "typedBridgeReturned", "input": "up", "uptimeNanoseconds": 40},
                {"phase": "isolatedInput", "kind": "consumerDrained", "uptimeNanoseconds": 70},
            ]}}
        }

        bridge, drain = collector.timing_values(report, "isolatedInput")

        self.assertEqual(bridge, [10, 15])
        self.assertEqual(drain, [30])

    def test_statistics_follow_frozen_worked_examples(self) -> None:
        self.assertEqual(collector.median_absolute_successive_difference([float(value) for value in range(20)]), 1.0)
        self.assertEqual(collector.bootstrap_interval([-2.0] * 20, seed=320032, resamples=100), (-2.0, -2.0))
        self.assertEqual(collector.classify_interval(-1.0, 1.0, 1.0), "equivalent")
        self.assertEqual(collector.classify_interval(-3.0, -2.0, 1.0), "candidateBBetter")
        self.assertEqual(collector.classify_interval(2.0, 3.0, 1.0), "candidateABetter")
        self.assertEqual(collector.classify_interval(-2.0, 2.0, 1.0), "inconclusive")

    def test_selection_never_promotes_b_before_lifecycle_review(self) -> None:
        self.assertEqual(collector.select_candidate(["equivalent", "candidateABetter"], False), "A")
        self.assertEqual(collector.select_candidate(["equivalent", "candidateBBetter"], False), "inconclusive")
        self.assertEqual(collector.select_candidate(["equivalent", "candidateBBetter"], True), "B")
        self.assertEqual(collector.select_candidate(["candidateABetter", "candidateBBetter"], True), "inconclusive")

    def test_empty_classifications_are_inconclusive(self) -> None:
        self.assertEqual(collector.select_candidate([], False), "inconclusive")
        self.assertEqual(collector.select_candidate([], True), "inconclusive")

    def test_command_timeout_becomes_collection_error(self) -> None:
        with self.assertRaisesRegex(collector.CollectionError, "command timed out after 0.05s"):
            collector.run_command(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                ROOT,
                0.05,
                0.05,
            )

    def test_compare_reports_uses_all_selected_paired_cells(self) -> None:
        records: list[dict] = []
        reports: dict[Path, dict] = {}
        metrics: dict[int, dict[str, float]] = {}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sequence = 0
            for round_ordinal in range(1, 21):
                for workload in ("normal", "stress"):
                    for candidate in ("A", "B"):
                        for instrumentation in ("full", "none"):
                            sequence += 1
                            path = (root / f"report-{sequence}.json").resolve()
                            report = {"id": sequence, "failedPollCount": 0, "censoredCount": 0}
                            reports[path] = report
                            metrics[sequence] = {
                                "accounting.attempted.phase": 1.0,
                                "cpu.meanOneCorePercent.phase": float(round_ordinal + (2 if candidate == "B" else 0)),
                            }
                            records.append({
                                "stage": "measured",
                                "round": round_ordinal,
                                "workload": workload,
                                "candidate": candidate,
                                "instrumentation": instrumentation,
                                "selected": True,
                                "reportPath": str(path),
                            })

            with (
                mock.patch.object(collector, "read_bound_report", side_effect=lambda record: reports[Path(record["reportPath"])]),
                mock.patch.object(collector, "run_metrics", side_effect=lambda report, _: metrics[report["id"]]),
            ):
                analysis = collector.compare_reports(records, logical_cpu_count=10)

        self.assertEqual(analysis["status"], "analyzed")
        self.assertEqual(analysis["exactAccountingFailures"], [])
        self.assertEqual(len(analysis["accountingByPairedRun"]), 80)
        self.assertEqual(len(analysis["comparisons"]), 4)
        self.assertEqual({item["classification"] for item in analysis["comparisons"]}, {"candidateABetter"})
        self.assertEqual(analysis["provisionalSelectionBeforeLifecycleReview"], "A")

    def test_analysis_rejects_a_changed_retained_report(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            path.write_text("{}")
            record = {
                "candidate": "A",
                "workload": "normal",
                "instrumentation": "full",
                "reportPath": str(path),
                "reportSha256": collector.sha256_file(path),
            }
            path.write_text('{"candidate":"A"}')

            with self.assertRaisesRegex(collector.CollectionError, "measured report digest mismatch"):
                collector.read_bound_report(record)

    def test_analysis_rejects_a_bound_report_with_validation_failures(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            path.write_text("{}")
            protocol = protocol_module.load_protocol()
            report = {
                "candidate": "A",
                "sourceRef": protocol["candidates"]["A"]["sourceRef"],
                "collectionProtocolSha256": collector.protocol_sha256(),
                "runnerSha256": collector.sha256_file(ROOT / "scripts" / "issue32_apparatus.py"),
                "expectedScenariosSha256": collector.sha256_file(apparatus.EXPECTED_SCENARIOS_PATH),
                "exitCode": 0,
                "validationFailures": ["fixtureFailure"],
            }
            record = {
                "candidate": "A",
                "workload": "normal",
                "instrumentation": "full",
                "reportPath": str(path),
                "reportSha256": collector.sha256_file(path),
            }

            with (
                mock.patch.object(collector, "read_report", return_value=report),
                self.assertRaisesRegex(collector.CollectionError, "measured report validation failure"),
            ):
                collector.read_bound_report(record)

    def test_gate_rejects_apparatus_or_matrix_drift_before_execution(self) -> None:
        prepared = collector.PreparedCandidate(
            candidate="A",
            worktree=ROOT,
            source_ref=protocol_module.load_protocol()["candidates"]["A"]["sourceRef"],
            source_closure={},
            executable=ROOT / "missing",
            executable_sha256="0" * 64,
            compiler="Swift",
        )
        spec = collector.RunSpec("measured", 1, "normal", "A", "full", 1)
        current_matrix = collector.sha256_file(apparatus.EXPECTED_SCENARIOS_PATH)
        current_apparatus = collector.sha256_file(ROOT / "scripts" / "issue32_apparatus.py")

        with self.assertRaisesRegex(collector.CollectionError, "apparatus changed"):
            collector.run_gate(prepared, spec, ROOT / "unused", collector.protocol_sha256(), "0" * 64, current_matrix)
        with self.assertRaisesRegex(collector.CollectionError, "expected matrix changed"):
            collector.run_gate(prepared, spec, ROOT / "unused", collector.protocol_sha256(), current_apparatus, "0" * 64)

    def test_analyze_revalidates_an_already_analyzed_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            campaign = Path(folder)
            state_path = campaign / "campaign-state.json"
            state_path.write_text(json.dumps({
                "status": "analyzed",
                "protocolSha256": collector.protocol_sha256(),
                "collectorSha256": collector.sha256_file(Path(collector.__file__)),
                "apparatusSha256": collector.sha256_file(ROOT / "scripts" / "issue32_apparatus.py"),
                "expectedScenariosSha256": collector.sha256_file(apparatus.EXPECTED_SCENARIOS_PATH),
                "records": [],
                "environmentObservations": [{"logicalCpuCount": 10}],
            }))
            expected = {"schemaVersion": 1, "status": "analyzed", "comparisons": []}

            with (
                mock.patch.object(sys, "argv", ["issue32_collector.py", "analyze", "--campaign-dir", str(campaign)]),
                mock.patch.object(collector, "compare_reports", return_value=expected) as compare,
                mock.patch("builtins.print"),
            ):
                result = collector.main()

            persisted_state = json.loads(state_path.read_text())
            self.assertEqual(result, 0)
            compare.assert_called_once_with([], 10)
            self.assertEqual(json.loads((campaign / "analysis.json").read_text()), expected)
            self.assertEqual(persisted_state["status"], "analyzed")
            self.assertEqual(persisted_state["analysisPath"], str((campaign / "analysis.json").resolve()))

    def test_collect_is_fail_closed_without_exact_execution_flag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "campaign"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "issue32_collector.py"),
                    "collect",
                    "--controls", str(Path(folder) / "missing-controls.json"),
                    "--worktree-a", str(Path(folder) / "a"),
                    "--worktree-b", str(Path(folder) / "b"),
                    "--output-dir", str(output),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--execute-frozen-campaign", result.stderr)
            self.assertFalse(output.exists())

    def test_cli_has_no_override_for_schedule_or_statistics(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "issue32_collector.py"), "collect", "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("--rounds", result.stdout)
        self.assertNotIn("--seed", result.stdout)
        self.assertNotIn("--resamples", result.stdout)
        self.assertNotIn("--order", result.stdout)


if __name__ == "__main__":
    unittest.main()
