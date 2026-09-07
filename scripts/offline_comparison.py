#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / ".build" / "release" / "ProArtVolumeOfflineHarness"
EVIDENCE_ROOT = ROOT / ".hermes" / "verification" / "evidence"
RUNNER_SCHEMA_VERSION = 1
CONTRACT_NAME = "shared-suspension-v1"
DEFAULT_WORKLOAD_MS = 1_200
DEFAULT_INTERVAL_MS = 20
WINDOWS_MS = {
    "activeIdle": (0, 200),
    "burst": (200, 500),
    "suspended": (500, 700),
    "postBurstRetention": (700, 900),
    "postSuspensionRetention": (900, 1_100),
}
REQUIRED_SCENARIOS = {
    "intent_semantics": {
        "upper_boundary",
        "lower_boundary",
        "rapid_steps",
        "mute_parity",
        "boundary_unmute",
        "fresh_seed",
    },
    "accepted_input": {"ordered_consumer", "service_outcome"},
    "service_recovery": {
        "revalidation_started",
        "failure_is_unavailable",
        "existing_backoff",
        "recovery_reseeds",
        "no_write_during_read_recovery",
    },
    "failed_write_recovery": {
        "admitted",
        "failure_is_unavailable",
        "existing_backoff",
        "recovery_reseeds",
        "failed_command_not_replayed",
    },
    "suspension": {
        "pending_discarded",
        "rejected_pass_through",
        "grant_does_not_clear",
        "external_results_latched",
        "explicit_reopen",
    },
    "sleep_wake": {
        "sleep_pass_through",
        "active_wake_revalidates",
        "fresh_hardware_after_wake",
        "suspended_wake_stays_suspended",
    },
    "overflow": {
        "capacity_two",
        "next_passes",
        "latched",
        "queue_discarded",
        "no_wait_for_capacity",
    },
    "stale_delivery": {
        "admitted",
        "session_rejected",
        "no_intent_or_osd",
        "bookkeeping_completed",
    },
}
REQUIRED_FRAMEWORK_TIMINGS = {
    "event_to_callback",
    "callback_entry_exit",
    "osd_first_draw",
    "timeout_and_tap_release",
}
EVENT_TIMESTAMP_RULE = "monotonic nonnegative process-uptime timestamps; no callback-duration SLA"


class OfflineReportError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OfflineReportError(f"Invalid offline evidence: {message}")


def resolve_report_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def portable_executable_binding(binding: Dict[str, Any]) -> Dict[str, Any]:
    return {"path": display_path(Path(binding["path"])), "sha256": binding["sha256"]}


def portable_error(error: Exception) -> str:
    return str(error).replace(str(ROOT), "<repository>")


def clear_runner_evidence(evidence_directory: Path) -> None:
    for pattern in ("*.json", "*.stdout", "*.stderr"):
        for path in evidence_directory.glob(pattern):
            try:
                path.unlink()
            except OSError as error:
                raise OfflineReportError(f"Cannot clear runner evidence: {path}") from error


def sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise OfflineReportError(f"Executable artifact is unreadable: {path}") from error


