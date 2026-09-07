import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.latency_report import build_latency_report


class IntentLatencyTests(unittest.TestCase):
    def events(self):
        events = [{"stage": "session_started", "uptimeNanoseconds": 0, "interactionIDs": []}]
        def event(stage, milliseconds, identifier, **values):
            events.append({"stage": stage, "uptimeNanoseconds": milliseconds * 1_000_000,
                           "interactionIDs": [identifier], **values})
        for identifier, timestamp, command, muted in [
            (1, 1000, "volume_up", False), (2, 3000, "toggle_mute", False),
            (3, 5000, "volume_down", True), (4, 7000, "volume_up", False),
            (5, 7100, "volume_down", False),
        ]:
            event("input_accepted", timestamp, identifier, command=command, startingMuted=muted)
            event("intent_reduced", timestamp + 1, identifier)
            event("osd_presentation_requested", timestamp + 2, identifier)
            event("command_enqueue_requested", timestamp + 3, identifier)
            event("command_enqueued", timestamp + 4, identifier)
            event("osd_first_draw_completed", timestamp + 30, identifier)
            begin = timestamp + 10 if identifier < 5 else 7410
            event("service_command_started", begin, identifier)
            event("active_output_started", begin + 1, identifier)
            event("active_output_completed", begin + 2, identifier, outcome="success")
            if identifier < 5:
                event("ddc_write_read_back_started", timestamp + 20, identifier)
                event("ddc_write_read_back_completed", timestamp + 390, identifier, outcome="success")
            terminal = "command_superseded" if identifier == 4 else "service_command_completed"
            event(terminal, timestamp + 400 if identifier < 5 else 7420, identifier)
        return sorted(events, key=lambda item: item["uptimeNanoseconds"])

    def report(self, events, schema=2):
        for sequence, event in enumerate(events, 1):
            event["sequence"] = sequence
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "fixture-executable"
            executable.write_bytes(b"synthetic-test-artifact")
            trace = Path(folder) / "trace.json"
            trace.write_text(json.dumps({"metadata": {
                "schemaVersion": schema, "executablePath": str(executable),
                "executableSHA256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "firstFrameMetric": "NSHostingView.draw_completed",
            }, "events": events}))
            return build_latency_report(trace, executable)

    def test_intent_trace_separates_draw_from_hardware_and_allows_no_write(self):
        report = self.report(self.events())
        self.assertEqual(report["status"], "passed", report["intent_errors"])
        self.assertEqual(report["contract"], "input_intent")
        self.assertEqual(report["interactions"][0]["accepted_to_first_draw_ms"], 30)
        self.assertEqual(report["interactions"][0]["ddc_write_read_back_ms"], 370)
        self.assertIsNone(report["interactions"][4]["ddc_write_read_back_ms"])
        self.assertEqual(report["draws_while_hardware_busy"], 5)

    def test_missing_and_duplicate_required_stages_do_not_pass(self):
        for stage in ("intent_reduced", "command_enqueued", "service_command_started",
                      "service_command_completed", "osd_first_draw_completed"):
            for duplicate in (False, True):
                with self.subTest(stage=stage, duplicate=duplicate):
                    events = self.events()
                    index = next(i for i, e in enumerate(events)
                                 if e["stage"] == stage and e["interactionIDs"] == [1])
                    if duplicate:
                        events.insert(index, copy.deepcopy(events[index]))
                    else:
                        events.pop(index)
                    self.assertEqual(self.report(events)["status"], "incomplete")

    def test_unpaired_or_uncorrelated_hardware_never_passes(self):
        for mutation in ("missing_start", "wrong_owner", "no_outcome", "overlap"):
            with self.subTest(mutation=mutation):
                events = self.events()
                start = next(e for e in events if e["stage"] == "ddc_write_read_back_started")
                end = next(e for e in events if e["stage"] == "ddc_write_read_back_completed")
                if mutation == "missing_start":
                    events.remove(start)
                elif mutation == "wrong_owner":
                    end["interactionIDs"] = [2]
                elif mutation == "no_outcome":
                    end.pop("outcome")
                else:
                    events.insert(events.index(start), copy.deepcopy(start))
                self.assertEqual(self.report(events)["status"], "incomplete")

    def test_superseded_presentation_requires_a_newer_request(self):
        events = self.events()
        draw = next(e for e in events if e["stage"] == "osd_first_draw_completed")
        draw["stage"] = "osd_presentation_superseded"
        self.assertEqual(self.report(events)["status"], "incomplete")
        draw["interactionIDs"] = [4]
        events.remove(draw)
        events = [e for e in events if not (e["stage"] == "osd_first_draw_completed"
                                           and e["interactionIDs"] == [4])]
        draw["uptimeNanoseconds"] = 7_103_000_000
        events.append(draw)
        events.append({"stage": "osd_first_draw_completed", "interactionIDs": [1],
                       "uptimeNanoseconds": 1_030_000_000})
        events.sort(key=lambda e: e["uptimeNanoseconds"])
        self.assertEqual(self.report(events)["status"], "passed")

    def test_same_timestamp_does_not_allow_reversed_causality(self):
        events = self.events()
        accepted = events[1]
        intent = events[2]
        intent["uptimeNanoseconds"] = accepted["uptimeNanoseconds"]
        events[1], events[2] = intent, accepted
        self.assertEqual(self.report(events)["status"], "incomplete")

    def test_duplicate_ids_and_empty_hardware_correlation_are_rejected(self):
        events = self.events()
        events[2]["interactionIDs"] = [1, 1]
        with self.assertRaises(RuntimeError):
            self.report(events)
        events[2]["interactionIDs"] = []
        self.assertEqual(self.report(events)["status"], "incomplete")

    def test_discarded_intent_is_not_convergence_proof(self):
        events = self.events()
        next(e for e in events if e["stage"] == "service_command_completed")["stage"] = "command_discarded"
        self.assertEqual(self.report(events)["status"], "incomplete")

    def test_historical_trace_is_never_new_contract_proof(self):
        self.assertEqual(self.report(self.events(), schema=1)["contract"], "historical_confirmed_feedback")


if __name__ == "__main__":
    unittest.main()
