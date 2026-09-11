import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "issue33_live_protocol.py"
SPEC = importlib.util.spec_from_file_location("issue33_live_protocol", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
protocol_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(protocol_module)


class Issue33LiveProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.protocol = protocol_module.load_protocol()

    def test_normal_schedule_is_counterbalanced_and_complete(self) -> None:
        schedule = protocol_module.normal_schedule(self.protocol)

        self.assertEqual(len(schedule), 16)
        self.assertEqual([item["condition"] for item in schedule[:4]], [
            "A/full", "B/full", "B/none", "A/none",
        ])
        for candidate in ("A", "B"):
            for instrumentation in ("full", "none"):
                selected = [
                    item for item in schedule
                    if item["candidate"] == candidate
                    and item["instrumentation"] == instrumentation
                ]
                self.assertEqual(len(selected), 4)

    def test_protocol_defines_two_distinct_campaign_application_identities(self) -> None:
        production = self.protocol["productionApplication"]
        identities = {
            candidate: value["applicationIdentity"]
            for candidate, value in self.protocol["candidates"].items()
        }

        self.assertEqual(production, {
            "bundleIdentifier": "dev.taekwondodev.ProArtVolume",
            "bundleName": "ProArt Volume",
            "installedBundle": "~/Applications/ProArt Volume.app",
            "executableName": "ProArtVolume",
        })
        self.assertEqual(identities["A"]["bundleIdentifier"], "dev.taekwondodev.ProArtVolume.CandidateA")
        self.assertEqual(identities["B"]["bundleIdentifier"], "dev.taekwondodev.ProArtVolume.CandidateB")
        self.assertEqual(identities["A"]["bundleName"], "ProArt Volume Candidate A")
        self.assertEqual(identities["B"]["bundleName"], "ProArt Volume Candidate B")
        self.assertEqual(len({production["bundleIdentifier"], *(value["bundleIdentifier"] for value in identities.values())}), 3)
        self.assertEqual(len({production["installedBundle"], *(value["installedBundle"] for value in identities.values())}), 3)

    def test_setup_and_readiness_contracts_are_separate_from_collection(self) -> None:
        setup = self.protocol["setup"]
        readiness = self.protocol["readiness"]

        self.assertEqual(setup["requiredConsent"], ["installationAndLaunch", "accessibilityPermissionChanges"])
        self.assertEqual(setup["candidateOrder"], ["A", "B"])
        self.assertTrue(setup["manualAccessibilityGrantOnly"])
        self.assertTrue(setup["noPhysicalInput"])
        self.assertEqual(readiness["schemaVersion"], 1)
        self.assertTrue(readiness["requiredBeforeOperatorInput"])
        self.assertTrue(readiness["identicalInFullAndNone"])
        self.assertEqual(readiness["terminalStates"], ["ready", "unavailable"])

    def test_runtime_actions_remain_behind_explicit_consent(self) -> None:
        consent = self.protocol["consent"]
        safety = self.protocol["safety"]

        self.assertFalse(consent["preparationRequiresRuntimeConsent"])
        self.assertTrue(consent["collectionRequiresExplicitSessionConsent"])
        self.assertTrue(consent["stressAndSleepWakeSeparatelyAuthorized"])
        self.assertTrue(safety["serialRunsOnly"])
        self.assertTrue(safety["stopImmediatelyOnInputDisruption"])
        self.assertTrue(safety["forbidSynthesizedSystemInput"])
        self.assertTrue(safety["forbidAutomaticPermissionChanges"])
        self.assertTrue(safety["forbidAutomaticRelaunch"])
        self.assertIn("issue33-stop", safety["emergencyStop"])

    def test_accounting_rule_resolves_issue32_ambiguity_before_observation(self) -> None:
        interpretation = self.protocol["accountingInterpretation"]

        self.assertTrue(interpretation["perRunIdentitiesMustReconcile"])
        self.assertFalse(interpretation["crossCandidateExactCountEqualityRequired"])
        self.assertEqual(interpretation["normalRejectedDiscardedOrOverflow"], "correctnessFailure")
        self.assertTrue(interpretation["fasterSurvivingSubsetCannotCompensateForLostWork"])

    def test_required_installed_metrics_and_bindings_are_frozen(self) -> None:
        binding = self.protocol["artifactBinding"]
        measurements = self.protocol["measurements"]
        resources = self.protocol["resourceSampling"]

        self.assertTrue(binding["requireInstalledExecutableHashMatch"])
        self.assertTrue(binding["requireExactlyOneInstalledProcess"])
        self.assertIn("callbackEntered", measurements["callbackDuration"])
        self.assertIn("CoreGraphics event timestamp", measurements["eventToCallback"])
        self.assertEqual(resources["memoryMeasures"], ["residentSizeBytes", "physicalFootprintBytes"])
        self.assertEqual(resources["wakeupMeasures"], ["packageIdleWakeups", "interruptWakeups"])
        self.assertEqual(resources["threadMeasure"], "procPidTaskInfoThreadCount")
        self.assertEqual(self.protocol["normalWorkload"]["admissionCapacity"], 8)
        equivalence = self.protocol["equivalence"]
        self.assertEqual(equivalence["pairedRunCount"], 4)
        self.assertEqual(equivalence["minimumSuccessiveDifferencesPerCandidateCondition"], 3)
        self.assertEqual(equivalence["bootstrapSeed"], 330033)
        self.assertTrue(equivalence["noFixedSlaOrInventedPracticalMargin"])

    def test_mutated_total_is_rejected(self) -> None:
        mutated = json.loads(json.dumps(self.protocol))
        mutated["normalWorkload"]["totalRuns"] = 15

        with self.assertRaisesRegex(protocol_module.ProtocolError, "normal run total"):
            protocol_module.validate_protocol(mutated)

    def test_automatic_relaunch_or_cross_candidate_equality_is_rejected(self) -> None:
        for key, value in (
            ("forbidAutomaticRelaunch", False),
            ("forbidSynthesizedSystemInput", False),
        ):
            with self.subTest(key=key):
                mutated = json.loads(json.dumps(self.protocol))
                mutated["safety"][key] = value
                with self.assertRaises(protocol_module.ProtocolError):
                    protocol_module.validate_protocol(mutated)

        mutated = json.loads(json.dumps(self.protocol))
        mutated["accountingInterpretation"]["crossCandidateExactCountEqualityRequired"] = True
        with self.assertRaises(protocol_module.ProtocolError):
            protocol_module.validate_protocol(mutated)

    def test_colliding_or_incomplete_candidate_identity_is_rejected(self) -> None:
        mutated = json.loads(json.dumps(self.protocol))
        mutated["candidates"]["B"]["applicationIdentity"] = dict(
            mutated["candidates"]["A"]["applicationIdentity"]
        )
        with self.assertRaisesRegex(protocol_module.ProtocolError, "identity"):
            protocol_module.validate_protocol(mutated)

        mutated = json.loads(json.dumps(self.protocol))
        del mutated["candidates"]["A"]["applicationIdentity"]["installedBundle"]
        with self.assertRaisesRegex(protocol_module.ProtocolError, "identity"):
            protocol_module.validate_protocol(mutated)


if __name__ == "__main__":
    unittest.main()
