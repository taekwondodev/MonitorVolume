#!/usr/bin/env python3

import argparse
import ast
import json
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


APP_NAME = "ProArt Volume"
EXECUTABLE_NAME = "ProArtVolume"
ROOT = Path(__file__).resolve().parents[1]
SOURCE_PLIST = ROOT / "Resources" / "Info.plist"
INSTALLED_BUNDLE = Path.home() / "Applications" / f"{APP_NAME}.app"
INSTALLED_EXECUTABLE = INSTALLED_BUNDLE / "Contents" / "MacOS" / EXECUTABLE_NAME


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run(command: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed ({' '.join(command)}): {detail}")
    return result


def read_metadata(path: Path) -> Dict[str, Any]:
    with path.open("rb") as file:
        return plistlib.load(file)


def source_metadata() -> Dict[str, Any]:
    metadata = read_metadata(SOURCE_PLIST)
    required_values = {
        "CFBundleExecutable": EXECUTABLE_NAME,
        "CFBundleName": APP_NAME,
        "CFBundlePackageType": "APPL",
        "LSUIElement": True,
    }
    mismatches = {
        key: {"expected": expected, "actual": metadata.get(key)}
        for key, expected in required_values.items()
        if metadata.get(key) != expected
    }
    required_strings = (
        "CFBundleIdentifier",
        "CFBundleShortVersionString",
        "CFBundleVersion",
        "LSMinimumSystemVersion",
    )
    missing_strings = [key for key in required_strings if not isinstance(metadata.get(key), str) or not metadata[key]]
    if mismatches or missing_strings:
        raise RuntimeError(
            f"Source bundle metadata is invalid: {json.dumps({'mismatches': mismatches, 'missing_strings': missing_strings}, sort_keys=True)}"
        )
    return metadata


def load_metadata(path: Path) -> Dict[str, Any]:
    expected = source_metadata()
    metadata = read_metadata(path)
    if metadata != expected:
        raise RuntimeError("Bundle metadata does not match Resources/Info.plist")
    return metadata


def build_release() -> Path:
    run(
        [
            "swift",
            "build",
            "-c",
            "release",
            "-Xswiftc",
            "-strict-concurrency=complete",
        ],
        cwd=ROOT,
    )
    executable = ROOT / ".build" / "release" / EXECUTABLE_NAME
    if not executable.is_file():
        raise RuntimeError(f"Release executable is missing: {executable}")
    return executable


def assemble_bundle(destination: Path, source_executable: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"Staging destination already exists: {destination}")
    executable_dir = destination / "Contents" / "MacOS"
    executable_dir.mkdir(parents=True)
    shutil.copy2(source_executable, executable_dir / EXECUTABLE_NAME)
    shutil.copy2(SOURCE_PLIST, destination / "Contents" / "Info.plist")
    load_metadata(destination / "Contents" / "Info.plist")
    run(["codesign", "--force", "--sign", "-", str(destination)])
    verify_bundle(destination, require_live_process=False)


def exact_processes(executable: Path) -> List[int]:
    result = run(["ps", "-axo", "pid=,comm="])
    target = str(executable.absolute())
    matches = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) == 2 and fields[1] == target:
            matches.append(int(fields[0]))
    return matches


def stop_installed_app() -> List[int]:
    if not INSTALLED_BUNDLE.exists() and not INSTALLED_BUNDLE.is_symlink():
        return []
    verify_bundle(INSTALLED_BUNDLE, require_live_process=False)
    stopped = []
    for pid in exact_processes(INSTALLED_EXECUTABLE):
        current = exact_processes(INSTALLED_EXECUTABLE)
        if pid not in current:
            continue
        os.kill(pid, signal.SIGTERM)
        stopped.append(pid)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and exact_processes(INSTALLED_EXECUTABLE):
        time.sleep(0.1)
    survivors = exact_processes(INSTALLED_EXECUTABLE)
    for pid in survivors:
        current = exact_processes(INSTALLED_EXECUTABLE)
        if pid in current:
            os.kill(pid, signal.SIGKILL)
    if survivors:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and exact_processes(INSTALLED_EXECUTABLE):
            time.sleep(0.1)
    if exact_processes(INSTALLED_EXECUTABLE):
        raise RuntimeError("The exact installed application process survived termination")
    return sorted(set(stopped + survivors))


def verify_bundle(bundle: Path, require_live_process: bool) -> Dict[str, Any]:
    contents = bundle / "Contents"
    executable_dir = contents / "MacOS"
    executable = executable_dir / EXECUTABLE_NAME
    if any(path.is_symlink() for path in (bundle, contents, executable_dir, executable)):
        raise RuntimeError(f"Application bundle contains an unsafe symlink: {bundle}")
    if not bundle.is_dir():
        raise RuntimeError(f"Application bundle is missing or unsafe: {bundle}")
    plist = contents / "Info.plist"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError(f"Bundle executable is missing or unsafe: {executable}")
    metadata = load_metadata(plist)
    run(["codesign", "--verify", "--deep", "--strict", str(bundle)])
    pids = exact_processes(executable)
    if require_live_process and len(pids) != 1:
        raise RuntimeError(f"Expected one exact installed process, found {pids}")
    return {
        "bundle": str(bundle),
        "bundle_identifier": metadata["CFBundleIdentifier"],
        "executable": str(executable),
        "ls_ui_element": metadata["LSUIElement"],
        "pids": pids,
        "signature": "valid",
    }


