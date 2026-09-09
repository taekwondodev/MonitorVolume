#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable, Literal

if __package__:
    from scripts import issue32_apparatus as apparatus
    from scripts import issue32_collection_protocol as collection_protocol
else:
    import issue32_apparatus as apparatus
    import issue32_collection_protocol as collection_protocol

ROOT = Path(__file__).resolve().parents[1]
TARGET = apparatus.TARGET
NUMERIC_GATE_FAILURES = {"phaseWithoutResourceSample", "phaseWithoutCpuInterval"}
ACCOUNTING_FIELDS = (
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
)


class CollectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunSpec:
    stage: Literal["warmup", "measured", "replacement"]
    round_ordinal: int
    workload: Literal["normal", "stress"]
    candidate: Literal["A", "B"]
    instrumentation: Literal["full", "none"]
    sequence: int
    replacement_ordinal: int | None = None


@dataclass(frozen=True)
class PreparedCandidate:
    candidate: Literal["A", "B"]
    worktree: Path
    source_ref: str
    source_closure: dict[str, str]
    executable: Path
    executable_sha256: str
    compiler: str


@dataclass(frozen=True)
class GateOutcome:
    spec: RunSpec
    directory: Path
    report: dict[str, Any]
    replaceable: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CollectionError(message)


def sha256_file(path: Path) -> str:
    return apparatus.sha256_file(path)


def stable_digest(value: Any) -> str:
    return apparatus.stable_digest(value)


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def read_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise CollectionError(f"cannot read report {path}: {error}") from error
    require(isinstance(value, dict), f"report is not an object: {path}")
    return value


def protocol_sha256() -> str:
    return sha256_file(collection_protocol.PROTOCOL_PATH)


def validate_report_binding(report: dict[str, Any]) -> None:
    protocol = collection_protocol.load_protocol()
    candidate = report.get("candidate")
    require(candidate in protocol["candidates"], "control candidate is invalid")
    require(report.get("sourceRef") == protocol["candidates"][candidate]["sourceRef"], "control source ref mismatch")
    require(report.get("collectionProtocolSha256") == protocol_sha256(), "control protocol digest mismatch")
    require(report.get("runnerSha256") == sha256_file(ROOT / "scripts" / "issue32_apparatus.py"), "control runner digest mismatch")
    require(report.get("expectedScenariosSha256") == sha256_file(apparatus.EXPECTED_SCENARIOS_PATH), "control matrix digest mismatch")
    require(report.get("validationFailures") == [], "control input did not pass its gate")
    require(report.get("exitCode") == 0, "control child exit was nonzero")
    require(report.get("behaviorFingerprint") == apparatus.behavior_fingerprint(report), "control behavior fingerprint mismatch")
    executable = report.get("executable") or {}
    require(isinstance(executable.get("sha256"), str), "control executable digest missing")


def control_manifest(report_paths: list[Path]) -> dict[str, Any]:
    require(len(report_paths) == 6, "control manifest requires exactly six reports")
    reports = [(path.resolve(), read_report(path.resolve())) for path in report_paths]
    for _, report in reports:
        validate_report_binding(report)
    by_candidate: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for item in reports:
        by_candidate[item[1]["candidate"]].append(item)
    require(set(by_candidate) == {"A", "B"}, "control manifest requires both candidates")

    controls: list[dict[str, Any]] = []
    for candidate in ("A", "B"):
        candidate_reports = by_candidate[candidate]
        require(len(candidate_reports) == 3, f"candidate {candidate} requires three controls")
        workloads = {
            report["childReport"]["apparatus"]["workloadClass"]
            for _, report in candidate_reports
        }
        require(len(workloads) == 1, f"candidate {candidate} controls use different workloads")
        full = [item for item in candidate_reports if item[1]["childReport"]["apparatus"]["instrumentation"] == "full"]
        none = [item for item in candidate_reports if item[1]["childReport"]["apparatus"]["instrumentation"] == "none"]
        require(len(full) == 2 and len(none) == 1, f"candidate {candidate} control modes are incomplete")
        require(apparatus.validate_control_pair(full[0][1], full[1][1]) == [], f"candidate {candidate} repeatability control failed")
        require(apparatus.validate_instrumentation_pair(full[0][1], none[0][1]) == [], f"candidate {candidate} instrumentation control failed")
        controls.extend(
            {
                "candidate": candidate,
                "instrumentation": report["childReport"]["apparatus"]["instrumentation"],
                "path": portable_path(path),
                "reportSha256": sha256_file(path),
                "configurationDigest": report["configurationDigest"],
                "executableSha256": report["executable"]["sha256"],
            }
            for path, report in candidate_reports
        )
    return {
        "schemaVersion": 1,
        "status": "controlsValidated",
        "protocolSha256": protocol_sha256(),
        "reports": sorted(controls, key=lambda item: (item["candidate"], item["instrumentation"], item["path"])),
    }


