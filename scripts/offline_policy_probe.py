#!/usr/bin/env python3

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "Sources/ProArtVolumeCore/Domain"
SOURCES = (
    "ControlEligibility.swift", "MediaKey.swift", "VolumeStep.swift",
    "VolumeLevel.swift", "MuteState.swift", "ConfirmedMonitorState.swift",
    "MonitorRepositoryError.swift",
)
EXPECTED_SCENARIOS = {
    "active_sleep_current_signal:missingPermission",
    "active_sleep_current_signal:permissionRevoked",
    "active_sleep_current_signal:tapDisabledByTimeout",
    "active_sleep_current_signal:tapDisabledByUserInput",
    "active_sleep_current_signal:deliveryOverflow",
    "active_sleep_current_signal:tapCreationFailed",
    "unavailable_sleep_current_signal:missingPermission",
    "unavailable_sleep_current_signal:permissionRevoked",
    "unavailable_sleep_current_signal:tapDisabledByTimeout",
    "unavailable_sleep_current_signal:tapDisabledByUserInput",
    "unavailable_sleep_current_signal:deliveryOverflow",
    "unavailable_sleep_current_signal:tapCreationFailed",
    "active_sleep_stale_signal:missingPermission",
    "active_sleep_stale_signal:permissionRevoked",
    "active_sleep_stale_signal:tapDisabledByTimeout",
    "active_sleep_stale_signal:tapDisabledByUserInput",
    "active_sleep_stale_signal:deliveryOverflow",
    "active_sleep_stale_signal:tapCreationFailed",
    "unavailable_sleep_stale_signal:missingPermission",
    "unavailable_sleep_stale_signal:permissionRevoked",
    "unavailable_sleep_stale_signal:tapDisabledByTimeout",
    "unavailable_sleep_stale_signal:tapDisabledByUserInput",
    "unavailable_sleep_stale_signal:deliveryOverflow",
    "unavailable_sleep_stale_signal:tapCreationFailed",
    "signal_before_sleep:missingPermission",
    "signal_before_sleep:permissionRevoked",
    "signal_before_sleep:tapDisabledByTimeout",
    "signal_before_sleep:tapDisabledByUserInput",
    "signal_before_sleep:deliveryOverflow",
    "signal_before_sleep:tapCreationFailed",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(arguments):
    return subprocess.run(
        arguments, cwd=ROOT, check=True, capture_output=True, timeout=120,
    ).stdout


def collect(ref, folder, probe_content):
    revision = command(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"]).decode().strip()
    folder.mkdir()
    sources = []
    bindings = {}
    for name in SOURCES:
        content = command(["git", "show", f"{revision}:{DOMAIN}/{name}"])
        path = folder / name
        path.write_bytes(content)
        sources.append(str(path))
        bindings[f"{DOMAIN}/{name}"] = digest(content)
    probe = folder / "OfflinePolicyProbe.swift"
    probe.write_bytes(probe_content)
    executable = folder / "OfflinePolicyProbe"
    flags = ["-O", "-swift-version", "6", "-strict-concurrency=complete", "-package-name", "ProArtVolume", "-parse-as-library"]
    build = subprocess.run(
        ["swiftc", *flags, *sources, str(probe), "-o", str(executable)],
        cwd=ROOT, capture_output=True, timeout=120,
    )
    (folder / "build.stdout").write_bytes(build.stdout)
    (folder / "build.stderr").write_bytes(build.stderr)
    build.check_returncode()
    raw = command([str(executable)])
    (folder / "observations.json").write_bytes(raw)
    observations = json.loads(raw)
    names = [observation["scenario"] for observation in observations]
    if len(names) != len(EXPECTED_SCENARIOS) or set(names) != EXPECTED_SCENARIOS:
        raise ValueError("Policy probe did not emit the expected unique scenario matrix")
    return {
        "revision": revision,
        "sourceHashes": bindings,
        "probeHash": digest(probe_content),
        "executableHash": digest(executable.read_bytes()),
        "compilerFlags": flags,
        "observations": observations,
    }


def main():
    parser = argparse.ArgumentParser(description="Observe real Domain policy parity without any app or framework drive.")
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    compiler = command(["swiftc", "--version"]).decode().strip()
    probe_content = (ROOT / "scripts" / "OfflinePolicyProbe.swift").read_bytes()
    a = collect(arguments.a, output / "A", probe_content)
    b = collect(arguments.b, output / "B", probe_content)
    if a["probeHash"] != b["probeHash"]:
        raise ValueError("Candidate observations were produced by different probes")
    b_observations = {item["scenario"]: item for item in b["observations"]}
    differences = [
        {"scenario": item["scenario"], "A": item, "B": b_observations[item["scenario"]]}
        for item in a["observations"] if item != b_observations[item["scenario"]]
    ]
    report = {
        "executionClass": "offline_domain_policy_probe",
        "compiler": compiler,
        "candidates": {"A": a, "B": b},
        "scenarioCountPerCandidate": len(a["observations"]),
        "differenceCount": len(differences),
        "differences": differences,
        "parity": "different" if differences else "equal_for_probed_scenarios_only",
        "scope": "Compiles exact committed Domain source. No Handler, app launch, permission query, system input, OSD, DDC or performance claim. Manual full-diff review remains required.",
    }
    (output / "policy-parity.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("executionClass", "scenarioCountPerCandidate", "differenceCount", "parity")}, indent=2))
    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
