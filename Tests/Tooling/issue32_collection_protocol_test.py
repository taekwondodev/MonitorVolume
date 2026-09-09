import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "issue32_collection_protocol.py"
SPEC = importlib.util.spec_from_file_location("issue32_collection_protocol", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
protocol_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(protocol_module)


class Issue32CollectionProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.protocol = protocol_module.load_protocol()

    def test_schedule_is_balanced_and_frozen_before_collection(self) -> None:
        schedule = protocol_module.measured_schedule(self.protocol)

        self.assertEqual(len(schedule), 160)
        for workload in ("normal", "stress"):
            for candidate in ("A", "B"):
                for instrumentation in ("full", "none"):
                    selected = [
                        item for item in schedule
                        if item["workload"] == workload
                        and item["candidate"] == candidate
                        and item["instrumentation"] == instrumentation
                    ]
                    self.assertEqual(len(selected), 20)
        self.assertEqual(
            self.protocol["measuredCollection"]["crossCandidateExecution"],
            "blockedUntilOfflineGatesAndControlsPass",
        )

    def test_candidate_order_and_workload_order_are_counterbalanced(self) -> None:
        schedule = protocol_module.measured_schedule(self.protocol)

        first_workloads = [
            schedule[index]["workload"]
            for index in range(0, len(schedule), 8)
        ]
        self.assertEqual(first_workloads, ["normal", "stress"] * 10)
        for round_ordinal in range(1, 21):
            round_items = [item for item in schedule if item["round"] == round_ordinal]
            for workload in ("normal", "stress"):
                selected = [item for item in round_items if item["workload"] == workload]
                self.assertEqual(len(selected), 4)
                self.assertEqual({item["candidate"] for item in selected}, {"A", "B"})
                self.assertEqual({item["instrumentation"] for item in selected}, {"full", "none"})

    def test_protocol_matches_single_candidate_gate_constants(self) -> None:
        apparatus_path = ROOT / "scripts" / "issue32_apparatus.py"
        apparatus_spec = importlib.util.spec_from_file_location("issue32_apparatus", apparatus_path)
        assert apparatus_spec is not None and apparatus_spec.loader is not None
        apparatus = importlib.util.module_from_spec(apparatus_spec)
        apparatus_spec.loader.exec_module(apparatus)
        gate = self.protocol["gate"]

        self.assertEqual(gate["capacity"], apparatus.FROZEN_PROTOCOL["capacity"])
        self.assertEqual(gate["phaseDurationMilliseconds"], apparatus.FROZEN_PROTOCOL["phaseDurationMilliseconds"])
        self.assertEqual(gate["pollIntervalMilliseconds"], apparatus.FROZEN_PROTOCOL["pollIntervalMilliseconds"])
        self.assertEqual(gate["clockSource"], apparatus.FROZEN_PROTOCOL["clockSource"])
        self.assertEqual(gate["cpuSource"], apparatus.FROZEN_PROTOCOL["cpuSource"])
        self.assertEqual(gate["missingDataPolicy"], apparatus.FROZEN_PROTOCOL["missingDataPolicy"])
        self.assertEqual(gate["candidateProcessTimeoutSeconds"], apparatus.FROZEN_PROTOCOL["candidateProcessTimeoutSeconds"])
        self.assertEqual(gate["terminationGraceSeconds"], apparatus.FROZEN_PROTOCOL["terminationGraceSeconds"])

    def test_missing_data_and_selection_have_no_implicit_fallback(self) -> None:
        missing = self.protocol["missingData"]
        selection = self.protocol["selection"]

        self.assertEqual(missing["numericImputation"], "none")
        self.assertEqual(missing["afterReplacementLimit"], "inconclusive")
        self.assertTrue(selection["candidateAAtMeasurableParity"])
        self.assertIn("inconclusive", selection)
        self.assertTrue(selection["nativeClaimsRemainUnavailable"])
        self.assertTrue(self.protocol["artifactBinding"]["configurationDigestIncludesProtocolSha256"])
        self.assertTrue(self.protocol["requiredMetrics"]["stressResultsRemainSeparate"])
        self.assertEqual(
            self.protocol["requiredMetrics"]["fullInstrumentationTimingByWorkload"]["phases"],
            ["isolatedInput", "repeatedBurst", "mixedBurst"],
        )
        self.assertEqual(
            self.protocol["equivalence"]["minimumSuccessiveDifferencesPerCandidateConfiguration"],
            19,
        )
        self.assertIn("pmset -g batt", self.protocol["environment"]["powerSourceObservation"])
        self.assertIn("ProcessInfo.thermalState", self.protocol["environment"]["thermalObservation"])

    def test_mutated_run_total_is_rejected(self) -> None:
        mutated = json.loads(json.dumps(self.protocol))
        mutated["measuredCollection"]["totalMeasuredRuns"] = 159

        with self.assertRaisesRegex(protocol_module.ProtocolError, "run total"):
            protocol_module.validate_protocol(mutated)

    def test_missing_environment_observation_is_rejected(self) -> None:
        mutated = json.loads(json.dumps(self.protocol))
        mutated["environment"]["thermalObservation"] = ""

        with self.assertRaises(protocol_module.ProtocolError):
            protocol_module.validate_protocol(mutated)

    def test_missing_exact_accounting_metric_is_rejected(self) -> None:
        mutated = json.loads(json.dumps(self.protocol))
        mutated["requiredMetrics"]["exactEveryRun"].remove("rejected")

        with self.assertRaises(protocol_module.ProtocolError):
            protocol_module.validate_protocol(mutated)


if __name__ == "__main__":
    unittest.main()
