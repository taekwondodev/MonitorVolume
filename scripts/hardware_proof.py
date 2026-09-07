from typing import Any


def validate_hardware_proof(report: Any) -> None:
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise RuntimeError(f"Invalid hardware proof: {message}")

    def snapshot(value: Any) -> None:
        require(isinstance(value, dict), "missing state")
        require(type(value.get("volume")) is int and 0 <= value["volume"] <= 100, "invalid volume")
        require(value.get("mute") in ("muted", "unmuted"), "invalid mute")

    def outcome(value: Any, expected: Any = None) -> bool:
        require(isinstance(value, dict), "missing outcome")
        require(type(value.get("confirmed")) is bool, "invalid confirmation")
        require(type(value.get("writeAttempted")) is bool, "missing operation evidence")
        elapsed = value.get("elapsedNanoseconds")
        require(type(elapsed) is int and elapsed >= 0, "invalid relative timing")
        observed = value.get("observed")
        if observed is not None:
            snapshot(observed)
        if value["confirmed"]:
            require(observed is not None and value.get("error") is None, "confirmation without state")
            if expected is not None:
                require(value["writeAttempted"], "write confirmation without attempt")
                require(observed == expected, "confirmation disagrees with request")
        else:
            require(isinstance(value.get("error"), str) and bool(value["error"]), "failure without error")
        return value["confirmed"]

    require(isinstance(report, dict), "missing report")
    require(report.get("status") in ("passed", "failed"), "invalid status")
    phases = report.get("phases")
    require(isinstance(phases, list) and len(phases) <= 2, "invalid phases")
    initial = None
    restored = True
    all_confirmed = True
    for index, phase in enumerate(phases):
        require(restored, "write phase after unconfirmed restoration")
        require(isinstance(phase, dict), "invalid phase")
        require(phase.get("control") == ("volume", "mute")[index], "invalid phase order")
        snapshot(phase.get("initial"))
        if initial is None:
            initial = phase["initial"]
        require(phase["initial"] == initial, "inconsistent initial state")
        requested = dict(initial)
        if index == 0:
            requested["volume"] += -1 if initial["volume"] == 100 else 1
        else:
            requested["mute"] = "unmuted" if initial["mute"] == "muted" else "muted"
        require(phase.get("requested") == requested, "missing real transition")
        require(phase.get("restorationRequested") == initial, "invalid restoration request")
        transitioned = outcome(phase.get("transition"), requested)
        restored = outcome(phase.get("restoration"), initial)
        all_confirmed = all_confirmed and transitioned and restored
    if phases and restored:
        require(len(phases) == 2, "missing phase after confirmed restoration")
    final = report.get("final")
    final_confirmed = outcome(final)
    require(not final["writeAttempted"], "final capture must be read-only")
    passed = (len(phases) == 2 and all_confirmed and final_confirmed
              and final["observed"] == initial)
    require((report["status"] == "passed") == passed, "status disagrees with phase evidence")
