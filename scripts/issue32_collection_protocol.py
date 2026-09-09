#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROTOCOL_PATH = Path(__file__).with_suffix(".json")


class ProtocolError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = json.loads(path.read_text())
    validate_protocol(protocol)
    return protocol


def condition(value: str) -> tuple[str, str]:
    candidate, instrumentation = value.split("/", 1)
    return candidate, instrumentation


def measured_schedule(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    measured = protocol["measuredCollection"]
    workload_orders = measured["workloadOrderByRoundParity"]
    condition_cycle = measured["conditionOrderCycle"]
    schedule: list[dict[str, Any]] = []
    for round_ordinal in range(1, measured["rounds"] + 1):
        workloads = workload_orders["odd" if round_ordinal % 2 else "even"]
        conditions = condition_cycle[(round_ordinal - 1) % len(condition_cycle)]
        for workload in workloads:
            for value in conditions:
                candidate, instrumentation = condition(value)
                schedule.append({
                    "round": round_ordinal,
                    "workload": workload,
                    "candidate": candidate,
                    "instrumentation": instrumentation,
                })
    return schedule


def warmup_schedule(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    warmup = protocol["warmup"]
    schedule: list[dict[str, Any]] = []
    for workload in warmup["workloadOrder"]:
        for value in warmup["scheduleConditionOrder"]:
            candidate, instrumentation = condition(value)
            schedule.append({
                "warmup": True,
                "workload": workload,
                "candidate": candidate,
                "instrumentation": instrumentation,
            })
    return schedule


def validate_protocol(protocol: dict[str, Any]) -> None:
    require(protocol.get("schemaVersion") == 1, "unsupported schema")
    require(protocol.get("status") == "frozenBeforeComparativeCollection", "protocol is not frozen")
    candidates = protocol["candidates"]
    require(set(candidates) == {"A", "B"}, "candidate set mismatch")
    for candidate in candidates.values():
        source_ref = candidate["sourceRef"]
        require(
            len(source_ref) == 40 and all(character in "0123456789abcdef" for character in source_ref),
            "candidate ref is not a full lowercase SHA",
        )
    gate = protocol["gate"]
    require(gate["capacity"] == 8, "capacity mismatch")
    require(gate["phaseDurationMilliseconds"] == 40, "phase duration mismatch")
    require(gate["pollIntervalMilliseconds"] == 10, "poll interval mismatch")
    require(gate["candidateProcessTimeoutSeconds"] == 30, "candidate watchdog mismatch")
    require(gate["terminationGraceSeconds"] == 2, "candidate termination grace mismatch")
    require(
        protocol["watchdogs"] == {
            "apparatusInvocationTimeoutSeconds": 90,
            "buildTimeoutSeconds": 300,
            "environmentCommandTimeoutSeconds": 30,
            "environmentProbeBuildTimeoutSeconds": 60,
        },
        "collector watchdog mismatch",
    )
    require(protocol["instrumentation"]["modes"] == ["full", "none"], "instrumentation matrix mismatch")
    require(set(protocol["workloads"]) == {"normal", "stress"}, "workload matrix mismatch")
    measured = protocol["measuredCollection"]
    required_conditions = {"A/full", "B/full", "A/none", "B/none"}
    require(
        all(set(order) == required_conditions and len(order) == 4 for order in measured["conditionOrderCycle"]),
        "condition order cycle mismatch",
    )
    require(
        set(measured["workloadOrderByRoundParity"]["odd"]) == {"normal", "stress"}
        and set(measured["workloadOrderByRoundParity"]["even"]) == {"normal", "stress"},
        "workload order mismatch",
    )
    schedule = measured_schedule(protocol)
    require(len(schedule) == measured["totalMeasuredRuns"], "measured run total mismatch")
    expected_count = measured["runsPerCandidateWorkloadInstrumentation"]
    require(measured["minimumValidRunsPerCandidateWorkloadInstrumentation"] == expected_count, "valid run minimum mismatch")
    for workload in protocol["workloads"]:
        for candidate in candidates:
            for instrumentation in protocol["instrumentation"]["modes"]:
                count = sum(
                    item["workload"] == workload
                    and item["candidate"] == candidate
                    and item["instrumentation"] == instrumentation
                    for item in schedule
                )
                require(count == expected_count, "measured schedule is unbalanced")
    warmups = warmup_schedule(protocol)
    require(len(warmups) == 8, "warmup schedule mismatch")
    require(protocol["missingData"]["numericImputation"] == "none", "numeric imputation is forbidden")
    require(protocol["artifactBinding"]["configurationDigestIncludesProtocolSha256"] is True, "protocol digest binding missing")
    required_metrics = protocol["requiredMetrics"]
    required_accounting = {
        "inputEventCount",
        "passedThroughEventCount",
        "deliveredCommandCount",
        "admissionAttempted",
        "admitted",
        "rejected",
        "discarded",
        "overflow",
        "completed",
        "peakOutstanding",
        "pending",
        "failedPollCount",
        "censoredCount",
    }
    require(required_accounting <= set(required_metrics["exactEveryRun"]), "exact accounting metrics missing")
    require(required_metrics["stressResultsRemainSeparate"] is True, "stress separation missing")
    timing_minima = required_metrics["fullInstrumentationTimingByWorkload"]["minimumSamplesPerRun"]
    require(
        timing_minima == {
            "isolatedInput": {"normal": 2, "stress": 2},
            "repeatedBurst": {"normal": 8, "stress": 32},
            "mixedBurst": {"normal": 6, "stress": 6},
            "consumerDrainDelayPerPhase": 1,
        },
        "timing sample minima mismatch",
    )
    environment = protocol["environment"]
    require(environment["powerSourceObservation"].startswith("retain and parse /usr/bin/pmset -g batt"), "power observation missing")
    require(environment["lowPowerModeObservation"].startswith("retain and parse the AC Power section of /usr/bin/pmset -g custom"), "low-power observation missing")
    require(environment["thermalObservation"].startswith("record Foundation ProcessInfo.thermalState"), "thermal observation missing")
    require(environment["retainEveryObservation"] is True, "environment retention missing")
    equivalence = protocol["equivalence"]
    require(
        equivalence["repeatabilityNoiseBand"]
        == "maximum candidate median absolute difference between the 19 successive valid same-configuration run summaries",
        "repeatability statistic mismatch",
    )
    require(equivalence["minimumSuccessiveDifferencesPerCandidateConfiguration"] == expected_count - 1, "repeatability sample minimum mismatch")
    require(protocol["selection"]["candidateAAtMeasurableParity"] is True, "parity preference mismatch")
    require(protocol["measuredCollection"]["crossCandidateExecution"] == "blockedUntilOfflineGatesAndControlsPass", "comparative gate missing")


def main() -> int:
    protocol = load_protocol()
    output = {
        "status": "valid",
        "warmupSchedule": warmup_schedule(protocol),
        "measuredSchedule": measured_schedule(protocol),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
