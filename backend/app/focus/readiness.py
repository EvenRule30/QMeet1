from __future__ import annotations

from typing import Any, Mapping


MIN_ROUTE_DECISIONS = 8
MIN_RESPONSE_GUARDED_ATTEMPTS = 3
MIN_EXACT_ROUTE_OBSERVATIONS = 5
MIN_HEALTHY_RATE = 0.95


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
    """Evaluate whether current-session evidence supports planner promotion.

    This function is advisory only. It never changes environment variables or
    runtime modes. The thresholds are intentionally modest for the prototype,
    but they still require evidence from all three routing surfaces.
    """

    normalized_planner_mode = planner_mode.strip().casefold()
    normalized_response_mode = response_mode.strip().casefold()
    normalized_route_mode = route_mode.strip().casefold()

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
        recommendation = "Keep the planner in shadow mode and resolve the blocking evidence."
    elif missing_evidence:
        status = "collecting"
        recommendation = "Keep the planner in shadow mode while collecting current-session evidence."
    else:
        status = "ready"
        recommendation = (
            "Current-session evidence supports a deliberate, manual planner-mode promotion review."
        )

    return {
        "status": status,
        "ready": status == "ready",
        "promotionTarget": "active",
        "automaticPromotion": False,
        "recommendation": recommendation,
        "blockers": blockers,
        "missingEvidence": missing_evidence,
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
