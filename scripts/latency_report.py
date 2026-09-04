#!/usr/bin/env python3

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional


ALLOWED_STAGES = {
    "session_started",
    "input_accepted",
    "command_enqueue_requested",
    "command_enqueued",
    "service_command_started",
    "service_command_completed",
    "active_output_started",
    "active_output_completed",
    "ddc_read_started",
    "ddc_read_completed",
    "ddc_write_read_back_started",
    "ddc_write_read_back_completed",
    "osd_presentation_requested",
    "osd_first_draw_completed",
}
ALLOWED_COMMANDS = {"volume_up", "volume_down", "toggle_mute"}
EXPECTED_FIRST_FRAME_METRIC = "NSHostingView.draw_completed"
REQUIRED_INTERACTION_METRICS = (
    "accepted_to_enqueue_request_ms",
    "enqueue_request_to_enqueued_ms",
    "accepted_to_enqueued_ms",
    "queue_delay_ms",
    "service_execution_ms",
    "active_output_ms",
    "ddc_read_ms",
    "accepted_to_osd_request_ms",
    "accepted_to_first_draw_ms",
)
SUMMARY_METRICS = (*REQUIRED_INTERACTION_METRICS, "ddc_write_read_back_ms")


def read_latency_evidence(path: Path, installed_executable: Path) -> Dict[str, Any]:
    try:
        evidence = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Latency evidence is unreadable: {path}") from error
    metadata = evidence.get("metadata")
    events = evidence.get("events")
    if not isinstance(metadata, dict) or metadata.get("schemaVersion") != 1:
        raise RuntimeError("Latency evidence metadata is invalid")
    if metadata.get("firstFrameMetric") != EXPECTED_FIRST_FRAME_METRIC:
        raise RuntimeError("Latency evidence first-frame metric is invalid")
    if metadata.get("executablePath") != str(installed_executable):
        raise RuntimeError("Latency evidence does not identify the installed executable")
    try:
        executable_hash = hashlib.sha256(installed_executable.read_bytes()).hexdigest()
    except OSError as error:
        raise RuntimeError("The installed executable is unreadable") from error
    if metadata.get("executableSHA256") != executable_hash:
        raise RuntimeError("Latency evidence does not match the installed executable")
    if not isinstance(events, list) or not events:
        raise RuntimeError("Latency evidence events are invalid")
    for event in events:
        validate_event(event)
    validate_event_order(events)
    return evidence


def validate_event(event: Any) -> None:
    if not isinstance(event, dict):
        raise RuntimeError("Latency evidence contains a non-object event")
    if event.get("stage") not in ALLOWED_STAGES:
        raise RuntimeError("Latency evidence contains an unknown stage")
    if not isinstance(event.get("sequence"), int) or not isinstance(event.get("uptimeNanoseconds"), int):
        raise RuntimeError("Latency evidence contains an invalid timestamp or sequence")
    interaction_ids = event.get("interactionIDs")
    if not isinstance(interaction_ids, list) or any(not isinstance(value, int) for value in interaction_ids):
        raise RuntimeError("Latency evidence contains invalid interaction identifiers")
    command = event.get("command")
    if command is not None and command not in ALLOWED_COMMANDS:
        raise RuntimeError("Latency evidence contains an unrelated command")
    if command is not None and event.get("stage") != "input_accepted":
        raise RuntimeError("Latency evidence contains command data outside accepted input")


def validate_event_order(events: List[Dict[str, Any]]) -> None:
    if events[0]["stage"] != "session_started" or any(
        event["stage"] == "session_started" for event in events[1:]
    ):
        raise RuntimeError("Latency evidence session start is invalid")
    if [event["sequence"] for event in events] != list(range(1, len(events) + 1)):
        raise RuntimeError("Latency evidence event sequence is invalid")
    timestamps = [event["uptimeNanoseconds"] for event in events]
    if timestamps != sorted(timestamps):
        raise RuntimeError("Latency evidence timestamps are not monotonic")
    accepted_events = [event for event in events if event["stage"] == "input_accepted"]
    accepted_ids = [
        event["interactionIDs"][0]
        for event in accepted_events
        if len(event["interactionIDs"]) == 1
    ]
    if len(accepted_ids) != len(accepted_events) or len(accepted_ids) != len(set(accepted_ids)):
        raise RuntimeError("Latency evidence accepted interaction identifiers are invalid")
    known_ids = set(accepted_ids)
    if any(not set(event["interactionIDs"]).issubset(known_ids) for event in events):
        raise RuntimeError("Latency evidence references an unknown interaction identifier")


