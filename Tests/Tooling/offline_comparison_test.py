import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.offline_comparison import (
    CONTRACT_NAME,
    DEFAULT_INTERVAL_MS,
    WINDOWS_MS,
    comparison_protocol,
    observed_overhead,
    protocol_from_contract,
    validate_comparison_report,
    validate_offline_report,
)


class OfflineComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.executable = Path(self.folder.name) / "ProArtVolumeOfflineHarness"
        self.executable.write_bytes(b"release-offline-fixture")

    def configuration(self, instrumentation="full"):
        return {
            "schemaVersion": 1,
            "contract": CONTRACT_NAME,
            "capacity": 2,
            "permissionPollIntervalMilliseconds": 1000,
            "permissionPollingRule": "poll only while the lifecycle is active, outside framework callbacks; stop in suspension and sleep",
            "tapTeardownRule": "reopen waits for the prior owner to release its tap and key pairing; no callback or MainActor wait",
            "samplingIntervalMilliseconds": DEFAULT_INTERVAL_MS,
            "observationWindowsMilliseconds": {
                name: end - start for name, (start, end) in WINDOWS_MS.items()
            },
            "cpuNormalization": "ps_percent_divided_by_logical_cpu",
            "ramMeasure": "resident_set_size_kib",
            "eventTimestampRule": "monotonic nonnegative process-uptime timestamps; no callback-duration SLA",
            "workload": "controlled_domain_service_drive",
            "workloadClassification": "offline_not_installed_app_performance",
            "capacitySelectionProcedure": "freeze capacity before comparison",
            "comparisonProcedure": "alternate equal Release runs",
            "repeatabilityCriteria": "compare complete outcome sequences",
            "instrumentationMode": instrumentation,
        }

    def contract(self, instrumentation="full", resource_state="active"):
        scenarios = []
        required = {
            "intent_semantics": {
                "upper_boundary", "lower_boundary", "rapid_steps", "mute_parity",
                "boundary_unmute", "fresh_seed",
            },
            "accepted_input": {"ordered_consumer", "service_outcome"},
            "service_recovery": {
                "revalidation_started", "failure_is_unavailable", "existing_backoff",
                "recovery_reseeds", "no_write_during_read_recovery",
            },
            "failed_write_recovery": {
                "admitted", "failure_is_unavailable", "existing_backoff",
                "recovery_reseeds", "failed_command_not_replayed",
            },
            "suspension": {
                "pending_discarded", "rejected_pass_through", "grant_does_not_clear",
                "external_results_latched", "explicit_reopen",
            },
            "sleep_wake": {
                "sleep_pass_through", "active_wake_revalidates",
                "fresh_hardware_after_wake", "suspended_wake_stays_suspended",
            },
            "overflow": {
                "capacity_two", "next_passes", "latched", "queue_discarded",
                "no_wait_for_capacity",
            },
            "stale_delivery": {
                "admitted", "session_rejected", "no_intent_or_osd",
                "bookkeeping_completed",
            },
        }
        for name, checks in required.items():
            scenarios.append({
                "name": name,
                "passed": True,
                "checks": {check: True for check in checks},
                "notes": ["fixture"],
            })
        events = [] if instrumentation == "none" else [
            {"sequence": 1, "timestampNanoseconds": 0, "scenario": "suspension",
             "kind": "rejected", "generation": 1, "accepted": False, "discarded": True},
            {"sequence": 2, "timestampNanoseconds": 1, "scenario": "suspension",
             "kind": "discarded", "generation": 1, "accepted": False, "discarded": True},
        ]
        return {
            "status": "passed",
            "executionClass": "offline_common_contract",
            "resourceState": resource_state,
            "instrumentation": instrumentation,
            "executable": {
                "path": str(self.executable),
                "sha256": hashlib.sha256(self.executable.read_bytes()).hexdigest(),
            },
            "configuration": self.configuration(instrumentation),
            "scenarios": scenarios,
            "events": events,
            "admission": {
                "attempted": 3, "admitted": 2, "rejected": 1, "discarded": 2,
                "overflow": 1, "completed": 0, "peakOutstanding": 2,
                "maximumDeliveryWaitNanoseconds": 1,
            },
            "frameworkTimings": {
                "event_to_callback": {"status": "unavailable", "reason": "fixture"},
                "callback_entry_exit": {"status": "unavailable", "reason": "fixture"},
                "osd_first_draw": {"status": "unavailable", "reason": "fixture"},
                "timeout_and_tap_release": {"status": "modeled", "reason": "fixture"},
            },
            "resourceContract": {
                "samplingMethod": "parent samples ps pcpu/rss every declared interval while this Release harness runs",
                "samplingIntervalMilliseconds": 20,
                "activeIdleWindowMilliseconds": 200,
                "burstWindowMilliseconds": 300,
                "suspendedWindowMilliseconds": 200,
                "postBurstRetentionWindowMilliseconds": 200,
                "postSuspensionRetentionWindowMilliseconds": 200,
                "wakeupMetric": {"status": "unavailable", "reason": "fixture"},
                "threadAndTapMetric": {"status": "modeled", "reason": "fixture"},
                "instrumentationOverhead": "fixture",
            },
            "workloadPhase": "eligible" if resource_state == "active" else "suspended",
            "liveReadiness": ["framework timing fixture is unavailable"],
        }

    def resource(self):
        windows = {}
        for name, bounds in WINDOWS_MS.items():
            windows[name] = {
                "boundsMilliseconds": list(bounds),
                "sampleCount": 1,
                "cpu": {"count": 1, "minimum": 1.0, "average": 1.0, "maximum": 1.0},
                "normalizedCpu": {"count": 1, "minimum": 0.1, "average": 0.1, "maximum": 0.1},
                "residentSetSizeKiB": {"count": 1, "minimum": 100, "average": 100, "maximum": 100},
            }
        return {
            "sampling": {
                "method": "ps",
                "intervalMilliseconds": DEFAULT_INTERVAL_MS,
                "logicalCPUCount": 10,
                "cpuMeasure": "ps_pcpu_percent",
                "cpuNormalization": "ps_percent_divided_by_logical_cpu",
                "ramMeasure": "resident_set_size_kib",
                "windowsMilliseconds": {
                    name: list(bounds) for name, bounds in WINDOWS_MS.items()
                },
            },
            "sampleCount": 1,
            "cpu": {
                "rawPercent": {"count": 1, "minimum": 1.0, "average": 1.0, "maximum": 1.0},
                "normalizedPercent": {"count": 1, "minimum": 0.1, "average": 0.1, "maximum": 0.1},
            },
            "ram": {
                "measure": "resident_set_size_kib",
                "baselineKiB": 100,
                "peakKiB": 100,
                "peakIncreaseKiB": 0,
            },
            "windows": windows,
            "wakeupsAndResources": {"status": "unavailable", "reason": "fixture"},
        }

    def run_report(self, instrumentation="full", resource_state="active"):
        contract = self.contract(instrumentation, resource_state)
        return {
            "schemaVersion": 1,
            "status": "passed",
            "executionClass": "offline_common_contract",
            "instrumentation": instrumentation,
            "resourceState": resource_state,
            "executable": {
                "path": str(self.executable),
                "sha256": hashlib.sha256(self.executable.read_bytes()).hexdigest(),
            },
            "contractReport": contract,
            "resource": self.resource(),
            "protocol": protocol_from_contract(contract),
            "workloadMilliseconds": 1200,
            "processDurationMilliseconds": 1200,
            "evidence": {"stdout": "stdout", "stderr": "stderr"},
            "failures": [],
        }

    def test_valid_full_run_passes(self):
        validate_offline_report(self.run_report(), self.executable)

    def test_none_instrumentation_must_not_emit_events(self):
        report = self.run_report(instrumentation="none")
        validate_offline_report(report, self.executable)
        report["contractReport"]["events"].append({})
        with self.assertRaisesRegex(RuntimeError, "instrumentation-none"):
            validate_offline_report(report, self.executable)

    def test_wrong_executable_hash_is_rejected(self):
        report = self.run_report()
        report["executable"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "hash"):
            validate_offline_report(report, self.executable)

    def test_missing_scenario_or_framework_gap_is_rejected(self):
        for mutation in ("scenario", "framework"):
            report = self.run_report()
            if mutation == "scenario":
                report["contractReport"]["scenarios"].pop()
            else:
                report["contractReport"]["frameworkTimings"].pop("osd_first_draw")
            with self.subTest(mutation=mutation):
                with self.assertRaises(RuntimeError):
                    validate_offline_report(report, self.executable)

    def test_admission_ledger_and_top_level_binding_are_validated(self):
        report = self.run_report()
        report["contractReport"]["admission"]["completed"] = 1
        with self.assertRaisesRegex(RuntimeError, "ledger"):
            validate_offline_report(report, self.executable)

        runs = [
            self.run_report("full", "active"),
            self.run_report("none", "active"),
            self.run_report("full", "suspended"),
        ]
        comparison = {
            "schemaVersion": 1,
            "status": "passed",
            "executionClass": "offline_comparison",
            "contract": CONTRACT_NAME,
            "protocol": comparison_protocol(),
            "executable": copy.deepcopy(runs[0]["executable"]),
            "runs": runs,
            "overhead": observed_overhead(runs[0], runs[1]),
            "failures": [],
        }
        comparison["executable"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "hash"):
            validate_comparison_report(comparison, self.executable)

        comparison = {
            "schemaVersion": 1,
            "status": "passed",
            "executionClass": "offline_comparison",
            "contract": CONTRACT_NAME,
            "protocol": comparison_protocol(),
            "executable": copy.deepcopy(runs[0]["executable"]),
            "runs": runs,
            "overhead": observed_overhead(runs[0], runs[1]),
            "failures": [],
        }
        comparison["overhead"]["cpu"]["deltaNormalizedAveragePercent"] += 1
        with self.assertRaisesRegex(RuntimeError, "overhead does not match"):
            validate_comparison_report(comparison, self.executable)

    def test_comparison_requires_the_declared_matrix_and_one_artifact(self):
        runs = [
            self.run_report("full", "active"),
            self.run_report("none", "active"),
            self.run_report("full", "suspended"),
        ]
        report = {
            "schemaVersion": 1,
            "status": "passed",
            "executionClass": "offline_comparison",
            "contract": CONTRACT_NAME,
            "protocol": comparison_protocol(),
            "executable": copy.deepcopy(runs[0]["executable"]),
            "runs": runs,
            "overhead": observed_overhead(runs[0], runs[1]),
            "failures": [],
        }
        validate_comparison_report(report, self.executable)
        broken = copy.deepcopy(report)
        broken["runs"].pop()
        with self.assertRaisesRegex(RuntimeError, "three declared runs"):
            validate_comparison_report(broken, self.executable)


if __name__ == "__main__":
    unittest.main()
