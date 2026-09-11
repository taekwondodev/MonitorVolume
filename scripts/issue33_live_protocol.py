#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROTOCOL_PATH = Path(__file__).with_suffix(".json")
CONDITIONS = {"A/full", "B/full", "A/none", "B/none"}
CONSENT_CATEGORIES = {
    "installationAndLaunch",
    "physicalVolumeInputAndDDCWrites",
    "accessibilityPermissionChanges",
    "normalUseUIActivity",
    "stress",
    "sleepWake",
}
IDENTITY_FIELDS = {"bundleIdentifier", "bundleName", "installedBundle", "executableName"}


class ProtocolError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = json.loads(path.read_text())
    validate_protocol(protocol)
    return protocol


def split_condition(value: str) -> tuple[str, str]:
    candidate, instrumentation = value.split("/", 1)
    return candidate, instrumentation


def normal_schedule(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    workload = protocol["normalWorkload"]
    cycle = workload["conditionOrderCycle"]
    schedule: list[dict[str, Any]] = []
    for round_ordinal in range(1, workload["rounds"] + 1):
        for value in cycle[(round_ordinal - 1) % len(cycle)]:
            candidate, instrumentation = split_condition(value)
            schedule.append({
                "ordinal": len(schedule) + 1,
                "round": round_ordinal,
                "condition": value,
                "candidate": candidate,
                "instrumentation": instrumentation,
                "workload": "normal",
            })
    return schedule


def acceptance_schedule(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    for kind in ("lifecycle", "stress"):
        for candidate in ("A", "B"):
            schedule.append({
                "ordinal": len(schedule) + 1,
                "candidate": candidate,
                "instrumentation": "full",
                "workload": kind,
            })
    return schedule


def validate_protocol(protocol: dict[str, Any]) -> None:
    require(protocol.get("schemaVersion") == 2, "unsupported schema")
    require(protocol.get("status") == "frozenBeforeInstalledCollection", "protocol is not frozen")
    require(protocol["authority"]["ticket"] == 33, "ticket authority mismatch")
    require(protocol["authority"]["offlineResult"] == 32, "offline authority mismatch")

    candidates = protocol["candidates"]
    require(set(candidates) == {"A", "B"}, "candidate set mismatch")
    require({candidate["topology"] for candidate in candidates.values()} == {
        "mainActor", "dedicatedOwnerThread",
    }, "candidate topology mismatch")
    production = protocol.get("productionApplication")
    if not isinstance(production, dict) or set(production) != IDENTITY_FIELDS:
        raise ProtocolError("production application identity mismatch")
    require(production == {
        "bundleIdentifier": "dev.taekwondodev.ProArtVolume",
        "bundleName": "ProArt Volume",
        "installedBundle": "~/Applications/ProArt Volume.app",
        "executableName": "ProArtVolume",
    }, "production application identity mismatch")
    identities = [production]
    for candidate_name, candidate in candidates.items():
        source_ref = candidate["sourceRef"]
        require(
            len(source_ref) == 40
            and all(character in "0123456789abcdef" for character in source_ref),
            "candidate ref is not a full lowercase SHA",
        )
        identity = candidate.get("applicationIdentity")
        require(isinstance(identity, dict) and set(identity) == IDENTITY_FIELDS, "candidate application identity mismatch")
        expected_suffix = f"Candidate{candidate_name}"
        require(identity == {
            "bundleIdentifier": f"{production['bundleIdentifier']}.{expected_suffix}",
            "bundleName": f"{production['bundleName']} Candidate {candidate_name}",
            "installedBundle": f"~/Applications/{production['bundleName']} Candidate {candidate_name}.app",
            "executableName": production["executableName"],
        }, "candidate application identity derivation mismatch")
        identities.append(identity)
    require(len({identity["bundleIdentifier"] for identity in identities}) == 3, "application identity collision")
    require(len({identity["installedBundle"] for identity in identities}) == 3, "application identity path collision")
    require(all(identity["executableName"] == "ProArtVolume" for identity in identities), "application identity executable mismatch")
    require(all(identity["installedBundle"].startswith("~/Applications/") for identity in identities), "application identity path mismatch")

    build = protocol["build"]
    require(build["product"] == "ProArtVolume", "installed product mismatch")
    require(build["configuration"] == "release", "build configuration mismatch")
    require(build["strictConcurrency"] == "complete", "strict concurrency mismatch")
    require(build["launch"] == "LaunchServices", "launch boundary mismatch")
    require(build["buildOncePerCandidate"] is True, "candidate build reuse missing")
    require(build["rebuildDuringMeasuredCollection"] is False, "measured rebuild is forbidden")

    consent = protocol["consent"]
    require(consent["preparationRequiresRuntimeConsent"] is False, "offline preparation consent mismatch")
    require(consent["collectionRequiresExplicitSessionConsent"] is True, "runtime consent gate missing")
    require(set(consent["categories"]) == CONSENT_CATEGORIES, "consent category mismatch")
    require(consent["stressAndSleepWakeSeparatelyAuthorized"] is True, "separate stress consent missing")
    require(consent["noConsentPersistenceAcrossSessions"] is True, "consent must be session scoped")

    setup = protocol["setup"]
    require(setup["requiredConsent"] == ["installationAndLaunch", "accessibilityPermissionChanges"], "setup consent mismatch")
    require(setup["candidateOrder"] == ["A", "B"], "setup candidate order mismatch")
    for key in ("manualAccessibilityGrantOnly", "noPhysicalInput", "requiresFreshReadinessPerCandidate", "idempotentForByteIdenticalInstall"):
        require(setup[key] is True, f"setup requirement missing: {key}")
    readiness = protocol["readiness"]
    require(readiness["schemaVersion"] == 1, "readiness schema mismatch")
    require(readiness["terminalStates"] == ["ready", "unavailable"], "readiness terminal states mismatch")
    for key in ("requiredBeforeOperatorInput", "identicalInFullAndNone", "excludedFromMeasuredPhases"):
        require(readiness[key] is True, f"readiness requirement missing: {key}")
    require(readiness["requiredFacts"] == [
        "candidateIdentity", "bundleIdentifier", "executableSha256", "processIdentifier",
        "sourceRef", "lifecycleGeneration", "accessibilityTrusted", "tapOwnerActive",
        "serviceValidationComplete",
    ], "readiness facts mismatch")

    safety = protocol["safety"]
    for key in (
        "oneOwnedAppAndHardwareWriter",
        "serialRunsOnly",
        "stopImmediatelyOnInputDisruption",
        "forbidWatchdog",
        "forbidSynthesizedSystemInput",
        "forbidAutomaticPermissionChanges",
        "forbidAutomaticRelaunch",
        "forbidPendingInputReplay",
    ):
        require(safety[key] is True, f"safety requirement missing: {key}")
    require("issue33-stop" in safety["emergencyStop"], "keyboard emergency stop route missing")

    instrumentation = protocol["instrumentation"]
    require(instrumentation["modes"] == ["full", "none"], "instrumentation matrix mismatch")
    require(instrumentation["inactivePathMustEmitNoDetailedEvents"] is True, "inactive path mismatch")
    require(
        instrumentation["noneArguments"] == instrumentation["commonReadinessArguments"],
        "inactive readiness arguments mismatch",
    )

    resources = protocol["resourceSampling"]
    require(resources["pollIntervalMilliseconds"] == 10, "resource interval mismatch")
    require(resources["numericImputation"] == "none", "numeric imputation is forbidden")
    require(resources["retainEverySample"] is True, "raw resource retention missing")
    require(resources["memoryMeasures"] == ["residentSizeBytes", "physicalFootprintBytes"], "memory metrics mismatch")
    require(resources["wakeupMeasures"] == ["packageIdleWakeups", "interruptWakeups"], "wakeup metrics mismatch")
    require(resources["threadMeasure"] == "procPidTaskInfoThreadCount", "thread metric mismatch")

    workload = protocol["normalWorkload"]
    require(workload["admissionCapacity"] == 8, "admission capacity mismatch")
    require(workload["rounds"] == len(workload["conditionOrderCycle"]), "condition cycle mismatch")
    require(
        all(len(order) == 4 and set(order) == CONDITIONS for order in workload["conditionOrderCycle"]),
        "condition order is not counterbalanced",
    )
    schedule = normal_schedule(protocol)
    require(len(schedule) == workload["totalRuns"], "normal run total mismatch")
    for candidate in candidates:
        for instrumentation_mode in instrumentation["modes"]:
            count = sum(
                item["candidate"] == candidate
                and item["instrumentation"] == instrumentation_mode
                for item in schedule
            )
            require(count == workload["runsPerCandidateInstrumentation"], "normal schedule is unbalanced")
    required_phases = {
        "activeIdle", "isolatedInput", "repeatedBurst", "mixedBurst",
        "uiActivity", "postBurstRetention",
    }
    require({phase["name"] for phase in workload["phases"]} == required_phases, "normal phase matrix mismatch")
    require(workload["balancedInputMustRestoreStartingVolumeAndMuteIntent"] is True, "balanced input missing")

    acceptance = protocol["acceptanceRuns"]
    require(acceptance["lifecyclePerCandidateFull"] == 1, "lifecycle run count mismatch")
    require(acceptance["stressPerCandidateFull"] == 1, "stress run count mismatch")
    require(len(acceptance_schedule(protocol)) == acceptance["totalRuns"], "acceptance run total mismatch")
    require(
        [phase["name"] for phase in acceptance["lifecycle"]["phases"]]
        == ["permissionRevoked", "regrantWithoutReopen", "explicitReopen", "sleepWake"],
        "lifecycle phase matrix mismatch",
    )
    require(
        [phase["name"] for phase in acceptance["stress"]["phases"]]
        == ["stressBurst", "postStressRetention"],
        "stress phase matrix mismatch",
    )
    require(acceptance["stress"]["mustRemainSeparateFromNormal"] is True, "stress separation missing")

    interpretation = protocol["accountingInterpretation"]
    require(interpretation["perRunIdentitiesMustReconcile"] is True, "per-run accounting gate missing")
    require(interpretation["crossCandidateExactCountEqualityRequired"] is False, "cross-candidate equality was not approved")
    require(interpretation["normalRejectedDiscardedOrOverflow"] == "correctnessFailure", "normal accounting gate mismatch")
    require(interpretation["fasterSurvivingSubsetCannotCompensateForLostWork"] is True, "survivor-bias rule missing")

    require(
        protocol["measurements"]["maximumEventToCallbackProxyNanoseconds"] == 1_000_000_000,
        "event-to-callback clock-compatibility bound mismatch",
    )

    binding = protocol["artifactBinding"]
    for key in (
        "retainProtocolFile", "retainProtocolSha256", "retainSourceClosure", "retainExecutable",
        "requireOneExecutableSha256PerCandidate", "requireInstalledExecutableHashMatch",
        "requireExactlyOneInstalledProcess", "forbidPublishedMachinePathsAndProcessIdentifiers",
    ):
        require(binding[key] is True, f"artifact binding missing: {key}")

    selection = protocol["selection"]
    require(selection["correctnessAvailabilityEvidenceIntegrityAndInputSafetyMustPass"] is True, "selection gates missing")
    require(selection["candidateAAtMeasurableParity"] is True, "parity preference mismatch")
    require(selection["stressIsGateAndSecondaryEvidenceNotNormalPerformance"] is True, "stress selection boundary missing")
    equivalence = protocol["equivalence"]
    require(equivalence["pairedRunCount"] == workload["rounds"], "paired run count mismatch")
    require(
        equivalence["minimumSuccessiveDifferencesPerCandidateCondition"] == workload["rounds"] - 1,
        "repeatability sample minimum mismatch",
    )
    require(equivalence["bootstrapResamples"] == 10_000, "bootstrap resample count mismatch")
    require(equivalence["bootstrapSeed"] == 330_033, "bootstrap seed mismatch")
    require(equivalence["noFixedSlaOrInventedPracticalMargin"] is True, "invented margin is forbidden")
    require(protocol["missingData"]["numericImputation"] == "none", "missing-data imputation is forbidden")
    require(protocol["missingData"]["noAutomaticReplacementRuns"] is True, "automatic replacements are forbidden")


def main() -> int:
    protocol = load_protocol()
    print(json.dumps({
        "status": "valid",
        "normalSchedule": normal_schedule(protocol),
        "acceptanceSchedule": acceptance_schedule(protocol),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
