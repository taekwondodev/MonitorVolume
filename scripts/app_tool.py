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
SOURCE_NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
SOURCE_ASSETS = ROOT / "Resources" / "Media.xcassets"
APP_ICON_NAME = "AppIcon"
INSTALLED_BUNDLE = Path.home() / "Applications" / f"{APP_NAME}.app"
INSTALLED_EXECUTABLE = INSTALLED_BUNDLE / "Contents" / "MacOS" / EXECUTABLE_NAME


def application_identity(identity: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    if identity is None:
        identity = {
            "bundleIdentifier": source_metadata()["CFBundleIdentifier"],
            "bundleName": APP_NAME,
            "installedBundle": str(INSTALLED_BUNDLE),
            "executableName": EXECUTABLE_NAME,
        }
    required = {"bundleIdentifier", "bundleName", "installedBundle", "executableName"}
    if not required.issubset(identity) or not all(
        isinstance(identity[key], str) and identity[key] for key in required
    ):
        raise RuntimeError("Application identity is incomplete")
    if identity["executableName"] != EXECUTABLE_NAME:
        raise RuntimeError("Application identity executable does not match the product")
    bundle = Path(identity["installedBundle"]).expanduser()
    if not bundle.is_absolute():
        raise RuntimeError("Application identity installed path must be absolute")
    return {**identity, "installedBundle": str(bundle), "installedExecutable": str(bundle / "Contents" / "MacOS" / EXECUTABLE_NAME)}


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
        "CFBundleIconFile": APP_ICON_NAME,
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


def expected_metadata(identity: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    expected = source_metadata()
    if identity is not None:
        normalized = application_identity(identity)
        expected["CFBundleIdentifier"] = normalized["bundleIdentifier"]
        expected["CFBundleName"] = normalized["bundleName"]
    return expected


def load_metadata(path: Path, identity: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    expected = expected_metadata(identity)
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


def signing_identity() -> str:
    result = run(["security", "find-identity", "-v", "-p", "codesigning"])
    identities = [line for line in result.stdout.splitlines() if "Apple Development" in line]
    if len(identities) > 1:
        raise RuntimeError("More than one Apple Development identity is installed; keep exactly one")
    if not identities:
        raise RuntimeError("No Apple Development signing identity is installed (Xcode > Settings > Accounts > Manage Certificates)")
    return identities[0].split('"')[1]


ICON_POINT_SIZES = (16, 32, 128, 256, 512)


def compile_app_icon(destination: Path) -> None:
    icon_set = SOURCE_ASSETS / f"{APP_ICON_NAME}.appiconset"
    sources = sorted(path for path in icon_set.glob("*.png") if not path.is_symlink()) if icon_set.is_dir() else []
    if len(sources) != 1:
        raise RuntimeError(f"Expected exactly one PNG in {icon_set}, found {len(sources)}")
    source = sources[0]
    dimensions = run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(source)]).stdout
    if dimensions.count(": 1024") != 2:
        raise RuntimeError(f"App icon artwork must be 1024x1024: {source.name}")
    resources_dir = destination / "Contents" / "Resources"
    with tempfile.TemporaryDirectory() as scratch:
        iconset = Path(scratch) / f"{APP_ICON_NAME}.iconset"
        iconset.mkdir()
        for points in ICON_POINT_SIZES:
            for scale in (1, 2):
                pixels = points * scale
                suffix = "@2x" if scale == 2 else ""
                run(["sips", "-z", str(pixels), str(pixels), str(source),
                     "--out", str(iconset / f"icon_{points}x{points}{suffix}.png")])
        run(["iconutil", "-c", "icns", str(iconset), "-o", str(resources_dir / f"{APP_ICON_NAME}.icns")])
    if not (resources_dir / f"{APP_ICON_NAME}.icns").is_file():
        raise RuntimeError("iconutil did not produce the app icon")


def assemble_bundle(
    destination: Path,
    source_executable: Path,
    identity: Optional[Dict[str, str]] = None,
) -> None:
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"Staging destination already exists: {destination}")
    executable_dir = destination / "Contents" / "MacOS"
    executable_dir.mkdir(parents=True)
    resources_dir = destination / "Contents" / "Resources"
    resources_dir.mkdir()
    shutil.copy2(source_executable, executable_dir / EXECUTABLE_NAME)
    with (destination / "Contents" / "Info.plist").open("wb") as file:
        plistlib.dump(expected_metadata(identity), file, sort_keys=True)
    shutil.copy2(SOURCE_NOTICES, resources_dir / SOURCE_NOTICES.name)
    compile_app_icon(destination)
    load_metadata(destination / "Contents" / "Info.plist", identity)
    run(["codesign", "--force", "--sign", signing_identity(), str(destination)])
    verify_bundle(destination, require_live_process=False, identity=identity)


