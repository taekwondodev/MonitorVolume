#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import random
import shutil
import statistics
import subprocess
import sys
import threading
import time
from types import ModuleType
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import issue33_live_protocol


SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_NAME = SCRIPT_PATH.name
ROOT = SCRIPT_PATH.parents[1]
PROTOCOL_PATH = ROOT / "scripts" / "issue33_live_protocol.json"
LOCK_PATH = ROOT / ".hermes" / "verification" / "issue33-live.lock"
LOCAL_KEYS = {
    "pid", "processIdentifier", "worktree", "installedExecutable", "executablePath",
    "bundle", "evidence", "campaignDirectory", "runDirectory", "preparedExecutable", "path",
    "raw", "command", "identity", "logicalCpuCount", "processStartAbsoluteTime",
    "accessibilityTrusted", "accessibility", "manualAccessibilityRemovalRecorded",
}
MESSAGE_FIELDS = (
    "schema", "sequence", "uptime_ns", "event", "name", "token", "tap", "result",
    "reason", "generation", "observed_generation", "current_generation", "event_timestamp_ns",
    "capacity", "attempted", "admitted", "rejected", "discarded", "overflow", "completed",
    "peak_outstanding", "pending",
)
INTEGER_MESSAGE_FIELDS = {
    "schema", "sequence", "uptime_ns", "token", "tap", "generation", "observed_generation",
    "current_generation", "event_timestamp_ns",
    "capacity", "attempted", "admitted", "rejected", "discarded", "overflow", "completed",
    "peak_outstanding", "pending",
}


class LiveGateFailure(RuntimeError):
    pass


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


class ProcTaskInfo(ctypes.Structure):
    _fields_ = [
        ("pti_virtual_size", ctypes.c_uint64),
        ("pti_resident_size", ctypes.c_uint64),
        ("pti_total_user", ctypes.c_uint64),
        ("pti_total_system", ctypes.c_uint64),
        ("pti_threads_user", ctypes.c_uint64),
        ("pti_threads_system", ctypes.c_uint64),
        ("pti_policy", ctypes.c_int32),
        ("pti_faults", ctypes.c_int32),
        ("pti_pageins", ctypes.c_int32),
        ("pti_cow_faults", ctypes.c_int32),
        ("pti_messages_sent", ctypes.c_int32),
        ("pti_messages_received", ctypes.c_int32),
        ("pti_syscalls_mach", ctypes.c_int32),
        ("pti_syscalls_unix", ctypes.c_int32),
        ("pti_csw", ctypes.c_int32),
        ("pti_threadnum", ctypes.c_int32),
        ("pti_numrunning", ctypes.c_int32),
        ("pti_priority", ctypes.c_int32),
    ]


