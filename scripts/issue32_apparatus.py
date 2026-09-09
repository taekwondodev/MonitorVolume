#!/usr/bin/env python3
"""Candidate-bound offline apparatus gate for issue #32.

This command never compares candidates. It builds and exercises exactly one dirty
candidate worktree, retains every raw poll, and binds the report to the source
closure and executable that produced it.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from typing import Any

TARGET = "ProArtVolumeIssue32Conformance"
EXPECTED_SCENARIOS_PATH = Path(__file__).with_name("issue32_expected_scenarios.json")
COLLECTION_PROTOCOL_PATH = Path(__file__).with_name("issue32_collection_protocol.json")
EXPECTED_CONTRACT = json.loads(EXPECTED_SCENARIOS_PATH.read_text())
EXPECTED_AVAILABILITY = EXPECTED_CONTRACT["availability"]
EXPECTED_SCENARIOS = EXPECTED_CONTRACT["scenarios"]
EXPECTED_TOPOLOGIES = EXPECTED_CONTRACT["topologies"]
SHARED_DRIVER_FILES = (
    "Sources/ProArtVolumeIssue32Conformance/ApparatusScenarios.swift",
    "Sources/ProArtVolumeIssue32Conformance/DeliveryScenarios.swift",
    "Sources/ProArtVolumeIssue32Conformance/FencingScenarios.swift",
    "Sources/ProArtVolumeIssue32Conformance/ScenarioDriver.swift",
)
SOURCE_FILES = (
    "Package.swift",
    "Sources/ProArtVolume/Domain/InputLifecycleDiagnostic.swift",
    "Sources/ProArtVolume/Handler/InputLifecycleDiagnostics.swift",
    "Sources/ProArtVolume/Handler/InputSuspensionBoundary.swift",
    "Sources/ProArtVolume/Handler/MediaKeyBridgeEvent.swift",
    "Sources/ProArtVolume/Handler/MediaKeyEventParser.swift",
    "Sources/ProArtVolume/Handler/MediaKeyInterceptor.swift",
    "Sources/ProArtVolume/Handler/PendingReopenCommand.swift",
    "Sources/ProArtVolume/Handler/PermissionObservationFence.swift",
    "Sources/ProArtVolumeIssue32Conformance/ApparatusScenarios.swift",
    "Sources/ProArtVolumeIssue32Conformance/CandidateBinding.swift",
    "Sources/ProArtVolumeIssue32Conformance/DeliveryScenarios.swift",
    "Sources/ProArtVolumeIssue32Conformance/FencingScenarios.swift",
    "Sources/ProArtVolumeIssue32Conformance/ScenarioDriver.swift",
)
B_ONLY_SOURCE_FILES = (
    "Sources/ProArtVolume/Handler/DedicatedMediaKeyTapOwner.swift",
)
DEPENDENCY_SOURCE_ROOTS = (
    "Sources/MonitorTransport",
    "Sources/ProArtVolumeCore",
)
FROZEN_PROTOCOL = {
    "capacity": 8,
    "candidateProcessTimeoutSeconds": 30,
    "clockSource": "parentObservedPythonMonotonicNanoseconds",
    "cpuSource": "procPidRusageV0CumulativeCpuTimeDeltaOverParentMonotonicInterval",
    "missingDataPolicy": "retainFailedAndCensored;excludeFromNumericSummary",
    "phaseDurationMilliseconds": 40,
    "pollIntervalMilliseconds": 10,
    "releaseConfiguration": True,
    "strictConcurrency": "complete",
    "terminationGraceSeconds": 2,
}


class GateFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def signal_process_group(process: subprocess.Popen[str], signal_number: int) -> None:
    try:
        os.killpg(process.pid, signal_number)
    except ProcessLookupError:
        pass


def terminate_process_group(
    process: subprocess.Popen[str],
    termination_grace_seconds: float,
) -> tuple[str, str]:
    signal_process_group(process, signal.SIGTERM)
    try:
        output = process.communicate(timeout=termination_grace_seconds)
    except subprocess.TimeoutExpired:
        signal_process_group(process, signal.SIGKILL)
        return process.communicate()
    signal_process_group(process, signal.SIGKILL)
    return output


def run_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: float,
    termination_grace_seconds: float,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        terminate_process_group(process, termination_grace_seconds)
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def run_checked(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: float = 300,
) -> str:
    try:
        result = run_process(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            termination_grace_seconds=FROZEN_PROTOCOL["terminationGraceSeconds"],
        )
    except subprocess.TimeoutExpired as error:
        raise GateFailure(f"command timed out after {timeout_seconds}s: {' '.join(command)}") from error
    if result.returncode != 0:
        raise GateFailure(
            f"command failed ({result.returncode}): {' '.join(command)}\n{result.stderr}"
        )
    return result.stdout.strip()


def observe_candidate_process(
    process: subprocess.Popen[str],
    phase_events: Path,
    poll_interval_seconds: float,
    timeout_seconds: float,
    termination_grace_seconds: float,
) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool]:
    samples: list[dict[str, Any]] = []
    observed_boundaries: list[dict[str, Any]] = []
    phase_offset = 0
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    while process.poll() is None:
        phase_offset = observe_phase_events(phase_events, phase_offset, observed_boundaries)
        samples.append(sample_process(process.pid, len(samples)))
        if time.monotonic() >= deadline:
            timed_out = True
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=termination_grace_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            break
        time.sleep(poll_interval_seconds)
    else:
        stdout, stderr = process.communicate()
    observe_phase_events(phase_events, phase_offset, observed_boundaries)
    samples.append(
        {
            "sequence": len(samples),
            "status": "censored",
            "uptimeNanoseconds": time.monotonic_ns(),
            "reason": "candidateProcessTimedOut" if timed_out else "processExitedBeforeNextPoll",
        }
    )
    derive_cpu_intervals(samples)
    return stdout, stderr, samples, observed_boundaries, timed_out


def resolve_executable(
    worktree: Path,
    prepared_executable: Path | None,
    expected_sha256: str | None,
) -> tuple[Path, list[str] | None]:
    expected_path = (worktree / ".build" / "release" / TARGET).resolve()
    if prepared_executable is not None:
        binary = prepared_executable.resolve()
        if binary != expected_path:
            raise GateFailure(f"prepared executable is not the candidate Release product: {binary}")
        if re.fullmatch(r"[0-9a-f]{64}", expected_sha256 or "") is None:
            raise GateFailure("prepared executable requires an exact lowercase SHA-256")
        if not binary.is_file() or sha256_file(binary) != expected_sha256:
            raise GateFailure("prepared executable hash mismatch")
        return binary, None

    if expected_sha256 is not None:
        raise GateFailure("expected executable SHA-256 requires a prepared executable")
    environment = dict(os.environ)
    environment["ISSUE_32_CONFORMANCE"] = "1"
    build_command = [
        "swift", "build", "-c", "release", "-Xswiftc",
        "-strict-concurrency=complete", "--product", TARGET,
    ]
    run_checked(build_command, cwd=worktree, env=environment)
    if not expected_path.is_file():
        raise GateFailure(f"built executable missing: {expected_path}")
    return expected_path, build_command


def source_binding(worktree: Path, candidate: str) -> dict[str, str]:
    files: list[str] = list(SOURCE_FILES + (B_ONLY_SOURCE_FILES if candidate == "B" else ()))
    for relative_root in DEPENDENCY_SOURCE_ROOTS:
        root = worktree / relative_root
        if not root.is_dir():
            raise GateFailure(f"missing source closure directory: {relative_root}")
        files.extend(
            str(path.relative_to(worktree))
            for path in sorted(root.rglob("*"))
            if path.is_file()
        )
    binding: dict[str, str] = {}
    for relative in files:
        path = worktree / relative
        if not path.is_file():
            raise GateFailure(f"missing source closure file: {relative}")
        binding[relative] = sha256_file(path)
    return binding


class RUsageInfoV0(ctypes.Structure):
    _fields_ = [
        ("ri_uuid", ctypes.c_uint8 * 16),
        ("ri_user_time", ctypes.c_uint64),
        ("ri_system_time", ctypes.c_uint64),
        ("ri_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_interrupt_wkups", ctypes.c_uint64),
        ("ri_pageins", ctypes.c_uint64),
        ("ri_wired_size", ctypes.c_uint64),
        ("ri_resident_size", ctypes.c_uint64),
        ("ri_phys_footprint", ctypes.c_uint64),
        ("ri_proc_start_abstime", ctypes.c_uint64),
        ("ri_proc_exit_abstime", ctypes.c_uint64),
    ]


LIBPROC = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
LIBPROC.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(RUsageInfoV0)]
LIBPROC.proc_pid_rusage.restype = ctypes.c_int


def sample_process(pid: int, sequence: int) -> dict[str, Any]:
    timestamp = time.monotonic_ns()
    usage = RUsageInfoV0()
    if LIBPROC.proc_pid_rusage(pid, 0, ctypes.byref(usage)) != 0:
        return {
            "sequence": sequence,
            "status": "failed",
            "uptimeNanoseconds": timestamp,
            "reason": f"procPidRusage:{ctypes.get_errno()}",
        }
    return {
        "sequence": sequence,
        "status": "sampled",
        "uptimeNanoseconds": timestamp,
        "rssBytes": usage.ri_resident_size,
        "cumulativeCpuNanoseconds": usage.ri_user_time + usage.ri_system_time,
        "cpuIntervalStartUptimeNanoseconds": None,
        "intervalCpuPercent": None,
    }


def derive_cpu_intervals(samples: list[dict[str, Any]]) -> None:
    previous: dict[str, Any] | None = None
    for sample in samples:
        if sample.get("status") != "sampled":
            continue
        if previous is not None:
            elapsed = sample["uptimeNanoseconds"] - previous["uptimeNanoseconds"]
            cpu_delta = sample["cumulativeCpuNanoseconds"] - previous["cumulativeCpuNanoseconds"]
            if elapsed > 0 and cpu_delta >= 0:
                sample["cpuIntervalStartUptimeNanoseconds"] = previous["uptimeNanoseconds"]
                sample["intervalCpuPercent"] = cpu_delta * 100 / elapsed
        previous = sample


def observe_phase_events(
    path: Path,
    offset: int,
    observations: list[dict[str, Any]],
) -> int:
    if not path.exists():
        return offset
    with path.open("rb") as handle:
        handle.seek(offset)
        pending = handle.read()
        last_newline = pending.rfind(b"\n")
        if last_newline < 0:
            return offset
        complete = pending[:last_newline]
        for raw_line in complete.splitlines():
            child = json.loads(raw_line)
            observations.append({
                "phase": child["phase"],
                "boundary": child["boundary"],
                "childUptimeNanoseconds": child["uptimeNanoseconds"],
                "uptimeNanoseconds": time.monotonic_ns(),
            })
        return offset + last_newline + 1


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    sampled = [sample for sample in samples if sample.get("status") == "sampled"]
    rss = [sample["rssBytes"] for sample in sampled]
    cpu = [
        sample["intervalCpuPercent"]
        for sample in sampled
        if sample.get("intervalCpuPercent") is not None
    ]
    return {
        "sampleCount": len(sampled),
        "cpuIntervalCount": len(cpu),
        "failedPollCount": sum(sample.get("status") == "failed" for sample in samples),
        "censoredCount": sum(sample.get("status") == "censored" for sample in samples),
        "maximumRssBytes": max(rss) if rss else None,
        "meanRssBytes": statistics.fmean(rss) if rss else None,
        "maximumCpuPercent": max(cpu) if cpu else None,
        "meanCpuPercent": statistics.fmean(cpu) if cpu else None,
    }


def phase_ranges(boundaries: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    starts: dict[str, int] = {}
    ranges: dict[str, tuple[int, int]] = {}
    for boundary in boundaries:
        phase = boundary["phase"]
        if boundary["boundary"] == "start":
            if phase in starts or phase in ranges:
                raise GateFailure(f"duplicate phase start: {phase}")
            starts[phase] = boundary["uptimeNanoseconds"]
        elif boundary["boundary"] == "end":
            if phase not in starts:
                raise GateFailure(f"phase end without start: {phase}")
            start = starts.pop(phase)
            end = boundary["uptimeNanoseconds"]
            if end < start:
                raise GateFailure(f"reversed phase range: {phase}")
            ranges[phase] = (start, end)
        else:
            raise GateFailure(f"unknown boundary: {boundary['boundary']}")
    if starts:
        raise GateFailure(f"unterminated phases: {sorted(starts)}")
    return ranges


def summarize_by_phase(
    samples: list[dict[str, Any]], boundaries: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for phase, (start, end) in phase_ranges(boundaries).items():
        phase_samples = []
        for sample in samples:
            if not start <= sample["uptimeNanoseconds"] <= end:
                continue
            phase_sample = dict(sample)
            interval_start = phase_sample.get("cpuIntervalStartUptimeNanoseconds")
            if interval_start is None or interval_start < start:
                phase_sample["intervalCpuPercent"] = None
            phase_samples.append(phase_sample)
        summaries[phase] = summarize(phase_samples)
    return summaries


def validate_phase_accounting(phases: Any) -> list[str]:
    required = (
        "inputEventCount", "passedThroughEventCount", "deliveredCommandCount",
        "admissionAttempted", "admitted", "rejected", "discarded", "overflow",
        "completed", "peakOutstanding", "pending",
    )
    if not isinstance(phases, list) or not phases:
        return ["phaseAccountingMissing"]
    failures: list[str] = []
    for phase in phases:
        if not isinstance(phase, dict) or any(type(phase.get(field)) is not int for field in required):
            failures.append("phaseAccountingMissing")
            continue
        if any(phase[field] < 0 for field in required):
            failures.append("phaseAccountingNegative")
        if phase["admissionAttempted"] != phase["admitted"] + phase["rejected"]:
            failures.append("phaseAdmissionAccountingMismatch")
        if phase["admitted"] != phase["completed"] + phase["discarded"] + phase["pending"]:
            failures.append("phaseCompletionAccountingMismatch")
        if phase["deliveredCommandCount"] > phase["completed"]:
            failures.append("phaseDeliveryAccountingMismatch")
        if phase["passedThroughEventCount"] > phase["inputEventCount"]:
            failures.append("phasePassThroughAccountingMismatch")
    return sorted(set(failures))


def validate_raw_report(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    samples = report.get("rawSamples")
    if not isinstance(samples, list) or not samples:
        return ["rawSamplesMissing"]
    sequences = [sample.get("sequence") for sample in samples]
    if sequences != list(range(len(samples))):
        failures.append("rawSampleSequenceMismatch")
    if report.get("resourceSummary") != summarize(samples):
        failures.append("resourceSummaryNotReconstructable")
    child = report.get("childReport") or {}
    apparatus = child.get("apparatus") or {}
    boundaries = report.get("observedPhaseBoundaries") or []
    try:
        reconstructed = summarize_by_phase(samples, boundaries)
    except (GateFailure, KeyError, TypeError):
        failures.append("phaseBoundaryInvalid")
    else:
        if report.get("phaseResourceSummaries") != reconstructed:
            failures.append("phaseSummaryNotReconstructable")
    if report.get("failedPollCount") != sum(
        sample.get("status") == "failed" for sample in samples
    ):
        failures.append("failedPollCountMismatch")
    if report.get("censoredCount") != sum(
        sample.get("status") == "censored" for sample in samples
    ):
        failures.append("censoredCountMismatch")
    if apparatus.get("clockSource") != "systemUptimeMonotonicNanoseconds":
        failures.append("childClockSourceMismatch")
    if report.get("resourceClockSource") != FROZEN_PROTOCOL["clockSource"]:
        failures.append("clockSourceMismatch")
    if apparatus.get("capacity") != FROZEN_PROTOCOL["capacity"]:
        failures.append("capacityMismatch")
    if apparatus.get("availability") != EXPECTED_AVAILABILITY:
        failures.append("availabilityMismatch")
    failures.extend(validate_phase_accounting(apparatus.get("phases")))
    workload = apparatus.get("workloadClass")
    if workload not in {"normal", "stress"}:
        failures.append("workloadClassInvalid")
    if any(key not in report for key in (
        "binding", "configurationDigest", "driverSha256",
        "expectedScenariosSha256", "collectionProtocolSha256", "runnerSha256",
    )):
        failures.append("artifactBindingMissing")
    child_boundaries = apparatus.get("phaseBoundaries") or []
    observed_child = [
        {
            "phase": item.get("phase"),
            "boundary": item.get("boundary"),
            "uptimeNanoseconds": item.get("childUptimeNanoseconds"),
        }
        for item in boundaries
    ]
    if observed_child != child_boundaries:
        failures.append("phaseObservationMismatch")
    summaries = report.get("phaseResourceSummaries") or {}
    if summaries and any(summary.get("sampleCount", 0) == 0 for summary in summaries.values()):
        failures.append("phaseWithoutResourceSample")
    if summaries and any(summary.get("cpuIntervalCount", 0) == 0 for summary in summaries.values()):
        failures.append("phaseWithoutCpuInterval")
    return failures


def behavior_fingerprint(report: dict[str, Any]) -> str:
    child = report["childReport"]
    apparatus = child["apparatus"]
    value = {
        "candidate": report["candidate"],
        "sourceRef": report["sourceRef"],
        "scenarioMatrix": child["scenarios"],
        "workloadClass": apparatus["workloadClass"],
        "phases": apparatus["phases"],
        "failures": child["failures"],
    }
    return stable_digest(value)


def validate_control_pair(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if left.get("validationFailures") != [] or right.get("validationFailures") != []:
        failures.append("controlInputGateFailed")
    if left.get("candidate") != right.get("candidate"):
        failures.append("controlCandidateMismatch")
    if left.get("sourceRef") != right.get("sourceRef"):
        failures.append("controlSourceRefMismatch")
    if left.get("configurationDigest") != right.get("configurationDigest"):
        failures.append("controlConfigurationMismatch")
    if behavior_fingerprint(left) != behavior_fingerprint(right):
        failures.append("controlBehaviorMismatch")
    return failures


def validate_instrumentation_pair(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if left.get("validationFailures") != [] or right.get("validationFailures") != []:
        failures.append("instrumentationInputGateFailed")
    if left.get("candidate") != right.get("candidate"):
        failures.append("instrumentationCandidateMismatch")
    if left.get("sourceRef") != right.get("sourceRef"):
        failures.append("instrumentationSourceRefMismatch")
    left_protocol = left.get("frozenProtocol") or {}
    right_protocol = right.get("frozenProtocol") or {}
    if left_protocol.get("workloadClass") != right_protocol.get("workloadClass"):
        failures.append("instrumentationWorkloadMismatch")
    if {left_protocol.get("instrumentation"), right_protocol.get("instrumentation")} != {"full", "none"}:
        failures.append("instrumentationModesIncomplete")
    if behavior_fingerprint(left) != behavior_fingerprint(right):
        failures.append("instrumentationBehaviorMismatch")
    return failures


def gate(args: argparse.Namespace) -> int:
    worktree = args.worktree.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise GateFailure(f"output directory already exists: {output}")
    if not (worktree / ".git").exists():
        raise GateFailure(f"not a Git worktree: {worktree}")
    if re.fullmatch(r"[0-9a-f]{40}", args.source_ref) is None:
        raise GateFailure("source ref must be a full lowercase 40-character Git SHA")
    if args.run_ordinal < 1:
        raise GateFailure("run ordinal must be positive")

    resolved_ref = run_checked(["git", "rev-parse", args.source_ref], cwd=worktree)
    if resolved_ref != args.source_ref:
        raise GateFailure(f"source ref did not resolve exactly: {args.source_ref}")
    expected_topology = EXPECTED_TOPOLOGIES[args.candidate]
    sources = source_binding(worktree, args.candidate)
    driver_sha = stable_digest({path: sources[path] for path in SHARED_DRIVER_FILES})
    compiler = run_checked(["swift", "--version"], cwd=worktree)
    protocol = dict(FROZEN_PROTOCOL)
    protocol.update(
        {
            "candidate": args.candidate,
            "instrumentation": args.instrumentation,
            "runOrdinal": args.run_ordinal,
            "workloadClass": args.workload,
        }
    )
    configuration_digest = stable_digest({
        "collectionProtocolSha256": sha256_file(COLLECTION_PROTOCOL_PATH),
        "gateProtocol": {key: value for key, value in protocol.items() if key != "runOrdinal"},
    })
    output.mkdir(parents=True)
    phase_events = output / "phase-events.jsonl"

    binary, build_command = resolve_executable(
        worktree,
        args.prepared_executable,
        args.expected_executable_sha256,
    )
    if source_binding(worktree, args.candidate) != sources:
        raise GateFailure("candidate source closure changed while preparing the executable")

    command = [
        str(binary),
        "--apparatus", args.workload,
        "--instrumentation", args.instrumentation,
        "--phase-ms", str(FROZEN_PROTOCOL["phaseDurationMilliseconds"]),
        "--phase-events", str(phase_events),
    ]
    process = subprocess.Popen(
        command,
        cwd=worktree,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    interval = FROZEN_PROTOCOL["pollIntervalMilliseconds"] / 1000
    stdout, stderr, samples, observed_boundaries, timed_out = observe_candidate_process(
        process,
        phase_events,
        interval,
        FROZEN_PROTOCOL["candidateProcessTimeoutSeconds"],
        FROZEN_PROTOCOL["terminationGraceSeconds"],
    )
    (output / "raw-samples.jsonl").write_text(
        "".join(json.dumps(sample, sort_keys=True) + "\n" for sample in samples)
    )
    (output / "stdout.json").write_text(stdout)
    (output / "stderr.txt").write_text(stderr)
    if timed_out:
        (output / "timeout.json").write_text(
            json.dumps(
                {
                    "candidateProcessTimeoutSeconds": FROZEN_PROTOCOL["candidateProcessTimeoutSeconds"],
                    "terminationGraceSeconds": FROZEN_PROTOCOL["terminationGraceSeconds"],
                },
                indent=2,
                sort_keys=True,
            ) + "\n"
        )
        raise GateFailure("candidate process timed out")
    try:
        child = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise GateFailure(f"child emitted invalid JSON: {error}") from error
    apparatus = child.get("apparatus") or {}
    retained_executable = output / TARGET
    retained_runner = output / "issue32_apparatus.py"
    retained_matrix = output / EXPECTED_SCENARIOS_PATH.name
    retained_collection_protocol = output / COLLECTION_PROTOCOL_PATH.name
    shutil.copy2(binary, retained_executable)
    shutil.copy2(Path(__file__), retained_runner)
    shutil.copy2(EXPECTED_SCENARIOS_PATH, retained_matrix)
    shutil.copy2(COLLECTION_PROTOCOL_PATH, retained_collection_protocol)
    report = {
        "schemaVersion": 2,
        "candidate": args.candidate,
        "sourceRef": args.source_ref,
        "resolvedSourceRef": resolved_ref,
        "binding": sources,
        "driverSha256": driver_sha,
        "expectedScenariosSha256": sha256_file(retained_matrix),
        "collectionProtocolSha256": sha256_file(retained_collection_protocol),
        "runnerSha256": sha256_file(retained_runner),
        "configurationDigest": configuration_digest,
        "compiler": compiler,
        "buildCommand": build_command,
        "executable": {"path": str(retained_executable), "sha256": sha256_file(retained_executable)},
        "builtExecutablePath": str(binary),
        "command": command,
        "frozenProtocol": protocol,
        "exitCode": process.returncode,
        "stdoutSha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "stderrSha256": hashlib.sha256(stderr.encode()).hexdigest(),
        "childReport": child,
        "resourceClockSource": FROZEN_PROTOCOL["clockSource"],
        "rawSamples": samples,
        "observedPhaseBoundaries": observed_boundaries,
        "resourceSummary": summarize(samples),
        "phaseResourceSummaries": summarize_by_phase(
            samples, observed_boundaries
        ),
        "failedPollCount": sum(sample["status"] == "failed" for sample in samples),
        "censoredCount": sum(sample["status"] == "censored" for sample in samples),
    }
    failures = validate_raw_report(report)
    if process.returncode != 0:
        failures.append("childExitFailure")
    if child.get("failures") != []:
        failures.append("childReportedFailure")
    if child.get("scenarios") != EXPECTED_SCENARIOS:
        failures.append("scenarioMatrixMismatch")
    if child.get("topology") != expected_topology:
        failures.append("candidateTopologyMismatch")
    if apparatus.get("instrumentation") != args.instrumentation:
        failures.append("instrumentationMismatch")
    if args.instrumentation == "full" and not apparatus.get("events"):
        failures.append("fullInstrumentationMissing")
    if args.instrumentation == "none" and apparatus.get("events") != []:
        failures.append("noneInstrumentationNotEmpty")
    report["validationFailures"] = sorted(set(failures))
    report["behaviorFingerprint"] = behavior_fingerprint(report)

    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output / "binding.json").write_text(
        json.dumps(
            {
                "candidate": args.candidate,
                "sourceRef": args.source_ref,
                "resolvedSourceRef": resolved_ref,
                "sourceClosure": sources,
                "driverSha256": driver_sha,
                "expectedScenariosSha256": report["expectedScenariosSha256"],
                "collectionProtocolSha256": report["collectionProtocolSha256"],
                "runnerSha256": report["runnerSha256"],
                "configurationDigest": configuration_digest,
                "executable": report["executable"],
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
    )
    if failures:
        raise GateFailure("apparatus validation failed: " + ", ".join(sorted(set(failures))))
    return 0


def control(args: argparse.Namespace) -> int:
    left = json.loads(args.left.read_text())
    right = json.loads(args.right.read_text())
    failures = (
        validate_control_pair(left, right)
        if args.mode == "repeatability"
        else validate_instrumentation_pair(left, right)
    )
    print(json.dumps({"failures": failures}, indent=2, sort_keys=True))
    return 1 if failures else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    gate_parser = subparsers.add_parser("gate")
    gate_parser.add_argument("--candidate", choices=("A", "B"), required=True)
    gate_parser.add_argument("--worktree", type=Path, required=True)
    gate_parser.add_argument("--source-ref", required=True)
    gate_parser.add_argument("--output-dir", type=Path, required=True)
    gate_parser.add_argument("--workload", choices=("normal", "stress"), required=True)
    gate_parser.add_argument("--instrumentation", choices=("full", "none"), required=True)
    gate_parser.add_argument("--run-ordinal", type=int, required=True)
    gate_parser.add_argument("--prepared-executable", type=Path)
    gate_parser.add_argument("--expected-executable-sha256")
    gate_parser.set_defaults(handler=gate)
    control_parser = subparsers.add_parser("control")
    control_parser.add_argument("--mode", choices=("repeatability", "instrumentation"), required=True)
    control_parser.add_argument("--left", type=Path, required=True)
    control_parser.add_argument("--right", type=Path, required=True)
    control_parser.set_defaults(handler=control)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return args.handler(args)
    except (GateFailure, OSError, KeyError, TypeError, ValueError) as error:
        output = getattr(args, "output_dir", None)
        if isinstance(output, Path) and output.is_dir():
            (output / "gate-error.txt").write_text(f"{error}\n")
        print(f"issue32-apparatus: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
