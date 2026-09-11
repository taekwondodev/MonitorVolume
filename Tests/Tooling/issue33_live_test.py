import importlib.util
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "issue33_live.py"
SPEC = importlib.util.spec_from_file_location("issue33_live", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
live = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(live)


class Issue33LiveTests(unittest.TestCase):
    def test_codesign_requirement_accepts_current_stdout_framing(self) -> None:
        completed = subprocess.CompletedProcess(
            ["codesign"], 0,
            stdout='# designated => cdhash H"0123456789abcdef"\n',
            stderr="Executable=/tmp/Candidate.app/Contents/MacOS/ProArtVolume\n",
        )
        with mock.patch.object(live.subprocess, "run", return_value=completed):
            requirement = live.codesign_requirement(Path("/tmp/Candidate.app"))

        self.assertEqual(requirement, 'cdhash H"0123456789abcdef"')

    def test_campaign_metadata_changes_only_identity_fields(self) -> None:
        source = {
            "CFBundleExecutable": "ProArtVolume",
            "CFBundleIdentifier": "dev.taekwondodev.ProArtVolume",
            "CFBundleName": "ProArt Volume",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "1",
            "LSMinimumSystemVersion": "15.0",
            "LSUIElement": True,
        }
        identity = {
            "candidate": "A",
            "bundleIdentifier": "dev.taekwondodev.ProArtVolume.CandidateA",
            "bundleName": "ProArt Volume Candidate A",
            "installedBundle": "/tmp/ProArt Volume Candidate A.app",
            "installedExecutable": "/tmp/ProArt Volume Candidate A.app/Contents/MacOS/ProArtVolume",
            "executableName": "ProArtVolume",
        }

        metadata = live.campaign_metadata(source, identity)

        self.assertEqual(metadata["CFBundleIdentifier"], identity["bundleIdentifier"])
        self.assertEqual(metadata["CFBundleName"], identity["bundleName"])
        self.assertEqual(
            {key: value for key, value in metadata.items() if key not in {"CFBundleIdentifier", "CFBundleName"}},
            {key: value for key, value in source.items() if key not in {"CFBundleIdentifier", "CFBundleName"}},
        )

    def test_application_identities_are_explicit_distinct_and_production_isolated(self) -> None:
        protocol = live.issue33_live_protocol.load_protocol()

        identities = live.application_identities(protocol)

        self.assertEqual(set(identities), {"production", "A", "B"})
        self.assertEqual(len({value["bundleIdentifier"] for value in identities.values()}), 3)
        self.assertEqual(len({value["installedBundle"] for value in identities.values()}), 3)
        self.assertEqual(identities["production"]["bundleName"], "ProArt Volume")
        self.assertEqual(identities["A"]["candidate"], "A")
        self.assertEqual(identities["B"]["candidate"], "B")


    def make_complete_campaign(self, root: Path) -> None:
        protocol_path = root / live.PROTOCOL_PATH.name
        runner_path = root / live.SCRIPT_NAME
        shutil.copy2(live.PROTOCOL_PATH, protocol_path)
        shutil.copy2(live.SCRIPT_PATH, runner_path)
        protocol = live.issue33_live_protocol.load_protocol(protocol_path)
        normal_schedule = live.issue33_live_protocol.normal_schedule(protocol)
        acceptance_schedule = live.issue33_live_protocol.acceptance_schedule(protocol)
        identities = live.application_identities(protocol)
        digest = "a" * 64
        bundle_files = {"Contents/MacOS/ProArtVolume": digest}
        candidates = {}
        for candidate in ("A", "B"):
            bundle = root / "candidates" / candidate / f"{identities[candidate]['bundleName']}.app"
            candidates[candidate] = {
                "candidate": candidate,
                "sourceRef": protocol["candidates"][candidate]["sourceRef"],
                "sourceClosure": {"Sources/Fixture.swift": digest},
                "preparedBundle": str(bundle),
                "preparedExecutable": str(bundle / "Contents" / "MacOS" / "ProArtVolume"),
                "executableSha256": digest,
                "infoPlistSha256": digest,
                "bundleFiles": bundle_files,
                "bundleFilesSha256": live.hashlib.sha256(
                    json.dumps(bundle_files, sort_keys=True).encode()
                ).hexdigest(),
                "designatedRequirement": f"identifier fixture-{candidate}",
                "noticesSha256": digest,
                "applicationIdentity": identities[candidate],
            }
        manifest = {
            "schemaVersion": 2,
            "status": "prepared",
            "campaignDirectory": str(root),
            "protocolSha256": live.sha256_file(protocol_path),
            "runnerSha256": live.sha256_file(runner_path),
            "productionApplication": identities["production"],
            "candidates": candidates,
            "normalSchedule": normal_schedule,
            "acceptanceSchedule": acceptance_schedule,
            "runs": [],
        }
        setup_records = []
        for candidate in ("A", "B"):
            setup_records.append({
                "candidate": candidate,
                "manualGrantAcknowledged": True,
                "readiness": self.readiness_record(candidate, candidates[candidate]),
            })
        live.write_json(root / "setup.json", {
            "schemaVersion": 2,
            "status": "passed",
            "consent": {
                "sessionScoped": True,
                "categories": ["accessibilityPermissionChanges", "installationAndLaunch"],
            },
            "candidates": setup_records,
            "physicalInputRequested": False,
            "automaticTCCAction": False,
            "error": None,
        })
        live.write_json(root / "cleanup.json", {
            "schemaVersion": 1,
            "status": "passed",
            "removedCandidates": ["A", "B"],
            "manualAccessibilityRemovalRecorded": True,
            "productionApplicationUntouched": True,
        })
        manifest["setup"] = {"status": "passed", "receiptSha256": live.sha256_file(root / "setup.json")}
        manifest["cleanup"] = {"status": "passed", "receiptSha256": live.sha256_file(root / "cleanup.json")}

        phases = [phase["name"] for phase in protocol["normalWorkload"]["phases"]]
        resource_metrics = {
            f"resource.{phase}.{suffix}"
            for phase in phases
            for suffix in protocol["equivalence"]["resourceMetricSuffixes"]
        }
        timing_metrics = {
            f"timing.{name}.{statistic}"
            for name in protocol["equivalence"]["timingMetricNames"]
            for statistic in protocol["equivalence"]["normalFullTimingStatistics"]
        }

        def add_report(workload: str, ordinal: int, schedule: dict[str, object]) -> None:
            candidate = str(schedule["candidate"])
            instrumentation = str(schedule["instrumentation"])
            metrics = {
                metric: 1.0 if candidate == "A" else 2.0
                for metric in resource_metrics | (timing_metrics if instrumentation == "full" else set())
            } if workload == "normal" else {}
            report = {
                "status": "captured",
                "workload": workload,
                "ordinal": ordinal,
                "candidate": candidate,
                "instrumentation": instrumentation,
                "schedule": schedule,
                "analysisMetrics": metrics,
                "readiness": self.readiness_record(candidate, candidates[candidate]),
                "operatorObservations": [{"passed": True}],
                "phaseResourceSummaries": {},
                "lifecycleSummary": {
                    "eventCounts": {"callbackEntered": 2, "callbackExited": 2, "handoff": 2, "accounting": 1},
                    "handoffCounts": {"admitted": 1, "pairedKeyUp": 1},
                    "budgetExhausted": False,
                    "accounting": {
                        "capacity": 8, "attempted": 1, "admitted": 1, "rejected": 0,
                        "discarded": 0, "overflow": 0, "completed": 1,
                        "peakOutstanding": 1, "pending": 0,
                    },
                    "tapResourcesReleased": True,
                    "complete": True,
                },
            }
            record = {
                "workload": workload,
                "ordinal": ordinal,
                "candidate": candidate,
                "instrumentation": instrumentation,
                "status": "captured",
            }
            path = live.run_report_path(root, record)
            live.write_json(path, report)
            record["reportSha256"] = live.sha256_file(path)
            manifest["runs"].append(record)

        for ordinal, schedule in enumerate(normal_schedule, start=1):
            add_report("normal", ordinal, schedule)
        for workload in ("lifecycle", "stress"):
            selected = [item for item in acceptance_schedule if item["workload"] == workload]
            for ordinal, schedule in enumerate(selected, start=1):
                add_report(workload, ordinal, schedule)
        live.write_json(root / "manifest.json", manifest)

    @staticmethod
    def readiness_record(candidate: str, binding: dict[str, object]) -> dict[str, object]:
        identity = binding["applicationIdentity"]
        assert isinstance(identity, dict)
        return {
            "schemaVersion": 1,
            "state": "ready",
            "candidate": candidate,
            "bundleIdentifier": identity["bundleIdentifier"],
            "executableSha256": binding["executableSha256"],
            "sourceRef": binding["sourceRef"],
            "generation": 1,
            "accessibilityTrusted": True,
            "tapOwnerActive": True,
            "serviceValidationComplete": True,
            "pid": 42,
        }

    def test_lifecycle_message_parser_preserves_fixed_fields(self) -> None:
        message = (
            "schema=3 sequence=7 uptime_ns=120 event=callbackEntered name=none token=0 tap=0 "
            "result=none reason=none generation=0 observed_generation=0 current_generation=0 "
            "event_timestamp_ns=100 capacity=0 attempted=0 admitted=0 rejected=0 discarded=0 "
            "overflow=0 completed=0 peak_outstanding=0 pending=0"
        )

        record = live.parse_lifecycle_message(message)

        self.assertEqual(record["sequence"], 7)
        self.assertEqual(record["event"], "callbackEntered")
        self.assertEqual(record["uptimeNanoseconds"], 120)
        self.assertEqual(record["eventTimestampNanoseconds"], 100)

    def test_callback_metrics_pair_entries_and_exits_without_relabeling_upstream_delay(self) -> None:
        records = [
            {"sequence": 1, "event": "callbackEntered", "uptimeNanoseconds": 120,
             "eventTimestampNanoseconds": 100},
            {"sequence": 2, "event": "handoff", "uptimeNanoseconds": 125,
             "eventTimestampNanoseconds": 0},
            {"sequence": 3, "event": "callbackExited", "uptimeNanoseconds": 130,
             "eventTimestampNanoseconds": 0},
        ]

        metrics = live.callback_metrics(records)

        self.assertEqual(metrics, [{
            "entrySequence": 1,
            "exitSequence": 3,
            "callbackDurationNanoseconds": 10,
            "eventToCallbackProxyNanoseconds": 20,
        }])

    def test_callback_metrics_reject_nested_or_unpaired_records(self) -> None:
        nested = [
            {"sequence": 1, "event": "callbackEntered", "uptimeNanoseconds": 10,
             "eventTimestampNanoseconds": 1},
            {"sequence": 2, "event": "callbackEntered", "uptimeNanoseconds": 11,
             "eventTimestampNanoseconds": 2},
        ]
        with self.assertRaises(live.LiveGateFailure):
            live.callback_metrics(nested)

    def test_callback_metrics_reject_clock_incompatibility(self) -> None:
        records = [
            {"sequence": 1, "event": "callbackEntered", "uptimeNanoseconds": 2_000_000_001,
             "eventTimestampNanoseconds": 1},
            {"sequence": 2, "event": "callbackExited", "uptimeNanoseconds": 2_000_000_002,
             "eventTimestampNanoseconds": 0},
        ]
        with self.assertRaises(live.LiveGateFailure):
            live.callback_metrics(records, 1_000_000_000)

    def test_lifecycle_log_orders_serialized_records_by_sequence(self) -> None:
        template = (
            "schema=3 sequence={sequence} uptime_ns={uptime} event={event} name=none token=0 tap=0 "
            "result=none reason=none generation=0 observed_generation=0 current_generation=0 "
            "event_timestamp_ns=0 capacity=0 attempted=0 admitted=0 rejected=0 discarded=0 "
            "overflow=0 completed=0 peak_outstanding=0 pending=0"
        )
        lines = [
            {"processID": 42, "eventMessage": template.format(sequence=2, uptime=20, event="sessionEnded")},
            {"processID": 42, "eventMessage": template.format(sequence=1, uptime=10, event="sessionStarted")},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "log.ndjson"
            path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")

            records = live.read_lifecycle_log(path, 42)

        self.assertEqual([record["sequence"] for record in records], [1, 2])

    def test_lifecycle_log_accepts_log_stream_filter_preamble(self) -> None:
        message = (
            "schema=3 sequence=1 uptime_ns=10 event=sessionStarted name=none token=0 tap=0 "
            "result=none reason=none generation=0 observed_generation=0 current_generation=0 "
            "event_timestamp_ns=0 capacity=0 attempted=0 admitted=0 rejected=0 discarded=0 "
            "overflow=0 completed=0 peak_outstanding=0 pending=0"
        )
        event = {"processID": 42, "eventMessage": message}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "log.ndjson"
            path.write_text(
                'Filtering the log data using "subsystem == \\"example\\""\n'
                + json.dumps(event)
                + "\n"
            )

            records = live.read_lifecycle_log(path, 42)

        self.assertEqual([record["sequence"] for record in records], [1])

    def test_readiness_uses_current_process_id_and_requires_exact_identity(self) -> None:
        message = (
            "schema=1 state=ready candidate=A bundle_id=dev.taekwondodev.ProArtVolume.CandidateA "
            f"executable_sha256={'a' * 64} source_ref={'b' * 40} generation=7 "
            "accessibility=true tap=true service=true"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "log.ndjson"
            path.write_text(json.dumps({"processID": 42, "eventMessage": message}) + "\n")

            readiness = live.read_readiness_log(path, 42, {
                "candidate": "A",
                "bundleIdentifier": "dev.taekwondodev.ProArtVolume.CandidateA",
                "executableSha256": "a" * 64,
                "sourceRef": "b" * 40,
            })

        self.assertEqual(readiness["generation"], 7)
        self.assertTrue(readiness["accessibilityTrusted"])
        self.assertTrue(readiness["tapOwnerActive"])
        self.assertTrue(readiness["serviceValidationComplete"])

    def test_readiness_rejects_false_prerequisite_and_stale_identity(self) -> None:
        message = (
            "schema=1 state=ready candidate=A bundle_id=wrong "
            f"executable_sha256={'a' * 64} source_ref={'b' * 40} generation=7 "
            "accessibility=false tap=true service=true"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "log.ndjson"
            path.write_text(json.dumps({"processID": 42, "eventMessage": message}) + "\n")
            with self.assertRaises(live.LiveGateFailure):
                live.read_readiness_log(path, 42, {
                    "candidate": "A", "bundleIdentifier": "expected",
                    "executableSha256": "a" * 64, "sourceRef": "b" * 40,
                })

    def test_readiness_rejects_unified_log_loss_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "log.ndjson"
            path.write_text(json.dumps({"eventType": "lossEvent"}) + "\n")

            with self.assertRaisesRegex(live.LiveGateFailure, "lost events"):
                live.read_readiness_log(path, 42, {})

    def test_known_process_contract_includes_production_and_both_candidates(self) -> None:
        manifest = {
            "productionApplication": {"installedExecutable": "/production"},
            "candidates": {
                "A": {"applicationIdentity": {"installedExecutable": "/candidate-a"}},
                "B": {"applicationIdentity": {"installedExecutable": "/candidate-b"}},
            },
        }
        module = mock.Mock()
        module.exact_processes.side_effect = lambda path: [9] if str(path) == "/candidate-a" else []

        processes = live.known_processes(manifest, module)

        self.assertEqual(processes, {"production": [], "A": [9], "B": []})
        with self.assertRaises(live.LiveGateFailure):
            live.require_all_known_stopped(manifest, module)

    def test_bound_stop_never_signals_production_and_validates_candidate_before_signal(self) -> None:
        manifest = {
            "productionApplication": {"installedExecutable": "/production"},
            "candidates": {
                "A": {"applicationIdentity": {"installedExecutable": "/candidate-a"}},
                "B": {"applicationIdentity": {"installedExecutable": "/candidate-b"}},
            },
        }
        module = mock.Mock()
        module.exact_processes.side_effect = lambda path: [7] if str(path) == "/candidate-a" else []
        module.stop_exact_processes.return_value = [7]
        with mock.patch.object(live, "validate_installed_bundle") as validate:
            stopped = live.stop_bound_candidates(manifest, module)

        self.assertEqual(stopped, {"A": [7], "B": []})
        validate.assert_called_once_with(module, manifest["candidates"]["A"])
        module.stop_exact_processes.assert_called_once_with(Path("/candidate-a"))
        self.assertNotIn(mock.call(Path("/production")), module.stop_exact_processes.call_args_list)

    def test_lifecycle_log_rejects_other_non_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "log.ndjson"
            path.write_text("not json\n")

            with self.assertRaises(live.LiveGateFailure):
                live.read_lifecycle_log(path, 42)

    def test_lifecycle_log_rejects_conflicting_process_identifiers(self) -> None:
        event = {"processID": 42, "processIdentifier": 43, "eventMessage": "unrelated"}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "log.ndjson"
            path.write_text(json.dumps(event) + "\n")

            with self.assertRaises(live.LiveGateFailure):
                live.read_lifecycle_log(path, 42, require_records=False)

    def test_required_consent_is_scoped_by_workload(self) -> None:
        normal = live.required_consent("normal")
        lifecycle = live.required_consent("lifecycle")
        stress = live.required_consent("stress")

        self.assertEqual(normal, {
            "installationAndLaunch", "physicalVolumeInputAndDDCWrites", "normalUseUIActivity",
        })
        self.assertEqual(lifecycle, {
            "installationAndLaunch", "physicalVolumeInputAndDDCWrites",
            "accessibilityPermissionChanges", "sleepWake",
        })
        self.assertEqual(stress, {
            "installationAndLaunch", "physicalVolumeInputAndDDCWrites", "stress",
        })

    def test_source_closure_uses_only_git_tracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            (root / "Sources").mkdir()
            (root / "Sources" / "A.swift").write_text("let value = 1\n")
            (root / ".build").mkdir()
            (root / ".build" / "ignored").write_text("x")
            subprocess.run(["git", "add", "Sources/A.swift"], cwd=root, check=True)

            closure = live.source_closure(root)

        self.assertEqual(set(closure), {"Sources/A.swift"})
        self.assertEqual(len(closure["Sources/A.swift"]), 64)

    def test_publishable_projection_removes_local_identifiers(self) -> None:
        report = {
            "candidate": "A",
            "pid": 123,
            "worktree": "/private/tmp/local",
            "installedExecutable": "/Users/person/Applications/App.app/x",
            "metrics": {"count": 4},
            "nested": [{"processIdentifier": 456, "value": 1}],
            "raw": {"thermal": {"command": ["/Users/person/campaign/EnvironmentProbe"]}},
            "logicalCpuCount": 10,
            "identity": {"swVers": "ProductName: macOS", "machine": "arm64", "model": "MacX,1"},
            "accessibilityTrusted": True,
            "error": "failed at /private/tmp/candidate-a/artifact",
        }

        projected = live.publishable_projection(report)

        self.assertEqual(projected, {
            "candidate": "A",
            "metrics": {"count": 4},
            "nested": [{"value": 1}],
            "error": "failed at <local-path>",
        })

    def test_emergency_stop_does_not_depend_on_current_runner_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_complete_campaign(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["runnerSha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            module = mock.Mock()
            module.exact_processes.return_value = []

            with mock.patch.object(live, "load_app_tool", return_value=module):
                result = live.stop_installed_app(root)

            self.assertEqual(result["status"], "stopped")
            module.stop_exact_processes.assert_not_called()

    def test_metric_comparison_rejects_unbound_directionality(self) -> None:
        protocol = live.issue33_live_protocol.load_protocol()
        protocol["equivalence"]["lowerIsBetterMetrics"].remove("residentSizeBytes")
        with self.assertRaisesRegex(live.LiveGateFailure, "directionality"):
            live.metric_comparisons([], protocol)

    def test_lifecycle_summary_retains_accounting_and_tap_release(self) -> None:
        records = [
            {"event": "sessionStarted", "uptimeNanoseconds": 1, "token": 0, "name": "none", "reason": "none", "result": "none"},
            {"event": "operationBegan", "uptimeNanoseconds": 2, "token": 2, "name": "tapCreate", "reason": "launch", "result": "none"},
            {"event": "operationEnded", "uptimeNanoseconds": 3, "token": 2, "name": "tapCreate", "reason": "none", "result": "returned"},
            {"event": "operationBegan", "uptimeNanoseconds": 4, "token": 4, "name": "tapInvalidate", "reason": "termination", "result": "none"},
            {"event": "operationEnded", "uptimeNanoseconds": 5, "token": 4, "name": "tapInvalidate", "reason": "none", "result": "returned"},
            {"event": "accounting", "uptimeNanoseconds": 6, "token": 0, "name": "none", "reason": "none", "result": "none", "capacity": 8, "attempted": 4, "admitted": 2, "rejected": 2, "discarded": 1, "overflow": 1, "completed": 1, "peakOutstanding": 2, "pending": 0},
            {"event": "sessionEnded", "uptimeNanoseconds": 7, "token": 0, "name": "none", "reason": "none", "result": "none"},
        ]

        summary = live.lifecycle_summary(records)

        self.assertEqual(summary["accounting"]["peakOutstanding"], 2)
        self.assertEqual(summary["accounting"]["pending"], 0)
        self.assertTrue(summary["tapResourcesReleased"])
        self.assertTrue(summary["complete"])

    def test_resource_summary_tracks_threads_and_process_identity(self) -> None:
        samples = [
            {"status": "sampled", "intervalCpuPercentOneCore": None, "residentSizeBytes": 10,
             "physicalFootprintBytes": 20, "packageIdleWakeups": 1, "interruptWakeups": 2,
             "threadCount": 3, "processStartAbsoluteTime": 99},
            {"status": "sampled", "intervalCpuPercentOneCore": 1.0, "residentSizeBytes": 11,
             "physicalFootprintBytes": 21, "packageIdleWakeups": 2, "interruptWakeups": 4,
             "threadCount": 4, "processStartAbsoluteTime": 99},
        ]

        summary = live.summarize_samples(samples)

        self.assertEqual(summary["baselineThreadCount"], 3)
        self.assertEqual(summary["maximumThreadCount"], 4)
        self.assertEqual(summary["endingThreadCount"], 4)
        samples[1]["processStartAbsoluteTime"] = 100
        with self.assertRaises(live.LiveGateFailure):
            live.summarize_samples(samples)

    def test_file_digest_guard_rejects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            payload = {"protocolSha256": "a" * 64, "runs": []}
            live.write_json(path, payload)
            expected = live.sha256_file(path)
            self.assertEqual(live.sha256_file(path), expected)
            payload["runs"].append({"ordinal": 1})
            live.write_json(path, payload)
            with self.assertRaises(live.LiveGateFailure):
                live.require_file_digest(path, expected, "manifest")

    def test_number_summary_uses_nearest_rank_p95(self) -> None:
        self.assertEqual(live.summarize_numbers([1, 2, 3, 4, 100]), {
            "sampleCount": 5,
            "median": 3.0,
            "nearestRankP95": 100.0,
            "maximum": 100.0,
        })

    def test_paired_classification_uses_repeatability_band(self) -> None:
        protocol = live.issue33_live_protocol.load_protocol()

        result = live.compare_metric_series(
            [10.0, 10.0, 10.0, 10.0],
            [20.0, 20.0, 20.0, 20.0],
            "timing.callbackDuration.median",
            protocol,
        )

        self.assertEqual(result["classification"], "candidateABetter")
        self.assertEqual(result["pairedRunCount"], 4)

    def test_selection_is_inconclusive_for_mixed_metric_winners(self) -> None:
        self.assertEqual(
            live.select_candidate(["candidateABetter", "candidateBBetter"], True),
            "inconclusive",
        )
        self.assertEqual(live.select_candidate(["equivalent"], True), "A")
        self.assertEqual(live.select_candidate(["candidateBBetter", "equivalent"], True), "B")
        self.assertEqual(live.select_candidate(["candidateABetter"], False), "inconclusive")

    def test_latency_metric_values_uses_known_stage_pairs(self) -> None:
        evidence = {
            "events": [
                {"stage": "input_accepted", "interactionIDs": [7], "uptimeNanoseconds": 1_000},
                {"stage": "intent_reduced", "interactionIDs": [7], "uptimeNanoseconds": 1_100},
                {"stage": "command_enqueued", "interactionIDs": [7], "uptimeNanoseconds": 1_200},
                {"stage": "osd_first_draw_completed", "interactionIDs": [7], "uptimeNanoseconds": 1_300},
                {"stage": "service_command_completed", "interactionIDs": [7], "uptimeNanoseconds": 1_800},
                {"stage": "ddc_write_read_back_started", "interactionIDs": [7], "uptimeNanoseconds": 1_400},
                {"stage": "ddc_write_read_back_completed", "interactionIDs": [7], "uptimeNanoseconds": 1_700},
            ]
        }
        values = live.latency_metric_values(evidence)
        self.assertEqual(values["acceptedToIntentReducedNanoseconds"], [100.0])
        self.assertEqual(values["acceptedToCommandEnqueuedNanoseconds"], [200.0])
        self.assertEqual(values["acceptedToFirstDrawNanoseconds"], [300.0])
        self.assertEqual(values["acceptedToServiceCompletionNanoseconds"], [800.0])
        self.assertEqual(values["ddcWriteReadBackNanoseconds"], [300.0])

    def test_analyze_campaign_reaches_bound_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_complete_campaign(root)

            result = live.analyze_campaign(root, "passed")

        self.assertEqual(result["runCount"], 20)
        self.assertEqual(result["normalAccounting"]["status"], "passed")
        self.assertEqual(result["selection"], "A")
        self.assertTrue(result["verifiedFacts"])
        self.assertTrue(result["manualObservations"])
        self.assertEqual(result["unavailableScenarios"], [{
            "scenario": "disabledTap",
            "reason": "notNaturallyEmitted",
        }])
        self.assertTrue(result["residualRisks"])

    def test_accounting_gate_rejects_normal_loss(self) -> None:
        gate = live.normal_accounting_gate([
            {
                "candidate": "A",
                "instrumentation": "full",
                "ordinal": 1,
                "lifecycleSummary": {
                    "complete": True,
                    "budgetExhausted": False,
                    "accounting": {
                        "attempted": 2,
                        "admitted": 1,
                        "rejected": 1,
                        "completed": 1,
                        "discarded": 0,
                        "overflow": 0,
                        "peakOutstanding": 1,
                        "pending": 0,
                        "capacity": 8,
                    },
                    "eventCounts": {"callbackEntered": 1, "callbackExited": 1, "handoff": 1, "tapDisabled": 0},
                    "handoffCounts": {"admitted": 1, "pairedKeyUp": 1, "overflow": 0, "staleDiscarded": 0},
                    "budgetExhaustedCount": 0,
                }
            }
        ])
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["failures"][0]["reasons"], ["rejectedOrDiscarded"])

    def test_analyze_campaign_publishes_inconclusive_for_missing_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_complete_campaign(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["runs"].pop()
            live.write_json(manifest_path, manifest)

            result = live.analyze_campaign(root, "incomplete")

            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["selection"], "inconclusive")
            self.assertEqual(len(result["missingRuns"]), 1)
            self.assertTrue((root / "analysis.json").is_file())

    def test_analysis_rejects_incomplete_setup_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_complete_campaign(root)
            setup_path = root / "setup.json"
            setup = json.loads(setup_path.read_text())
            setup["candidates"].pop()
            live.write_json(setup_path, setup)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["setup"]["receiptSha256"] = live.sha256_file(setup_path)
            live.write_json(manifest_path, manifest)

            result = live.analyze_campaign(root, "passed")

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["selection"], "inconclusive")
        self.assertIn("setup", result["prerequisiteFailures"])

    def test_manifest_candidate_identity_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_complete_campaign(root)
            manifest = json.loads((root / "manifest.json").read_text())
            manifest["candidates"]["A"]["applicationIdentity"] = manifest["productionApplication"]

            with self.assertRaisesRegex(live.LiveGateFailure, "identity binding"):
                live.require_campaign_bindings(root, manifest)


if __name__ == "__main__":
    unittest.main()
