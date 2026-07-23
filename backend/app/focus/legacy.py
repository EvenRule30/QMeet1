from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from app.focus.models import (
    FocusStatus,
    LegacyFocusSeed,
    PendingQuestion,
)


def _clean(value: object, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()[:limit]


def _clean_list(value: object, limit: int = 30) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []
    seen: set[str] = set()

    for raw in value:
        item = _clean(raw, 500)
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break

    return result


def _call_optional(module_name: str, function_name: str) -> Any:
    try:
        module = __import__(module_name, fromlist=[function_name])
        function: Callable[..., Any] | None = getattr(
            module,
            function_name,
            None,
        )
        return function() if callable(function) else None
    except Exception:
        return None


def _status_from_stage(stage: str) -> FocusStatus:
    normalized = stage.casefold().strip()

    if normalized == "complete":
        return FocusStatus.COMPLETE
    if normalized == "ready":
        return FocusStatus.READY
    if normalized in {"waiting", "blocked"}:
        return FocusStatus.WAITING
    if normalized in {"discovery", "clarifying"}:
        return FocusStatus.CLARIFYING
    return FocusStatus.ACTIVE


def _pending_question_from_context(
    context: dict[str, Any],
    *,
    asked_at: str,
) -> PendingQuestion | None:
    raw_pending = context.get("pendingQuestion")

    if isinstance(raw_pending, dict):
        question = _clean(raw_pending.get("question"), 320)
        if question:
            return PendingQuestion(
                target=(
                    _clean(raw_pending.get("target"), 80)
                    or "legacy_pending_question"
                ),
                question=question,
                askedAt=(
                    _clean(raw_pending.get("askedAt"), 80)
                    or asked_at
                ),
            )

    open_questions = _clean_list(context.get("openQuestions"), 20)
    if not open_questions:
        return None

    return PendingQuestion(
        target="legacy_open_question",
        question=open_questions[0],
        askedAt=asked_at,
    )


def load_legacy_focus_seed() -> LegacyFocusSeed | None:
    """Read the current legacy focus without making it a dependency of Focus.

    Imports are deliberately optional so the new architecture can remain usable
    while the old work-context module is being simplified or removed.
    """

    session = _call_optional("app.memory_store", "get_active_session")
    if not isinstance(session, dict):
        return None

    context_payload = _call_optional(
        "app.work_context",
        "get_background_work_context",
    )
    context = (
        context_payload.get("activeContext")
        if isinstance(context_payload, dict)
        else None
    )
    if not isinstance(context, dict):
        context = {}

    title = _clean(session.get("title"), 180) or _clean(
        context.get("title"),
        180,
    )
    if not title:
        return None

    objective = (
        _clean(context.get("objective"), 500)
        or _clean(session.get("goal"), 500)
        or title
    )
    audience = _clean(context.get("audience"), 300)
    stakeholders = [audience] if audience else []

    focus_type = _clean(context.get("focusType"), 60)
    mode = _clean(context.get("mode"), 60) or _clean(
        session.get("mode"),
        60,
    )
    tags = [value for value in (focus_type, mode) if value]

    created_at = _clean(session.get("startedAt"), 80)
    updated_at = _clean(context.get("updatedAt"), 80)
    if not created_at:
        created_at = datetime.now().astimezone().isoformat()
    if not updated_at:
        updated_at = created_at

    return LegacyFocusSeed(
        focusId=_clean(session.get("id"), 160),
        title=title,
        objective=objective,
        subject=_clean(context.get("subject"), 400),
        stakeholders=stakeholders,
        requirements=_clean_list(context.get("requirements"), 20),
        constraints=_clean_list(context.get("constraints"), 20),
        preferences=_clean_list(context.get("preferences"), 20),
        decisions=_clean_list(context.get("decisions"), 30),
        knownFacts=_clean_list(context.get("knownFacts"), 40),
        milestones=_clean_list(context.get("milestones"), 20),
        completedMilestones=_clean_list(
            context.get("recentProgress"),
            40,
        ),
        pendingQuestion=_pending_question_from_context(
            context,
            asked_at=updated_at,
        ),
        nextAction=_clean(context.get("nextAction"), 600),
        status=_status_from_stage(_clean(context.get("stage"), 40)),
        tags=tags,
        createdAt=created_at,
        updatedAt=updated_at,
    )