def validate_control_manifest(manifest: dict[str, Any]) -> None:
    require(manifest.get("schemaVersion") == 1, "unsupported control manifest schema")
    require(manifest.get("status") == "controlsValidated", "control manifest is not validated")
    require(manifest.get("protocolSha256") == protocol_sha256(), "control manifest protocol digest mismatch")
    paths = [resolve_path(item["path"]) for item in manifest.get("reports", [])]
    require(control_manifest(paths) == manifest, "control manifest does not reconstruct from retained reports")


def materialize_run_specs(protocol: dict[str, Any]) -> tuple[list[RunSpec], list[RunSpec]]:
    warmups = [
        RunSpec(
            stage="warmup",
            round_ordinal=0,
            workload=item["workload"],
            candidate=item["candidate"],
            instrumentation=item["instrumentation"],
            sequence=index,
        )
        for index, item in enumerate(collection_protocol.warmup_schedule(protocol), 1)
    ]
    measured = [
        RunSpec(
            stage="measured",
            round_ordinal=item["round"],
            workload=item["workload"],
            candidate=item["candidate"],
            instrumentation=item["instrumentation"],
            sequence=index,
        )
        for index, item in enumerate(collection_protocol.measured_schedule(protocol), 1)
    ]
    return warmups, measured


def workload_blocks(specs: list[RunSpec]) -> list[list[RunSpec]]:
    blocks: list[list[RunSpec]] = []
    for index in range(0, len(specs), 4):
        block = specs[index:index + 4]
        require(len(block) == 4, "schedule contains an incomplete workload block")
        require(len({item.workload for item in block}) == 1, "workload block mixes workloads")
        require(len({item.round_ordinal for item in block}) == 1, "workload block mixes rounds")
        require({(item.candidate, item.instrumentation) for item in block} == {
            ("A", "full"), ("B", "full"), ("A", "none"), ("B", "none")
        }, "workload block condition matrix mismatch")
        blocks.append(block)
    return blocks