def exact_processes(executable: Path) -> List[int]:
    result = run(["ps", "-axo", "pid=,comm="])
    target = str(executable.absolute())
    matches = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) == 2 and fields[1] == target:
            matches.append(int(fields[0]))
    return matches


def stop_exact_processes(executable: Path) -> List[int]:
    stopped = []
    for pid in exact_processes(executable):
        current = exact_processes(executable)
        if pid not in current:
            continue
        os.kill(pid, signal.SIGTERM)
        stopped.append(pid)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and exact_processes(executable):
        time.sleep(0.1)
    survivors = exact_processes(executable)
    for pid in survivors:
        current = exact_processes(executable)
        if pid in current:
            os.kill(pid, signal.SIGKILL)
    if survivors:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and exact_processes(executable):
            time.sleep(0.1)
    if exact_processes(executable):
        raise RuntimeError("The exact installed application process survived termination")
    return sorted(set(stopped + survivors))


def stop_installed_app() -> List[int]:
    if not INSTALLED_BUNDLE.exists() and not INSTALLED_BUNDLE.is_symlink():
        return []
    if INSTALLED_BUNDLE.is_symlink() or not INSTALLED_EXECUTABLE.is_file():
        raise RuntimeError(f"Installed path is not a {APP_NAME} bundle: {INSTALLED_BUNDLE}")
    return stop_exact_processes(INSTALLED_EXECUTABLE)


