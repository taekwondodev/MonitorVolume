#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PRODUCT = "ProArtVolumeIssue32Conformance"
BUILD_COMMAND = [
    "swift",
    "build",
    "-c",
    "release",
    "-Xswiftc",
    "-strict-concurrency=complete",
    "--product",
    PRODUCT,
]
BRIDGE_SOURCES = [
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
]
EXPECTED_SCENARIOS_PATH = Path(__file__).with_name("issue32_expected_scenarios.json")
EXPECTED_CONTRACT = json.loads(EXPECTED_SCENARIOS_PATH.read_text())
EXPECTED_SCENARIOS = EXPECTED_CONTRACT["scenarios"]
EXPECTED_TOPOLOGIES = EXPECTED_CONTRACT["topologies"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)


def required_sources(worktree: Path) -> list[Path]:
    paths = [worktree / "Package.swift"]
    for directory in (worktree / "Sources" / "MonitorTransport", worktree / "Sources" / "ProArtVolumeCore"):
        paths.extend(path for path in directory.rglob("*") if path.is_file())
    paths.extend(worktree / relative for relative in BRIDGE_SOURCES)
    owner = worktree / "Sources/ProArtVolume/Handler/DedicatedMediaKeyTapOwner.swift"
    if owner.is_file():
        paths.append(owner)
    missing = [str(path.relative_to(worktree)) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing source closure: {missing}")
    return sorted(set(paths))


def git_value(worktree: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=worktree,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def write_text(path: Path, value: str) -> None:
    path.write_text(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    arguments = parser.parse_args()

    worktree = arguments.worktree.resolve()
    evidence = arguments.evidence_dir.resolve()
    if evidence.exists():
        raise RuntimeError(f"evidence directory already exists: {evidence}")
    evidence.mkdir(parents=True)

    sources = required_sources(worktree)
    env = os.environ.copy()
    env["ISSUE_32_CONFORMANCE"] = "1"
    compiler = run(["swift", "--version"], worktree, env)
    write_text(evidence / "compiler.txt", compiler.stdout + compiler.stderr)

    build = run(BUILD_COMMAND, worktree, env)
    write_text(evidence / "build-stdout.txt", build.stdout)
    write_text(evidence / "build-stderr.txt", build.stderr)
    write_text(evidence / "build-exit.txt", f"{build.returncode}\n")

    executable = worktree / ".build" / "release" / PRODUCT
    run_result: subprocess.CompletedProcess[str] | None = None
    report: dict[str, Any] | None = None
    validation_failures: list[str] = []
    if build.returncode == 0 and executable.is_file():
        retained_executable = evidence / PRODUCT
        shutil.copy2(executable, retained_executable)
        run_result = run([str(executable)], worktree, env)
        write_text(evidence / "stdout.json", run_result.stdout)
        write_text(evidence / "stderr.txt", run_result.stderr)
        write_text(evidence / "exit.txt", f"{run_result.returncode}\n")
        try:
            report = json.loads(run_result.stdout)
        except json.JSONDecodeError:
            validation_failures.append("invalidJSON")
        if report is not None:
            if report.get("schemaVersion") != 2:
                validation_failures.append("schemaVersionMismatch")
            if report.get("failures") != []:
                validation_failures.append("reportedFailure")
            if report.get("scenarios") != EXPECTED_SCENARIOS:
                validation_failures.append("expectedMatrixMismatch")
            candidate = "B" if any(path.name == "DedicatedMediaKeyTapOwner.swift" for path in sources) else "A"
            expected_topology = EXPECTED_TOPOLOGIES[candidate]
            if report.get("topology") != expected_topology:
                validation_failures.append("topologyMismatch")
    else:
        write_text(evidence / "stdout.json", "")
        write_text(evidence / "stderr.txt", "executable unavailable\n")
        write_text(evidence / "exit.txt", "not-run\n")
        validation_failures.append("buildFailed")

    source_bindings = [
        {
            "path": str(path.relative_to(worktree)),
            "sha256": sha256(path),
        }
        for path in sources
    ]
    driver = worktree / "Sources/ProArtVolumeIssue32Conformance/ScenarioDriver.swift"
    binding = worktree / "Sources/ProArtVolumeIssue32Conformance/CandidateBinding.swift"
    metadata = {
        "schemaVersion": 1,
        "candidateHead": git_value(worktree, "rev-parse", "HEAD"),
        "candidateBranch": git_value(worktree, "branch", "--show-current"),
        "candidateDiffSha256": hashlib.sha256(
            subprocess.run(
                ["git", "diff", "--binary", "HEAD"],
                cwd=worktree,
                capture_output=True,
                check=True,
            ).stdout
        ).hexdigest(),
        "configuration": "release",
        "swiftFlags": ["-strict-concurrency=complete", "ISSUE_32_CONFORMANCE=1"],
        "capacity": 8,
        "driverSha256": sha256(driver),
        "bindingSha256": sha256(binding),
        "executableSha256": sha256(evidence / PRODUCT) if (evidence / PRODUCT).is_file() else None,
        "sourceClosure": source_bindings,
        "buildExit": build.returncode,
        "runExit": run_result.returncode if run_result is not None else None,
        "validationFailures": validation_failures,
    }
    (evidence / "binding.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    shutil.copy2(driver, evidence / "ScenarioDriver.swift")
    shutil.copy2(binding, evidence / "CandidateBinding.swift")
    for shared_scenario in ("ApparatusScenarios.swift", "DeliveryScenarios.swift", "FencingScenarios.swift"):
        shutil.copy2(
            worktree / "Sources/ProArtVolumeIssue32Conformance" / shared_scenario,
            evidence / shared_scenario,
        )
    return 0 if build.returncode == 0 and run_result is not None and run_result.returncode == 0 and not validation_failures else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
