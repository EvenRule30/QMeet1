from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Mapping


MIN_ROUTE_DECISIONS = 8
MIN_RESPONSE_GUARDED_ATTEMPTS = 3
MIN_EXACT_ROUTE_OBSERVATIONS = 5
MIN_HEALTHY_RATE = 0.95

_VALIDATION_HISTORY_LOCK = Lock()
_DEFAULT_VALIDATION_HISTORY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "qmeet_focus_validation.json"
)


def _integer(summary: Mapping[str, Any], key: str) -> int:
    value = summary.get(key, 0)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _rate(summary: Mapping[str, Any], key: str) -> float:
    value = summary.get(key, 0.0)
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _normalized_mode(value: str) -> str:
    return value.strip().casefold()


def _readiness_recommendation(*, status: str, planner_mode: str) -> str:
    if planner_mode == "active":
        if status == "blocked":
            return (
                "Active-mode validation found blocking evidence. Keep guarded routing "
                "and response safeguards enabled while resolving it."
            )
        if status == "collecting":
            return (
                "Continue active-mode validation while collecting current-session evidence."
            )
        return (
            "Current-session evidence supports continued active-mode operation with "
            "guarded routing and response safeguards."
        )

    if planner_mode == "off":
        return (
            "Enable the planner in shadow mode with guarded routing and response modes "
            "before collecting promotion evidence."
        )

    if status == "blocked":
        return "Keep the planner in shadow mode and resolve the blocking evidence."
    if status == "collecting":
        return "Keep the planner in shadow mode while collecting current-session evidence."
    return (
        "Current-session evidence supports a deliberate, manual planner-mode promotion review."
    )


def _display_metadata(*, status: str, planner_mode: str) -> dict[str, str]:
    if planner_mode == "active":
        status_label = {
            "ready": "Healthy",
            "collecting": "Collecting health evidence",
            "blocked": "Attention required",
        }.get(status, status.replace("_", " ").title())
        return {
            "stage": "active_validation",
            "panelTitle": "Active Planner Validation",
            "statusLabel": status_label,
            "statusMeta": "Current-session guarded health",
            "evidenceLabel": "Health evidence still needed",
            "automaticActionLabel": "Automatic mode changes",
        }

    if planner_mode == "off":
        return {
            "stage": "planner_setup",
            "panelTitle": "Planner Setup Readiness",
            "statusLabel": "Planner disabled",
            "statusMeta": "Enable shadow mode to begin",
            "evidenceLabel": "Setup and evidence still needed",
            "automaticActionLabel": "Automatic mode changes",
        }

    status_label = {
        "ready": "Ready for review",
        "collecting": "Collecting",
        "blocked": "Blocked",
    }.get(status, status.replace("_", " ").title())
    return {
        "stage": "promotion_readiness",
        "panelTitle": "Planner Promotion Readiness",
        "statusLabel": status_label,
        "statusMeta": "Manual promotion review",
        "evidenceLabel": "Promotion evidence still needed",
        "automaticActionLabel": "Automatic promotion",
    }


def validation_history_path() -> Path:
    configured = os.getenv("QMEET_FOCUS_VALIDATION_PATH", "").strip()
    return Path(configured).expanduser() if configured else _DEFAULT_VALIDATION_HISTORY_PATH