def run_command(
    command: list[str],
    cwd: Path,
    timeout_seconds: float,
    termination_grace_seconds: float,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return apparatus.run_process(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            termination_grace_seconds=termination_grace_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise CollectionError(f"command timed out after {timeout_seconds}s: {' '.join(command)}") from error


def prepare_candidate(candidate: Literal["A", "B"], worktree: Path, campaign_dir: Path) -> PreparedCandidate:
    protocol = collection_protocol.load_protocol()
    watchdogs = protocol["watchdogs"]
    source_ref = protocol["candidates"][candidate]["sourceRef"]
    resolved = apparatus.run_checked(
        ["git", "rev-parse", source_ref],
        cwd=worktree,
        timeout_seconds=watchdogs["environmentCommandTimeoutSeconds"],
    )
    require(resolved == source_ref, f"candidate {candidate} source ref did not resolve exactly")
    before = apparatus.source_binding(worktree, candidate)
    environment = dict(os.environ)
    environment["ISSUE_32_CONFORMANCE"] = "1"
    command = ["swift", "build", "-c", "release", "-Xswiftc", "-strict-concurrency=complete", "--product", TARGET]
    result = run_command(
        command,
        worktree,
        watchdogs["buildTimeoutSeconds"],
        protocol["gate"]["terminationGraceSeconds"],
        environment,
    )
    require(result.returncode == 0, f"candidate {candidate} Release build failed: {result.stderr}")
    after = apparatus.source_binding(worktree, candidate)
    require(after == before, f"candidate {candidate} source closure changed during build")
    executable = (worktree / ".build" / "release" / TARGET).resolve()
    require(executable.is_file(), f"candidate {candidate} Release executable is missing")
    digest = sha256_file(executable)
    artifact_dir = campaign_dir / "artifacts" / candidate
    artifact_dir.mkdir(parents=True)
    retained = artifact_dir / TARGET
    shutil.copy2(executable, retained)
    require(sha256_file(retained) == digest, f"candidate {candidate} retained executable mismatch")
    compiler = apparatus.run_checked(
        ["swift", "--version"],
        cwd=worktree,
        timeout_seconds=watchdogs["environmentCommandTimeoutSeconds"],
    )
    write_json_atomic(artifact_dir / "binding.json", {
        "candidate": candidate,
        "sourceRef": source_ref,
        "sourceClosure": before,
        "compiler": compiler,
        "buildCommand": command,
        "executablePath": portable_path(executable),
        "executableSha256": digest,
        "retainedExecutable": portable_path(retained),
        "protocolSha256": protocol_sha256(),
    })
    return PreparedCandidate(candidate, worktree, source_ref, before, executable, digest, compiler)


def compile_environment_probe(campaign_dir: Path) -> Path:
    watchdogs = collection_protocol.load_protocol()["watchdogs"]
    source = ROOT / "scripts" / "Issue32EnvironmentProbe.swift"
    executable = campaign_dir / "artifacts" / "Issue32EnvironmentProbe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    result = run_command(
        ["swiftc", str(source), "-o", str(executable)],
        ROOT,
        watchdogs["environmentProbeBuildTimeoutSeconds"],
        collection_protocol.load_protocol()["gate"]["terminationGraceSeconds"],
    )
    require(result.returncode == 0, f"environment probe build failed: {result.stderr}")
    return executable


def parse_power_source(output: str) -> str:
    if "'AC Power'" in output:
        return "ac"
    if "'Battery Power'" in output:
        return "battery"
    raise CollectionError("power source is unavailable")


def parse_ac_low_power_mode(output: str) -> bool:
    section: list[str] = []
    active = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.endswith("Power:"):
            active = stripped == "AC Power:"
            continue
        if active:
            section.append(stripped)
    for line in section:
        fields = line.split()
        if len(fields) == 2 and fields[0] == "lowpowermode" and fields[1] in {"0", "1"}:
            return fields[1] == "1"
    raise CollectionError("AC low-power mode is unavailable")


def checked_observation(command: list[str]) -> dict[str, Any]:
    protocol = collection_protocol.load_protocol()
    timeout = protocol["watchdogs"]["environmentCommandTimeoutSeconds"]
    result = run_command(command, ROOT, timeout, protocol["gate"]["terminationGraceSeconds"])
    require(result.returncode == 0, f"environment command failed: {' '.join(command)}")
    return {"command": command, "stdout": result.stdout, "stderr": result.stderr, "exitCode": result.returncode}


def observe_environment(probe: Path, ordinal: int, boundary: str) -> dict[str, Any]:
    power = checked_observation(["/usr/bin/pmset", "-g", "batt"])
    low_power = checked_observation(["/usr/bin/pmset", "-g", "custom"])
    thermal = checked_observation([str(probe)])
    sw_vers = checked_observation(["/usr/bin/sw_vers"])
    machine = checked_observation(["/usr/bin/uname", "-m"])
    model = checked_observation(["/usr/sbin/sysctl", "-n", "hw.model"])
    logical_cpu = checked_observation(["/usr/sbin/sysctl", "-n", "hw.logicalcpu"])
    swift = checked_observation(["swift", "--version"])
    thermal_value = json.loads(thermal["stdout"])
    observation = {
        "ordinal": ordinal,
        "boundary": boundary,
        "powerSource": parse_power_source(power["stdout"]),
        "lowPowerMode": parse_ac_low_power_mode(low_power["stdout"]),
        "thermalState": thermal_value["thermalState"],
        "logicalCpuCount": int(logical_cpu["stdout"].strip()),
        "identity": {
            "swVers": sw_vers["stdout"],
            "machine": machine["stdout"].strip(),
            "model": model["stdout"].strip(),
            "swift": swift["stdout"],
        },
        "raw": {
            "power": power,
            "lowPower": low_power,
            "thermal": thermal,
            "swVers": sw_vers,
            "machine": machine,
            "model": model,
            "logicalCpu": logical_cpu,
            "swift": swift,
        },
    }
    validate_environment(observation)
    return observation


def validate_environment(observation: dict[str, Any], baseline: dict[str, Any] | None = None) -> None:
    require(observation.get("powerSource") == "ac", "campaign requires AC power")
    require(observation.get("lowPowerMode") is False, "campaign requires low-power mode off")
    require(observation.get("thermalState") == "nominal", "campaign requires nominal thermal state")
    require(type(observation.get("logicalCpuCount")) is int and observation["logicalCpuCount"] > 0, "logical CPU count is invalid")
    if baseline is not None:
        require(observation["identity"] == baseline["identity"], "host, OS, or toolchain identity changed")
        require(observation["logicalCpuCount"] == baseline["logicalCpuCount"], "logical CPU count changed")


def run_gate(
    prepared: PreparedCandidate,
    spec: RunSpec,
    output: Path,
    expected_protocol_sha256: str,
    expected_apparatus_sha256: str,
    expected_matrix_sha256: str,
) -> GateOutcome:
    require(protocol_sha256() == expected_protocol_sha256, "collection protocol changed during campaign")
    require(sha256_file(ROOT / "scripts" / "issue32_apparatus.py") == expected_apparatus_sha256, "apparatus changed during campaign")
    require(sha256_file(apparatus.EXPECTED_SCENARIOS_PATH) == expected_matrix_sha256, "expected matrix changed during campaign")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "issue32_apparatus.py"),
        "gate",
        "--candidate", prepared.candidate,
        "--worktree", str(prepared.worktree),
        "--source-ref", prepared.source_ref,
        "--output-dir", str(output),
        "--workload", spec.workload,
        "--instrumentation", spec.instrumentation,
        "--run-ordinal", str(spec.sequence),
        "--prepared-executable", str(prepared.executable),
        "--expected-executable-sha256", prepared.executable_sha256,
    ]
    protocol = collection_protocol.load_protocol()
    timeout = protocol["watchdogs"]["apparatusInvocationTimeoutSeconds"]
    result = run_command(command, ROOT, timeout, protocol["gate"]["terminationGraceSeconds"])
    report_path = output / "report.json"
    require(report_path.is_file(), f"apparatus did not retain report: {output}")
    report = read_report(report_path)
    failures = set(report.get("validationFailures") or [])
    replaceable = bool(failures) and failures <= NUMERIC_GATE_FAILURES and report.get("exitCode") == 0
    if result.returncode != 0 and not replaceable:
        raise CollectionError(f"hard apparatus gate failure in {output}: {sorted(failures)}")
    require(report.get("executable", {}).get("sha256") == prepared.executable_sha256, "measured executable hash drift")
    require(report.get("binding") == prepared.source_closure, "measured source closure drift")
    require(report.get("collectionProtocolSha256") == expected_protocol_sha256, "measured protocol digest drift")
    require(protocol_sha256() == expected_protocol_sha256, "collection protocol changed during campaign")
    require(sha256_file(ROOT / "scripts" / "issue32_apparatus.py") == expected_apparatus_sha256, "apparatus changed during campaign")
    require(sha256_file(apparatus.EXPECTED_SCENARIOS_PATH) == expected_matrix_sha256, "expected matrix changed during campaign")
    return GateOutcome(spec, output, report, replaceable)


