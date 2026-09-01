#!/usr/bin/env python3

import argparse
import json
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

APP_EXECUTABLE = "ProArtVolume"
APP_NAME = "ProArt Volume"


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def verification_root() -> Path:
    return repository_root() / ".hermes" / "verification"


def emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run(command: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)


def load_state(path: str) -> tuple[Path, dict]:
    state_path = Path(path).resolve()
    state = json.loads(state_path.read_text())
    expected_root = repository_root().resolve()
    if Path(state["repository_root"]).resolve() != expected_root:
        raise RuntimeError("State belongs to a different repository")
    return state_path, state


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def process_command(pid: int) -> Optional[str]:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        text=True,
        capture_output=True,
        check=False,
    )
    command = result.stdout.strip()
    return command or None


def matching_pids(executable: Path) -> list[int]:
    result = run(["ps", "-axo", "pid=,command="])
    target = str(executable.resolve())
    matches = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if target in command:
            matches.append(int(pid_text))
    return matches


def prepare() -> dict:
    root = repository_root().resolve()
    run_id = uuid.uuid4().hex
    run_dir = verification_root() / "runs" / run_id
    build_dir = run_dir / "build"
    bundle = run_dir / f"{APP_NAME}.app"
    contents = bundle / "Contents"
    executable_dir = contents / "MacOS"
    executable_dir.mkdir(parents=True)
    run(
        [
            "swift",
            "build",
            "-c",
            "release",
            "--scratch-path",
            str(build_dir),
            "-Xswiftc",
            "-strict-concurrency=complete",
        ],
        cwd=root,
    )
    source_executable = build_dir / "release" / APP_EXECUTABLE
    destination_executable = executable_dir / APP_EXECUTABLE
    shutil.copy2(source_executable, destination_executable)
    identifier = f"dev.taekwondodev.ProArtVolume.verify.{run_id}"
    plist = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleExecutable": APP_EXECUTABLE,
        "CFBundleIdentifier": identifier,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "15.0",
        "LSUIElement": True,
    }
    with (contents / "Info.plist").open("wb") as file:
        plistlib.dump(plist, file)
    run(["codesign", "--force", "--sign", "-", str(bundle)])
    state_path = run_dir / "state.json"
    evidence_dir = verification_root() / "evidence" / run_id
    state = {
        "bundle": str(bundle.resolve()),
        "bundle_identifier": identifier,
        "evidence_dir": str(evidence_dir.resolve()),
        "executable": str(destination_executable.resolve()),
        "pid": None,
        "repository_root": str(root),
        "run_dir": str(run_dir.resolve()),
        "run_id": run_id,
    }
    save_state(state_path, state)
    return {"status": "prepared", "state": str(state_path), "bundle": str(bundle)}


def doctor(state_path_text: str) -> dict:
    _, state = load_state(state_path_text)
    bundle = Path(state["bundle"])
    executable = Path(state["executable"])
    plist_path = bundle / "Contents" / "Info.plist"
    if not bundle.is_dir() or not executable.is_file() or not plist_path.is_file():
        raise RuntimeError("Prepared bundle is incomplete")
    with plist_path.open("rb") as file:
        plist = plistlib.load(file)
    if plist.get("CFBundleExecutable") != APP_EXECUTABLE:
        raise RuntimeError("Bundle executable identity does not match")
    if plist.get("CFBundleIdentifier") != state["bundle_identifier"]:
        raise RuntimeError("Bundle identifier does not match state")
    if plist.get("LSUIElement") is not True:
        raise RuntimeError("Bundle is not configured as a menu-bar agent")
    run(["codesign", "--verify", "--strict", str(bundle)])
    return {
        "status": "healthy",
        "bundle": str(bundle),
        "bundle_identifier": state["bundle_identifier"],
        "executable": str(executable),
        "ls_ui_element": True,
    }


def drive(state_path_text: str) -> dict:
    state_path, state = load_state(state_path_text)
    bundle = Path(state["bundle"])
    executable = Path(state["executable"])
    existing = matching_pids(executable)
    if existing:
        raise RuntimeError(f"Owned bundle is already running: {existing}")
    run(["open", "-n", "-a", str(bundle)])
    deadline = time.monotonic() + 10
    pids = []
    while time.monotonic() < deadline:
        pids = matching_pids(executable)
        if len(pids) == 1:
            break
        time.sleep(0.1)
    if len(pids) != 1:
        raise RuntimeError(f"Expected one owned process, found {pids}")
    pid = pids[0]
    state["pid"] = pid
    save_state(state_path, state)
    first_command = process_command(pid)
    time.sleep(1)
    second_command = process_command(pid)
    if not first_command or not second_command or str(executable) not in second_command:
        raise RuntimeError("Owned process did not remain alive")
    evidence_dir = Path(state["evidence_dir"])
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "launch.json"
    evidence = {
        "action": "open bundle through Launch Services",
        "bundle": str(bundle),
        "bundle_identifier": state["bundle_identifier"],
        "executable": str(executable),
        "launch_method": "open -n -a",
        "pass_condition": "exact prepared executable remains alive after launch",
        "pid": pid,
        "process_command": second_command,
        "status": "passed",
    }
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return {"status": "passed", "evidence": str(evidence_path), "pid": pid}


def cleanup(state_path_text: str) -> dict:
    state_path, state = load_state(state_path_text)
    pid = state.get("pid")
    executable = str(Path(state["executable"]).resolve())
    if pid is not None:
        command = process_command(pid)
        if command and executable in command:
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and process_command(pid):
                time.sleep(0.1)
            if process_command(pid):
                os.kill(pid, signal.SIGKILL)
        if process_command(pid):
            raise RuntimeError("Owned process survived cleanup")
    run_dir = Path(state["run_dir"])
    shutil.rmtree(run_dir)
    return {"status": "clean", "removed": str(run_dir), "evidence_preserved": state["evidence_dir"]}


def prove() -> dict:
    prepared = prepare()
    state_path = prepared["state"]
    evidence = None
    failure = None
    try:
        doctor(state_path)
        evidence = drive(state_path)
    except Exception as error:
        failure = error
    cleanup_result = cleanup(state_path)
    if failure is not None:
        raise failure
    if evidence is None:
        raise RuntimeError("Drive completed without evidence")
    evidence_path = Path(evidence["evidence"])
    if not evidence_path.is_file():
        raise RuntimeError("Evidence did not survive cleanup")
    return {
        "status": "passed",
        "capability": "launch menu-bar agent",
        "evidence": str(evidence_path),
        "cleanup": cleanup_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    for name in ("doctor", "drive", "cleanup"):
        command = subparsers.add_parser(name)
        command.add_argument("--state", required=True)
    subparsers.add_parser("prove")
    arguments = parser.parse_args()
    try:
        if arguments.command == "prepare":
            result = prepare()
        elif arguments.command == "doctor":
            result = doctor(arguments.state)
        elif arguments.command == "drive":
            result = drive(arguments.state)
        elif arguments.command == "cleanup":
            result = cleanup(arguments.state)
        else:
            result = prove()
        emit(result)
        return 0
    except Exception as error:
        emit({"status": "failed", "error": str(error)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