def event_time(events: List[Dict[str, Any]], stage: str) -> Optional[int]:
    timestamps = [event["uptimeNanoseconds"] for event in events if event["stage"] == stage]
    return min(timestamps) if timestamps else None


def elapsed_milliseconds(start: Optional[int], end: Optional[int]) -> Optional[float]:
    if start is None or end is None or end < start:
        return None
    return round((end - start) / 1_000_000, 3)


def interval_milliseconds(events: List[Dict[str, Any]], start_stage: str, end_stage: str) -> Optional[float]:
    starts = sorted(event["uptimeNanoseconds"] for event in events if event["stage"] == start_stage)
    ends = sorted(event["uptimeNanoseconds"] for event in events if event["stage"] == end_stage)
    if not starts or len(starts) != len(ends) or any(end < start for start, end in zip(starts, ends)):
        return None
    return round(sum(end - start for start, end in zip(starts, ends)) / 1_000_000, 3)


def interaction_budget(accepted_event: Dict[str, Any], events: List[Dict[str, Any]]) -> Dict[str, Any]:
    interaction_ids = accepted_event["interactionIDs"]
    if len(interaction_ids) != 1:
        raise RuntimeError("Accepted latency event must identify exactly one interaction")
    interaction_id = interaction_ids[0]
    interaction_events = [event for event in events if interaction_id in event["interactionIDs"]]
    accepted = accepted_event["uptimeNanoseconds"]
    enqueued = event_time(interaction_events, "command_enqueued")
    service_started = event_time(interaction_events, "service_command_started")
    service_completed = event_time(interaction_events, "service_command_completed")
    enqueue_requested = event_time(interaction_events, "command_enqueue_requested")
    osd_requested = event_time(interaction_events, "osd_presentation_requested")
    first_draw = event_time(interaction_events, "osd_first_draw_completed")
    return {
        "id": interaction_id,
        "command": accepted_event.get("command"),
        "starting_muted": accepted_event.get("startingMuted"),
        "accepted_to_enqueue_request_ms": elapsed_milliseconds(accepted, enqueue_requested),
        "enqueue_request_to_enqueued_ms": elapsed_milliseconds(enqueue_requested, enqueued),
        "accepted_to_enqueued_ms": elapsed_milliseconds(accepted, enqueued),
        "queue_delay_ms": elapsed_milliseconds(enqueued, service_started),
        "service_execution_ms": elapsed_milliseconds(service_started, service_completed),
        "active_output_ms": interval_milliseconds(
            interaction_events,
            "active_output_started",
            "active_output_completed",
        ),
        "ddc_read_ms": interval_milliseconds(
            interaction_events,
            "ddc_read_started",
            "ddc_read_completed",
        ),
        "ddc_write_read_back_ms": interval_milliseconds(
            interaction_events,
            "ddc_write_read_back_started",
            "ddc_write_read_back_completed",
        ),
        "accepted_to_osd_request_ms": elapsed_milliseconds(accepted, osd_requested),
        "accepted_to_first_draw_ms": elapsed_milliseconds(accepted, first_draw),
        "failed_stage_count": sum(event.get("outcome") == "failure" for event in interaction_events),
    }


def is_isolated(accepted_events: List[Dict[str, Any]], index: int) -> bool:
    timestamp = accepted_events[index]["uptimeNanoseconds"]
    preceding_gap = timestamp - accepted_events[index - 1]["uptimeNanoseconds"] if index > 0 else 1_000_000_000
    following_gap = (
        accepted_events[index + 1]["uptimeNanoseconds"] - timestamp
        if index + 1 < len(accepted_events)
        else 1_000_000_000
    )
    return preceding_gap >= 1_000_000_000 and following_gap >= 1_000_000_000


