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


def run_json(command: list[str], root: Path, allow_failure: bool = False) -> Dict[str, Any]:
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if result.returncode != 0 and not allow_failure:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed ({' '.join(command)}): {detail}")
    try:
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise RuntimeError("Command returned a non-object result")
        if result.returncode != 0:
            payload["status"] = "failed"
        return payload
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Command returned invalid JSON: {' '.join(command)}") from error


def prove() -> Dict[str, Any]:
    root = repository_root()
    scripts = root / "scripts"
    evidence_dir = root / ".hermes" / "verification" / "evidence" / uuid.uuid4().hex
    evidence_dir.mkdir(parents=True)
    evidence_path = evidence_dir / "launch.json"
    evidence: Dict[str, Any] = {
        "action": "verify installed Release, stop its exact process, then prove hardware transitions and restorations",
        "pass_condition": "verified bundle and sole live owner, followed by confirmed volume and mute transitions and restorations",
        "status": "failed",
    }
    def persist() -> None:
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")

    persist()
    try:
        evidence["build"] = run_json([str(scripts / "build-app.sh")], root)
        persist()
        evidence["verification"] = run_json([str(scripts / "verify-installed-app.sh")], root)
        persist()
        evidence["isolation"] = run_json([str(scripts / "stop-app.sh")], root)
        persist()
        proof = run_json([str(scripts / "probe-monitor-status.sh")], root, allow_failure=True)
        evidence["hardware_proof"] = proof
        evidence["status"] = "passed" if proof.get("status") == "passed" else "failed"
        persist()
    except Exception as error:
        evidence["error"] = str(error)
        persist()
    finally:
        try:
            if "build" in evidence:
                evidence["cleanup"] = run_json([str(scripts / "stop-app.sh")], root)
        except Exception as error:
            evidence["status"] = "failed"
            evidence["cleanup_error"] = str(error)
        persist()
    if not evidence_path.is_file():
        raise RuntimeError("Evidence did not survive cleanup")
    return {
        "status": evidence["status"],
        "capability": "invisible app launch and isolated hardware transition/restoration proof",
        "cleanup": evidence.get("cleanup"),
        "evidence": str(evidence_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prove",))
    arguments = parser.parse_args()
    try:
        result = prove() if arguments.command == "prove" else {}
        emit(result)
        return 0 if result.get("status") == "passed" else 1
    except Exception as error:
        emit({"status": "failed", "error": str(error)})
        return 1


if __name__ == "__main__":
    sys.exit(main())