#!/usr/bin/env python3

import argparse
import ast
import ctypes
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
from typing import Any, Dict, List, Optional, Sequence



APP_NAME = "Monitor Volume"
EXECUTABLE_NAME = "MonitorVolume"
LEGACY_APP_NAME = "ProArt Volume"
LEGACY_EXECUTABLE_NAME = "ProArtVolume"
ROOT = Path(__file__).resolve().parents[1]
SOURCE_PLIST = ROOT / "Resources" / "Info.plist"
SOURCE_NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
SOURCE_ASSETS = ROOT / "Resources" / "Media.xcassets"
APP_ICON_NAME = "AppIcon"
INSTALLED_BUNDLE = Path.home() / "Applications" / f"{APP_NAME}.app"
INSTALLED_EXECUTABLE = INSTALLED_BUNDLE / "Contents" / "MacOS" / EXECUTABLE_NAME
LEGACY_BUNDLE = Path.home() / "Applications" / f"{LEGACY_APP_NAME}.app"
LEGACY_EXECUTABLE = LEGACY_BUNDLE / "Contents" / "MacOS" / LEGACY_EXECUTABLE_NAME
IDLE_BASELINE = ROOT / "docs" / "performance" / "idle-baseline.json"
IDLE_CHART = ROOT / "docs" / "performance" / "idle.svg"
IDLE_SAMPLE_COUNT = 6
IDLE_SAMPLE_INTERVAL_SECONDS = 0.5
RUSAGE_INFO_V0 = 0
LIBC = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
LIBC.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
LIBC.proc_pid_rusage.restype = ctypes.c_int
LIBC.mach_timebase_info.argtypes = [ctypes.c_void_p]
LIBC.mach_timebase_info.restype = ctypes.c_int


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


class MachTimebaseInfo(ctypes.Structure):
    _fields_ = [
        ("numer", ctypes.c_uint32),
        ("denom", ctypes.c_uint32),
    ]


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


def remove_legacy_bundle() -> Dict[str, Any]:
    if not LEGACY_BUNDLE.exists() and not LEGACY_BUNDLE.is_symlink():
        return {"removed": False, "stopped_pids": []}
    if LEGACY_BUNDLE.is_symlink():
        raise RuntimeError(f"Legacy bundle must not be a symlink: {LEGACY_BUNDLE}")
    stopped: List[int] = []
    if LEGACY_EXECUTABLE.is_file():
        stopped = stop_exact_processes(LEGACY_EXECUTABLE)
    shutil.rmtree(LEGACY_BUNDLE)
    if LEGACY_BUNDLE.exists() or LEGACY_BUNDLE.is_symlink():
        raise RuntimeError(f"Legacy bundle survived removal: {LEGACY_BUNDLE}")
    return {"removed": True, "stopped_pids": stopped}


def install_and_launch(launch_arguments: Optional[List[str]] = None) -> Dict[str, Any]:
    applications = INSTALLED_BUNDLE.parent
    if applications.is_symlink():
        raise RuntimeError(f"Applications directory must not be a symlink: {applications}")
    applications.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".MonitorVolume-install-", dir=applications))
    try:
        staged_bundle = staging_root / INSTALLED_BUNDLE.name
        assemble_bundle(staged_bundle, build_release())
        installed = replace_and_launch(staged_bundle, launch_arguments)
        legacy = remove_legacy_bundle()
        return {**installed, "legacy_bundle_removed": legacy["removed"], "legacy_stopped_pids": legacy["stopped_pids"]}
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def process_rusage(pid: int) -> RUsageInfoV0:
    info = RUsageInfoV0()
    if LIBC.proc_pid_rusage(pid, RUSAGE_INFO_V0, ctypes.byref(info)) != 0:
        raise RuntimeError(f"Unable to read resource usage for pid {pid}")
    return info


def cpu_time_seconds(usage: RUsageInfoV0) -> float:
    timebase = MachTimebaseInfo()
    if LIBC.mach_timebase_info(ctypes.byref(timebase)) != 0 or timebase.numer == 0 or timebase.denom == 0:
        raise RuntimeError("Unable to read Mach timebase")
    ticks = usage.ri_user_time + usage.ri_system_time
    return ticks * timebase.numer / timebase.denom / 1_000_000_000


def idle_cpu_percent(samples: Sequence[Dict[str, float]]) -> float:
    if len(samples) < 2:
        raise RuntimeError("Idle CPU measurement requires at least two samples")
    percents = []
    for previous, current in zip(samples, samples[1:]):
        delta_cpu_seconds = current["cpu_s"] - previous["cpu_s"]
        delta_wall_seconds = current["wall_s"] - previous["wall_s"]
        if delta_wall_seconds <= 0:
            raise RuntimeError("Idle CPU samples are not ordered in wall time")
        percents.append(max(0.0, delta_cpu_seconds / delta_wall_seconds * 100.0))
    return sum(percents) / len(percents)


def bundle_size_bytes(bundle: Path) -> int:
    total = 0
    for path in bundle.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        total += path.stat().st_size
    return total