def gate_directory(campaign_dir: Path, spec: RunSpec) -> Path:
    replacement = "" if spec.replacement_ordinal is None else f"-replacement-{spec.replacement_ordinal}"
    return campaign_dir / "runs" / f"{spec.stage}-{spec.sequence:03d}-round-{spec.round_ordinal:02d}-{spec.workload}-{spec.candidate}-{spec.instrumentation}{replacement}"


def summarize_numbers(values: list[float]) -> dict[str, float | int]:
    require(bool(values), "numeric summary is empty")
    require(all(math.isfinite(value) for value in values), "numeric summary contains a non-finite value")
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return {
        "sampleCount": len(values),
        "median": statistics.median(values),
        "nearestRankP95": ordered[rank - 1],
        "maximum": ordered[-1],
    }


def timing_values(report: dict[str, Any], phase: str) -> tuple[list[float], list[float]]:
    events = [event for event in report["childReport"]["apparatus"]["events"] if event.get("phase") == phase]
    bridge: list[float] = []
    final_return: int | None = None
    pending: tuple[str, int] | None = None
    drain: list[float] = []
    for event in events:
        kind = event.get("kind")
        if kind == "typedBridgeRequested":
            require(pending is None, f"overlapping bridge request in {phase}")
            pending = (event["input"], event["uptimeNanoseconds"])
        elif kind == "typedBridgeReturned":
            if pending is None or pending[0] != event.get("input"):
                raise CollectionError(f"unpaired bridge return in {phase}")
            current = pending
            require(event["uptimeNanoseconds"] >= current[1], f"negative bridge duration in {phase}")
            bridge.append(event["uptimeNanoseconds"] - current[1])
            final_return = event["uptimeNanoseconds"]
            pending = None
        elif kind == "consumerDrained" and final_return is not None:
            require(event["uptimeNanoseconds"] >= final_return, f"negative drain duration in {phase}")
            drain.append(event["uptimeNanoseconds"] - final_return)
            final_return = None
    require(pending is None, f"unterminated bridge request in {phase}")
    return bridge, drain


