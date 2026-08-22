from __future__ import annotations

from app.daily_brief import is_daily_brief_request
from app.qmeet_agent_shadow import AgentShadowDecision


def apply_daily_brief_ownership_floor(
    user_message: str,
    decision: AgentShadowDecision,
) -> AgentShadowDecision:
    """Keep day-planning requests on the read-only Daily Brief conversation lane.

    The single-intent agent can reasonably notice the task aspect of a request such
    as "what should I do today?" and propose a global task read. That is too narrow:
    Daily Brief intentionally combines canonical Focus, global tasks, and Calendar.

    This floor changes ownership only. It does not read or mutate capability state;
    the dedicated Daily Brief conversation lane remains responsible for assembling
    one verified cross-capability snapshot before generating the visible response.
    """

    if not is_daily_brief_request(user_message):
        return decision

    return decision.model_copy(
        update={
            "turnOwner": "general_chat",
            "focusRelevant": False,
            "disposition": "conversation",
            "proposedCapability": "none",
            "proposedAction": "conversation.respond",
            "proposedArguments": {},
            "responsePlan": (
                "Use the dedicated read-only Daily Brief conversation lane to combine "
                "verified canonical Focus, global tasks, and Calendar context into one "
                "prioritized recommendation for today."
            ),
            "confidence": max(decision.confidence, 0.99),
            "reason": (
                "Deterministic Daily Brief ownership floor: a clear day-planning request "
                "must reach the cross-capability read-only Daily Brief lane instead of "
                "being reduced to one Tasks or Calendar read."
            ),
        }
    )