def verify_bundle(
    bundle: Path,
    require_live_process: bool,
    require_notices: bool = True,
    identity: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    normalized = application_identity(identity)
    contents = bundle / "Contents"
    executable_dir = contents / "MacOS"
    executable = executable_dir / normalized["executableName"]
    if any(path.is_symlink() for path in (bundle, contents, executable_dir, executable)):
        raise RuntimeError(f"Application bundle contains an unsafe symlink: {bundle}")
    if not bundle.is_dir():
        raise RuntimeError(f"Application bundle is missing or unsafe: {bundle}")
    plist = contents / "Info.plist"
    notices = contents / "Resources" / SOURCE_NOTICES.name
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError(f"Bundle executable is missing or unsafe: {executable}")
    notices_valid = notices.is_file() and notices.read_bytes() == SOURCE_NOTICES.read_bytes()
    if require_notices and not notices_valid:
        raise RuntimeError(f"Third-party notices are missing or invalid: {notices}")
    metadata = load_metadata(plist, identity)
    icon = contents / "Resources" / f"{APP_ICON_NAME}.icns"
    if metadata.get("CFBundleIconFile") != APP_ICON_NAME or not icon.is_file():
        raise RuntimeError(f"App icon is missing from the bundle: {icon}")
    run(["codesign", "--verify", "--deep", "--strict", str(bundle)])
    signature = run(["codesign", "--display", "--verbose=2", str(bundle)]).stderr
    authority = next((line.split("=", 1)[1] for line in signature.splitlines() if line.startswith("Authority=")), "adhoc")
    pids = exact_processes(executable)
    if require_live_process and len(pids) != 1:
        raise RuntimeError(f"Expected one exact installed process, found {pids}")
    return {
        "bundle": str(bundle),
        "bundle_identifier": metadata["CFBundleIdentifier"],
        "executable": str(executable),
        "ls_ui_element": metadata["LSUIElement"],
        "pids": pids,
        "signature": authority,
        "third_party_notices": str(notices) if notices_valid else None,
    }


def reconcile_backup(backup: Path) -> None:
    if not backup.exists() and not backup.is_symlink():
        return
    if backup.is_symlink() or not backup.is_dir():
        raise RuntimeError(f"Backup path is unsafe: {backup}")
    verify_bundle(backup, require_live_process=False, require_notices=False)
    if not INSTALLED_BUNDLE.exists() and not INSTALLED_BUNDLE.is_symlink():
        backup.rename(INSTALLED_BUNDLE)
        return
    shutil.rmtree(backup)


def launch_and_verify(
    bundle: Path,
    require_notices: bool = True,
    launch_arguments: Optional[List[str]] = None,
    identity: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    command = ["open", "-n", "-a", str(bundle)]
    if launch_arguments:
        command.extend(["--args", *launch_arguments])
    run(command)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        executable = Path(application_identity(identity)["installedExecutable"])
        if len(exact_processes(executable)) == 1:
            break
        time.sleep(0.1)
    return verify_bundle(bundle, require_live_process=True, require_notices=require_notices, identity=identity)


def rollback_install(backup: Path, replaced: bool, was_running: bool) -> None:
    if replaced and (not backup.exists() or backup.is_symlink()):
        raise RuntimeError("Previous application backup is unavailable for rollback")
    if INSTALLED_BUNDLE.exists() or INSTALLED_BUNDLE.is_symlink():
        stop_exact_processes(INSTALLED_EXECUTABLE)
        shutil.rmtree(INSTALLED_BUNDLE)
    if replaced:
        backup.rename(INSTALLED_BUNDLE)
        if was_running:
            launch_and_verify(INSTALLED_BUNDLE, require_notices=False)


def replace_and_launch(staged_bundle: Path, launch_arguments: Optional[List[str]]) -> Dict[str, Any]:
    applications = INSTALLED_BUNDLE.parent
    if applications.is_symlink():
        raise RuntimeError(f"Applications directory must not be a symlink: {applications}")
    applications.mkdir(parents=True, exist_ok=True)
    backup = applications / f".{INSTALLED_BUNDLE.name}.backup"
    reconcile_backup(backup)
    if INSTALLED_BUNDLE.is_symlink():
        raise RuntimeError(f"Installed bundle must not be a symlink: {INSTALLED_BUNDLE}")
    if INSTALLED_BUNDLE.exists():
        if not INSTALLED_BUNDLE.is_dir() or not (INSTALLED_BUNDLE / "Contents" / "MacOS" / EXECUTABLE_NAME).is_file():
            raise RuntimeError(f"Installed path is not a {APP_NAME} bundle: {INSTALLED_BUNDLE}")
    stopped = stop_installed_app()
    replaced = INSTALLED_BUNDLE.exists()
    try:
        if replaced:
            INSTALLED_BUNDLE.rename(backup)
        staged_bundle.rename(INSTALLED_BUNDLE)
        verified = launch_and_verify(INSTALLED_BUNDLE, launch_arguments=launch_arguments)
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


def install_and_launch(launch_arguments: Optional[List[str]] = None) -> Dict[str, Any]:
    applications = INSTALLED_BUNDLE.parent
    if applications.is_symlink():
        raise RuntimeError(f"Applications directory must not be a symlink: {applications}")
    applications.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".ProArtVolume-install-", dir=applications))
    try:
        staged_bundle = staging_root / INSTALLED_BUNDLE.name
        assemble_bundle(staged_bundle, build_release())
        return replace_and_launch(staged_bundle, launch_arguments)
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def check_source() -> Dict[str, Any]:
    build_release()
    if not SOURCE_NOTICES.is_file():
        raise RuntimeError(f"Third-party notices are missing: {SOURCE_NOTICES}")
    run(
        [
            "xcrun",
            "clang",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fsyntax-only",
            "-I",
            str(ROOT / "Sources" / "MonitorTransport" / "include"),
            str(ROOT / "Sources" / "MonitorTransport" / "MonitorTransport.c"),
        ]
    )
    shell_scripts = sorted((ROOT / "scripts").glob("*.sh"))
    for script in shell_scripts:
        run(["bash", "-n", str(script)])
    python_files = [
        ROOT / "scripts" / "app_tool.py",
        ROOT / "Tests" / "Tooling" / "command_surface_test.py",
    ]
    for path in python_files:
        ast.parse(path.read_text(), filename=str(path))
    run(["git", "diff", "--check"], cwd=ROOT)
    load_metadata(SOURCE_PLIST)
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(ROOT / "Tests" / "Tooling"),
            "-p",
            "*_test.py",
        ],
        cwd=ROOT,
    )
    return {
        "status": "passed",
        "c_transport_warnings_as_errors": True,
        "release_strict_concurrency": True,
        "git_diff_check": True,
        "shell_scripts_checked": [str(path.relative_to(ROOT)) for path in shell_scripts],
        "python_files_checked": [str(path.relative_to(ROOT)) for path in python_files],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "build",
            "check",
            "stop",
            "verify",
        ),
    )
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
        return {"incomplete": 2, "failed": 1}.get(result.get("status", ""), 0)
    except Exception as error:
        emit({"status": "failed", "error": str(error)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