def rapid_run_length(accepted_events: List[Dict[str, Any]]) -> int:
    return len(rapid_interaction_ids(accepted_events))


def rapid_interaction_ids(accepted_events: List[Dict[str, Any]]) -> List[int]:
    longest = []
    current = []
    for preceding, following in zip(accepted_events, accepted_events[1:]):
        if not current:
            current = [preceding["interactionIDs"][0]]
        if following["uptimeNanoseconds"] - preceding["uptimeNanoseconds"] <= 350_000_000:
            current.append(following["interactionIDs"][0])
            if len(current) > len(longest):
                longest = current.copy()
        else:
            current = []
    return longest


def metric_summary(interactions: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    values = [interaction[key] for interaction in interactions if interaction.get(key) is not None]
    if not values:
        return {"count": 0, "minimum": None, "median": None, "maximum": None}
    return {
        "count": len(values),
        "minimum": min(values),
        "median": round(statistics.median(values), 3),
        "maximum": max(values),
    }


def build_latency_report(path: Path, installed_executable: Path) -> Dict[str, Any]:
    evidence = read_latency_evidence(path, installed_executable)
    events = evidence["events"]
    accepted_events = sorted(
        (event for event in events if event["stage"] == "input_accepted"),
        key=lambda event: event["uptimeNanoseconds"],
    )
    interactions = [interaction_budget(event, events) for event in accepted_events]
    isolated_events = [event for index, event in enumerate(accepted_events) if is_isolated(accepted_events, index)]
    scenario_interaction_ids = {
        "isolated_volume": [
            event["interactionIDs"][0]
            for event in isolated_events
            if event.get("command") in ("volume_up", "volume_down") and event.get("startingMuted") is False
        ],
        "isolated_mute": [
            event["interactionIDs"][0]
            for event in isolated_events
            if event.get("command") == "toggle_mute"
        ],
        "muted_volume": [
            event["interactionIDs"][0]
            for event in accepted_events
            if event.get("command") in ("volume_up", "volume_down") and event.get("startingMuted") is True
        ],
        "rapid_consecutive": rapid_interaction_ids(accepted_events),
    }
    coverage = {name: bool(interaction_ids) for name, interaction_ids in scenario_interaction_ids.items()}
    interaction_by_id = {interaction["id"]: interaction for interaction in interactions}
    scenario_summary = {
        name: {
            key: metric_summary(
                [interaction_by_id[interaction_id] for interaction_id in interaction_ids],
                key,
            )
            for key in SUMMARY_METRICS
        }
        for name, interaction_ids in scenario_interaction_ids.items()
    }
    missing_scenarios = [name for name, covered in coverage.items() if not covered]
    missing_metrics = {
        str(interaction["id"]): [key for key in REQUIRED_INTERACTION_METRICS if interaction[key] is None]
        for interaction in interactions
        if any(interaction[key] is None for key in REQUIRED_INTERACTION_METRICS)
    }
    missing_global_metrics = []
    if not any(interaction["ddc_write_read_back_ms"] is not None for interaction in interactions):
        missing_global_metrics.append("ddc_write_read_back_ms")
    complete = (
        not missing_scenarios
        and not missing_metrics
        and not missing_global_metrics
        and bool(interactions)
        and all(interaction["failed_stage_count"] == 0 for interaction in interactions)
    )
    return {
        "status": "passed" if complete else "incomplete",
        "evidence": str(path),
        "metadata": evidence["metadata"],
        "coverage": coverage,
        "scenario_interaction_ids": scenario_interaction_ids,
        "scenario_summary": scenario_summary,
        "missing_scenarios": missing_scenarios,
        "missing_metrics_by_interaction": missing_metrics,
        "missing_global_metrics": missing_global_metrics,
        "rapid_run_length": rapid_run_length(accepted_events),
        "summary": {key: metric_summary(interactions, key) for key in SUMMARY_METRICS},
        "interactions": interactions,
    }
