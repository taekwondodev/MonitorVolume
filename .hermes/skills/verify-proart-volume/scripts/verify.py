#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_json(command: list[str], root: Path) -> Dict[str, Any]:
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed ({' '.join(command)}): {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Command returned invalid JSON: {' '.join(command)}") from error


def prove() -> Dict[str, Any]:
    root = repository_root()
    scripts = root / "scripts"
    launched = False
    try:
        build = run_json([str(scripts / "build-app.sh")], root)
        launched = True
        verification = run_json([str(scripts / "verify-installed-app.sh")], root)
        run_id = uuid.uuid4().hex
        evidence_dir = root / ".hermes" / "verification" / "evidence" / run_id
        evidence_dir.mkdir(parents=True)
        evidence_path = evidence_dir / "launch.json"
        evidence = {
            "action": "build, install, and open the Release bundle through repository tooling",
            "build": build,
            "pass_condition": "installed bundle identity, signature, executable, and exact live process are verified",
            "status": "passed",
            "verification": verification,
        }
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    finally:
        cleanup = run_json([str(scripts / "stop-app.sh")], root) if launched else None
    if not evidence_path.is_file():
        raise RuntimeError("Evidence did not survive cleanup")
    return {
        "status": "passed",
        "capability": "launch installed menu-bar agent",
        "cleanup": cleanup,
        "evidence": str(evidence_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prove",))
    arguments = parser.parse_args()
    try:
        result = prove() if arguments.command == "prove" else {}
        emit(result)
        return 0
    except Exception as error:
        emit({"status": "failed", "error": str(error)})
        return 1


if __name__ == "__main__":
    sys.exit(main())