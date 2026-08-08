from __future__ import annotations

from app.focus import store as focus_store
from app.focus.context_hygiene import question_answered_by_focus_update
from app.focus.lifecycle import (
    NativeFocusLifecycleError,
    NativeFocusUpdateRequest,
    NativeFocusUpdateResult,
)
from app.focus.models import FocusEventType, FocusStatus


_NATIVE_GOAL_QUESTION_SOURCE = "focus-native-goal-question-resolution"


def resolve_pending_question_after_verified_update(
    request: NativeFocusUpdateRequest,
    result: NativeFocusUpdateResult,
) -> NativeFocusUpdateResult:
    """Clear a generic outcome question when a verified goal update answers it.

    The lifecycle update remains the authority for the objective mutation. This
    companion step only clears the exact pending question returned by that
    verified update, persists a canonical QUESTION_CLEARED event, and then
    re-verifies Focus identity and objective before returning success wording.
    """
    if not result.verified:
        return result
    if request.objective is None or "objective" not in result.changedFields:
        return result

    pending = result.activeFocus.pendingQuestion
    if not question_answered_by_focus_update(
        pending,
        field="objective",
        value=request.objective,
    ):
        return result
    if pending is None:
        return result

    expected_focus_id = request.expectedFocusId.strip()
    expected_objective = request.objective.strip()
    pending_question = pending.question.strip()
    if not expected_objective or not pending_question:
        return result

    try:
        with focus_store._STORE_LOCK:
            document = focus_store._read_log_unlocked()
            current = focus_store.reduce_events(document.events)

            if (
                current.status in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
                or current.focusId != expected_focus_id
                or current.objective != expected_objective
            ):
                raise NativeFocusLifecycleError(
                    "question_resolution_stale",
                    "The Focus changed before its answered coaching question could be cleared.",
                )

            current_pending = current.pendingQuestion
            if current_pending is None:
                return result.model_copy(update={"activeFocus": current})

            if current_pending.question.strip().casefold() != pending_question.casefold():
                # A newer question now owns the coaching slot. Never clear it on
                # behalf of an older lifecycle receipt.
                return result.model_copy(update={"activeFocus": current})

            clear_event = focus_store._new_event(
                FocusEventType.QUESTION_CLEARED,
                focus_id=expected_focus_id,
                payload={
                    "nativeLifecycleCompanion": True,
                    "nativeOperation": "update_focus",
                    "resolvedByField": "objective",
                    "resolvedQuestion": pending_question,
                },
                source_turn_id=f"{request.sourceTurnId}:goal-question",
                source=_NATIVE_GOAL_QUESTION_SOURCE,
            )
            document.events.append(clear_event)
            focus_store._atomic_write_unlocked(document)

            persisted_document = focus_store._read_log_unlocked()
            persisted_events = list(persisted_document.events)
            persisted_ids = {event.id for event in persisted_events}
            persisted = focus_store.reduce_events(persisted_events)

            if (
                clear_event.id not in persisted_ids
                or persisted.focusId != expected_focus_id
                or persisted.objective != expected_objective
                or persisted.pendingQuestion is not None
            ):
                raise NativeFocusLifecycleError(
                    "question_resolution_verification_failed",
                    "The goal update succeeded, but the answered coaching question could not be verified as cleared.",
                )
    except NativeFocusLifecycleError:
        raise
    except focus_store.FocusStoreError as exc:
        raise NativeFocusLifecycleError(
            "question_resolution_write_failed",
            "The goal update succeeded, but the canonical coaching question could not be updated.",
            status_code=503,
        ) from exc
    except Exception as exc:
        raise NativeFocusLifecycleError(
            "question_resolution_write_failed",
            "The goal update succeeded, but the coaching-question resolution could not be completed.",
            status_code=503,
        ) from exc

    return result.model_copy(
        update={
            "activeFocus": persisted,
            "message": f"{result.message} Answered the current Focus question.",
        }
    )
