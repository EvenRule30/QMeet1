from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.focus.context_hygiene import (
    duplicate_values_to_remove,
    find_semantic_match,
    question_answered_by_context,
    semantically_equivalent,
)
from app.focus.models import (
    FocusEventType,
    FocusField,
    FocusOperation,
    FocusOperationKind,
    FocusState,
    FocusStatus,
    ResponseIntent,
    TurnPlan,
    TurnRoute,
)
from app.focus.store import apply_turn_plan, get_state, list_events

FocusContextField = Literal[
    "requirements",
    "constraints",
    "preferences",
    "decisions",
    "knownFacts",
]

_OPEN_STATUSES = {
    FocusStatus.CLARIFYING,
    FocusStatus.ACTIVE,
    FocusStatus.WAITING,
    FocusStatus.READY,
}
_FIELD_ENUM = {
    "requirements": FocusField.REQUIREMENTS,
    "constraints": FocusField.CONSTRAINTS,
    "preferences": FocusField.PREFERENCES,
    "decisions": FocusField.DECISIONS,
    "knownFacts": FocusField.KNOWN_FACTS,
}
_HYGIENE_FIELDS = {
    "requirements": FocusField.REQUIREMENTS,
    "constraints": FocusField.CONSTRAINTS,
    "preferences": FocusField.PREFERENCES,
    "decisions": FocusField.DECISIONS,
    "knownFacts": FocusField.KNOWN_FACTS,
}
_MAX_HYGIENE_REMOVALS = 14
_CONTEXT_SOURCE = "native-focus-context"
_CONTEXT_NEUTRAL_RESPONSE_EVENT_TYPES = {
    FocusEventType.RESPONSE_CANDIDATE,
    FocusEventType.RESPONSE_SELECTION,
    FocusEventType.ASSISTANT_REPLIED,
}

_HEALTH_LOCK = RLock()


def _empty_health() -> dict[str, object]:
    return {
        "version": 1,
        "updatedAt": "",
        "addFocusContext": {
            "attemptCount": 0,
            "addedCount": 0,
            "reusedCount": 0,
            "verifiedCount": 0,
            "failedCount": 0,
            "lastOutcome": "",
            "lastFailureCode": "",
            "lastSourceTurnId": "",
            "lastActiveFocusId": "",
            "lastField": "",
            "lastUpdatedAt": "",
        },
    }


def _health_file() -> Path:
    configured = os.getenv("QMEET_FOCUS_CONTEXT_HEALTH_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "qmeet_focus_context_health.json"


def _read_health_unlocked() -> dict[str, object]:
    path = _health_file()
    if not path.exists():
        return _empty_health()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_health()
    if not isinstance(payload, dict):
        return _empty_health()
    baseline = _empty_health()
    incoming = payload.get("addFocusContext")
    section = baseline["addFocusContext"]
    if isinstance(incoming, dict) and isinstance(section, dict):
        section.update(incoming)
    baseline["updatedAt"] = str(payload.get("updatedAt", ""))
    return baseline


def _atomic_write_health_unlocked(document: dict[str, object]) -> None:
    path = _health_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    document["updatedAt"] = _now_iso()
    handle = None
    temporary_path: Path | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(handle.name)
        json.dump(document, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        temporary_path.replace(path)
    finally:
        if handle is not None:
            handle.close()
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


class NativeFocusContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedFocusId: str = Field(min_length=1, max_length=160)
    expectedObjective: str = Field(default="", max_length=500)
    field: FocusContextField
    value: str = Field(min_length=1, max_length=800)
    sourceTurnId: str = Field(default="", max_length=120)

    @field_validator(
        "expectedFocusId",
        "expectedObjective",
        "value",
        "sourceTurnId",
    )
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.split()).strip()


class NativeFocusContextSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focusId: str
    title: str
    objective: str
    status: Literal["clarifying", "active", "waiting", "ready"]
    requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    knownFacts: list[str] = Field(default_factory=list)
    updatedAt: str


class NativeFocusContextVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activeFocusMatches: bool
    objectivePreserved: bool
    contextPersisted: bool
    sourceTurnUnique: bool


class NativeFocusContextResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True] = True
    operation: Literal["add_focus_context"] = "add_focus_context"
    outcome: Literal["added", "reused"]
    verified: Literal[True] = True
    focusId: str
    focusTitle: str
    field: FocusContextField
    value: str
    canonicalValue: str
    sourceTurnId: str
    updatedAt: str
    focusContext: NativeFocusContextSnapshot
    verification: NativeFocusContextVerification
    message: str