def logical_cpu_count() -> int:
    result = subprocess.run(
        ["sysctl", "-n", "hw.logicalcpu"],
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        try:
            count = int(result.stdout.strip())
            if count > 0:
                return count
        except ValueError:
            pass
    fallback = os.cpu_count()
    if fallback is None or fallback <= 0:
        raise OfflineReportError("Logical CPU count is unavailable")
    return fallback


def build_release() -> Path:
    result = subprocess.run(
        [
            "swift",
            "build",
            "--product",
            "ProArtVolumeOfflineHarness",
            "-c",
            "release",
            "-Xswiftc",
            "-strict-concurrency=complete",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise OfflineReportError(f"Offline Release build failed: {detail}")
    if not HARNESS.is_file() or not os.access(HARNESS, os.X_OK):
        raise OfflineReportError(f"Offline Release executable is missing: {HARNESS}")
    return HARNESS.resolve()


def process_sample(pid: int, elapsed_ms: int) -> Optional[Dict[str, Any]]:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "pcpu=,rss=,state="],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    fields = result.stdout.strip().split()
    if len(fields) < 2:
        return None
    try:
        cpu = float(fields[0])
        resident = int(fields[1])
    except ValueError:
        return None
    return {
        "elapsedMilliseconds": max(0, elapsed_ms),
        "cpuPercent": cpu,
        "residentSetSizeKiB": resident,
    }


def sample_process(process: subprocess.Popen, interval_ms: int) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    started = time.monotonic()
    while process.poll() is None:
        elapsed_ms = int((time.monotonic() - started) * 1_000)
        sample = process_sample(process.pid, elapsed_ms)
        if sample is not None:
            samples.append(sample)
        time.sleep(interval_ms / 1_000)
    return samples


def numeric_summary(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        return {"count": 0, "minimum": None, "average": None, "maximum": None}
    return {
        "count": len(values),
        "minimum": round(min(values), 3),
        "average": round(sum(values) / len(values), 3),
        "maximum": round(max(values), 3),
    }


def summarize_resources(samples: List[Dict[str, Any]], interval_ms: int) -> Dict[str, Any]:
    cpus = logical_cpu_count()
    normalized = [sample["cpuPercent"] / cpus for sample in samples]
    cpu_values = [sample["cpuPercent"] for sample in samples]
    resident = [sample["residentSetSizeKiB"] for sample in samples]
    windows: Dict[str, Any] = {}
    for name, (start_ms, end_ms) in WINDOWS_MS.items():
        selected = [
            sample for sample in samples
            if start_ms <= sample["elapsedMilliseconds"] < end_ms
        ]
        window_cpu = [sample["cpuPercent"] for sample in selected]
        window_normalized = [sample["cpuPercent"] / cpus for sample in selected]
        window_ram = [sample["residentSetSizeKiB"] for sample in selected]
        windows[name] = {
            "boundsMilliseconds": [start_ms, end_ms],
            "sampleCount": len(selected),
            "cpu": numeric_summary(window_cpu),
            "normalizedCpu": numeric_summary(window_normalized),
            "residentSetSizeKiB": numeric_summary(window_ram),
        }
    active_idle_start, active_idle_end = WINDOWS_MS["activeIdle"]
    baseline_samples = [
        sample["residentSetSizeKiB"]
        for sample in samples
        if active_idle_start <= sample["elapsedMilliseconds"] < active_idle_end
    ]
    baseline = baseline_samples[-1] if baseline_samples else (resident[0] if resident else None)
    peak = max(resident) if resident else None
    return {
        "sampling": {
            "method": "ps",
            "intervalMilliseconds": interval_ms,
            "logicalCPUCount": cpus,
            "cpuMeasure": "ps_pcpu_percent",
            "cpuNormalization": "ps_percent_divided_by_logical_cpu",
            "ramMeasure": "resident_set_size_kib",
            "windowsMilliseconds": {
                name: [start, end] for name, (start, end) in WINDOWS_MS.items()
            },
        },
        "sampleCount": len(samples),
        "cpu": {
            "rawPercent": numeric_summary(cpu_values),
            "normalizedPercent": numeric_summary(normalized),
        },
        "ram": {
            "measure": "resident_set_size_kib",
            "baselineKiB": baseline,
            "peakKiB": peak,
            "peakIncreaseKiB": None if baseline is None or peak is None else peak - baseline,
        },
        "windows": windows,
        "wakeupsAndResources": {
            "status": "unavailable",
            "reason": "The portable offline sampler exposes CPU and resident memory through ps; native wakeup and resource counters require a later runtime campaign.",
        },
    }


def protocol_from_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    configuration = contract.get("configuration")
    require(isinstance(configuration, dict), "missing common configuration")
    fields = (
        "capacitySelectionProcedure",
        "comparisonProcedure",
        "repeatabilityCriteria",
        "instrumentationMode",
        "workload",
        "workloadClassification",
        "eventTimestampRule",
    )
    protocol = {field: configuration.get(field) for field in fields}
    protocol.update({
        "contract": configuration.get("contract"),
        "capacity": configuration.get("capacity"),
        "samplingIntervalMilliseconds": configuration.get("samplingIntervalMilliseconds"),
        "observationWindowsMilliseconds": configuration.get("observationWindowsMilliseconds"),
        "cpuNormalization": configuration.get("cpuNormalization"),
        "ramMeasure": configuration.get("ramMeasure"),
        "noProductLatencySLA": True,
    })
    return protocol


def validate_contract_report(
    contract: Any,
    executable: Path,
    instrumentation: str,
    resource_state: str,
) -> None:
    require(isinstance(contract, dict), "missing Swift contract report")
    require(contract.get("status") == "passed", "Swift contract scenarios did not pass")
    require(contract.get("executionClass") == "offline_common_contract", "wrong execution class")
    require(contract.get("instrumentation") == instrumentation, "instrumentation mode disagrees with the command")
    require(contract.get("resourceState") == resource_state, "resource state disagrees with the command")
    require(contract.get("workloadPhase") == ("eligible" if resource_state == "active" else "suspended"), "workload lifecycle state disagrees with the command")
    binding = contract.get("executable")
    require(isinstance(binding, dict), "missing executable binding")
    require(resolve_report_path(str(binding.get("path", ""))).resolve() == executable.resolve(), "Swift report identifies another executable")
    require(binding.get("sha256") == sha256(executable), "Swift report hash does not match the executable")

    configuration = contract.get("configuration")
    require(isinstance(configuration, dict), "missing contract configuration")
    require(configuration.get("schemaVersion") == 1, "unsupported contract configuration schema")
    require(configuration.get("contract") == CONTRACT_NAME, "wrong shared contract")
    require(configuration.get("capacity") == 2, "capacity is not frozen at the declared fixture value")
    require(configuration.get("permissionPollIntervalMilliseconds") == 1_000, "permission polling interval is not frozen")
    require(
        configuration.get("permissionPollingRule") == "poll only while the lifecycle is active, outside framework callbacks; stop in suspension and sleep",
        "permission polling is not active-only",
    )
    require(
        configuration.get("tapTeardownRule") == "reopen waits for the prior owner to release its tap and key pairing; no callback or MainActor wait",
        "tap teardown rule is missing",
    )
    require(configuration.get("samplingIntervalMilliseconds") == DEFAULT_INTERVAL_MS, "sampling interval is not frozen")
    require(configuration.get("cpuNormalization") == "ps_percent_divided_by_logical_cpu", "CPU normalization is not declared")
    require(configuration.get("ramMeasure") == "resident_set_size_kib", "RAM measure is not declared")
    require(configuration.get("eventTimestampRule") == EVENT_TIMESTAMP_RULE, "event timestamp rule is not declared")
    windows = configuration.get("observationWindowsMilliseconds")
    require(windows == {name: end - start for name, (start, end) in WINDOWS_MS.items()}, "observation windows are not the common fixture")
    for field in (
        "workload",
        "workloadClassification",
        "capacitySelectionProcedure",
        "comparisonProcedure",
        "repeatabilityCriteria",
    ):
        require(isinstance(configuration.get(field), str) and configuration[field], f"missing protocol field: {field}")
    require(configuration.get("instrumentationMode") == instrumentation, "configuration instrumentation disagrees")

    scenarios = contract.get("scenarios")
    require(isinstance(scenarios, list), "missing scenarios")
    by_name: Dict[str, Dict[str, Any]] = {}
    for scenario in scenarios:
        require(isinstance(scenario, dict), "invalid scenario")
        name = scenario.get("name")
        require(isinstance(name, str) and name not in by_name, "duplicate or invalid scenario name")
        require(scenario.get("passed") is True, f"scenario did not pass: {name}")
        checks = scenario.get("checks")
        require(isinstance(checks, dict), f"missing scenario checks: {name}")
        require(all(value is True for value in checks.values()), f"false scenario check: {name}")
        by_name[name] = scenario
    require(set(by_name) == set(REQUIRED_SCENARIOS), "scenario set does not cover the common contract")
    for name, required_checks in REQUIRED_SCENARIOS.items():
        require(required_checks.issubset(by_name[name]["checks"]), f"scenario is missing checks: {name}")

    admission = contract.get("admission")
    require(isinstance(admission, dict), "missing admission evidence")
    integer_fields = (
        "attempted",
        "admitted",
        "rejected",
        "discarded",
        "overflow",
        "completed",
        "peakOutstanding",
        "maximumDeliveryWaitNanoseconds",
    )
    for field in integer_fields:
        require(type(admission.get(field)) is int and admission[field] >= 0, f"invalid admission field: {field}")
    require(admission["attempted"] >= admission["admitted"], "admitted work exceeds attempts")
    require(admission["peakOutstanding"] <= configuration["capacity"], "fixture exceeded capacity")
    require(admission["overflow"] >= 1, "overflow was not exercised")
    require(admission["discarded"] >= 1, "discarded work was not recorded")
    require(admission["completed"] <= admission["admitted"], "completed work exceeds admitted work")
    require(admission["admitted"] == admission["completed"] + admission["discarded"], "admission ledger is not conserved")

    framework_timings = contract.get("frameworkTimings")
    require(isinstance(framework_timings, dict), "missing framework timing coverage")
    require(set(framework_timings) == REQUIRED_FRAMEWORK_TIMINGS, "framework timing coverage is incomplete")
    for name, timing in framework_timings.items():
        require(isinstance(timing, dict), f"invalid framework timing: {name}")
        require(timing.get("status") in ("unavailable", "modeled"), f"framework timing is overstated: {name}")
        require(isinstance(timing.get("reason"), str) and timing["reason"], f"framework timing lacks a reason: {name}")

    resource_contract = contract.get("resourceContract")
    require(isinstance(resource_contract, dict), "missing Swift resource contract")
    require(resource_contract.get("samplingIntervalMilliseconds") == DEFAULT_INTERVAL_MS, "Swift resource interval is not frozen")
    require(resource_contract.get("samplingMethod") == "parent samples ps pcpu/rss every declared interval while this Release harness runs", "Swift resource sampler is not declared")
    wakeup_metric = resource_contract.get("wakeupMetric")
    thread_metric = resource_contract.get("threadAndTapMetric")
    require(isinstance(wakeup_metric, dict) and wakeup_metric.get("status") == "unavailable", "Swift wakeup coverage is overstated")
    require(isinstance(thread_metric, dict) and thread_metric.get("status") == "modeled", "Swift thread/tap coverage is overstated")
    require(isinstance(resource_contract.get("instrumentationOverhead"), str) and resource_contract["instrumentationOverhead"], "Swift overhead procedure is missing")
    for field, window_name in (
        ("activeIdleWindowMilliseconds", "activeIdle"),
        ("burstWindowMilliseconds", "burst"),
        ("suspendedWindowMilliseconds", "suspended"),
        ("postBurstRetentionWindowMilliseconds", "postBurstRetention"),
        ("postSuspensionRetentionWindowMilliseconds", "postSuspensionRetention"),
    ):
        start, end = WINDOWS_MS[window_name]
        require(resource_contract.get(field) == end - start, f"Swift resource window is not frozen: {field}")
    readiness = contract.get("liveReadiness")
    require(isinstance(readiness, list) and bool(readiness) and all(isinstance(item, str) and item for item in readiness), "live proof gaps are missing")

    events = contract.get("events")
    require(isinstance(events, list), "missing event collection")
    if instrumentation == "full":
        require(events, "full instrumentation produced no events")
        sequences = [event.get("sequence") for event in events if isinstance(event, dict)]
        require(sequences == list(range(1, len(events) + 1)), "event sequence is not contiguous")
        timestamps = [event.get("timestampNanoseconds") for event in events if isinstance(event, dict)]
        require(all(type(value) is int and value >= 0 for value in timestamps), "event timestamp is invalid")
        require(timestamps == sorted(timestamps), "event timestamps are not monotonic")
        require(any(event.get("accepted") is False for event in events if isinstance(event, dict)), "rejected work is not recorded")
        require(any(event.get("discarded") is True for event in events if isinstance(event, dict)), "discarded work is not recorded")
    else:
        require(events == [], "instrumentation-none run emitted full event records")


def validate_resource_report(resource: Any, interval_ms: int) -> None:
    require(isinstance(resource, dict), "missing resource report")
    sampling = resource.get("sampling")
    require(isinstance(sampling, dict), "missing resource sampling declaration")
    require(sampling.get("method") == "ps", "unexpected resource sampling method")
    require(sampling.get("intervalMilliseconds") == interval_ms, "resource interval disagrees")
    require(type(sampling.get("logicalCPUCount")) is int and sampling["logicalCPUCount"] > 0, "invalid logical CPU count")
    require(sampling.get("cpuNormalization") == "ps_percent_divided_by_logical_cpu", "resource normalization disagrees")
    require(sampling.get("ramMeasure") == "resident_set_size_kib", "resource RAM measure disagrees")
    require(sampling.get("windowsMilliseconds") == {
        name: [start, end] for name, (start, end) in WINDOWS_MS.items()
    }, "resource windows disagree")
    require(type(resource.get("sampleCount")) is int and resource["sampleCount"] > 0, "no process samples were captured")
    cpu = resource.get("cpu")
    require(isinstance(cpu, dict), "missing CPU resource summary")
    raw = cpu.get("rawPercent")
    normalized = cpu.get("normalizedPercent")
    for summary in (raw, normalized):
        require(isinstance(summary, dict), "invalid CPU summary")
        require(summary.get("count") == resource["sampleCount"], "CPU summary count disagrees")
        require(summary.get("average") is not None and summary.get("maximum") is not None, "CPU summary is empty")
        require(summary["maximum"] >= summary["average"], "CPU peak is below average")
    ram = resource.get("ram")
    require(isinstance(ram, dict), "missing RAM resource summary")
    require(ram.get("measure") == "resident_set_size_kib", "RAM measure is missing")
    require(type(ram.get("baselineKiB")) is int and ram["baselineKiB"] >= 0, "invalid RAM baseline")
    require(type(ram.get("peakKiB")) is int and ram["peakKiB"] >= ram["baselineKiB"], "invalid RAM peak")
    windows = resource.get("windows")
    require(isinstance(windows, dict) and set(windows) == set(WINDOWS_MS), "resource windows are incomplete")
    for name, window in windows.items():
        require(isinstance(window, dict), f"invalid resource window: {name}")
        require(window.get("boundsMilliseconds") == list(WINDOWS_MS[name]), f"invalid resource window bounds: {name}")
        require(type(window.get("sampleCount")) is int and window["sampleCount"] > 0, f"invalid resource window count: {name}")
    unavailable = resource.get("wakeupsAndResources")
    require(isinstance(unavailable, dict), "missing wakeup/resource coverage")
    require(unavailable.get("status") == "unavailable", "offline run overstated wakeup/resource coverage")
    require(isinstance(unavailable.get("reason"), str) and unavailable["reason"], "wakeup/resource gap lacks a reason")


def validate_offline_report(report: Any, executable: Path) -> None:
    require(isinstance(report, dict), "report is not an object")
    require(report.get("schemaVersion") == RUNNER_SCHEMA_VERSION, "unsupported runner schema")
    require(report.get("status") == "passed", "offline run did not pass")
    require(report.get("failures") == [], "offline run contains failures")
    require(report.get("executionClass") == "offline_common_contract", "wrong runner execution class")
    instrumentation = report.get("instrumentation")
    resource_state = report.get("resourceState")
    require(instrumentation in ("full", "none"), "invalid instrumentation mode")
    require(resource_state in ("active", "suspended"), "invalid resource state")
    binding = report.get("executable")
    require(isinstance(binding, dict), "missing runner executable binding")
    require(resolve_report_path(str(binding.get("path", ""))).resolve() == executable.resolve(), "runner executable path is not exact")
    require(binding.get("sha256") == sha256(executable), "runner executable hash is stale")
    require(type(report.get("workloadMilliseconds")) is int and report["workloadMilliseconds"] >= 1_100, "workload does not cover the declared windows")
    require(type(report.get("processDurationMilliseconds")) is int and report["processDurationMilliseconds"] >= report["workloadMilliseconds"], "process ended before the declared workload")
    validate_contract_report(report.get("contractReport"), executable, instrumentation, resource_state)
    validate_resource_report(report.get("resource"), DEFAULT_INTERVAL_MS)
    protocol = report.get("protocol")
    require(protocol == protocol_from_contract(report["contractReport"]), "runner protocol is not copied from the common contract")


def run_once(
    executable: Path,
    instrumentation: str,
    resource_state: str,
    workload_ms: int,
    interval_ms: int,
    evidence_directory: Path,
) -> Dict[str, Any]:
    stdout_path = evidence_directory / f"{instrumentation}-{resource_state}.stdout"
    stderr_path = evidence_directory / f"{instrumentation}-{resource_state}.stderr"
    started = time.monotonic()
    process = subprocess.Popen(
        [
            str(executable),
            "--workload-ms",
            str(workload_ms),
            "--instrumentation",
            instrumentation,
            "--resource-state",
            resource_state,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    samples = sample_process(process, interval_ms)
    stdout, stderr = process.communicate()
    process_duration_ms = int((time.monotonic() - started) * 1_000)
    stdout_path.write_text(stdout)
    stderr_path.write_text(stderr)
    try:
        contract = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise OfflineReportError(f"Offline harness returned invalid JSON: {stderr.strip() or error}") from error
    resource = summarize_resources(samples, interval_ms)
    binding_hash = sha256(executable)
    report: Dict[str, Any] = {
        "schemaVersion": RUNNER_SCHEMA_VERSION,
        "status": "failed",
        "executionClass": "offline_common_contract",
        "instrumentation": instrumentation,
        "resourceState": resource_state,
        "executable": {"path": str(executable), "sha256": binding_hash},
        "contractReport": contract,
        "resource": resource,
        "protocol": protocol_from_contract(contract),
        "workloadMilliseconds": workload_ms,
        "processDurationMilliseconds": process_duration_ms,
        "evidence": {"stdout": display_path(stdout_path), "stderr": display_path(stderr_path)},
        "failures": [],
    }
    if isinstance(report["contractReport"].get("executable"), dict):
        report["contractReport"]["executable"] = portable_executable_binding(report["contractReport"]["executable"])
    report["executable"] = portable_executable_binding(report["executable"])
    if process.returncode != 0:
        report["failures"].append(f"offline executable exited with status {process.returncode}")
    try:
        require(process.returncode == 0, "offline executable exited unsuccessfully")
        validate_offline_report({**report, "status": "passed"}, executable)
    except OfflineReportError as error:
        report["failures"].append(portable_error(error))
    else:
        if not report["failures"]:
            report["status"] = "passed"
    report_path = evidence_directory / f"{instrumentation}-{resource_state}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def comparison_protocol() -> Dict[str, Any]:
    return {
        "candidateSet": ["common_contract"],
        "instrumentationPair": ["full", "none"],
        "resourceStates": ["active", "suspended"],
        "runOrder": "alternate equal Release runs; this suite executes full-active, none-active, full-suspended",
        "capacityFrozenBeforeComparison": True,
        "productLatencySLA": None,
        "interpretation": "offline common-contract evidence, not installed-app performance or native framework timing",
    }


def observed_overhead(full_active: Dict[str, Any], none_active: Dict[str, Any]) -> Dict[str, Any]:
    full_cpu = full_active["resource"]["cpu"]
    none_cpu = none_active["resource"]["cpu"]
    full_ram = full_active["resource"]["ram"]
    none_ram = none_active["resource"]["ram"]
    full_average = full_cpu["normalizedPercent"]["average"]
    none_average = none_cpu["normalizedPercent"]["average"]
    full_peak = full_cpu["normalizedPercent"]["maximum"]
    none_peak = none_cpu["normalizedPercent"]["maximum"]
    return {
        "status": "descriptive",
        "pairedRuns": ["full-active", "none-active"],
        "cpu": {
            "fullNormalizedAveragePercent": full_average,
            "noneNormalizedAveragePercent": none_average,
            "deltaNormalizedAveragePercent": round(full_average - none_average, 3),
            "fullNormalizedPeakPercent": full_peak,
            "noneNormalizedPeakPercent": none_peak,
            "deltaNormalizedPeakPercent": round(full_peak - none_peak, 3),
        },
        "ram": {
            "fullPeakKiB": full_ram["peakKiB"],
            "nonePeakKiB": none_ram["peakKiB"],
            "deltaPeakKiB": full_ram["peakKiB"] - none_ram["peakKiB"],
        },
        "interpretation": "Descriptive observations only; repeatability and candidate runtime evidence are required before a performance conclusion.",
    }


def validate_comparison_report(report: Any, executable: Path) -> None:
    require(isinstance(report, dict), "comparison report is not an object")
    require(report.get("schemaVersion") == RUNNER_SCHEMA_VERSION, "unsupported comparison schema")
    require(report.get("status") == "passed", "offline comparison did not pass")
    require(report.get("failures") == [], "offline comparison contains failures")
    require(report.get("executionClass") == "offline_comparison", "wrong comparison execution class")
    require(report.get("contract") == CONTRACT_NAME, "comparison contract is missing")
    require(report.get("protocol") == comparison_protocol(), "comparison protocol is not frozen")
    binding = report.get("executable")
    require(isinstance(binding, dict), "comparison executable binding is missing")
    require(resolve_report_path(str(binding.get("path", ""))).resolve() == executable.resolve(), "comparison executable path is stale")
    require(binding.get("sha256") == sha256(executable), "comparison executable hash is stale")
    runs = report.get("runs")
    require(isinstance(runs, list) and len(runs) == 3, "comparison must contain three declared runs")
    modes = {(run.get("instrumentation"), run.get("resourceState")) for run in runs if isinstance(run, dict)}
    require(modes == {("full", "active"), ("none", "active"), ("full", "suspended")}, "comparison run matrix is incomplete")
    hashes = set()
    paths = set()
    for run in runs:
        validate_offline_report(run, executable)
        hashes.add(run["executable"]["sha256"])
        paths.add(run["executable"]["path"])
    require(len(hashes) == 1 and len(paths) == 1, "comparison runs are not bound to one Release artifact")
    full_active = next(run for run in runs if run["instrumentation"] == "full" and run["resourceState"] == "active")
    none_active = next(run for run in runs if run["instrumentation"] == "none" and run["resourceState"] == "active")
    require(full_active["workloadMilliseconds"] == none_active["workloadMilliseconds"], "overhead runs use different workloads")
    overhead = report.get("overhead")
    require(isinstance(overhead, dict), "comparison overhead summary is missing")
    require(overhead.get("status") == "descriptive", "comparison overhead is overstated")
    require(overhead.get("pairedRuns") == ["full-active", "none-active"], "overhead runs are not paired")
    require(isinstance(overhead.get("interpretation"), str) and overhead["interpretation"], "overhead interpretation is missing")
    require(overhead == observed_overhead(full_active, none_active), "comparison overhead does not match paired runs")
    for section in (overhead.get("cpu"), overhead.get("ram")):
        require(isinstance(section, dict), "comparison overhead section is invalid")
        for value in section.values():
            require(type(value) in (int, float), "comparison overhead contains a non-numeric value")


def run_suite(workload_ms: int, interval_ms: int, evidence_directory: Path) -> Dict[str, Any]:
    require(interval_ms == DEFAULT_INTERVAL_MS, "the common comparison freezes a 20ms sampler")
    executable = build_release()
    runs = [
        run_once(executable, "full", "active", workload_ms, interval_ms, evidence_directory),
        run_once(executable, "none", "active", workload_ms, interval_ms, evidence_directory),
        run_once(executable, "full", "suspended", workload_ms, interval_ms, evidence_directory),
    ]
    report: Dict[str, Any] = {
        "schemaVersion": RUNNER_SCHEMA_VERSION,
        "status": "failed",
        "executionClass": "offline_comparison",
        "contract": CONTRACT_NAME,
        "protocol": comparison_protocol(),
        "executable": portable_executable_binding({"path": str(executable), "sha256": sha256(executable)}),
        "runs": runs,
        "overhead": observed_overhead(runs[0], runs[1]),
        "evidenceDirectory": display_path(evidence_directory),
        "failures": [],
    }
    try:
        validate_comparison_report({**report, "status": "passed"}, executable)
    except OfflineReportError as error:
        report["failures"].append(portable_error(error))
    else:
        report["status"] = "passed"
    (evidence_directory / "comparison.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run", "compare"))
    parser.add_argument("--instrumentation", choices=("full", "none"), default="full")
    parser.add_argument("--resource-state", choices=("active", "suspended"), default="active")
    parser.add_argument("--workload-ms", type=int, default=DEFAULT_WORKLOAD_MS)
    parser.add_argument("--interval-ms", type=int, default=DEFAULT_INTERVAL_MS)
    arguments = parser.parse_args()
    if arguments.workload_ms < 1_100:
        emit({"status": "failed", "error": "workload must cover the declared 1,100ms observation windows"})
        return 1
    evidence_directory = EVIDENCE_ROOT / "offline-contract"
    evidence_directory.mkdir(parents=True, exist_ok=True)
    try:
        clear_runner_evidence(evidence_directory)
        if arguments.command == "run":
            executable = build_release()
            report = run_once(
                executable,
                arguments.instrumentation,
                arguments.resource_state,
                arguments.workload_ms,
                arguments.interval_ms,
                evidence_directory,
            )
        else:
            report = run_suite(arguments.workload_ms, arguments.interval_ms, evidence_directory)
        emit(report)
        return 0 if report.get("status") == "passed" else 1
    except Exception as error:
        failure = {"status": "failed", "error": portable_error(error), "evidenceDirectory": display_path(evidence_directory)}
        (evidence_directory / "failure.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        emit(failure)
        return 1


if __name__ == "__main__":
    sys.exit(main())