def _validated_history_record(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None

    required_strings = (
        "kind",
        "plannerMode",
        "validatedAt",
        "sessionStartedAt",
    )
    for key in required_strings:
        if not isinstance(value.get(key), str) or not str(value[key]).strip():
            return None

    result: dict[str, object] = {
        "kind": str(value["kind"]),
        "plannerMode": str(value["plannerMode"]),
        "validatedAt": str(value["validatedAt"]),
        "sessionStartedAt": str(value["sessionStartedAt"]),
        "routeDecisions": _integer(value, "routeDecisions"),
        "responseGuardedAttempts": _integer(value, "responseGuardedAttempts"),
        "exactRouteObservations": _integer(value, "exactRouteObservations"),
        "routeHealthyRate": _rate(value, "routeHealthyRate"),
        "responseHealthyRate": _rate(value, "responseHealthyRate"),
    }
    return result


def load_last_successful_validation(
    *,
    history_path: Path | None = None,
) -> dict[str, object] | None:
    target = history_path or validation_history_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return _validated_history_record(raw)


def update_last_successful_validation(
    *,
    readiness: Mapping[str, Any],
    session_started_at: str,
    planner_mode: str,
    response_mode: str,
    route_mode: str,
    planner_enabled: bool,
    history_path: Path | None = None,
    validated_at: str | None = None,
) -> dict[str, object] | None:
    """Persist the first successful validation snapshot for each backend session.

    The status endpoint polls frequently, so an already-recorded session is returned
    without rewriting its timestamp. Persistence is best-effort; status reporting
    remains available even if the metadata file cannot be written.
    """

    target = history_path or validation_history_path()
    with _VALIDATION_HISTORY_LOCK:
        existing = load_last_successful_validation(history_path=target)

        normalized_planner_mode = _normalized_mode(planner_mode)
        normalized_response_mode = _normalized_mode(response_mode)
        normalized_route_mode = _normalized_mode(route_mode)
        ready = bool(readiness.get("ready"))
        can_record = (
            ready
            and planner_enabled
            and normalized_planner_mode in {"shadow", "active"}
            and normalized_response_mode == "guarded"
            and normalized_route_mode == "guarded"
            and bool(session_started_at.strip())
        )
        if not can_record:
            return existing

        if (
            existing
            and existing.get("sessionStartedAt") == session_started_at
            and existing.get("plannerMode") == normalized_planner_mode
        ):
            return existing

        samples = readiness.get("currentSamples")
        sample_values = samples if isinstance(samples, Mapping) else {}
        record: dict[str, object] = {
            "kind": (
                "active_validation"
                if normalized_planner_mode == "active"
                else "promotion_readiness"
            ),
            "plannerMode": normalized_planner_mode,
            "validatedAt": validated_at or datetime.now().astimezone().isoformat(),
            "sessionStartedAt": session_started_at,
            "routeDecisions": _integer(sample_values, "routeDecisions"),
            "responseGuardedAttempts": _integer(
                sample_values,
                "responseGuardedAttempts",
            ),
            "exactRouteObservations": _integer(
                sample_values,
                "exactRouteObservations",
            ),
            "routeHealthyRate": _rate(sample_values, "routeHealthyRate"),
            "responseHealthyRate": _rate(sample_values, "responseHealthyRate"),
        }

        temporary_path = target.with_name(f"{target.name}.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, target)
        except OSError:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            return existing

        return record


def build_promotion_readiness(
    *,
    response_selection: Mapping[str, Any],
    route_selection: Mapping[str, Any],
    exact_route_observation: Mapping[str, Any],
    planner_mode: str,
    response_mode: str,
    route_mode: str,
    planner_enabled: bool,
) -> dict[str, object]:
    """Evaluate current-session evidence for promotion or active validation.

    This function is advisory only. It never changes environment variables or
    runtime modes. The thresholds are intentionally modest for the prototype,
    but they still require evidence from all three routing surfaces.
    """

    normalized_planner_mode = _normalized_mode(planner_mode)
    normalized_response_mode = _normalized_mode(response_mode)
    normalized_route_mode = _normalized_mode(route_mode)
    route_decisions = _integer(route_selection, "decisionCount")
    response_attempts = _integer(response_selection, "guardedAttemptCount")
    exact_observations = _integer(exact_route_observation, "observationCount")

    route_healthy_rate = _rate(route_selection, "healthyDecisionRate")
    response_healthy_rate = _rate(response_selection, "healthyDecisionRate")

    blockers: list[str] = []
    missing_evidence: list[str] = []
    if not planner_enabled or normalized_planner_mode == "off":
        blockers.append("Focus planner is disabled.")

    if normalized_response_mode != "guarded":
        blockers.append("Visible response mode is not guarded.")
    if normalized_route_mode != "guarded":
        blockers.append("Planner route mode is not guarded.")

    response_system_failures = _integer(response_selection, "systemFailureCount")
    response_unknown = _integer(response_selection, "unknownFallbackCount")
    route_system_failures = _integer(route_selection, "systemFailureCount")
    route_unknown = _integer(route_selection, "unknownFallbackCount")
    exact_unknown = _integer(exact_route_observation, "unknownCount")

    if response_system_failures:
        blockers.append(
            f"Current session has {response_system_failures} response system failure"
            f"{'s' if response_system_failures != 1 else ''}."
        )
    if response_unknown:
        blockers.append(
            f"Current session has {response_unknown} unknown response outcome"
            f"{'s' if response_unknown != 1 else ''}."
        )
    if route_system_failures:
        blockers.append(
            f"Current session has {route_system_failures} routing system failure"
            f"{'s' if route_system_failures != 1 else ''}."
        )
    if route_unknown:
        blockers.append(
            f"Current session has {route_unknown} unknown routing outcome"
            f"{'s' if route_unknown != 1 else ''}."
        )
    if exact_unknown:
        blockers.append(
            f"Current session has {exact_unknown} unclassified exact route"
            f"{'s' if exact_unknown != 1 else ''}."
        )

    if route_decisions >= MIN_ROUTE_DECISIONS and route_healthy_rate < MIN_HEALTHY_RATE:
        blockers.append(
            f"Healthy guarded routing is {route_healthy_rate:.1%}, below {MIN_HEALTHY_RATE:.0%}."
        )
    if (
        response_attempts >= MIN_RESPONSE_GUARDED_ATTEMPTS
        and response_healthy_rate < MIN_HEALTHY_RATE
    ):
        blockers.append(
            f"Healthy guarded responses are {response_healthy_rate:.1%}, below {MIN_HEALTHY_RATE:.0%}."
        )

    if route_decisions < MIN_ROUTE_DECISIONS:
        missing_evidence.append(
            f"Need {MIN_ROUTE_DECISIONS - route_decisions} more guarded route decision"
            f"{'s' if MIN_ROUTE_DECISIONS - route_decisions != 1 else ''}."
        )
    if response_attempts < MIN_RESPONSE_GUARDED_ATTEMPTS:
        missing_evidence.append(
            f"Need {MIN_RESPONSE_GUARDED_ATTEMPTS - response_attempts} more guarded response attempt"
            f"{'s' if MIN_RESPONSE_GUARDED_ATTEMPTS - response_attempts != 1 else ''}."
        )
    if exact_observations < MIN_EXACT_ROUTE_OBSERVATIONS:
        missing_evidence.append(
            f"Need {MIN_EXACT_ROUTE_OBSERVATIONS - exact_observations} more exact local route observation"
            f"{'s' if MIN_EXACT_ROUTE_OBSERVATIONS - exact_observations != 1 else ''}."
        )

    if blockers:
        status = "blocked"
    elif missing_evidence:
        status = "collecting"
    else:
        status = "ready"

    recommendation = _readiness_recommendation(
        status=status,
        planner_mode=normalized_planner_mode,
    )
    display = _display_metadata(
        status=status,
        planner_mode=normalized_planner_mode,
    )

    return {
        "status": status,
        "ready": status == "ready",
        "promotionTarget": "active",
        "automaticPromotion": False,
        "recommendation": recommendation,
        "blockers": blockers,
        "missingEvidence": missing_evidence,
        **display,
        "sampleRequirements": {
            "routeDecisions": MIN_ROUTE_DECISIONS,
            "responseGuardedAttempts": MIN_RESPONSE_GUARDED_ATTEMPTS,
            "exactRouteObservations": MIN_EXACT_ROUTE_OBSERVATIONS,
            "healthyRate": MIN_HEALTHY_RATE,
        },
        "currentSamples": {
            "routeDecisions": route_decisions,
            "responseGuardedAttempts": response_attempts,
            "exactRouteObservations": exact_observations,
            "routeHealthyRate": route_healthy_rate,
            "responseHealthyRate": response_healthy_rate,
        },
    }