class NativeFocusContextError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _health(
    outcome: str,
    failure_code: str = "",
    *,
    source_turn_id: str = "",
    active_focus_id: str = "",
    field: str = "",
) -> None:
    try:
        with _HEALTH_LOCK:
            document = _read_health_unlocked()
            section = document.get("addFocusContext")
            if not isinstance(section, dict):
                document = _empty_health()
                section = document["addFocusContext"]
            assert isinstance(section, dict)
            section["attemptCount"] = int(section.get("attemptCount", 0)) + 1
            if failure_code:
                section["failedCount"] = int(section.get("failedCount", 0)) + 1
                section["lastOutcome"] = "failed"
                section["lastFailureCode"] = failure_code
            else:
                section["verifiedCount"] = int(section.get("verifiedCount", 0)) + 1
                count_key = "reusedCount" if outcome == "reused" else "addedCount"
                section[count_key] = int(section.get(count_key, 0)) + 1
                section["lastOutcome"] = outcome
                section["lastFailureCode"] = ""
            section["lastSourceTurnId"] = source_turn_id
            section["lastActiveFocusId"] = active_focus_id
            section["lastField"] = field
            section["lastUpdatedAt"] = _now_iso()
            _atomic_write_health_unlocked(document)
    except Exception:
        # Health evidence must never change the mutation result.
        return


def get_native_focus_context_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        return _read_health_unlocked()


def reset_native_focus_context_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        document = _empty_health()
        _atomic_write_health_unlocked(document)
        return document


def _snapshot(state: FocusState) -> NativeFocusContextSnapshot:
    if state.status not in _OPEN_STATUSES:
        raise NativeFocusContextError(
            "stale_focus",
            "The canonical Focus is no longer open.",
        )
    return NativeFocusContextSnapshot(
        focusId=state.focusId,
        title=state.title,
        objective=state.objective,
        status=state.status.value,
        requirements=list(state.requirements),
        constraints=list(state.constraints),
        preferences=list(state.preferences),
        decisions=list(state.decisions),
        knownFacts=list(state.knownFacts),
        updatedAt=state.updatedAt,
    )


def _message(
    field: FocusContextField,
    value: str,
    title: str,
    outcome: str,
    *,
    question_resolved: bool,
) -> str:
    labels = {
        "requirements": "requirement",
        "constraints": "constraint",
        "preferences": "preference",
        "decisions": "decision",
        "knownFacts": "Focus detail",
    }
    verb = "Kept" if outcome == "reused" else "Added"
    message = f"{verb} {labels[field]} for {title}: {value}."
    if question_resolved:
        message = f"{message} Answered the current Focus question."
    return message


def _verified_result(
    *,
    request: NativeFocusContextRequest,
    state: FocusState,
    source_turn_id: str,
    outcome: Literal["added", "reused"],
    canonical_value: str,
    question_resolved: bool = False,
) -> NativeFocusContextResult:
    return NativeFocusContextResult(
        outcome=outcome,
        focusId=state.focusId,
        focusTitle=state.title,
        field=request.field,
        value=request.value,
        canonicalValue=canonical_value,
        sourceTurnId=source_turn_id,
        updatedAt=state.updatedAt,
        focusContext=_snapshot(state),
        verification=NativeFocusContextVerification(
            activeFocusMatches=True,
            objectivePreserved=True,
            contextPersisted=True,
            sourceTurnUnique=True,
        ),
        message=_message(
            request.field,
            request.value,
            state.title,
            outcome,
            question_resolved=question_resolved,
        ),
    )


