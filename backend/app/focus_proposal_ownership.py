from __future__ import annotations

from app.focus_proposal import (
    is_natural_proposal_acceptance,
    prepare_focus_proposal_turn,
)
from app.qmeet_agent_shadow import AgentShadowDecision


def apply_focus_proposal_ownership_floor(
    user_message: str,
    decision: AgentShadowDecision,
) -> AgentShadowDecision:
    """Resolve short agreement safely against one fresh Focus proposal.

    A fresh, canonically valid proposal remains Focus-owned. The same natural
    acknowledgment without a fresh proposal is explicitly conversational so an
    over-eager lifecycle classifier cannot reinterpret "okay, let's do it" as
    an unspecified Focus mutation.
    """

    if prepare_focus_proposal_turn(user_message):
        return decision.model_copy(
            update={
                "turnOwner": "focus",
                "focusRelevant": True,
                "disposition": "conversation",
                "proposedCapability": "focus",
                "proposedAction": "focus.help",
                "proposedArguments": {},
                "responsePlan": (
                    "Accept the one fresh Daily Brief next-step proposal only after "
                    "canonical Focus identity and current nextAction are re-verified."
                ),
                "confidence": 1.0,
                "reason": (
                    "Deterministic proposal-acceptance ownership floor: this short reply "
                    "unambiguously accepts QMeet's immediately preceding fresh Focus next-step proposal."
                ),
            }
        )

    if not is_natural_proposal_acceptance(user_message):
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
                "Interpret this short acknowledgment from recent conversation only. "
                "There is no fresh verified Focus proposal, so do not mutate Focus."
            ),
            "confidence": max(decision.confidence, 0.99),
            "reason": (
                "Deterministic orphan-acceptance safety floor: natural agreement without "
                "one fresh verified proposal is conversation, never an implicit Focus mutation."
            ),
        }
    )