def load_idle_baseline(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Idle baseline is missing: {path}")
    payload = json.loads(path.read_text())
    required_numbers = ("idle_cpu_percent", "physical_footprint_bytes", "bundle_size_bytes")
    missing = [key for key in required_numbers if not isinstance(payload.get(key), (int, float))]
    provenance = payload.get("provenance")
    if missing or not isinstance(provenance, dict) or payload.get("schema") != 1 or payload.get("state") != "idle":
        raise RuntimeError(f"Idle baseline is invalid: {path}")
    return payload


def format_mebibytes(byte_count: float) -> str:
    return f"{byte_count / (1024 * 1024):.2f} MiB"


def format_cpu_percent(cpu: float) -> str:
    return f"{cpu:.3f}%"


def render_idle_chart(baseline: Dict[str, Any]) -> str:
    cpu = float(baseline["idle_cpu_percent"])
    footprint = float(baseline["physical_footprint_bytes"])
    bundle = float(baseline["bundle_size_bytes"])
    cpu_label = format_cpu_percent(cpu)
    footprint_label = format_mebibytes(footprint)
    bundle_label = format_mebibytes(bundle)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="280" viewBox="0 0 720 280" role="img">\n'
        '  <title>Monitor Volume idle measurements</title>\n'
        '  <rect width="720" height="280" rx="28" fill="#111111"/>\n'
        '  <text x="360" y="48" text-anchor="middle" fill="#F5F5F5" font-family="SF Pro Display, Helvetica Neue, sans-serif" font-size="20">Idle Release app</text>\n'
        '  <rect x="36" y="80" width="200" height="160" rx="20" fill="#1C1C1E"/>\n'
        '  <text x="136" y="124" text-anchor="middle" fill="#8E8E93" font-family="SF Pro Text, Helvetica Neue, sans-serif" font-size="13">Idle CPU</text>\n'
        f'  <text x="136" y="172" text-anchor="middle" fill="#7DFFB3" font-family="SF Pro Display, Helvetica Neue, sans-serif" font-size="28">{cpu_label}</text>\n'
        '  <rect x="260" y="80" width="200" height="160" rx="20" fill="#1C1C1E"/>\n'
        '  <text x="360" y="124" text-anchor="middle" fill="#8E8E93" font-family="SF Pro Text, Helvetica Neue, sans-serif" font-size="13">Physical footprint</text>\n'
        f'  <text x="360" y="172" text-anchor="middle" fill="#64D2FF" font-family="SF Pro Display, Helvetica Neue, sans-serif" font-size="28">{footprint_label}</text>\n'
        '  <rect x="484" y="80" width="200" height="160" rx="20" fill="#1C1C1E"/>\n'
        '  <text x="584" y="124" text-anchor="middle" fill="#8E8E93" font-family="SF Pro Text, Helvetica Neue, sans-serif" font-size="13">Installed bundle</text>\n'
        f'  <text x="584" y="172" text-anchor="middle" fill="#FFD60A" font-family="SF Pro Display, Helvetica Neue, sans-serif" font-size="28">{bundle_label}</text>\n'
        "</svg>\n"
    )


def write_idle_chart(baseline_path: Path = IDLE_BASELINE, chart_path: Path = IDLE_CHART) -> Path:
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.write_text(render_idle_chart(load_idle_baseline(baseline_path)))
    return chart_path


def machine_provenance() -> Dict[str, str]:
    return {
        "architecture": run(["uname", "-m"]).stdout.strip(),
        "machine_model": run(["sysctl", "-n", "hw.model"]).stdout.strip(),
        "os_build": run(["sw_vers", "-buildVersion"]).stdout.strip(),
        "os_version": run(["sw_vers", "-productVersion"]).stdout.strip(),
    }


def profile_installed_app() -> Dict[str, Any]:
    verified = verify_bundle(INSTALLED_BUNDLE, require_live_process=True)
    pid = verified["pids"][0]
    samples = []
    footprints = []
    for index in range(IDLE_SAMPLE_COUNT):
        if exact_processes(INSTALLED_EXECUTABLE) != [pid]:
            raise RuntimeError("Installed application is not the live process")
        usage = process_rusage(pid)
        samples.append(
            {
                "cpu_s": cpu_time_seconds(usage),
                "wall_s": time.monotonic(),
            }
        )
        footprints.append(int(usage.ri_phys_footprint))
        if index + 1 < IDLE_SAMPLE_COUNT:
            time.sleep(IDLE_SAMPLE_INTERVAL_SECONDS)
    if exact_processes(INSTALLED_EXECUTABLE) != [pid]:
        raise RuntimeError("Installed application is not the live process")
    baseline = {
        "bundle_size_bytes": bundle_size_bytes(INSTALLED_BUNDLE),
        "idle_cpu_percent": idle_cpu_percent(samples),
        "physical_footprint_bytes": int(sum(footprints) / len(footprints)),
        "provenance": machine_provenance(),
        "schema": 1,
        "state": "idle",
    }
    IDLE_BASELINE.parent.mkdir(parents=True, exist_ok=True)
    IDLE_BASELINE.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
    write_idle_chart()
    return {
        "status": "profiled",
        "baseline": str(IDLE_BASELINE),
        "chart": str(IDLE_CHART),
        **baseline,
        **verified,
    }


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
    python_files = [ROOT / "scripts" / "app_tool.py", *sorted((ROOT / "Tests" / "Tooling").glob("*_test.py"))]
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
            "profile",
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
        elif arguments.command == "profile":
            result = profile_installed_app()
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
