#!/usr/bin/env python3

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.latency_report import build_latency_report


class LatencyReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.executable_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.executable_directory.cleanup)
        self.installed_executable = Path(self.executable_directory.name) / "ProArtVolume"
        self.installed_executable.write_bytes(b"installed-release-artifact")

    def event(self, stage: str, timestamp: int, interaction_ids=None, **values):
        return {
            "sequence": 0,
            "uptimeNanoseconds": timestamp,
            "stage": stage,
            "interactionIDs": interaction_ids or [],
            **values,
        }

    def interaction_events(self, interaction_ids, start: int):
        return [
            self.event("command_enqueued", start + 10_000_000, interaction_ids),
            self.event("service_command_started", start + 20_000_000, interaction_ids),
            self.event("active_output_started", start + 30_000_000, interaction_ids),
            self.event("active_output_completed", start + 40_000_000, interaction_ids, outcome="success"),
            self.event("ddc_read_started", start + 50_000_000, interaction_ids),
            self.event("ddc_read_completed", start + 150_000_000, interaction_ids, outcome="success"),
            self.event("ddc_write_read_back_started", start + 160_000_000, interaction_ids),
            self.event("ddc_write_read_back_completed", start + 560_000_000, interaction_ids, outcome="success"),
            self.event("service_command_completed", start + 570_000_000, interaction_ids),
        ]

    def resequenced(self, events):
        for sequence, event in enumerate(events, start=1):
            event["sequence"] = sequence
        return events

    def complete_events(self):
        events = [self.event("session_started", 1)]
        interactions = [
            (1, "volume_up", False, 1_000_000_000),
            (2, "toggle_mute", False, 3_000_000_000),
            (3, "volume_down", True, 5_000_000_000),
            (4, "volume_up", False, 7_000_000_000),
            (5, "volume_down", False, 7_100_000_000),
            (6, "volume_up", False, 7_200_000_000),
            (7, "volume_down", False, 7_300_000_000),
        ]
        for interaction_id, command, starting_muted, timestamp in interactions:
            events.append(
                self.event(
                    "input_accepted",
                    timestamp,
                    [interaction_id],
                    command=command,
                    startingMuted=starting_muted,
                )
            )
            events.append(self.event("command_enqueue_requested", timestamp + 1_000_000, [interaction_id]))
        for interaction_id, _, _, timestamp in interactions[:4]:
            events.extend(self.interaction_events([interaction_id], timestamp))
        events.extend(self.interaction_events([5, 6, 7], 7_580_000_000))
        for interaction_id, _, _, timestamp in interactions[:3]:
            events.append(self.event("osd_presentation_requested", timestamp + 580_000_000, [interaction_id]))
            events.append(self.event("osd_first_draw_completed", timestamp + 600_000_000, [interaction_id]))
        events.append(self.event("osd_presentation_requested", 8_180_000_000, [4, 5, 6, 7]))
        events.append(self.event("osd_first_draw_completed", 8_200_000_000, [4, 5, 6, 7]))
        events.sort(key=lambda event: event["uptimeNanoseconds"])
        return self.resequenced(events)

    def write_evidence(self, directory: str, events) -> Path:
        path = Path(directory) / "trace.json"
        path.write_text(
            json.dumps(
                {
                    "metadata": {
                        "schemaVersion": 1,
                        "executablePath": str(self.installed_executable),
                        "executableSHA256": hashlib.sha256(self.installed_executable.read_bytes()).hexdigest(),
                        "firstFrameMetric": "NSHostingView.draw_completed",
                    },
                    "events": events,
                }
            )
        )
        return path

    def test_complete_trace_passes_all_scenarios_and_reports_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = build_latency_report(
                self.write_evidence(directory, self.complete_events()),
                self.installed_executable,
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["coverage"], {
            "isolated_volume": True,
            "isolated_mute": True,
            "muted_volume": True,
            "rapid_consecutive": True,
        })
        self.assertEqual(report["rapid_run_length"], 4)
        self.assertEqual(report["scenario_interaction_ids"]["isolated_volume"], [1])
        self.assertEqual(report["scenario_interaction_ids"]["isolated_mute"], [2])
        self.assertEqual(report["scenario_interaction_ids"]["muted_volume"], [3])
        self.assertEqual(report["scenario_interaction_ids"]["rapid_consecutive"], [4, 5, 6, 7])
        self.assertEqual(report["interactions"][0]["accepted_to_first_draw_ms"], 600.0)
        self.assertEqual(report["interactions"][0]["queue_delay_ms"], 10.0)
        self.assertEqual(report["missing_metrics_by_interaction"], {})
        self.assertEqual(report["missing_global_metrics"], [])

    def test_missing_required_stage_keeps_report_incomplete(self) -> None:
        events = self.resequenced([
            event
            for event in self.complete_events()
            if not (event["stage"] == "ddc_read_completed" and event["interactionIDs"] == [3])
        ])
        with tempfile.TemporaryDirectory() as directory:
            report = build_latency_report(
                self.write_evidence(directory, events),
                self.installed_executable,
            )

        self.assertEqual(report["status"], "incomplete")
        self.assertIn("ddc_read_ms", report["missing_metrics_by_interaction"]["3"])

    def test_missing_enqueue_request_keeps_report_incomplete(self) -> None:
        events = self.resequenced([
            event
            for event in self.complete_events()
            if event["stage"] != "command_enqueue_requested"
        ])
        with tempfile.TemporaryDirectory() as directory:
            report = build_latency_report(
                self.write_evidence(directory, events),
                self.installed_executable,
            )

        self.assertEqual(report["status"], "incomplete")
        self.assertIn(
            "accepted_to_enqueue_request_ms",
            report["missing_metrics_by_interaction"]["1"],
        )

    def test_noncontiguous_event_sequence_is_rejected(self) -> None:
        events = self.complete_events()
        events[-1]["sequence"] = events[-2]["sequence"]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, events)
            with self.assertRaisesRegex(RuntimeError, "event sequence"):
                build_latency_report(path, self.installed_executable)

    def test_nonmonotonic_timestamps_are_rejected(self) -> None:
        events = self.complete_events()
        events[2]["uptimeNanoseconds"] = events[1]["uptimeNanoseconds"] - 1
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, events)
            with self.assertRaisesRegex(RuntimeError, "timestamps are not monotonic"):
                build_latency_report(path, self.installed_executable)

    def test_duplicate_accepted_interaction_is_rejected(self) -> None:
        events = self.complete_events()
        accepted_events = [event for event in events if event["stage"] == "input_accepted"]
        accepted_events[1]["interactionIDs"] = accepted_events[0]["interactionIDs"]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, events)
            with self.assertRaisesRegex(RuntimeError, "accepted interaction identifiers"):
                build_latency_report(path, self.installed_executable)

    def test_missing_session_start_is_rejected(self) -> None:
        events = self.resequenced(self.complete_events()[1:])
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, events)
            with self.assertRaisesRegex(RuntimeError, "session start"):
                build_latency_report(path, self.installed_executable)

    def test_wrong_first_frame_metric_is_rejected(self) -> None:
        events = self.complete_events()
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, events)
            evidence = json.loads(path.read_text())
            evidence["metadata"]["firstFrameMetric"] = "unknown"
            path.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(RuntimeError, "first-frame metric"):
                build_latency_report(path, self.installed_executable)

    def test_rapid_limit_presses_do_not_require_redundant_ddc_writes(self) -> None:
        events = self.resequenced([
            event
            for event in self.complete_events()
            if not (
                event["stage"] in ("ddc_write_read_back_started", "ddc_write_read_back_completed")
                and any(interaction_id in event["interactionIDs"] for interaction_id in (4, 5, 6, 7))
            )
        ])
        with tempfile.TemporaryDirectory() as directory:
            report = build_latency_report(
                self.write_evidence(directory, events),
                self.installed_executable,
            )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["rapid_run_length"], 4)

    def test_archived_baseline_binds_original_path_and_preserved_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, self.complete_events())
            original_trace = path.read_bytes()
            archive = Path(directory) / "archived-executable"
            self.installed_executable.rename(archive)
            report = build_latency_report(path, self.installed_executable, archived_executable=archive)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["contract"], "historical_confirmed_feedback")
            self.assertEqual(report["artifact_binding"]["mode"], "historical_archive")
            self.assertEqual(report["artifact_binding"]["verified_artifact"], str(archive))
            self.assertEqual(report["metadata"]["executablePath"], str(self.installed_executable))
            self.assertEqual(report["interactions"][0]["accepted_to_first_draw_ms"], 600.0)
            self.assertEqual(path.read_bytes(), original_trace)
            with self.assertRaisesRegex(RuntimeError, "unreadable"):
                build_latency_report(path, self.installed_executable)
            self.installed_executable.write_bytes(b"replacement-installed-artifact")
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                build_latency_report(path, self.installed_executable)
            self.assertEqual(
                build_latency_report(path, self.installed_executable, archived_executable=archive)["status"],
                "passed",
            )

    def test_archive_rejects_wrong_path_wrong_bytes_and_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, self.complete_events())
            archive = Path(directory) / "archived-executable"
            self.installed_executable.rename(archive)
            with self.assertRaisesRegex(RuntimeError, "does not identify"):
                build_latency_report(path, archive, archived_executable=archive)
            archive.write_bytes(b"wrong-archive")
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                build_latency_report(path, self.installed_executable, archived_executable=archive)
            archive.unlink()
            with self.assertRaisesRegex(RuntimeError, "unreadable"):
                build_latency_report(path, self.installed_executable, archived_executable=archive)

    def test_archive_does_not_bypass_event_validation(self) -> None:
        events = self.complete_events()
        events[-1]["sequence"] = events[-2]["sequence"]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, events)
            archive = Path(directory) / "archived-executable"
            self.installed_executable.rename(archive)
            with self.assertRaisesRegex(RuntimeError, "event sequence"):
                build_latency_report(path, self.installed_executable, archived_executable=archive)

    def test_archive_cannot_stand_in_for_current_contract_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, self.complete_events())
            evidence = json.loads(path.read_text())
            evidence["metadata"]["schemaVersion"] = 2
            path.write_text(json.dumps(evidence))
            archive = Path(directory) / "archived-executable"
            self.installed_executable.rename(archive)
            with self.assertRaisesRegex(RuntimeError, "historical schema-1"):
                build_latency_report(path, self.installed_executable, archived_executable=archive)

    def test_unrelated_command_is_rejected(self) -> None:
        events = self.complete_events()
        events[1]["command"] = "play_pause"
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_evidence(directory, events)
            with self.assertRaisesRegex(RuntimeError, "unrelated command"):
                build_latency_report(path, self.installed_executable)


if __name__ == "__main__":
    unittest.main()
