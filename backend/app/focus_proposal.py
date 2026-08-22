from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4

from app.focus.models import FocusEvent, FocusEventType, FocusStatus
from app.focus.store import append_events, get_state


_PROPOSAL_TTL_SECONDS = 180
_OPEN_FOCUS_STATUSES = {
    FocusStatus.CLARIFYING,
    FocusStatus.ACTIVE,
    FocusStatus.WAITING,
    FocusStatus.READY,
}
_PROPOSAL_LOCK = RLock()


@dataclass(frozen=True)
class FocusNextActionProposal:
    focus_id: str
    focus_title: str
    next_action: str
    expected_next_action: str
    created_at: datetime
    expires_at: datetime
    source: str = "daily-brief"


@dataclass(frozen=True)
class FocusProposalAcceptanceResult:
    handled: bool
    changed: bool
    message: str
    focus_id: str = ""
    next_action: str = ""


_PENDING_PROPOSAL: FocusNextActionProposal | None = None

_ACCEPTANCE_PATTERNS = (
    re.compile(r"^(?:ok|okay|alright|all right|sure|yes|yeah|yep|sounds good)[.!]?$", re.I),
    re.compile(r"^(?:ok|okay|alright|all right|sure|yes|yeah|yep)[, ]+(?:let'?s\s+)?(?:do|go with|start with|start on)\s+(?:it|that|there)[.!]?$", re.I),
    re.compile(r"^(?:let'?s\s+)?(?:do|go with|start with|start on)\s+(?:it|that|there)[.!]?$", re.I),
    re.compile(r"^(?:go ahead|do it|let'?s do it|let'?s start there)[.!]?$", re.I),
)

_PROPOSAL_EXTRACTION_PATTERNS = (
    re.compile(r"\bI[’']d start by\s+(?P<action>[^.!?]+)", re.I),
    re.compile(r"\bI would start by\s+(?P<action>[^.!?]+)", re.I),
    re.compile(r"\bI[’']d recommend first\s+(?P<action>[^.!?]+)", re.I),
    re.compile(r"\bFirst(?: step)?[:,]\s*(?P<action>[^.!?]+)", re.I),
)


def _now() -> datetime:
    return datetime.now().astimezone()


def _normalize_text(value: Any, *, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].strip()


def _is_open_focus_status(value: Any) -> bool:
    try:
        return FocusStatus(str(getattr(value, "value", value))) in _OPEN_FOCUS_STATUSES
    except ValueError:
        return False


def _is_expired(proposal: FocusNextActionProposal) -> bool:
    return _now() >= proposal.expires_at


def is_natural_proposal_acceptance(user_message: str) -> bool:
    text = _normalize_text(user_message, limit=160)
    if not text or len(text.split()) > 8:
        return False
    return any(pattern.fullmatch(text) for pattern in _ACCEPTANCE_PATTERNS)


def clear_pending_focus_proposal() -> None:
    global _PENDING_PROPOSAL
    with _PROPOSAL_LOCK:
        _PENDING_PROPOSAL = None


def get_pending_focus_proposal() -> FocusNextActionProposal | None:
    global _PENDING_PROPOSAL
    with _PROPOSAL_LOCK:
        proposal = _PENDING_PROPOSAL
        if proposal is None:
            return None
        if _is_expired(proposal):
            _PENDING_PROPOSAL = None
            return None
        return proposal


def _extract_next_action_from_reply(reply: str) -> str:
    text = _normalize_text(reply, limit=4000)
    for pattern in _PROPOSAL_EXTRACTION_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        action = _normalize_text(match.group("action"), limit=500).strip(' "“”')
        action = re.sub(r"^(?:just|simply)\s+", "", action, flags=re.I)
        if not action or len(action.split()) > 24:
            return ""
        # One-turn acceptance is only safe when QMeet proposed one concrete step.
        if re.search(r"\b(?:or|alternatively|either)\b", action, flags=re.I):
            return ""
        return action
    return ""