def reconcile_backup(backup: Path) -> None:
    if not backup.exists() and not backup.is_symlink():
        return
    if backup.is_symlink() or not backup.is_dir():
        raise RuntimeError(f"Backup path is unsafe: {backup}")
    verify_bundle(backup, require_live_process=False)
    if not INSTALLED_BUNDLE.exists() and not INSTALLED_BUNDLE.is_symlink():
        backup.rename(INSTALLED_BUNDLE)
        return
    verify_bundle(INSTALLED_BUNDLE, require_live_process=False)
    shutil.rmtree(backup)


def launch_and_verify(bundle: Path) -> Dict[str, Any]:
    run(["open", "-n", "-a", str(bundle)])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if len(exact_processes(INSTALLED_EXECUTABLE)) == 1:
            break
        time.sleep(0.1)
    return verify_bundle(bundle, require_live_process=True)


def rollback_install(backup: Path, replaced: bool, was_running: bool) -> None:
    if INSTALLED_BUNDLE.exists() or INSTALLED_BUNDLE.is_symlink():
        stop_installed_app()
        shutil.rmtree(INSTALLED_BUNDLE)
    if replaced:
        if not backup.exists() or backup.is_symlink():
            raise RuntimeError("Previous application backup is unavailable for rollback")
        backup.rename(INSTALLED_BUNDLE)
        if was_running:
            launch_and_verify(INSTALLED_BUNDLE)


def install_and_launch() -> Dict[str, Any]:
    applications = INSTALLED_BUNDLE.parent
    if applications.is_symlink():
        raise RuntimeError(f"Applications directory must not be a symlink: {applications}")
    applications.mkdir(parents=True, exist_ok=True)
    backup = applications / f".{INSTALLED_BUNDLE.name}.backup"
    reconcile_backup(backup)
    if INSTALLED_BUNDLE.is_symlink():
        raise RuntimeError(f"Installed bundle must not be a symlink: {INSTALLED_BUNDLE}")
    if INSTALLED_BUNDLE.exists():
        verify_bundle(INSTALLED_BUNDLE, require_live_process=False)
    source_executable = build_release()
    staging_root = Path(tempfile.mkdtemp(prefix=".ProArtVolume-install-", dir=applications))
    staged_bundle = staging_root / INSTALLED_BUNDLE.name
    try:
        assemble_bundle(staged_bundle, source_executable)
        stopped = stop_installed_app()
        replaced = INSTALLED_BUNDLE.exists()
        try:
            if replaced:
                INSTALLED_BUNDLE.rename(backup)
            staged_bundle.rename(INSTALLED_BUNDLE)
            verified = launch_and_verify(INSTALLED_BUNDLE)
        except Exception as install_error:
            try:
                rollback_install(backup, replaced, bool(stopped))
            except Exception as rollback_error:
                raise RuntimeError(f"Install failed ({install_error}); rollback failed ({rollback_error})") from rollback_error
            raise
        backup_cleanup_pending = False
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except Exception:
                backup_cleanup_pending = True
        return {
            "status": "installed",
            "backup_cleanup_pending": backup_cleanup_pending,
            "replaced_existing_bundle": replaced,
            "stopped_pids": stopped,
            **verified,
        }
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def check_source() -> Dict[str, Any]:
    build_release()
    shell_scripts = sorted((ROOT / "scripts").glob("*.sh"))
    for script in shell_scripts:
        run(["bash", "-n", str(script)])
    python_files = [
        ROOT / "scripts" / "app_tool.py",
        ROOT / "Tests" / "Tooling" / "command_surface_test.py",
        ROOT / ".hermes" / "skills" / "verify-proart-volume" / "scripts" / "verify.py",
    ]
    for path in python_files:
        ast.parse(path.read_text(), filename=str(path))
    load_metadata(SOURCE_PLIST)
    run([sys.executable, str(ROOT / "Tests" / "Tooling" / "command_surface_test.py")], cwd=ROOT)
    return {
        "status": "passed",
        "release_strict_concurrency": True,
        "shell_scripts_checked": [str(path.relative_to(ROOT)) for path in shell_scripts],
        "python_files_checked": [str(path.relative_to(ROOT)) for path in python_files],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "check", "stop", "verify"))
    arguments = parser.parse_args()
    try:
        if arguments.command == "build":
            result = install_and_launch()
        elif arguments.command == "check":
            result = check_source()
        elif arguments.command == "stop":
            result = {"status": "stopped", "pids": stop_installed_app()}
        else:
            result = {"status": "passed", **verify_bundle(INSTALLED_BUNDLE, require_live_process=True)}
        emit(result)
        return 0
    except Exception as error:
        emit({"status": "failed", "error": str(error)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