def phase_samples(report: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    start, end = apparatus.phase_ranges(report["observedPhaseBoundaries"])[phase]
    return [
        sample for sample in report["rawSamples"]
        if sample.get("status") == "sampled" and start <= sample["uptimeNanoseconds"] <= end
    ]


def run_metrics(report: dict[str, Any], logical_cpu_count: int) -> dict[str, float]:
    metrics: dict[str, float] = {}
    apparatus_report = report["childReport"]["apparatus"]
    workload = apparatus_report["workloadClass"]
    instrumentation = apparatus_report["instrumentation"]
    timing_phases = {"isolatedInput", "repeatedBurst", "mixedBurst"}
    minimum = collection_protocol.load_protocol()["minimumTimingSamplesPerValidRun"]
    for phase_result in apparatus_report["phases"]:
        phase = phase_result["phase"]
        for field in ACCOUNTING_FIELDS:
            metrics[f"accounting.{field}.{phase}"] = float(phase_result[field])
        resource = report["phaseResourceSummaries"][phase]
        metrics[f"cpu.meanOneCorePercent.{phase}"] = float(resource["meanCpuPercent"])
        metrics[f"cpu.maximumOneCorePercent.{phase}"] = float(resource["maximumCpuPercent"])
        metrics[f"cpu.meanMachineCapacityPercent.{phase}"] = float(resource["meanCpuPercent"]) / logical_cpu_count
        metrics[f"cpu.maximumMachineCapacityPercent.{phase}"] = float(resource["maximumCpuPercent"]) / logical_cpu_count
        rss = [float(sample["rssBytes"]) for sample in phase_samples(report, phase)]
        require(bool(rss), f"phase {phase} has no resident-size samples")
        metrics[f"memory.medianResidentSizeBytes.{phase}"] = statistics.median(rss)
        metrics[f"memory.maximumResidentSizeBytes.{phase}"] = max(rss)
        metrics[f"memory.lastResidentSizeBytes.{phase}"] = rss[-1]
        if instrumentation == "full" and phase in timing_phases:
            bridge, drain = timing_values(report, phase)
            expected_bridge = minimum["bridgeRoundTripNanoseconds"][
                f"{workload}{phase[0].upper()}{phase[1:]}" if phase == "repeatedBurst" else phase
            ]
            expected_drain = minimum["consumerDrainDelayNanoseconds"][phase]
            require(len(bridge) >= expected_bridge, f"phase {phase} bridge timing samples are incomplete")
            require(len(drain) >= expected_drain, f"phase {phase} drain timing samples are incomplete")
            for name, values in (("bridgeRoundTripNanoseconds", bridge), ("consumerDrainDelayNanoseconds", drain)):
                for statistic, value in summarize_numbers(values).items():
                    metrics[f"timing.{name}.{statistic}.{phase}"] = float(value)
    return metrics


def median_absolute_successive_difference(values: list[float]) -> float:
    require(len(values) >= 20, "repeatability requires 20 valid summaries")
    return float(statistics.median(abs(right - left) for left, right in zip(values, values[1:])))


def bootstrap_interval(differences: list[float], seed: int, resamples: int = 10_000) -> tuple[float, float]:
    require(bool(differences), "paired bootstrap requires differences")
    generator = random.Random(seed)
    estimates = sorted(
        statistics.median(generator.choice(differences) for _ in differences)
        for _ in range(resamples)
    )
    lower = estimates[max(0, math.ceil(0.025 * len(estimates)) - 1)]
    upper = estimates[max(0, math.ceil(0.975 * len(estimates)) - 1)]
    return float(lower), float(upper)


def classify_interval(lower: float, upper: float, noise_band: float) -> str:
    if -noise_band <= lower and upper <= noise_band:
        return "equivalent"
    if upper < -noise_band:
        return "candidateBBetter"
    if lower > noise_band:
        return "candidateABetter"
    return "inconclusive"


def select_candidate(classifications: Iterable[str], lifecycle_review_green: bool) -> str:
    values = set(classifications)
    if not values or "inconclusive" in values or ("candidateABetter" in values and "candidateBBetter" in values):
        return "inconclusive"
    if values <= {"equivalent", "candidateABetter"}:
        return "A"
    if lifecycle_review_green and "candidateBBetter" in values and values <= {"equivalent", "candidateBBetter"}:
        return "B"
    return "inconclusive"


def performance_metric(name: str) -> bool:
    if name.startswith("accounting."):
        return False
    if ".sampleCount." in name or ".intervalCount." in name:
        return False
    return name.startswith(("timing.", "cpu.", "memory."))


def read_bound_report(record: dict[str, Any]) -> dict[str, Any]:
    path = resolve_path(record["reportPath"])
    require(sha256_file(path) == record.get("reportSha256"), f"measured report digest mismatch: {path}")
    report = read_report(path)
    protocol = collection_protocol.load_protocol()
    candidate = record["candidate"]
    require(report.get("candidate") == candidate, "measured report candidate mismatch")
    require(report.get("sourceRef") == protocol["candidates"][candidate]["sourceRef"], "measured report source ref mismatch")
    require(report.get("collectionProtocolSha256") == protocol_sha256(), "measured report protocol digest mismatch")
    require(report.get("runnerSha256") == sha256_file(ROOT / "scripts" / "issue32_apparatus.py"), "measured report apparatus digest mismatch")
    require(report.get("expectedScenariosSha256") == sha256_file(apparatus.EXPECTED_SCENARIOS_PATH), "measured report matrix digest mismatch")
    require(report.get("exitCode") == 0, "measured report child exit failure")
    require(report.get("validationFailures") == [], "measured report validation failure")
    require(report.get("childReport", {}).get("failures") == [], "measured child report failure")
    require(report.get("childReport", {}).get("scenarios") == apparatus.EXPECTED_SCENARIOS, "measured report scenario mismatch")
    require(report.get("childReport", {}).get("topology") == apparatus.EXPECTED_TOPOLOGIES[candidate], "measured report topology mismatch")
    require(apparatus.validate_raw_report(report) == [], "measured raw report reconstruction failed")
    require(report.get("behaviorFingerprint") == apparatus.behavior_fingerprint(report), "measured behavior fingerprint mismatch")
    frozen = report.get("frozenProtocol") or {}
    require(frozen.get("workloadClass") == record["workload"], "measured report workload mismatch")
    require(frozen.get("instrumentation") == record["instrumentation"], "measured report instrumentation mismatch")
    return report


def compare_reports(records: list[dict[str, Any]], logical_cpu_count: int) -> dict[str, Any]:
    measured = [record for record in records if record["stage"] in {"measured", "replacement"} and record.get("selected") is True]
    require(len(measured) == 160, "analysis requires 160 selected measured runs")
    by_key = {(item["round"], item["workload"], item["candidate"], item["instrumentation"]): read_bound_report(item) for item in measured}
    expected_keys = {
        (round_ordinal, workload, candidate, instrumentation)
        for round_ordinal in range(1, 21)
        for workload in ("normal", "stress")
        for candidate in ("A", "B")
        for instrumentation in ("full", "none")
    }
    require(set(by_key) == expected_keys, "analysis selected-run matrix mismatch")
    metrics = {key: run_metrics(report, logical_cpu_count) for key, report in by_key.items()}
    comparisons: list[dict[str, Any]] = []
    exact_failures: list[str] = []
    accounting: list[dict[str, Any]] = []
    protocol = collection_protocol.load_protocol()
    for workload in ("normal", "stress"):
        for instrumentation in ("full", "none"):
            pairs = [
                (metrics[(round_ordinal, workload, "A", instrumentation)], metrics[(round_ordinal, workload, "B", instrumentation)])
                for round_ordinal in range(1, 21)
            ]
            accounting_keys = sorted(key for key in pairs[0][0] if key.startswith("accounting."))
            for key in accounting_keys:
                if any(left[key] != right[key] for left, right in pairs):
                    exact_failures.append(f"{workload}.{instrumentation}.{key}")
            for round_ordinal, (left, right) in enumerate(pairs, 1):
                accounting.append({
                    "round": round_ordinal,
                    "workload": workload,
                    "instrumentation": instrumentation,
                    "candidateA": {key: left[key] for key in accounting_keys},
                    "candidateB": {key: right[key] for key in accounting_keys},
                })
            metric_names = sorted(set.intersection(*(set(left) & set(right) for left, right in pairs)))
            for metric in metric_names:
                if not performance_metric(metric):
                    continue
                left_values = [left[metric] for left, _ in pairs]
                right_values = [right[metric] for _, right in pairs]
                differences = [right - left for left, right in zip(left_values, right_values)]
                band = max(
                    median_absolute_successive_difference(left_values),
                    median_absolute_successive_difference(right_values),
                )
                metric_seed = protocol["equivalence"]["bootstrapSeed"] + int(hashlib.sha256(f"{workload}.{instrumentation}.{metric}".encode()).hexdigest()[:8], 16)
                lower, upper = bootstrap_interval(differences, metric_seed, protocol["equivalence"]["bootstrapResamples"])
                comparisons.append({
                    "workload": workload,
                    "instrumentation": instrumentation,
                    "metric": metric,
                    "pairedRunCount": len(differences),
                    "medianBMinusA": statistics.median(differences),
                    "repeatabilityNoiseBand": band,
                    "bootstrapConfidenceInterval": [lower, upper],
                    "classification": classify_interval(lower, upper, band),
                })
    overhead: list[dict[str, Any]] = []
    for workload in ("normal", "stress"):
        for candidate in ("A", "B"):
            for metric in sorted(metrics[(1, workload, candidate, "full")]):
                if not metric.startswith(("cpu.", "memory.")):
                    continue
                if metric not in metrics[(1, workload, candidate, "none")]:
                    continue
                differences = [
                    metrics[(round_ordinal, workload, candidate, "full")][metric]
                    - metrics[(round_ordinal, workload, candidate, "none")][metric]
                    for round_ordinal in range(1, 21)
                ]
                overhead.append({
                    "candidate": candidate,
                    "workload": workload,
                    "metric": metric,
                    "pairedRunCount": len(differences),
                    "fullMinusNone": summarize_numbers(differences),
                })
    quality = [
        {
            "round": item["round"],
            "workload": item["workload"],
            "candidate": item["candidate"],
            "instrumentation": item["instrumentation"],
            "stage": item["stage"],
            "failedPollCount": by_key[(item["round"], item["workload"], item["candidate"], item["instrumentation"])]["failedPollCount"],
            "censoredCount": by_key[(item["round"], item["workload"], item["candidate"], item["instrumentation"])]["censoredCount"],
        }
        for item in measured
    ]
    classifications = [item["classification"] for item in comparisons]
    if exact_failures:
        classifications.append("inconclusive")
    return {
        "schemaVersion": 1,
        "status": "analyzed" if not exact_failures else "inconclusive",
        "protocolSha256": protocol_sha256(),
        "availability": apparatus.EXPECTED_AVAILABILITY,
        "exactAccountingFailures": exact_failures,
        "accountingByPairedRun": accounting,
        "comparisons": comparisons,
        "instrumentationOverhead": overhead,
        "runQuality": quality,
        "provisionalSelectionBeforeLifecycleReview": select_candidate(classifications, lifecycle_review_green=False),
    }


def report_record(outcome: GateOutcome, selected: bool) -> dict[str, Any]:
    return {
        "stage": outcome.spec.stage,
        "round": outcome.spec.round_ordinal,
        "workload": outcome.spec.workload,
        "candidate": outcome.spec.candidate,
        "instrumentation": outcome.spec.instrumentation,
        "sequence": outcome.spec.sequence,
        "replacementOrdinal": outcome.spec.replacement_ordinal,
        "selected": selected,
        "replaceable": outcome.replaceable,
        "reportPath": portable_path(outcome.directory / "report.json"),
        "reportSha256": sha256_file(outcome.directory / "report.json"),
    }


def execute_block(
    campaign_dir: Path,
    block: list[RunSpec],
    prepared: dict[str, PreparedCandidate],
    records: list[dict[str, Any]],
    cooldown_seconds: float,
    expected_protocol_sha256: str,
    expected_apparatus_sha256: str,
    expected_matrix_sha256: str,
) -> None:
    outcomes: dict[tuple[str, str], GateOutcome] = {}
    for spec in block:
        outcome = run_gate(
            prepared[spec.candidate],
            spec,
            gate_directory(campaign_dir, spec),
            expected_protocol_sha256,
            expected_apparatus_sha256,
            expected_matrix_sha256,
        )
        outcomes[(spec.candidate, spec.instrumentation)] = outcome
        if cooldown_seconds:
            time.sleep(cooldown_seconds)
    if block[0].stage == "warmup":
        require(not any(outcome.replaceable for outcome in outcomes.values()), "warmup gate lacked required numeric evidence")
        records.extend(report_record(outcome, selected=False) for outcome in outcomes.values())
        return

    maximum = collection_protocol.load_protocol()["missingData"]["maximumReplacementPairedRoundsPerConfiguration"]
    for instrumentation in ("full", "none"):
        pair = [outcomes[(candidate, instrumentation)] for candidate in ("A", "B")]
        if not any(outcome.replaceable for outcome in pair):
            records.extend(report_record(outcome, selected=True) for outcome in pair)
            continue
        records.extend(report_record(outcome, selected=False) for outcome in pair)
        selected = False
        for replacement in range(1, maximum + 1):
            replacement_pair: list[GateOutcome] = []
            for candidate in ("A", "B"):
                original = outcomes[(candidate, instrumentation)].spec
                spec = RunSpec("replacement", original.round_ordinal, original.workload, candidate, instrumentation, 1000 + original.sequence * 10 + replacement, replacement)
                outcome = run_gate(
                    prepared[candidate],
                    spec,
                    gate_directory(campaign_dir, spec),
                    expected_protocol_sha256,
                    expected_apparatus_sha256,
                    expected_matrix_sha256,
                )
                replacement_pair.append(outcome)
                if cooldown_seconds:
                    time.sleep(cooldown_seconds)
            valid = not any(outcome.replaceable for outcome in replacement_pair)
            records.extend(report_record(outcome, selected=valid) for outcome in replacement_pair)
            if valid:
                selected = True
                break
        require(selected, f"replacement limit exhausted for round {block[0].round_ordinal} {block[0].workload} {instrumentation}")


def execute_campaign(args: argparse.Namespace) -> dict[str, Any]:
    require(args.execute_frozen_campaign is True, "comparative execution requires --execute-frozen-campaign")
    protocol = collection_protocol.load_protocol()
    pinned_protocol_sha256 = protocol_sha256()
    pinned_apparatus_sha256 = sha256_file(ROOT / "scripts" / "issue32_apparatus.py")
    pinned_matrix_sha256 = sha256_file(apparatus.EXPECTED_SCENARIOS_PATH)
    controls_path = args.controls.resolve()
    controls = read_report(controls_path)
    validate_control_manifest(controls)
    campaign_dir = args.output_dir.resolve()
    require(not campaign_dir.exists(), f"campaign output already exists: {campaign_dir}")
    for worktree in (args.worktree_a.resolve(), args.worktree_b.resolve()):
        require((worktree / ".git").exists(), f"not a Git worktree: {worktree}")
    campaign_dir.mkdir(parents=True)
    shutil.copy2(collection_protocol.PROTOCOL_PATH, campaign_dir / collection_protocol.PROTOCOL_PATH.name)
    shutil.copy2(Path(__file__), campaign_dir / Path(__file__).name)
    shutil.copy2(ROOT / "scripts" / "issue32_apparatus.py", campaign_dir / "issue32_apparatus.py")
    shutil.copy2(apparatus.EXPECTED_SCENARIOS_PATH, campaign_dir / apparatus.EXPECTED_SCENARIOS_PATH.name)
    shutil.copy2(controls_path, campaign_dir / "control-manifest.json")
    require(sha256_file(campaign_dir / collection_protocol.PROTOCOL_PATH.name) == pinned_protocol_sha256, "retained protocol mismatch")
    require(sha256_file(campaign_dir / Path(__file__).name) == sha256_file(Path(__file__)), "retained collector mismatch")
    require(sha256_file(campaign_dir / "issue32_apparatus.py") == sha256_file(ROOT / "scripts" / "issue32_apparatus.py"), "retained apparatus mismatch")
    require(sha256_file(campaign_dir / apparatus.EXPECTED_SCENARIOS_PATH.name) == sha256_file(apparatus.EXPECTED_SCENARIOS_PATH), "retained matrix mismatch")
    require(sha256_file(campaign_dir / "control-manifest.json") == sha256_file(controls_path), "retained control manifest mismatch")
    state = {
        "schemaVersion": 1,
        "status": "controlsValidated",
        "protocolSha256": pinned_protocol_sha256,
        "collectorSha256": sha256_file(Path(__file__)),
        "apparatusSha256": pinned_apparatus_sha256,
        "expectedScenariosSha256": pinned_matrix_sha256,
        "controlManifestSha256": sha256_file(controls_path),
        "records": [],
        "environmentObservations": [],
    }
    write_json_atomic(campaign_dir / "campaign-state.json", state)
    try:
        probe = compile_environment_probe(campaign_dir)
        prepared = {
            "A": prepare_candidate("A", args.worktree_a.resolve(), campaign_dir),
            "B": prepare_candidate("B", args.worktree_b.resolve(), campaign_dir),
        }
        state["status"] = "artifactsPrepared"
        write_json_atomic(campaign_dir / "campaign-state.json", state)
        warmups, measured = materialize_run_specs(protocol)
        baseline: dict[str, Any] | None = None
        block_ordinal = 0
        for stage, specs in (("warmup", warmups), ("measured", measured)):
            state["status"] = stage
            for block in workload_blocks(specs):
                block_ordinal += 1
                if protocol["environment"]["preBlockStabilizationMilliseconds"]:
                    time.sleep(protocol["environment"]["preBlockStabilizationMilliseconds"] / 1000)
                before = observe_environment(probe, block_ordinal, "before")
                if baseline is None:
                    baseline = before
                validate_environment(before, baseline)
                state["environmentObservations"].append(before)
                execute_block(
                    campaign_dir,
                    block,
                    prepared,
                    state["records"],
                    protocol["environment"]["betweenRunsCooldownMilliseconds"] / 1000,
                    pinned_protocol_sha256,
                    pinned_apparatus_sha256,
                    pinned_matrix_sha256,
                )
                after = observe_environment(probe, block_ordinal, "after")
                validate_environment(after, baseline)
                state["environmentObservations"].append(after)
                write_json_atomic(campaign_dir / "campaign-state.json", state)
        state["status"] = "collected"
        write_json_atomic(campaign_dir / "campaign-state.json", state)
        if baseline is None:
            raise CollectionError("campaign baseline environment is missing")
        analysis = compare_reports(state["records"], baseline["logicalCpuCount"])
        write_json_atomic(campaign_dir / "analysis.json", analysis)
        state["status"] = analysis["status"]
        state["analysisPath"] = portable_path(campaign_dir / "analysis.json")
        write_json_atomic(campaign_dir / "campaign-state.json", state)
        return state
    except Exception as error:
        state["status"] = "inconclusive" if "replacement limit exhausted" in str(error) else "failed"
        state["error"] = str(error).replace(str(ROOT), "<repository>")
        write_json_atomic(campaign_dir / "campaign-state.json", state)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    controls = subparsers.add_parser("validate-controls")
    controls.add_argument("--report", type=Path, action="append", required=True)
    controls.add_argument("--manifest-out", type=Path, required=True)
    collect = subparsers.add_parser("collect")
    collect.add_argument("--execute-frozen-campaign", action="store_true")
    collect.add_argument("--controls", type=Path, required=True)
    collect.add_argument("--worktree-a", type=Path, required=True)
    collect.add_argument("--worktree-b", type=Path, required=True)
    collect.add_argument("--output-dir", type=Path, required=True)
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--campaign-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "validate-controls":
            output = args.manifest_out.resolve()
            require(not output.exists(), f"control manifest already exists: {output}")
            output.parent.mkdir(parents=True, exist_ok=True)
            manifest = control_manifest(args.report)
            write_json_atomic(output, manifest)
            print(json.dumps(manifest, indent=2, sort_keys=True))
            return 0
        if args.command == "analyze":
            campaign_dir = args.campaign_dir.resolve()
            state = read_report(campaign_dir / "campaign-state.json")
            require(state.get("status") in {"collected", "analyzed", "inconclusive"}, "campaign is not ready for analysis")
            require(state.get("protocolSha256") == protocol_sha256(), "campaign protocol digest is stale")
            require(state.get("collectorSha256") == sha256_file(Path(__file__)), "campaign collector digest is stale")
            require(state.get("apparatusSha256") == sha256_file(ROOT / "scripts" / "issue32_apparatus.py"), "campaign apparatus digest is stale")
            require(state.get("expectedScenariosSha256") == sha256_file(apparatus.EXPECTED_SCENARIOS_PATH), "campaign matrix digest is stale")
            observations = state.get("environmentObservations") or []
            require(bool(observations), "campaign environment observations are missing")
            analysis = compare_reports(state["records"], observations[0]["logicalCpuCount"])
            write_json_atomic(campaign_dir / "analysis.json", analysis)
            state["status"] = analysis["status"]
            state["analysisPath"] = portable_path(campaign_dir / "analysis.json")
            write_json_atomic(campaign_dir / "campaign-state.json", state)
            print(json.dumps(analysis, indent=2, sort_keys=True))
            return 0 if analysis["status"] == "analyzed" else 1
        result = execute_campaign(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "analyzed" else 1
    except (CollectionError, apparatus.GateFailure, collection_protocol.ProtocolError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"issue32-collector: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