def remember_focus_next_action_proposal(
    context: dict[str, Any],
    assistant_reply: str,
) -> FocusNextActionProposal | None:
    """Remember one concrete Daily Brief next-step proposal for the next turn only."""

    clear_pending_focus_proposal()
    focus = context.get("activeFocus") if isinstance(context, dict) else None
    if not isinstance(focus, dict):
        return None

    focus_id = _normalize_text(focus.get("focusId"), limit=180)
    focus_title = _normalize_text(focus.get("title"), limit=180)
    expected_next_action = _normalize_text(focus.get("nextAction"), limit=500)
    if not focus_id or expected_next_action:
        # I4 only fills a missing next action. It never silently replaces one.
        return None
    if not _is_open_focus_status(focus.get("status")):
        return None

    next_action = _extract_next_action_from_reply(assistant_reply)
    if not next_action:
        return None

    created_at = _now()
    proposal = FocusNextActionProposal(
        focus_id=focus_id,
        focus_title=focus_title,
        next_action=next_action,
        expected_next_action=expected_next_action,
        created_at=created_at,
        expires_at=created_at + timedelta(seconds=_PROPOSAL_TTL_SECONDS),
    )
    global _PENDING_PROPOSAL
    with _PROPOSAL_LOCK:
        _PENDING_PROPOSAL = proposal
    return proposal


def _proposal_matches_canonical_focus(proposal: FocusNextActionProposal) -> bool:
    try:
        state = get_state()
    except Exception:
        return False
    return (
        state.focusId == proposal.focus_id
        and state.status in _OPEN_FOCUS_STATUSES
        and _normalize_text(state.nextAction, limit=500) == proposal.expected_next_action
    )


def prepare_focus_proposal_turn(user_message: str) -> bool:
    """Return True only when this turn can accept the fresh proposal.

    Any other user turn expires the proposal. This is intentionally one-turn
    conversational context, not durable Memory.
    """

    proposal = get_pending_focus_proposal()
    if proposal is None:
        return False
    if not is_natural_proposal_acceptance(user_message):
        clear_pending_focus_proposal()
        return False
    if not _proposal_matches_canonical_focus(proposal):
        clear_pending_focus_proposal()
        return False
    return True


def accept_pending_focus_next_action(
    user_message: str,
    *,
    source_turn_id: str = "",
) -> FocusProposalAcceptanceResult | None:
    proposal = get_pending_focus_proposal()
    if proposal is None:
        return None
    if not is_natural_proposal_acceptance(user_message):
        # A proposal belongs only to the immediately following user turn, even
        # when a legacy/direct chat caller bypasses the shadow ownership seam.
        clear_pending_focus_proposal()
        return None

    # Consume first so retries/double submits cannot apply the same proposal twice.
    clear_pending_focus_proposal()
    if not _proposal_matches_canonical_focus(proposal):
        return FocusProposalAcceptanceResult(
            handled=True,
            changed=False,
            message=(
                "That suggestion is no longer current, so I did not change your Focus."
            ),
            focus_id=proposal.focus_id,
            next_action=proposal.next_action,
        )

    turn_id = _normalize_text(source_turn_id, limit=120) or f"proposal-turn-{uuid4().hex}"
    event = FocusEvent(
        id=f"focus-event-{uuid4().hex}",
        focusId=proposal.focus_id,
        type=FocusEventType.NEXT_ACTION_SET,
        payload={"value": proposal.next_action},
        sourceTurnId=turn_id,
        source="daily-brief-proposal-acceptance",
        confidence=1.0,
        createdAt=_now().isoformat(),
    )
    try:
        append_events([event])
        state = get_state()
    except Exception:
        return FocusProposalAcceptanceResult(
            handled=True,
            changed=False,
            message="I couldn't verify that Focus update, so I left the next step unchanged.",
            focus_id=proposal.focus_id,
            next_action=proposal.next_action,
        )

    verified = (
        state.focusId == proposal.focus_id
        and state.status in _OPEN_FOCUS_STATUSES
        and _normalize_text(state.nextAction, limit=500) == proposal.next_action
    )
    if not verified:
        return FocusProposalAcceptanceResult(
            handled=True,
            changed=False,
            message="I couldn't verify that Focus update, so I won't claim it changed.",
            focus_id=proposal.focus_id,
            next_action=proposal.next_action,
        )

    action = proposal.next_action.rstrip(". ")
    return FocusProposalAcceptanceResult(
        handled=True,
        changed=True,
        message=f"Alright — your Focus next step is now: {action}.",
        focus_id=proposal.focus_id,
        next_action=proposal.next_action,
    )