def _hygiene_operations(
    state: FocusState,
    *,
    preferred_field: FocusContextField,
    preferred_value: str,
) -> list[FocusOperation]:
    removal_pairs: list[tuple[FocusField, str]] = []
    for field_name, field_enum in _HYGIENE_FIELDS.items():
        values = list(getattr(state, field_name, []))
        if field_name == preferred_field:
            removals = duplicate_values_to_remove(
                values,
                preferred=preferred_value,
            )
        else:
            removals = duplicate_values_to_remove(values)
        for duplicate in removals:
            removal_pairs.append((field_enum, duplicate))

    operations: list[FocusOperation] = []
    seen: set[tuple[str, str]] = set()
    for field_enum, duplicate in removal_pairs:
        key = (field_enum.value, duplicate.casefold())
        if not duplicate or key in seen:
            continue
        seen.add(key)
        operations.append(
            FocusOperation(
                kind=FocusOperationKind.REMOVE_LIST_ITEM,
                field=field_enum,
                value=duplicate,
                confidence=1.0,
                reason="Canonical semantic duplicate cleanup.",
            )
        )
        if len(operations) >= _MAX_HYGIENE_REMOVALS:
            break
    return operations


def _context_turn_group_is_exclusive(
    events: list,
    *,
    focus_id: str,
) -> bool:
    """Verify mutation ownership without treating response telemetry as a conflict.

    ``apply_turn_plan`` appends response-candidate telemetry under the same
    ``sourceTurnId`` using a dedicated response source. Later guarded-response
    bookkeeping can append response-selection and assistant-reply events as
    well. Those derived events do not own or mutate the Focus operation and
    therefore must not invalidate native context source-turn exclusivity.

    Any other event in the turn group must belong to this context operation
    and to the expected Focus.
    """
    for event in events:
        event_type = getattr(event, "type", None)
        event_focus_id = str(getattr(event, "focusId", "") or "").strip()
        if event_type in _CONTEXT_NEUTRAL_RESPONSE_EVENT_TYPES:
            if event_focus_id and event_focus_id != focus_id:
                return False
            continue
        if (
            getattr(event, "source", _CONTEXT_SOURCE) != _CONTEXT_SOURCE
            or event_focus_id != focus_id
        ):
            return False
    return True


def _matching_context_events(
    events: list,
    *,
    focus_id: str,
    field: FocusContextField,
    value: str,
) -> list:
    return [
        event
        for event in events
        if getattr(event, "type", FocusEventType.LIST_ITEM_ADDED)
        == FocusEventType.LIST_ITEM_ADDED
        and event.focusId == focus_id
        and str(event.payload.get("field", "")) == field
        and semantically_equivalent(
            str(event.payload.get("value", "")),
            value,
        )
    ]


