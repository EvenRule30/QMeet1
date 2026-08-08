from __future__ import annotations

from typing import Any

from app.focus.models import FocusState, FocusStatus
from app.focus.store import get_state


_OPEN_FOCUS_STATUSES = {
    FocusStatus.CLARIFYING,
    FocusStatus.ACTIVE,
    FocusStatus.WAITING,
    FocusStatus.READY,
}


def _canonical_session_mode(state: FocusState) -> str:
    """Project the canonical Focus into the small legacy coaching mode vocabulary."""

    haystack = f"{state.title} {state.objective} {state.subject}".casefold()
    if "meeting" in haystack:
        return "meeting"
    if any(
        token in haystack
        for token in (
            "code",
            "coding",
            "software",
            "app",
            "website",
            "api",
            "database",
            "python",
            "javascript",
            "typescript",
            "react",
            "bug",
            "debug",
        )
    ):
        return "coding"
    if any(
        token in haystack
        for token in (
            "research",
            "paper",
            "essay",
            "literature review",
            "study",
        )
    ):
        return "research"
    if any(
        token in haystack
        for token in (
            "plan",
            "planning",
            "presentation",
            "proposal",
            "roadmap",
            "strategy",
            "deadline",
            "event",
            "trip",
            "launch",
            "review",
        )
    ):
        return "planning"
    return "general"


def get_canonical_active_session() -> dict[str, Any]:
    """Expose canonical Focus through the read shape expected by work_context.

    This is intentionally a read adapter only. It never writes the compatibility
    Memory projection and never treats that projection as an ownership source.
    """

    state = get_state()
    active = (
        state.status in _OPEN_FOCUS_STATUSES
        and bool(state.focusId.strip())
        and bool((state.title or state.objective).strip())
    )
    if not active:
        return {
            "ok": True,
            "provider": "canonical-focus",
            "activeSession": None,
            "message": "No canonical active Focus is available.",
        }

    session = {
        "id": state.focusId,
        "title": state.title or state.objective or "Current focus",
        "mode": _canonical_session_mode(state),
        "goal": state.objective,
        "startedAt": state.createdAt,
        "updatedAt": state.updatedAt,
        "pinnedNoteIds": [],
        "linkedTaskIds": [],
    }
    return {
        "ok": True,
        "provider": "canonical-focus",
        "activeSession": session,
        "message": "Active session projected from canonical Focus state.",
    }


def install_canonical_work_context_source() -> None:
    """Redirect the mature background-coaching module to canonical Focus reads."""

    from app import work_context

    work_context.get_active_session = get_canonical_active_session