LIBPROC = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
LIBPROC.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(RUsageInfoV0)]
LIBPROC.proc_pid_rusage.restype = ctypes.c_int
LIBPROC.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
LIBPROC.proc_pidinfo.restype = ctypes.c_int
PROC_PIDTASKINFO = 4


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveGateFailure(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file_digest(path: Path, expected: str, description: str) -> None:
    require(path.is_file(), f"{description} is missing")
    require(sha256_file(path) == expected, f"{description} digest mismatch")


def codesign_requirement(bundle: Path) -> str:
    result = subprocess.run(["codesign", "-d", "-r-", str(bundle)], text=True, capture_output=True, timeout=30)
    require(result.returncode == 0, "codesign designated requirement is unavailable")
    lines: list[str] = []
    for line in (*result.stdout.splitlines(), *result.stderr.splitlines()):
        match = re.fullmatch(r"(?:# )?designated => (.+)", line)
        if match is not None:
            lines.append(match.group(1))
    require(len(lines) == 1 and bool(lines[0]), "codesign designated requirement is ambiguous")
    return lines[0]


def require_campaign_bindings(
    campaign_directory: Path, manifest: dict[str, Any], *, require_runner_identity: bool = True,
) -> None:
    require_file_digest(campaign_directory / PROTOCOL_PATH.name, manifest["protocolSha256"], "campaign protocol")
    if require_runner_identity:
        require_file_digest(campaign_directory / SCRIPT_NAME, manifest["runnerSha256"], "campaign runner")
        require_file_digest(SCRIPT_PATH, manifest["runnerSha256"], "executed runner")
    protocol = issue33_live_protocol.load_protocol(campaign_directory / PROTOCOL_PATH.name)
    identities = application_identities(protocol)
    require(manifest.get("schemaVersion") == 2, "campaign manifest schema mismatch")
    require(manifest.get("status") == "prepared", "campaign manifest status mismatch")
    require(
        Path(manifest.get("campaignDirectory", "")).resolve() == campaign_directory.resolve(),
        "campaign manifest directory mismatch",
    )
    require(manifest.get("productionApplication") == identities["production"], "production application binding mismatch")
    candidates_value = manifest.get("candidates")
    if not isinstance(candidates_value, dict):
        raise LiveGateFailure("candidate manifest set mismatch")
    candidates: dict[str, Any] = candidates_value
    require(set(candidates) == {"A", "B"}, "candidate manifest set mismatch")
    digest_pattern = re.compile(r"[0-9a-f]{64}")
    for candidate in ("A", "B"):
        binding = candidates[candidate]
        expected_bundle = campaign_directory / "candidates" / candidate / f"{identities[candidate]['bundleName']}.app"
        expected_executable = expected_bundle / "Contents" / "MacOS" / identities[candidate]["executableName"]
        require(binding.get("sourceRef") == protocol["candidates"][candidate]["sourceRef"], "candidate source ref binding mismatch")
        require(binding.get("applicationIdentity") == identities[candidate], "candidate application identity binding mismatch")
        require(Path(binding.get("preparedBundle", "")).resolve() == expected_bundle.resolve(), "prepared bundle path mismatch")
        require(Path(binding.get("preparedExecutable", "")).resolve() == expected_executable.resolve(), "prepared executable path mismatch")
        for field in ("executableSha256", "infoPlistSha256", "bundleFilesSha256", "noticesSha256"):
            require(isinstance(binding.get(field), str) and digest_pattern.fullmatch(binding[field]) is not None, f"candidate {field} binding mismatch")
        require(isinstance(binding.get("designatedRequirement"), str) and bool(binding["designatedRequirement"]), "candidate designated requirement binding mismatch")
        bundle_files = binding.get("bundleFiles")
        require(isinstance(bundle_files, dict) and bool(bundle_files), "candidate bundle file binding mismatch")
        require(
            all(isinstance(path, str) and isinstance(digest, str) and digest_pattern.fullmatch(digest) is not None for path, digest in bundle_files.items()),
            "candidate bundle file digest mismatch",
        )
        require(
            hashlib.sha256(json.dumps(bundle_files, sort_keys=True).encode()).hexdigest() == binding["bundleFilesSha256"],
            "candidate bundle closure digest mismatch",
        )
        source = binding.get("sourceClosure")
        require(
            isinstance(source, dict) and bool(source)
            and all(isinstance(path, str) and isinstance(digest, str) and digest_pattern.fullmatch(digest) is not None for path, digest in source.items()),
            "candidate source closure binding mismatch",
        )
    require(manifest.get("normalSchedule") == issue33_live_protocol.normal_schedule(protocol), "normal schedule binding mismatch")
    require(manifest.get("acceptanceSchedule") == issue33_live_protocol.acceptance_schedule(protocol), "acceptance schedule binding mismatch")
    require(isinstance(manifest.get("runs"), list), "campaign run list mismatch")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run_checked(command: list[str], *, cwd: Path | None = None, timeout: int = 300) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise LiveGateFailure(f"command failed ({' '.join(command)}): {detail}")
    return result.stdout.strip()


def checked_observation(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
    require(result.returncode == 0, f"environment command failed: {' '.join(command)}")
    return {
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exitCode": result.returncode,
    }


def parse_power_source(output: str) -> str:
    if "'AC Power'" in output:
        return "ac"
    if "'Battery Power'" in output:
        return "battery"
    raise LiveGateFailure("power source is unavailable")


def parse_ac_low_power_mode(output: str) -> bool:
    active = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.endswith("Power:"):
            active = stripped == "AC Power:"
        elif active:
            fields = stripped.split()
            if len(fields) == 2 and fields[0] == "lowpowermode" and fields[1] in {"0", "1"}:
                return fields[1] == "1"
    raise LiveGateFailure("AC low-power mode is unavailable")


def observe_environment(probe: Path, boundary: str) -> dict[str, Any]:
    power = checked_observation(["/usr/bin/pmset", "-g", "batt"])
    low_power = checked_observation(["/usr/bin/pmset", "-g", "custom"])
    thermal = checked_observation([str(probe)])
    sw_vers = checked_observation(["/usr/bin/sw_vers"])
    machine = checked_observation(["/usr/bin/uname", "-m"])
    model = checked_observation(["/usr/sbin/sysctl", "-n", "hw.model"])
    logical_cpu = checked_observation(["/usr/sbin/sysctl", "-n", "hw.logicalcpu"])
    swift = checked_observation(["swift", "--version"])
    observation = {
        "boundary": boundary,
        "powerSource": parse_power_source(power["stdout"]),
        "lowPowerMode": parse_ac_low_power_mode(low_power["stdout"]),
        "thermalState": json.loads(thermal["stdout"])["thermalState"],
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
    require(observation["powerSource"] == "ac", "campaign requires AC power")
    require(observation["lowPowerMode"] is False, "campaign requires low-power mode off")
    require(observation["thermalState"] == "nominal", "campaign requires nominal thermal state")
    require(observation["logicalCpuCount"] > 0, "logical CPU count is invalid")
    if baseline is not None:
        require(observation["identity"] == baseline["identity"], "host, OS, or toolchain changed")
        require(observation["logicalCpuCount"] == baseline["logicalCpuCount"], "logical CPU count changed")


def compile_environment_probe(destination: Path) -> dict[str, str]:
    source = ROOT / "scripts" / "Issue32EnvironmentProbe.swift"
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_checked(["swiftc", str(source), "-o", str(destination)], timeout=60)
    return {"sourceSha256": sha256_file(source), "executableSha256": sha256_file(destination)}


def git_output(worktree: Path, *arguments: str) -> str:
    return run_checked(["git", *arguments], cwd=worktree)


def tracked_files(worktree: Path) -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=worktree, check=True, capture_output=True,
    ).stdout
    return sorted(value.decode() for value in output.split(b"\0") if value)


def source_closure(worktree: Path, files: Iterable[str] | None = None) -> dict[str, str]:
    selected = tracked_files(worktree) if files is None else sorted(files)
    closure: dict[str, str] = {}
    for relative in selected:
        path = worktree / relative
        require(path.is_file(), f"tracked source is missing: {relative}")
        closure[relative] = sha256_file(path)
    return closure


def candidate_state(worktree: Path, expected_ref: str) -> dict[str, Any]:
    require(worktree.is_dir(), f"candidate worktree is missing: {worktree}")
    actual_ref = git_output(worktree, "rev-parse", "HEAD")
    require(actual_ref == expected_ref, f"candidate HEAD mismatch: expected {expected_ref}, found {actual_ref}")
    status = git_output(worktree, "status", "--porcelain")
    require(not status, "candidate worktree must be clean")
    return {
        "sourceRef": actual_ref,
        "sourceClosure": source_closure(worktree),
        "swiftVersion": run_checked(["swift", "--version"], cwd=worktree),
    }


def load_app_tool(worktree: Path, module_name: str) -> ModuleType:
    script = worktree / "scripts" / "app_tool.py"
    require(script.is_file(), f"candidate app tool is missing: {script}")
    scripts = str(script.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    specification = importlib.util.spec_from_file_location(module_name, script)
    if specification is None or specification.loader is None:
        raise LiveGateFailure("candidate app tool is unloadable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def expand_identity(candidate: str, value: dict[str, Any]) -> dict[str, str]:
    bundle = Path(value["installedBundle"]).expanduser()
    executable = bundle / "Contents" / "MacOS" / value["executableName"]
    return {
        "candidate": candidate,
        "bundleIdentifier": value["bundleIdentifier"],
        "bundleName": value["bundleName"],
        "installedBundle": str(bundle),
        "installedExecutable": str(executable),
        "executableName": value["executableName"],
    }


def application_identities(protocol: dict[str, Any]) -> dict[str, dict[str, str]]:
    identities = {"production": expand_identity("production", protocol["productionApplication"])}
    identities.update({
        candidate: expand_identity(candidate, value["applicationIdentity"])
        for candidate, value in protocol["candidates"].items()
    })
    require(len({value["bundleIdentifier"] for value in identities.values()}) == len(identities), "application identity collision")
    require(len({value["installedBundle"] for value in identities.values()}) == len(identities), "application identity path collision")
    return identities


def campaign_metadata(source: dict[str, Any], identity: dict[str, str]) -> dict[str, Any]:
    metadata = dict(source)
    metadata["CFBundleIdentifier"] = identity["bundleIdentifier"]
    metadata["CFBundleName"] = identity["bundleName"]
    require(metadata["CFBundleExecutable"] == identity["executableName"], "campaign executable name mismatch")
    return metadata


def build_candidate(
    worktree: Path,
    candidate: str,
    destination_bundle: Path,
    identity: dict[str, str],
) -> dict[str, Any]:
    candidate_tool = load_app_tool(worktree, f"issue33_app_tool_{candidate.lower()}_prepare")
    campaign_tool = load_app_tool(ROOT, f"issue33_campaign_app_tool_{candidate.lower()}_prepare")
    executable = Path(candidate_tool.build_release())
    require(executable.is_file(), "candidate Release executable is missing")
    destination_bundle.parent.mkdir(parents=True)
    campaign_tool.assemble_bundle(destination_bundle, executable, identity)
    destination_executable = destination_bundle / "Contents" / "MacOS" / identity["executableName"]
    info_plist = destination_bundle / "Contents" / "Info.plist"
    designated_requirement = codesign_requirement(destination_bundle)
    bundle_files = campaign_tool.bundle_file_digests(destination_bundle)
    return {
        "candidate": candidate,
        "preparedBundle": str(destination_bundle),
        "preparedExecutable": str(destination_executable),
        "executableSha256": sha256_file(destination_executable),
        "infoPlistSha256": sha256_file(info_plist),
        "bundleFiles": bundle_files,
        "bundleFilesSha256": hashlib.sha256(json.dumps(bundle_files, sort_keys=True).encode()).hexdigest(),
        "designatedRequirement": designated_requirement,
        "noticesSha256": sha256_file(worktree / "THIRD_PARTY_NOTICES.md"),
        "applicationIdentity": identity,
    }


def prepare(campaign_directory: Path, worktrees: dict[str, Path]) -> dict[str, Any]:
    require(not campaign_directory.exists(), "campaign directory already exists")
    staging = campaign_directory.with_name(f".{campaign_directory.name}.prepare-{os.getpid()}")
    require(not staging.exists(), "campaign preparation staging directory already exists")
    protocol = issue33_live_protocol.load_protocol(PROTOCOL_PATH)
    identities = application_identities(protocol)
    states = {
        candidate: candidate_state(worktrees[candidate], protocol["candidates"][candidate]["sourceRef"])
        for candidate in ("A", "B")
    }
    try:
        staging.mkdir(parents=True)
        retained_protocol = staging / PROTOCOL_PATH.name
        retained_runner = staging / SCRIPT_NAME
        shutil.copy2(PROTOCOL_PATH, retained_protocol)
        shutil.copy2(SCRIPT_PATH, retained_runner)
        environment_probe = staging / "artifacts" / "EnvironmentProbe"
        environment_probe_binding = compile_environment_probe(environment_probe)
        candidates: dict[str, Any] = {}
        for candidate in ("A", "B"):
            identity = identities[candidate]
            relative_bundle = Path("candidates") / candidate / f"{identity['bundleName']}.app"
            relative_executable = relative_bundle / "Contents" / "MacOS" / "ProArtVolume"
            built = build_candidate(worktrees[candidate], candidate, staging / relative_bundle, identity)
            built["preparedBundle"] = str(campaign_directory / relative_bundle)
            built["preparedExecutable"] = str(campaign_directory / relative_executable)
            require(candidate_state(
                worktrees[candidate], protocol["candidates"][candidate]["sourceRef"],
            )["sourceClosure"] == states[candidate]["sourceClosure"], "candidate changed during build")
            candidates[candidate] = {
                **built,
                **states[candidate],
                "worktree": str(worktrees[candidate]),
            }
        manifest = {
            "schemaVersion": 2,
            "status": "prepared",
            "campaignDirectory": str(campaign_directory),
            "protocolSha256": sha256_file(retained_protocol),
            "runnerSha256": sha256_file(retained_runner),
            "environmentProbe": {
                "path": str(campaign_directory / "artifacts" / "EnvironmentProbe"),
                **environment_probe_binding,
            },
            "productionApplication": identities["production"],
            "candidates": candidates,
            "normalSchedule": issue33_live_protocol.normal_schedule(protocol),
            "acceptanceSchedule": issue33_live_protocol.acceptance_schedule(protocol),
            "runs": [],
        }
        write_json(staging / "manifest.json", manifest)
        staging.replace(campaign_directory)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def parse_lifecycle_message(message: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in MESSAGE_FIELDS:
        match = re.search(rf"(?:^| ){re.escape(field)}=([^ ]+)", message)
        if match is None:
            raise LiveGateFailure(f"lifecycle message is missing {field}")
        value: Any = match.group(1)
        if field in INTEGER_MESSAGE_FIELDS:
            try:
                value = int(value)
            except ValueError as error:
                raise LiveGateFailure(f"lifecycle message has invalid {field}") from error
        values[field] = value
    require(values["schema"] == 3, "lifecycle schema mismatch")
    return {
        "schemaVersion": values["schema"],
        "sequence": values["sequence"],
        "uptimeNanoseconds": values["uptime_ns"],
        "event": values["event"],
        "name": values["name"],
        "token": values["token"],
        "tap": values["tap"],
        "result": values["result"],
        "reason": values["reason"],
        "generation": values["generation"],
        "observedGeneration": values["observed_generation"],
        "currentGeneration": values["current_generation"],
        "eventTimestampNanoseconds": values["event_timestamp_ns"],
        "capacity": values["capacity"],
        "attempted": values["attempted"],
        "admitted": values["admitted"],
        "rejected": values["rejected"],
        "discarded": values["discarded"],
        "overflow": values["overflow"],
        "completed": values["completed"],
        "peakOutstanding": values["peak_outstanding"],
        "pending": values["pending"],
    }


def callback_metrics(records: list[dict[str, Any]], maximum_proxy_nanoseconds: int = 1_000_000_000) -> list[dict[str, int]]:
    pending: dict[str, Any] | None = None
    metrics: list[dict[str, int]] = []
    for record in records:
        if record["event"] == "callbackEntered":
            require(pending is None, "nested callback entry")
            require(record["eventTimestampNanoseconds"] > 0, "callback entry lacks event timestamp")
            require(record["uptimeNanoseconds"] >= record["eventTimestampNanoseconds"], "event timestamp follows callback entry")
            pending = record
        elif record["event"] == "callbackExited":
            if pending is None:
                raise LiveGateFailure("callback exit lacks entry")
            require(record["uptimeNanoseconds"] >= pending["uptimeNanoseconds"], "callback exit precedes entry")
            proxy = pending["uptimeNanoseconds"] - pending["eventTimestampNanoseconds"]
            require(proxy <= maximum_proxy_nanoseconds, "event and callback clocks are not nanosecond-compatible")
            metrics.append({
                "entrySequence": pending["sequence"],
                "exitSequence": record["sequence"],
                "callbackDurationNanoseconds": record["uptimeNanoseconds"] - pending["uptimeNanoseconds"],
                "eventToCallbackProxyNanoseconds": proxy,
            })
            pending = None
    require(pending is None, "callback entry lacks exit")
    return metrics


def lifecycle_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    event_counts: dict[str, int] = {}
    handoff_counts: dict[str, int] = {}
    tap_disabled_counts: dict[str, int] = {}
    operation_starts: dict[int, dict[str, Any]] = {}
    query_starts: dict[int, dict[str, Any]] = {}
    operation_durations: dict[str, list[float]] = {}
    completed_operations: dict[str, int] = {}
    lifecycle_starts: list[dict[str, Any]] = []
    gate_closure_durations: list[float] = []
    accounting: dict[str, int] | None = None
    for record in records:
        event = record["event"]
        event_counts[event] = event_counts.get(event, 0) + 1
        if event == "handoff":
            name = record["name"]
            handoff_counts[name] = handoff_counts.get(name, 0) + 1
        elif event == "tapDisabled":
            reason = record["reason"]
            tap_disabled_counts[reason] = tap_disabled_counts.get(reason, 0) + 1
        elif event == "accounting":
            require(accounting is None, "duplicate lifecycle accounting snapshot")
            accounting = {
                key: record[key]
                for key in (
                    "capacity", "attempted", "admitted", "rejected", "discarded", "overflow",
                    "completed", "peakOutstanding", "pending",
                )
            }
        elif event == "lifecycle" and record["reason"] in {
            "missingAccessibility", "permissionRevoked", "disabledTap",
            "deliveryOverflow", "sleep", "termination", "deinitialization",
        }:
            lifecycle_starts.append(record)
        elif event == "operationBegan":
            require(record["token"] not in operation_starts, "duplicate operation token")
            operation_starts[record["token"]] = record
        elif event == "operationEnded":
            start = operation_starts.pop(record["token"], None)
            if start is None:
                raise LiveGateFailure("unpaired lifecycle operation")
            require(start["name"] == record["name"], "lifecycle operation kind mismatch")
            require(record["uptimeNanoseconds"] >= start["uptimeNanoseconds"], "lifecycle operation time reversed")
            operation_durations.setdefault(record["name"], []).append(
                float(record["uptimeNanoseconds"] - start["uptimeNanoseconds"])
            )
            if record["result"] == "returned":
                completed_operations[record["name"]] = completed_operations.get(record["name"], 0) + 1
            if record["name"] == "stop" and lifecycle_starts:
                lifecycle = lifecycle_starts.pop(0)
                gate_closure_durations.append(
                    float(record["uptimeNanoseconds"] - lifecycle["uptimeNanoseconds"])
                )
        elif event == "queryBegan":
            require(record["token"] not in query_starts, "duplicate query token")
            query_starts[record["token"]] = record
        elif event == "queryReturned":
            start = query_starts.pop(record["token"], None)
            if start is None:
                raise LiveGateFailure("unpaired lifecycle query")
            require(start["name"] == record["name"], "lifecycle query kind mismatch")
    require(not operation_starts, "unfinished lifecycle operation")
    require(not query_starts, "unfinished lifecycle query")
    tap_resources_released = (
        completed_operations.get("tapCreate", 0) == completed_operations.get("tapInvalidate", 0)
        and completed_operations.get("sourceAdd", 0) == completed_operations.get("sourceRemove", 0)
    )
    complete = (
        event_counts.get("sessionStarted", 0) == 1
        and event_counts.get("sessionEnded", 0) == 1
        and event_counts.get("budgetExhausted", 0) == 0
        and accounting is not None
        and accounting["pending"] == 0
        and tap_resources_released
    )
    return {
        "eventCounts": event_counts,
        "handoffCounts": handoff_counts,
        "tapDisabledCounts": tap_disabled_counts,
        "budgetExhausted": event_counts.get("budgetExhausted", 0) > 0,
        "accounting": accounting,
        "tapResourcesReleased": tap_resources_released,
        "complete": complete,
        "operationDurationNanoseconds": {
            name: summarize_numbers(values) for name, values in sorted(operation_durations.items())
        },
        "gateClosureNanoseconds": summarize_numbers(gate_closure_durations) if gate_closure_durations else None,
    }


def read_lifecycle_log(path: Path, pid: int, require_records: bool = True) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        if not raw_line.strip():
            continue
        if (
            line_number == 1
            and raw_line.startswith('Filtering the log data using "')
            and raw_line.endswith('"')
        ):
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise LiveGateFailure("unified log stream emitted invalid NDJSON") from error
        if event.get("eventType") == "lossEvent" or event.get("type") == "lossEvent":
            raise LiveGateFailure("unified log reported lost events")
        event_pid = event.get("processID")
        legacy_event_pid = event.get("processIdentifier")
        require(
            event_pid is None or legacy_event_pid is None or event_pid == legacy_event_pid,
            "unified log event has conflicting process identifiers",
        )
        if event_pid is None:
            event_pid = legacy_event_pid
        if event_pid != pid:
            continue
        message = event.get("eventMessage") or event.get("composedMessage")
        if isinstance(message, str) and message.startswith("schema=3 "):
            records.append(parse_lifecycle_message(message))
    records.sort(key=lambda record: record["sequence"])
    if require_records:
        require(bool(records), "no lifecycle records were captured")
    require(
        [record["sequence"] for record in records] == list(range(1, len(records) + 1)),
        "lifecycle record sequence has gaps",
    )
    return records


def read_readiness_log(path: Path, pid: int, expected: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        if not raw_line.strip():
            continue
        if line_number == 1 and raw_line.startswith('Filtering the log data using "') and raw_line.endswith('"'):
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise LiveGateFailure("unified log stream emitted invalid NDJSON") from error
        if event.get("eventType") == "lossEvent" or event.get("type") == "lossEvent":
            raise LiveGateFailure("unified log reported lost events")
        event_pid = event.get("processID")
        legacy_pid = event.get("processIdentifier")
        require(event_pid is None or legacy_pid is None or event_pid == legacy_pid, "unified log event has conflicting process identifiers")
        if (event_pid if event_pid is not None else legacy_pid) != pid:
            continue
        message = event.get("eventMessage") or event.get("composedMessage")
        if not isinstance(message, str) or not message.startswith("schema=1 state="):
            continue
        fields = dict(item.split("=", 1) for item in message.split())
        required = {
            "schema", "state", "candidate", "bundle_id", "executable_sha256", "source_ref",
            "generation", "accessibility", "tap", "service",
        }
        require(set(fields) == required, "readiness record fields mismatch")
        require(fields["state"] in {"ready", "unavailable"}, "readiness state mismatch")
        require(fields["generation"].isdigit() and int(fields["generation"]) > 0, "readiness generation mismatch")
        records.append({
            "schemaVersion": 1,
            "state": fields["state"],
            "candidate": fields["candidate"],
            "bundleIdentifier": fields["bundle_id"],
            "executableSha256": fields["executable_sha256"],
            "sourceRef": fields["source_ref"],
            "generation": int(fields["generation"]),
            "accessibilityTrusted": fields["accessibility"] == "true",
            "tapOwnerActive": fields["tap"] == "true",
            "serviceValidationComplete": fields["service"] == "true",
            "pid": pid,
        })
    require(len(records) == 1, "readiness must contain exactly one terminal record")
    record = records[0]
    for key in ("candidate", "bundleIdentifier", "executableSha256", "sourceRef"):
        require(record[key] == expected[key], f"readiness {key} mismatch")
    if record["state"] == "ready":
        require(record["accessibilityTrusted"] and record["tapOwnerActive"] and record["serviceValidationComplete"], "ready attestation has false prerequisites")
    return record


def wait_for_readiness(path: Path, pid: int, expected: dict[str, Any], timeout_seconds: float = 15) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return read_readiness_log(path, pid, expected)
            except LiveGateFailure as error:
                last_error = error
        time.sleep(0.1)
    raise LiveGateFailure(f"readiness timeout: {last_error or 'no attestation'}")


def known_processes(manifest: dict[str, Any], module: ModuleType) -> dict[str, list[int]]:
    identities = {"production": manifest["productionApplication"]}
    identities.update({candidate: binding["applicationIdentity"] for candidate, binding in manifest["candidates"].items()})
    return {
        name: module.exact_processes(Path(identity["installedExecutable"]))
        for name, identity in identities.items()
    }


def require_all_known_stopped(manifest: dict[str, Any], module: ModuleType) -> None:
    running = {name: pids for name, pids in known_processes(manifest, module).items() if pids}
    require(not running, f"known application processes must be stopped: {running}")


def stop_bound_candidates(manifest: dict[str, Any], module: ModuleType) -> dict[str, list[int]]:
    stopped: dict[str, list[int]] = {}
    for candidate, binding in manifest["candidates"].items():
        identity = binding["applicationIdentity"]
        executable = Path(identity["installedExecutable"])
        pids = module.exact_processes(executable)
        if not pids:
            stopped[candidate] = []
            continue
        validate_installed_bundle(module, binding)
        stopped[candidate] = module.stop_exact_processes(executable)
    return stopped


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
    task = ProcTaskInfo()
    task_size = ctypes.sizeof(task)
    if LIBPROC.proc_pidinfo(pid, PROC_PIDTASKINFO, 0, ctypes.byref(task), task_size) != task_size:
        return {
            "sequence": sequence,
            "status": "failed",
            "uptimeNanoseconds": timestamp,
            "reason": f"procPidTaskInfo:{ctypes.get_errno()}",
        }
    return {
        "sequence": sequence,
        "status": "sampled",
        "uptimeNanoseconds": timestamp,
        "residentSizeBytes": usage.ri_resident_size,
        "physicalFootprintBytes": usage.ri_phys_footprint,
        "cumulativeCpuNanoseconds": usage.ri_user_time + usage.ri_system_time,
        "packageIdleWakeups": usage.ri_pkg_idle_wkups,
        "interruptWakeups": usage.ri_interrupt_wkups,
        "threadCount": task.pti_threadnum,
        "processStartAbsoluteTime": usage.ri_proc_start_abstime,
        "cpuIntervalStartUptimeNanoseconds": None,
        "intervalCpuPercentOneCore": None,
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
                sample["intervalCpuPercentOneCore"] = cpu_delta * 100 / elapsed
        previous = sample


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    sampled = [sample for sample in samples if sample.get("status") == "sampled"]
    cpu = [sample["intervalCpuPercentOneCore"] for sample in sampled if sample["intervalCpuPercentOneCore"] is not None]
    resident = [sample["residentSizeBytes"] for sample in sampled]
    footprint = [sample["physicalFootprintBytes"] for sample in sampled]
    threads = [sample["threadCount"] for sample in sampled]
    process_starts = {sample["processStartAbsoluteTime"] for sample in sampled}
    require(len(process_starts) <= 1, "resource samples crossed process identities")
    return {
        "sampleCount": len(sampled),
        "cpuIntervalCount": len(cpu),
        "failedPollCount": sum(sample.get("status") == "failed" for sample in samples),
        "censoredCount": sum(sample.get("status") == "censored" for sample in samples),
        "meanCpuPercentOneCore": statistics.fmean(cpu) if cpu else None,
        "maximumCpuPercentOneCore": max(cpu) if cpu else None,
        "baselineResidentSizeBytes": resident[0] if resident else None,
        "medianResidentSizeBytes": statistics.median(resident) if resident else None,
        "maximumResidentSizeBytes": max(resident) if resident else None,
        "baselinePhysicalFootprintBytes": footprint[0] if footprint else None,
        "medianPhysicalFootprintBytes": statistics.median(footprint) if footprint else None,
        "maximumPhysicalFootprintBytes": max(footprint) if footprint else None,
        "baselineThreadCount": threads[0] if threads else None,
        "medianThreadCount": statistics.median(threads) if threads else None,
        "maximumThreadCount": max(threads) if threads else None,
        "endingThreadCount": threads[-1] if threads else None,
        "packageIdleWakeupsDelta": sampled[-1]["packageIdleWakeups"] - sampled[0]["packageIdleWakeups"] if len(sampled) > 1 else None,
        "interruptWakeupsDelta": sampled[-1]["interruptWakeups"] - sampled[0]["interruptWakeups"] if len(sampled) > 1 else None,
    }


def summarize_numbers(values: list[float]) -> dict[str, Any]:
    require(bool(values), "numeric summary requires values")
    ordered = sorted(float(value) for value in values)
    rank = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "sampleCount": len(ordered),
        "median": float(statistics.median(ordered)),
        "nearestRankP95": ordered[rank],
        "maximum": ordered[-1],
    }


def first_interaction_time(events: list[dict[str, Any]], interaction_id: int, stage: str) -> int | None:
    values = [
        event["uptimeNanoseconds"]
        for event in events
        if event.get("stage") == stage and interaction_id in event.get("interactionIDs", [])
    ]
    return min(values) if values else None


def latency_metric_values(evidence: dict[str, Any]) -> dict[str, list[float]]:
    events = evidence["events"]
    values: dict[str, list[float]] = {
        "acceptedToIntentReducedNanoseconds": [],
        "acceptedToCommandEnqueuedNanoseconds": [],
        "acceptedToFirstDrawNanoseconds": [],
        "acceptedToServiceCompletionNanoseconds": [],
        "ddcWriteReadBackNanoseconds": [],
    }
    accepted = [event for event in events if event.get("stage") == "input_accepted"]
    for event in accepted:
        require(len(event["interactionIDs"]) == 1, "accepted event identity mismatch")
        interaction_id = event["interactionIDs"][0]
        start = event["uptimeNanoseconds"]
        for stage, metric in (
            ("intent_reduced", "acceptedToIntentReducedNanoseconds"),
            ("command_enqueued", "acceptedToCommandEnqueuedNanoseconds"),
            ("osd_first_draw_completed", "acceptedToFirstDrawNanoseconds"),
            ("service_command_completed", "acceptedToServiceCompletionNanoseconds"),
        ):
            end = first_interaction_time(events, interaction_id, stage)
            if end is not None:
                require(end >= start, f"latency stage precedes acceptance: {stage}")
                values[metric].append(float(end - start))
        starts = sorted(
            value["uptimeNanoseconds"] for value in events
            if value.get("stage") == "ddc_write_read_back_started"
            and interaction_id in value.get("interactionIDs", [])
        )
        ends = sorted(
            value["uptimeNanoseconds"] for value in events
            if value.get("stage") == "ddc_write_read_back_completed"
            and interaction_id in value.get("interactionIDs", [])
        )
        require(len(starts) == len(ends), "DDC write/read-back timing pair mismatch")
        for operation_start, operation_end in zip(starts, ends):
            require(operation_end >= operation_start, "DDC write/read-back completion precedes start")
            values["ddcWriteReadBackNanoseconds"].append(float(operation_end - operation_start))
    return values


def analysis_metrics(
    callback_values: list[dict[str, int]],
    latency_evidence: dict[str, Any] | None,
    phase_summaries: dict[str, dict[str, Any]],
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    callback_fields = (
        "callbackDurationNanoseconds", "eventToCallbackProxyNanoseconds",
    )
    for field in callback_fields:
        values = [float(item[field]) for item in callback_values]
        if values:
            for statistic, value in summarize_numbers(values).items():
                if statistic != "sampleCount":
                    metrics[f"timing.{field}.{statistic}"] = float(value)
    if latency_evidence is not None:
        for name, values in latency_metric_values(latency_evidence).items():
            if values:
                for statistic, value in summarize_numbers(values).items():
                    if statistic != "sampleCount":
                        metrics[f"timing.{name}.{statistic}"] = float(value)
    resource_fields = {
        "meanCpuPercentOneCore": "cpuPercentOneCore.mean",
        "maximumCpuPercentOneCore": "cpuPercentOneCore.maximum",
        "baselineResidentSizeBytes": "residentSizeBytes.baseline",
        "medianResidentSizeBytes": "residentSizeBytes.median",
        "maximumResidentSizeBytes": "residentSizeBytes.maximum",
        "baselinePhysicalFootprintBytes": "physicalFootprintBytes.baseline",
        "medianPhysicalFootprintBytes": "physicalFootprintBytes.median",
        "maximumPhysicalFootprintBytes": "physicalFootprintBytes.maximum",
        "packageIdleWakeupsDelta": "packageIdleWakeups.delta",
        "interruptWakeupsDelta": "interruptWakeups.delta",
    }
    for phase, summary in phase_summaries.items():
        for source, name in resource_fields.items():
            if summary.get(source) is not None:
                metrics[f"resource.{phase}.{name}"] = float(summary[source])
    return metrics


def median_absolute_successive_difference(values: list[float]) -> float:
    require(len(values) >= 4, "repeatability requires four run summaries")
    return float(statistics.median(abs(right - left) for left, right in zip(values, values[1:])))


def bootstrap_interval(differences: list[float], seed: int, resamples: int) -> tuple[float, float]:
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


def compare_metric_series(
    candidate_a: list[float], candidate_b: list[float], metric: str, protocol: dict[str, Any],
) -> dict[str, Any]:
    expected = protocol["equivalence"]["pairedRunCount"]
    require(len(candidate_a) == expected and len(candidate_b) == expected, "paired metric count mismatch")
    differences = [right - left for left, right in zip(candidate_a, candidate_b)]
    noise_band = max(
        median_absolute_successive_difference(candidate_a),
        median_absolute_successive_difference(candidate_b),
    )
    seed = protocol["equivalence"]["bootstrapSeed"] + int(hashlib.sha256(metric.encode()).hexdigest()[:8], 16)
    lower, upper = bootstrap_interval(
        differences, seed, protocol["equivalence"]["bootstrapResamples"],
    )
    return {
        "metric": metric,
        "pairedRunCount": len(differences),
        "medianBMinusA": float(statistics.median(differences)),
        "repeatabilityNoiseBand": noise_band,
        "bootstrapConfidenceInterval": [lower, upper],
        "classification": classify_interval(lower, upper, noise_band),
    }


def select_candidate(classifications: Iterable[str], lifecycle_review_green: bool) -> str:
    values = set(classifications)
    if not lifecycle_review_green or not values or "inconclusive" in values or {"candidateABetter", "candidateBBetter"} <= values:
        return "inconclusive"
    if values <= {"equivalent", "candidateABetter"}:
        return "A"
    if "candidateBBetter" in values and values <= {"equivalent", "candidateBBetter"}:
        return "B"
    return "inconclusive"


def phase_ranges(boundaries: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    starts: dict[str, int] = {}
    ranges: dict[str, tuple[int, int]] = {}
    for boundary in boundaries:
        phase = boundary["phase"]
        if boundary["boundary"] == "start":
            require(phase not in starts and phase not in ranges, f"duplicate phase: {phase}")
            starts[phase] = boundary["uptimeNanoseconds"]
        else:
            require(boundary["boundary"] == "end" and phase in starts, f"unmatched phase end: {phase}")
            ranges[phase] = (starts.pop(phase), boundary["uptimeNanoseconds"])
    require(not starts, "unterminated phase")
    return ranges


def summarize_by_phase(samples: list[dict[str, Any]], boundaries: list[dict[str, Any]]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for phase, (start, end) in phase_ranges(boundaries).items():
        selected: list[dict[str, Any]] = []
        for sample in samples:
            if not start <= sample["uptimeNanoseconds"] <= end:
                continue
            value = dict(sample)
            interval_start = value.get("cpuIntervalStartUptimeNanoseconds")
            if interval_start is None or interval_start < start:
                value["intervalCpuPercentOneCore"] = None
            selected.append(value)
        summary = summarize_samples(selected)
        require(summary["sampleCount"] > 0, f"phase lacks resource sample: {phase}")
        require(summary["cpuIntervalCount"] > 0, f"phase lacks CPU interval: {phase}")
        summaries[phase] = summary
    return summaries


def required_consent(workload: str) -> set[str]:
    common = {"installationAndLaunch", "physicalVolumeInputAndDDCWrites"}
    if workload == "normal":
        return common | {"normalUseUIActivity"}
    if workload == "lifecycle":
        return common | {"accessibilityPermissionChanges", "sleepWake"}
    if workload == "stress":
        return common | {"stress"}
    raise LiveGateFailure(f"unknown workload: {workload}")


def publishable_projection(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: publishable_projection(item)
            for key, item in value.items()
            if key not in LOCAL_KEYS
        }
    if isinstance(value, list):
        return [publishable_projection(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?:/Users/[^/\s]+|/private/tmp)(?:/[^\s]+)*", "<local-path>", value)
    return value


def candidate_run(manifest: dict[str, Any], workload: str, ordinal: int) -> dict[str, Any]:
    key = "normalSchedule" if workload == "normal" else "acceptanceSchedule"
    selected = [item for item in manifest[key] if item["workload"] == workload]
    require(1 <= ordinal <= len(selected), "run ordinal is outside the frozen schedule")
    return selected[ordinal - 1]


def start_log_stream(destination: Path) -> tuple[subprocess.Popen[str], Any, Any]:
    output = destination.open("w")
    error_output = destination.with_suffix(".stderr.txt").open("w")
    predicate = 'subsystem == "dev.taekwondodev.ProArtVolume" AND (category == "input-lifecycle" OR category == "campaign-readiness")'
    process = subprocess.Popen(
        ["/usr/bin/log", "stream", "--style", "ndjson", "--level", "info", "--predicate", predicate],
        text=True,
        stdout=output,
        stderr=error_output,
        start_new_session=True,
    )
    time.sleep(0.2)
    if process.poll() is not None:
        stop_owned_process(process)
        output.close()
        error_output.close()
        raise LiveGateFailure("unified log stream exited during startup")
    return process, output, error_output


def stop_owned_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, 15)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, 9)
        process.wait(timeout=2)


def sample_until_stopped(pid: int, destination: Path, interval: float, stop: threading.Event) -> None:
    sequence = 0
    with destination.open("w") as handle:
        while not stop.is_set():
            sample = sample_process(pid, sequence)
            handle.write(json.dumps(sample, sort_keys=True) + "\n")
            handle.flush()
            sequence += 1
            stop.wait(interval)
        censored = {
            "sequence": sequence,
            "status": "censored",
            "uptimeNanoseconds": time.monotonic_ns(),
            "reason": "samplingStopped",
        }
        handle.write(json.dumps(censored, sort_keys=True) + "\n")
        handle.flush()


def phase_definitions(protocol: dict[str, Any], workload: str) -> list[dict[str, Any]]:
    if workload == "normal":
        return protocol["normalWorkload"]["phases"]
    return protocol["acceptanceRuns"][workload]["phases"]


def operator_phases(protocol: dict[str, Any], workload: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    boundaries: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for definition in phase_definitions(protocol, workload):
        phase = definition["name"]
        prompt = f"{phase}: {definition['operatorAction']} (minimum {definition['minimumSeconds']}s)"
        require(input(f"{prompt}\nType START to begin: ").strip() == "START", f"phase not started: {phase}")
        start = time.monotonic_ns()
        boundaries.append({"phase": phase, "boundary": "start", "uptimeNanoseconds": start})
        require(input("Type DONE after completing the action and wait: ").strip() == "DONE", f"phase not completed: {phase}")
        end = time.monotonic_ns()
        boundaries.append({"phase": phase, "boundary": "end", "uptimeNanoseconds": end})
        elapsed = (end - start) / 1_000_000_000
        require(elapsed >= definition["minimumSeconds"], f"phase ended too early: {phase}")
        pass_condition = definition.get("passCondition")
        if pass_condition is not None:
            require(
                input(f"Confirm this observation by typing PASS: {pass_condition}\n").strip() == "PASS",
                f"phase observation did not pass: {phase}",
            )
        observations.append({
            "phase": phase,
            "elapsedSeconds": elapsed,
            "operatorAction": definition["operatorAction"],
            "passCondition": pass_condition,
            "passed": True,
        })
    require(input("Type USABLE if ordinary keyboard and pointer input remained usable: ").strip() == "USABLE", "ordinary input usability was not confirmed")
    return boundaries, observations


def validate_installed_bundle(module: ModuleType, binding: dict[str, Any]) -> dict[str, Any]:
    identity = binding["applicationIdentity"]
    bundle = Path(identity["installedBundle"])
    executable = Path(identity["installedExecutable"])
    verified = module.verify_bundle(bundle, require_live_process=False, identity=identity)
    require_file_digest(executable, binding["executableSha256"], "installed executable")
    require_file_digest(bundle / "Contents" / "Info.plist", binding["infoPlistSha256"], "installed metadata")
    require(module.bundle_file_digests(bundle) == binding["bundleFiles"], "installed bundle file closure mismatch")
    require(codesign_requirement(bundle) == binding["designatedRequirement"], "installed designated requirement mismatch")
    return verified


def validate_all_installed(module: ModuleType, manifest: dict[str, Any]) -> None:
    for binding in manifest["candidates"].values():
        validate_installed_bundle(module, binding)


def readiness_arguments(binding: dict[str, Any]) -> list[str]:
    identity = binding["applicationIdentity"]
    return [
        "--campaign-readiness", identity["candidate"], binding["sourceRef"], binding["executableSha256"],
    ]


def validate_readiness_record(record: Any, candidate: str, binding: dict[str, Any]) -> None:
    require(isinstance(record, dict), "readiness record is missing")
    expected = {
        "candidate": candidate,
        "bundleIdentifier": binding["applicationIdentity"]["bundleIdentifier"],
        "executableSha256": binding["executableSha256"],
        "sourceRef": binding["sourceRef"],
    }
    require(record.get("schemaVersion") == 1 and record.get("state") == "ready", "readiness did not pass")
    for key, value in expected.items():
        require(record.get(key) == value, f"readiness {key} mismatch")
    require(
        isinstance(record.get("generation"), int) and record["generation"] > 0,
        "readiness generation mismatch",
    )
    require(
        all(record.get(key) is True for key in (
            "accessibilityTrusted", "tapOwnerActive", "serviceValidationComplete",
        )),
        "readiness prerequisites did not pass",
    )


def validate_setup_receipt(
    campaign_directory: Path,
    manifest: dict[str, Any],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    setup_binding = manifest.get("setup")
    require(isinstance(setup_binding, dict) and setup_binding.get("status") == "passed", "campaign setup is incomplete")
    path = campaign_directory / "setup.json"
    require_file_digest(path, setup_binding["receiptSha256"], "campaign setup receipt")
    receipt = json.loads(path.read_text())
    require(receipt.get("schemaVersion") == 2 and receipt.get("status") == "passed", "campaign setup receipt did not pass")
    require(receipt.get("consent") == {
        "sessionScoped": True,
        "categories": sorted(protocol["setup"]["requiredConsent"]),
    }, "campaign setup consent mismatch")
    require(receipt.get("physicalInputRequested") is False, "setup requested physical input")
    require(receipt.get("automaticTCCAction") is False, "setup performed automatic TCC action")
    records_value = receipt.get("candidates")
    if not isinstance(records_value, list):
        raise LiveGateFailure("campaign setup candidate records are missing")
    records: list[dict[str, Any]] = records_value
    require([record.get("candidate") for record in records] == protocol["setup"]["candidateOrder"], "campaign setup candidate order mismatch")
    for record in records:
        candidate = record["candidate"]
        require(record.get("manualGrantAcknowledged") is True, "manual Accessibility grant was not acknowledged")
        validate_readiness_record(record.get("readiness"), candidate, manifest["candidates"][candidate])
    return receipt


def launch_installed(module: ModuleType, binding: dict[str, Any], launch_arguments: list[str]) -> dict[str, Any]:
    identity = binding["applicationIdentity"]
    validate_installed_bundle(module, binding)
    installed = module.launch_and_verify(Path(identity["installedBundle"]), launch_arguments=launch_arguments, identity=identity)
    require(installed.get("pids") and len(installed["pids"]) == 1, "installed process count mismatch")
    require_file_digest(Path(identity["installedExecutable"]), binding["executableSha256"], "launched executable")
    return installed


def request_normal_quit(bundle_identifier: str) -> None:
    require(re.fullmatch(r"[A-Za-z0-9.-]+", bundle_identifier) is not None, "unsafe bundle identifier")
    run_checked([
        "/usr/bin/osascript", "-e", f'tell application id "{bundle_identifier}" to quit',
    ], timeout=15)


def run_live(campaign_directory: Path, workload: str, ordinal: int, consent: set[str]) -> dict[str, Any]:
    protocol = issue33_live_protocol.load_protocol(campaign_directory / PROTOCOL_PATH.name)
    manifest_path = campaign_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    require(manifest["status"] == "prepared", "campaign is not prepared")
    require_campaign_bindings(campaign_directory, manifest)
    validate_setup_receipt(campaign_directory, manifest, protocol)
    required = required_consent(workload)
    require(consent == required, f"consent mismatch; required exactly {sorted(required)}")
    scheduled = candidate_run(manifest, workload, ordinal)
    candidate = scheduled["candidate"]
    instrumentation = scheduled["instrumentation"]
    candidate_manifest = manifest["candidates"][candidate]
    worktree = Path(candidate_manifest["worktree"])
    require(candidate_state(worktree, candidate_manifest["sourceRef"])["sourceClosure"] == candidate_manifest["sourceClosure"], "candidate source changed after preparation")
    prepared_executable = Path(candidate_manifest["preparedExecutable"])
    require_file_digest(prepared_executable, candidate_manifest["executableSha256"], "prepared executable")
    run_directory = campaign_directory / "runs" / f"{workload}-{ordinal:02d}-{candidate}-{instrumentation}"
    require(not run_directory.exists(), "run directory already exists")
    run_directory.mkdir(parents=True)
    write_json(run_directory / "consent.json", {"sessionScoped": True, "categories": sorted(consent)})

    log_process: subprocess.Popen[str] | None = None
    log_output: Any = None
    log_error_output: Any = None
    sampler_stop = threading.Event()
    sampler: threading.Thread | None = None
    app_tool: ModuleType | None = None
    installed: dict[str, Any] | None = None
    readiness: dict[str, Any] | None = None
    boundaries: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    error: str | None = None
    log_path = run_directory / "unified-log.ndjson"
    samples_path = run_directory / "raw-samples.jsonl"
    latency_path = run_directory / "trace.json"
    environment: list[dict[str, Any]] = []
    try:
        probe = Path(manifest["environmentProbe"]["path"])
        require(sha256_file(probe) == manifest["environmentProbe"]["executableSha256"], "environment probe digest mismatch")
        log_process, log_output, log_error_output = start_log_stream(log_path)
        launch_arguments = readiness_arguments(candidate_manifest)
        if instrumentation == "full":
            launch_arguments += [
                "--diagnose-input-lifecycle",
                "--latency-evidence", str(latency_path),
                "--latency-revision", candidate_manifest["sourceRef"],
            ]
        app_tool = load_app_tool(ROOT, f"issue33_campaign_app_tool_{candidate.lower()}_run_{time.time_ns()}")
        validate_all_installed(app_tool, manifest)
        require_all_known_stopped(manifest, app_tool)
        installed = launch_installed(app_tool, candidate_manifest, launch_arguments)
        pid = installed["pids"][0]
        processes = known_processes(manifest, app_tool)
        require(processes[candidate] == [pid], "selected candidate process ownership mismatch")
        other = "B" if candidate == "A" else "A"
        require(not processes["production"] and not processes[other], "another application identity is running")
        readiness = wait_for_readiness(log_path, pid, {
            "candidate": candidate,
            "bundleIdentifier": candidate_manifest["applicationIdentity"]["bundleIdentifier"],
            "executableSha256": candidate_manifest["executableSha256"],
            "sourceRef": candidate_manifest["sourceRef"],
        })
        validate_readiness_record(readiness, candidate, candidate_manifest)
        environment.append(observe_environment(probe, "before"))
        sampler = threading.Thread(
            target=sample_until_stopped,
            args=(pid, samples_path, protocol["resourceSampling"]["pollIntervalMilliseconds"] / 1000, sampler_stop),
            daemon=True,
        )
        sampler.start()
        boundaries, observations = operator_phases(protocol, workload)
        request_normal_quit(installed["bundle_identifier"])
        deadline = time.monotonic() + 10
        installed_executable = Path(candidate_manifest["applicationIdentity"]["installedExecutable"])
        while time.monotonic() < deadline and app_tool.exact_processes(installed_executable):
            time.sleep(0.1)
        require(not app_tool.exact_processes(installed_executable), "application did not quit normally")
        after_environment = observe_environment(probe, "after")
        validate_environment(after_environment, environment[0])
        environment.append(after_environment)
    except Exception as caught:
        error = str(caught)
    finally:
        sampler_stop.set()
        if sampler is not None:
            sampler.join(timeout=2)
        if log_process is not None:
            stop_owned_process(log_process)
        if log_output is not None:
            log_output.close()
        if log_error_output is not None:
            log_error_output.close()
        if app_tool is not None:
            try:
                stop_bound_candidates(manifest, app_tool)
                require_all_known_stopped(manifest, app_tool)
            except Exception as cleanup_error:
                error = f"{error}; cleanup failed: {cleanup_error}" if error else f"cleanup failed: {cleanup_error}"

    samples = [json.loads(line) for line in samples_path.read_text().splitlines()] if samples_path.exists() else []
    derive_cpu_intervals(samples)
    report: dict[str, Any] = {
        "schemaVersion": 2,
        "status": "failed" if error else "captured",
        "candidate": candidate,
        "topology": protocol["candidates"][candidate]["topology"],
        "sourceRef": candidate_manifest["sourceRef"],
        "instrumentation": instrumentation,
        "workload": workload,
        "ordinal": ordinal,
        "schedule": scheduled,
        "pid": installed["pids"][0] if installed else None,
        "worktree": str(worktree),
        "runDirectory": str(run_directory),
        "installedExecutable": candidate_manifest["applicationIdentity"]["installedExecutable"],
        "executableSha256": candidate_manifest["executableSha256"],
        "protocolSha256": manifest["protocolSha256"],
        "readiness": readiness,
        "phaseBoundaries": boundaries,
        "operatorObservations": observations,
        "environmentObservations": environment,
        "resourceSummary": summarize_samples(samples),
        "phaseResourceSummaries": summarize_by_phase(samples, boundaries) if boundaries and samples else {},
        "error": error,
    }
    if instrumentation == "full" and installed is not None and log_path.exists():
        try:
            if app_tool is None:
                raise LiveGateFailure("candidate app tool was not loaded")
            lifecycle = read_lifecycle_log(log_path, installed["pids"][0])
            report["lifecycleRecords"] = lifecycle
            lifecycle_result = lifecycle_summary(lifecycle)
            require(lifecycle_result["complete"], "lifecycle trace is incomplete")
            require(
                lifecycle_result["accounting"]["capacity"] == protocol["normalWorkload"]["admissionCapacity"],
                "live admission capacity mismatch",
            )
            report["lifecycleSummary"] = lifecycle_result
            callbacks = callback_metrics(
                lifecycle, protocol["measurements"]["maximumEventToCallbackProxyNanoseconds"],
            )
            report["callbackMetrics"] = callbacks
            latency_evidence = app_tool.read_latency_evidence(
                latency_path, Path(candidate_manifest["applicationIdentity"]["installedExecutable"]),
            )
            report["latencyEvidenceSha256"] = sha256_file(latency_path)
            report["analysisMetrics"] = analysis_metrics(
                callbacks, latency_evidence, report["phaseResourceSummaries"],
            )
        except Exception as evidence_error:
            report["status"] = "failed"
            report["error"] = f"{report['error']}; evidence failed: {evidence_error}" if report["error"] else f"evidence failed: {evidence_error}"
    elif instrumentation == "none":
        if installed is None or not log_path.exists():
            raise LiveGateFailure("inactive-path log evidence is unavailable")
        require(not read_lifecycle_log(log_path, installed["pids"][0], require_records=False), "inactive path emitted lifecycle records")
        report["analysisMetrics"] = analysis_metrics([], None, report["phaseResourceSummaries"])
    write_json(run_directory / "report.json", report)
    write_json(run_directory / "publishable-report.json", publishable_projection(report))
    manifest["runs"].append({
        "workload": workload,
        "ordinal": ordinal,
        "candidate": candidate,
        "instrumentation": instrumentation,
        "status": report["status"],
        "reportSha256": sha256_file(run_directory / "report.json"),
    })
    write_json(manifest_path, manifest)
    if report["status"] != "captured":
        raise LiveGateFailure(report["error"] or "live run failed")
    return report


def setup_campaign(campaign_directory: Path, consent: set[str]) -> dict[str, Any]:
    protocol = issue33_live_protocol.load_protocol(campaign_directory / PROTOCOL_PATH.name)
    required = set(protocol["setup"]["requiredConsent"])
    require(consent == required, f"setup consent mismatch; required exactly {sorted(required)}")
    manifest_path = campaign_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    require_campaign_bindings(campaign_directory, manifest)
    require("setup" not in manifest, "campaign setup already passed")
    attempts = manifest.setdefault("setupAttempts", [])
    attempt_directory = campaign_directory / "setup-attempts" / f"attempt-{len(attempts) + 1:02d}"
    require(not attempt_directory.exists(), "setup attempt already exists")
    attempt_directory.mkdir(parents=True)
    write_json(attempt_directory / "consent.json", {"sessionScoped": True, "categories": sorted(consent)})
    module = load_app_tool(ROOT, f"issue33_campaign_app_tool_setup_{time.time_ns()}")
    records: list[dict[str, Any]] = []
    error: str | None = None
    try:
        require_all_known_stopped(manifest, module)
        for candidate in protocol["setup"]["candidateOrder"]:
            binding = manifest["candidates"][candidate]
            module.install_campaign_bundle(
                Path(binding["preparedBundle"]), binding["applicationIdentity"], launch_arguments=None,
            )
            validate_installed_bundle(module, binding)
        for candidate in protocol["setup"]["candidateOrder"]:
            binding = manifest["candidates"][candidate]
            identity = binding["applicationIdentity"]
            require_all_known_stopped(manifest, module)
            prompt_launch = module.launch_and_verify(
                Path(identity["installedBundle"]), launch_arguments=[], identity=identity,
            )
            require(
                input(f"Grant Accessibility manually to {identity['bundleName']}, then type GRANTED: ").strip() == "GRANTED",
                f"manual Accessibility grant not acknowledged for Candidate {candidate}",
            )
            module.stop_exact_processes(Path(identity["installedExecutable"]))
            require_all_known_stopped(manifest, module)
            log_path = attempt_directory / f"candidate-{candidate}-readiness.ndjson"
            log_process, log_output, log_error = start_log_stream(log_path)
            try:
                launched = launch_installed(module, binding, readiness_arguments(binding))
                readiness = wait_for_readiness(log_path, launched["pids"][0], {
                    "candidate": candidate,
                    "bundleIdentifier": identity["bundleIdentifier"],
                    "executableSha256": binding["executableSha256"],
                    "sourceRef": binding["sourceRef"],
                })
                validate_readiness_record(readiness, candidate, binding)
                records.append({"candidate": candidate, "manualGrantAcknowledged": True, "promptLaunch": prompt_launch, "readiness": readiness})
            finally:
                stop_owned_process(log_process)
                log_output.close()
                log_error.close()
                module.stop_exact_processes(Path(identity["installedExecutable"]))
                require_all_known_stopped(manifest, module)
        validate_all_installed(module, manifest)
    except Exception as caught:
        error = str(caught)
    finally:
        try:
            stop_bound_candidates(manifest, module)
            require_all_known_stopped(manifest, module)
        except Exception as cleanup_error:
            error = f"{error}; cleanup failed: {cleanup_error}" if error else f"cleanup failed: {cleanup_error}"
    receipt = {
        "schemaVersion": 2,
        "status": "failed" if error else "passed",
        "consent": {"sessionScoped": True, "categories": sorted(consent)},
        "candidates": records,
        "physicalInputRequested": False,
        "automaticTCCAction": False,
        "error": error,
    }
    receipt_path = attempt_directory / "setup.json"
    write_json(receipt_path, receipt)
    attempts.append({"status": receipt["status"], "receipt": str(receipt_path), "receiptSha256": sha256_file(receipt_path)})
    if not error:
        shutil.copy2(receipt_path, campaign_directory / "setup.json")
        manifest["setup"] = {"status": "passed", "receiptSha256": sha256_file(campaign_directory / "setup.json")}
    write_json(manifest_path, manifest)
    if error:
        raise LiveGateFailure(error)
    return receipt


def stop_installed_app(campaign_directory: Path) -> dict[str, Any]:
    manifest_path = campaign_directory / "manifest.json"
    require(manifest_path.is_file(), "campaign manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    require_campaign_bindings(campaign_directory, manifest, require_runner_identity=False)
    module = load_app_tool(ROOT, f"issue33_app_tool_stop_{time.time_ns()}")
    stopped = stop_bound_candidates(manifest, module)
    require_all_known_stopped(manifest, module)
    return {"status": "stopped", "candidates": stopped}


def cleanup_campaign(campaign_directory: Path, accessibility_removal_recorded: bool) -> dict[str, Any]:
    require(accessibility_removal_recorded, "manual Accessibility removal observation is required")
    manifest_path = campaign_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    require_campaign_bindings(campaign_directory, manifest, require_runner_identity=False)
    module = load_app_tool(ROOT, f"issue33_app_tool_cleanup_{time.time_ns()}")
    production_bundle = Path(manifest["productionApplication"]["installedBundle"])
    require(not production_bundle.is_symlink(), "production application bundle is an unsafe symlink")
    production_before = module.bundle_file_digests(production_bundle) if production_bundle.exists() else None
    stop_installed_app(campaign_directory)
    removed: list[str] = []
    for candidate, binding in manifest["candidates"].items():
        identity = binding["applicationIdentity"]
        bundle = Path(identity["installedBundle"])
        if not bundle.exists() and not bundle.is_symlink():
            continue
        validate_installed_bundle(module, binding)
        shutil.rmtree(bundle)
        require(not bundle.exists() and not bundle.is_symlink(), f"Candidate {candidate} bundle removal failed")
        removed.append(candidate)
    require_all_known_stopped(manifest, module)
    production_after = module.bundle_file_digests(production_bundle) if production_bundle.exists() else None
    require(production_after == production_before, "production application changed during cleanup")
    receipt = {
        "schemaVersion": 1,
        "status": "passed",
        "removedCandidates": removed,
        "manualAccessibilityRemovalRecorded": True,
        "productionApplicationUntouched": production_after == production_before,
    }
    write_json(campaign_directory / "cleanup.json", receipt)
    manifest["cleanup"] = {"status": "passed", "receiptSha256": sha256_file(campaign_directory / "cleanup.json")}
    write_json(manifest_path, manifest)
    return receipt


def expected_run_keys(manifest: dict[str, Any]) -> set[tuple[str, int]]:
    normal = {("normal", ordinal) for ordinal, _ in enumerate(manifest["normalSchedule"], start=1)}
    acceptance: set[tuple[str, int]] = set()
    for workload in ("lifecycle", "stress"):
        count = sum(item["workload"] == workload for item in manifest["acceptanceSchedule"])
        acceptance.update((workload, ordinal) for ordinal in range(1, count + 1))
    return normal | acceptance


def run_report_path(campaign_directory: Path, record: dict[str, Any]) -> Path:
    return campaign_directory / "runs" / (
        f"{record['workload']}-{record['ordinal']:02d}-{record['candidate']}-{record['instrumentation']}"
    ) / "report.json"


def load_campaign_reports(
    campaign_directory: Path, manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = manifest["runs"]
    keys = [(record["workload"], record["ordinal"]) for record in records]
    require(len(keys) == len(set(keys)), "campaign has duplicate run identities")
    missing = expected_run_keys(manifest) - set(keys)
    reports: list[dict[str, Any]] = []
    for record in records:
        path = run_report_path(campaign_directory, record)
        require(path.is_file(), "campaign report is missing")
        require_file_digest(path, record["reportSha256"], "campaign report")
        report = json.loads(path.read_text())
        for field in ("workload", "ordinal", "candidate", "instrumentation"):
            require(report[field] == record[field], f"campaign report {field} mismatch")
        reports.append(report)
    return reports, [
        {"workload": workload, "ordinal": ordinal}
        for workload, ordinal in sorted(missing)
    ]


def missing_required_metrics(
    normal_reports: list[dict[str, Any]], protocol: dict[str, Any],
) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for report in normal_reports:
        if report["status"] != "captured":
            continue
        required = required_metric_keys(protocol, report["instrumentation"])
        absent = sorted(required - set(report.get("analysisMetrics", {})))
        if absent:
            missing.append({
                "candidate": report["candidate"],
                "ordinal": report["ordinal"],
                "instrumentation": report["instrumentation"],
                "metrics": absent,
            })
    return missing


def metric_comparisons(normal_reports: list[dict[str, Any]], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    all_required = required_metric_keys(protocol, "full") | required_metric_keys(protocol, "none")
    direction_names = {
        metric.split(".")[1] if metric.startswith("timing.") else metric.split(".")[-2]
        for metric in all_required
    }
    require(
        direction_names == set(protocol["equivalence"]["lowerIsBetterMetrics"]),
        "metric directionality is not bound to every required metric",
    )
    for instrumentation in ("full", "none"):
        selected = [report for report in normal_reports if report["instrumentation"] == instrumentation]
        required_metrics = required_metric_keys(protocol, instrumentation)
        for report in selected:
            missing = required_metrics - set(report["analysisMetrics"])
            require(not missing, f"required {instrumentation} metrics missing: {sorted(missing)}")
        for metric in sorted(required_metrics):
            by_candidate: dict[str, list[float]] = {}
            for candidate in ("A", "B"):
                reports = sorted(
                    (report for report in selected if report["candidate"] == candidate),
                    key=lambda report: report["schedule"]["round"],
                )
                by_candidate[candidate] = [report["analysisMetrics"][metric] for report in reports]
            comparison = compare_metric_series(by_candidate["A"], by_candidate["B"], metric, protocol)
            comparison["instrumentation"] = instrumentation
            comparisons.append(comparison)
    return comparisons


def required_metric_keys(protocol: dict[str, Any], instrumentation: str) -> set[str]:
    phases = [phase["name"] for phase in protocol["normalWorkload"]["phases"]]
    resource = {
        f"resource.{phase}.{suffix}"
        for phase in phases
        for suffix in protocol["equivalence"]["resourceMetricSuffixes"]
    }
    if instrumentation == "none":
        return resource
    require(instrumentation == "full", "unknown instrumentation mode")
    timing = {
        f"timing.{name}.{statistic}"
        for name in protocol["equivalence"]["timingMetricNames"]
        for statistic in protocol["equivalence"]["normalFullTimingStatistics"]
    }
    return resource | timing


def instrumentation_overhead(normal_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for candidate in ("A", "B"):
        full = {
            report["schedule"]["round"]: report
            for report in normal_reports
            if report["candidate"] == candidate and report["instrumentation"] == "full"
        }
        none = {
            report["schedule"]["round"]: report
            for report in normal_reports
            if report["candidate"] == candidate and report["instrumentation"] == "none"
        }
        expected_rounds = set(range(1, len(full) + 1))
        require(set(full) == set(none) == expected_rounds, "instrumentation pairing mismatch")
        require(bool(expected_rounds), "instrumentation condition lacks paired rounds")
        common = set.intersection(*(
            set(full[round_number]["analysisMetrics"]) & set(none[round_number]["analysisMetrics"])
            for round_number in sorted(full)
        ))
        for metric in sorted(value for value in common if value.startswith("resource.")):
            differences = [
                full[round_number]["analysisMetrics"][metric] - none[round_number]["analysisMetrics"][metric]
                for round_number in sorted(full)
            ]
            results.append({
                "candidate": candidate,
                "metric": metric,
                "pairedRunCount": len(differences),
                "medianFullMinusInactive": float(statistics.median(differences)),
                "minimumFullMinusInactive": min(differences),
                "maximumFullMinusInactive": max(differences),
            })
    return results


def normal_accounting_gate(normal_reports: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for report in normal_reports:
        if report["instrumentation"] != "full":
            continue
        summary = report["lifecycleSummary"]
        events = summary["eventCounts"]
        handoffs = summary["handoffCounts"]
        accounting = summary["accounting"]
        reasons: list[str] = []
        rejected = accounting["rejected"] + accounting["discarded"] + accounting["overflow"]
        if rejected:
            reasons.append("rejectedOrDiscarded")
        if summary["budgetExhausted"] or not summary["complete"]:
            reasons.append("incompleteLifecycleTrace")
        if events.get("callbackEntered", 0) != events.get("callbackExited", 0):
            reasons.append("callbackPairMismatch")
        if events.get("callbackEntered", 0) != events.get("handoff", 0) + events.get("tapDisabled", 0):
            reasons.append("callbackAccountingMismatch")
        if handoffs.get("admitted", 0) != handoffs.get("pairedKeyUp", 0):
            reasons.append("admissionPairMismatch")
        if accounting["attempted"] != accounting["admitted"] + accounting["rejected"]:
            reasons.append("admissionAccountingMismatch")
        if accounting["admitted"] != accounting["completed"] + accounting["discarded"] + accounting["pending"]:
            reasons.append("completionAccountingMismatch")
        if accounting["peakOutstanding"] > accounting["capacity"]:
            reasons.append("capacityExceeded")
        if reasons:
            failures.append({
                "candidate": report["candidate"],
                "ordinal": report["ordinal"],
                "rejectedOrDiscardedCount": rejected,
                "reasons": reasons,
            })
    return {"status": "passed" if not failures else "failed", "failures": failures}


def report_evidence_sections(
    reports: list[dict[str, Any]], *, complete: bool,
) -> dict[str, Any]:
    manual_observations = [
        {
            "workload": report["workload"],
            "ordinal": report["ordinal"],
            "candidate": report["candidate"],
            "observations": report.get("operatorObservations", []),
        }
        for report in reports
        if report.get("operatorObservations")
    ]
    disabled_tap_observed = any(
        bool(report.get("lifecycleSummary", {}).get("tapDisabledCounts"))
        for report in reports
    )
    unavailable_scenarios = [] if disabled_tap_observed else [{
        "scenario": "disabledTap",
        "reason": "notNaturallyEmitted",
    }]
    unavailable_scenarios.extend(
        {
            "scenario": f"{report['workload']}:{report['ordinal']}",
            "reason": report.get("error") or report.get("status", "unavailable"),
        }
        for report in reports
        if report.get("status") != "captured"
    )
    verified_facts = ["retainedReportDigestsValidated"]
    if complete:
        verified_facts.extend([
            "candidateReadinessValidatedForEveryRun",
            "requiredRunAndMetricSetComplete",
            "setupAndCleanupReceiptsValidated",
        ])
    return {
        "verifiedFacts": verified_facts,
        "manualObservations": manual_observations,
        "unavailableScenarios": unavailable_scenarios,
        "residualRisks": [
            "manual observations remain human-attested rather than machine-derived",
            "a disabledTap event that did not occur naturally was not forced",
            "candidate comparison alone does not prove the originating incident resolved",
        ],
    }


def analyze_campaign(campaign_directory: Path, lifecycle_review: str) -> dict[str, Any]:
    protocol = issue33_live_protocol.load_protocol(campaign_directory / PROTOCOL_PATH.name)
    manifest_path = campaign_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    require_campaign_bindings(campaign_directory, manifest)
    setup = manifest.get("setup")
    cleanup = manifest.get("cleanup")
    prerequisite_failures: list[str] = []
    try:
        validate_setup_receipt(campaign_directory, manifest, protocol)
    except Exception:
        prerequisite_failures.append("setup")
    if not isinstance(cleanup, dict) or cleanup.get("status") != "passed":
        prerequisite_failures.append("cleanup")
    elif not (campaign_directory / "cleanup.json").is_file() or sha256_file(campaign_directory / "cleanup.json") != cleanup.get("receiptSha256"):
        prerequisite_failures.append("cleanupDigest")
    else:
        cleanup_receipt = json.loads((campaign_directory / "cleanup.json").read_text())
        if not (
            cleanup_receipt.get("schemaVersion") == 1
            and cleanup_receipt.get("status") == "passed"
            and set(cleanup_receipt.get("removedCandidates", [])) == {"A", "B"}
            and cleanup_receipt.get("manualAccessibilityRemovalRecorded") is True
            and cleanup_receipt.get("productionApplicationUntouched") is True
        ):
            prerequisite_failures.append("cleanupReceipt")
    reports, missing_runs = load_campaign_reports(campaign_directory, manifest)
    normal = [report for report in reports if report["workload"] == "normal"]
    acceptance = [report for report in reports if report["workload"] != "normal"]
    failed_runs = [
        {"workload": report["workload"], "ordinal": report["ordinal"], "candidate": report["candidate"]}
        for report in reports if report["status"] != "captured"
    ]
    absent_metrics = missing_required_metrics(normal, protocol)
    missing_readiness: list[dict[str, Any]] = []
    for report in reports:
        candidate = report["candidate"]
        try:
            validate_readiness_record(report.get("readiness"), candidate, manifest["candidates"][candidate])
        except Exception:
            missing_readiness.append({
                "workload": report["workload"],
                "ordinal": report["ordinal"],
                "candidate": candidate,
            })
    if prerequisite_failures or missing_runs or failed_runs or absent_metrics or missing_readiness:
        analysis = {
            "schemaVersion": 1,
            "status": "incomplete",
            "protocolSha256": manifest["protocolSha256"],
            "runCount": len(reports),
            "missingRuns": missing_runs,
            "failedRuns": failed_runs,
            "missingRequiredMetrics": absent_metrics,
            "missingReadiness": missing_readiness,
            "prerequisiteFailures": prerequisite_failures,
            "lifecycleReview": lifecycle_review,
            "metricComparisons": [],
            "selection": "inconclusive",
            "selectionRationale": "required evidence is missing or a retained run failed",
            **report_evidence_sections(reports, complete=False),
        }
        write_json(campaign_directory / "analysis.json", analysis)
        write_json(campaign_directory / "publishable-analysis.json", publishable_projection(analysis))
        return analysis
    require(len(normal) == protocol["normalWorkload"]["totalRuns"], "normal run count mismatch")
    require(len(acceptance) == protocol["acceptanceRuns"]["totalRuns"], "acceptance run count mismatch")
    require(all(all(item["passed"] for item in report["operatorObservations"]) for report in acceptance), "acceptance observation failed")
    accounting = normal_accounting_gate(normal)
    comparisons = metric_comparisons(normal, protocol)
    classifications = [item["classification"] for item in comparisons]
    lifecycle_green = lifecycle_review == "passed" and accounting["status"] == "passed"
    selection = select_candidate(classifications, lifecycle_green)
    analysis = {
        "schemaVersion": 1,
        "status": "complete",
        "protocolSha256": manifest["protocolSha256"],
        "runCount": len(reports),
        "normalAccounting": accounting,
        "lifecycleReview": lifecycle_review,
        "metricComparisons": comparisons,
        "instrumentationOverhead": instrumentation_overhead(normal),
        "acceptanceSummaries": [
            {
                "workload": report["workload"],
                "candidate": report["candidate"],
                "operatorObservations": report["operatorObservations"],
                "lifecycleSummary": report["lifecycleSummary"],
                "phaseResourceSummaries": report["phaseResourceSummaries"],
            }
            for report in acceptance
        ],
        "selection": selection,
        "selectionRationale": "frozen paired bootstrap and repeatability-noise rule",
        **report_evidence_sections(reports, complete=True),
    }
    write_json(campaign_directory / "analysis.json", analysis)
    write_json(campaign_directory / "publishable-analysis.json", publishable_projection(analysis))
    return analysis


def doctor(worktrees: dict[str, Path]) -> dict[str, Any]:
    protocol = issue33_live_protocol.load_protocol(PROTOCOL_PATH)
    states = {
        candidate: candidate_state(worktrees[candidate], protocol["candidates"][candidate]["sourceRef"])
        for candidate in ("A", "B")
    }
    return {
        "status": "readyForOfflinePreparation",
        "protocolSha256": sha256_file(PROTOCOL_PATH),
        "candidates": {
            candidate: {
                "sourceRef": state["sourceRef"],
                "sourceFileCount": len(state["sourceClosure"]),
            }
            for candidate, state in states.items()
        },
        "runtimeConsentGranted": False,
    }


def emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def worktree_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidate-a-worktree", type=Path, required=True)
    parser.add_argument("--candidate-b-worktree", type=Path, required=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    doctor_parser = commands.add_parser("doctor")
    worktree_arguments(doctor_parser)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--campaign-dir", type=Path, required=True)
    worktree_arguments(prepare_parser)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--campaign-dir", type=Path, required=True)
    run_parser.add_argument("--workload", choices=("normal", "lifecycle", "stress"), required=True)
    run_parser.add_argument("--ordinal", type=int, required=True)
    run_parser.add_argument("--consent", action="append", default=[])
    setup_parser = commands.add_parser("setup")
    setup_parser.add_argument("--campaign-dir", type=Path, required=True)
    setup_parser.add_argument("--consent", action="append", default=[])
    analyze_parser = commands.add_parser("analyze")
    analyze_parser.add_argument("--campaign-dir", type=Path, required=True)
    analyze_parser.add_argument("--lifecycle-review", choices=("passed", "failed", "incomplete"), required=True)
    stop_parser = commands.add_parser("stop")
    stop_parser.add_argument("--campaign-dir", type=Path, required=True)
    cleanup_parser = commands.add_parser("cleanup")
    cleanup_parser.add_argument("--campaign-dir", type=Path, required=True)
    cleanup_parser.add_argument("--accessibility-removal-recorded", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.command == "doctor":
            result = doctor({"A": arguments.candidate_a_worktree.resolve(), "B": arguments.candidate_b_worktree.resolve()})
        elif arguments.command == "prepare":
            result = prepare(
                arguments.campaign_dir.resolve(),
                {"A": arguments.candidate_a_worktree.resolve(), "B": arguments.candidate_b_worktree.resolve()},
            )
        elif arguments.command == "run":
            LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOCK_PATH.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = run_live(
                    arguments.campaign_dir.resolve(), arguments.workload, arguments.ordinal,
                    set(arguments.consent),
                )
        elif arguments.command == "setup":
            LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOCK_PATH.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = setup_campaign(arguments.campaign_dir.resolve(), set(arguments.consent))
        elif arguments.command == "analyze":
            result = analyze_campaign(arguments.campaign_dir.resolve(), arguments.lifecycle_review)
        elif arguments.command == "stop":
            result = stop_installed_app(arguments.campaign_dir.resolve())
        else:
            result = cleanup_campaign(arguments.campaign_dir.resolve(), arguments.accessibility_removal_recorded)
        emit(result)
        return 0
    except Exception as error:
        emit({"status": "failed", "error": str(error)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