def add_focus_context_verified(
    request: NativeFocusContextRequest,
) -> NativeFocusContextResult:
    source_turn_id = request.sourceTurnId or f"focus-context-{uuid4().hex}"
    current = get_state()
    if current.focusId != request.expectedFocusId or current.status not in _OPEN_STATUSES:
        _health(
            "failed",
            "stale_focus",
            source_turn_id=source_turn_id,
            active_focus_id=current.focusId,
            field=request.field,
        )
        raise NativeFocusContextError(
            "stale_focus",
            "The expected canonical Focus is not the active Focus.",
        )
    if current.objective != request.expectedObjective:
        _health(
            "failed",
            "stale_objective",
            source_turn_id=source_turn_id,
            active_focus_id=current.focusId,
            field=request.field,
        )
        raise NativeFocusContextError(
            "stale_objective",
            "The canonical Focus objective changed before this context could be attached.",
        )

    existing_turn_events = [
        event for event in list_events(limit=1000) if event.sourceTurnId == source_turn_id
    ]
    field_values = list(getattr(current, request.field))
    if existing_turn_events:
        matching_context_events = _matching_context_events(
            existing_turn_events,
            focus_id=current.focusId,
            field=request.field,
            value=request.value,
        )
        group_is_exclusive = _context_turn_group_is_exclusive(
            existing_turn_events,
            focus_id=current.focusId,
        )
        canonical_match = find_semantic_match(field_values, request.value)
        if (
            len(matching_context_events) != 1
            or canonical_match is None
            or not group_is_exclusive
        ):
            _health(
                "failed",
                "source_turn_conflict",
                source_turn_id=source_turn_id,
                active_focus_id=current.focusId,
                field=request.field,
            )
            raise NativeFocusContextError(
                "source_turn_conflict",
                "This source turn is already attached to a different canonical Focus change.",
            )
        _health(
            "reused",
            source_turn_id=source_turn_id,
            active_focus_id=current.focusId,
            field=request.field,
        )
        return _verified_result(
            request=request,
            state=current,
            source_turn_id=source_turn_id,
            outcome="reused",
            canonical_value=canonical_match,
        )

    semantic_match = find_semantic_match(field_values, request.value)
    canonical_value = semantic_match or request.value
    already_present = semantic_match is not None
    question_should_clear = (
        getattr(current, "pendingAction", None) is None
        and question_answered_by_context(
            getattr(current, "pendingQuestion", None),
            field=request.field,
            value=request.value,
        )
    )

    operations = _hygiene_operations(
        current,
        preferred_field=request.field,
        preferred_value=canonical_value,
    )
    operations.append(
        FocusOperation(
            kind=FocusOperationKind.ADD_LIST_ITEM,
            field=_FIELD_ENUM[request.field],
            value=canonical_value,
            confidence=1.0,
            reason="Explicit user-supplied durable Focus context.",
        )
    )
    if question_should_clear:
        operations.append(
            FocusOperation(
                kind=FocusOperationKind.CLEAR_PENDING_QUESTION,
                confidence=1.0,
                reason="The durable user context answered the current Focus question.",
            )
        )

    plan = TurnPlan(
        route=TurnRoute.FOCUS_ACTION,
        focusOperations=operations,
        responseIntent=ResponseIntent(
            acknowledge="",
            answerDirectly=False,
            attachToFocus=True,
        ),
        confidence=1.0,
        reason="Verified native Focus context accumulation with canonical hygiene.",
    )
    updated = apply_turn_plan(
        plan,
        message=request.value,
        turn_id=source_turn_id,
        source=_CONTEXT_SOURCE,
    )

    persisted = any(
        item.casefold() == canonical_value.casefold()
        for item in list(getattr(updated, request.field))
    )
    active_matches = (
        updated.focusId == request.expectedFocusId and updated.status in _OPEN_STATUSES
    )
    objective_preserved = updated.objective == request.expectedObjective
    turn_events = [
        event for event in list_events(limit=1000) if event.sourceTurnId == source_turn_id
    ]
    context_events = _matching_context_events(
        turn_events,
        focus_id=request.expectedFocusId,
        field=request.field,
        value=canonical_value,
    )
    source_unique = (
        len(context_events) == 1
        and _context_turn_group_is_exclusive(
            turn_events,
            focus_id=request.expectedFocusId,
        )
    )
    if question_should_clear:
        question_state_valid = getattr(updated, "pendingQuestion", None) is None
    else:
        question_state_valid = (
            getattr(updated, "pendingQuestion", None)
            == getattr(current, "pendingQuestion", None)
            and getattr(updated, "pendingAction", None)
            == getattr(current, "pendingAction", None)
            and getattr(updated, "nextAction", "")
            == getattr(current, "nextAction", "")
        )

    if not (
        active_matches
        and objective_preserved
        and persisted
        and source_unique
        and question_state_valid
    ):
        _health(
            "failed",
            "verification_failed",
            source_turn_id=source_turn_id,
            active_focus_id=updated.focusId,
            field=request.field,
        )
        raise NativeFocusContextError(
            "verification_failed",
            "Canonical Focus state did not verify the context item, objective, and question continuity.",
        )

    outcome: Literal["added", "reused"] = "reused" if already_present else "added"
    _health(
        outcome,
        source_turn_id=source_turn_id,
        active_focus_id=updated.focusId,
        field=request.field,
    )
    return _verified_result(
        request=request,
        state=updated,
        source_turn_id=source_turn_id,
        outcome=outcome,
        canonical_value=canonical_value,
        question_resolved=question_should_clear,
    )
