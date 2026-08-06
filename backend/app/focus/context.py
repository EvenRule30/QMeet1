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

from app.focus.models import (
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



def _contains(values: list[str], target: str) -> bool:
    expected = target.casefold()
    return any(value.casefold() == expected for value in values)


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


def _message(field: FocusContextField, value: str, title: str, outcome: str) -> str:
    labels = {
        "requirements": "requirement",
        "constraints": "constraint",
        "preferences": "preference",
        "decisions": "decision",
        "knownFacts": "Focus detail",
    }
    verb = "Kept" if outcome == "reused" else "Added"
    return f'{verb} {labels[field]} for {title}: {value}.'


def _verified_result(
    *,
    request: NativeFocusContextRequest,
    state: FocusState,
    source_turn_id: str,
    outcome: Literal["added", "reused"],
) -> NativeFocusContextResult:
    return NativeFocusContextResult(
        outcome=outcome,
        focusId=state.focusId,
        focusTitle=state.title,
        field=request.field,
        value=request.value,
        sourceTurnId=source_turn_id,
        updatedAt=state.updatedAt,
        focusContext=_snapshot(state),
        verification=NativeFocusContextVerification(
            activeFocusMatches=True,
            objectivePreserved=True,
            contextPersisted=True,
            sourceTurnUnique=True,
        ),
        message=_message(request.field, request.value, state.title, outcome),
    )


def add_focus_context_verified(
    request: NativeFocusContextRequest,
) -> NativeFocusContextResult:
    source_turn_id = request.sourceTurnId or f"focus-context-{uuid4().hex}"
    current = get_state()
    if current.focusId != request.expectedFocusId or current.status not in _OPEN_STATUSES:
        _health("failed", "stale_focus", source_turn_id=source_turn_id, active_focus_id=current.focusId, field=request.field)
        raise NativeFocusContextError(
            "stale_focus",
            "The expected canonical Focus is not the active Focus.",
        )
    if current.objective != request.expectedObjective:
        _health("failed", "stale_objective", source_turn_id=source_turn_id, active_focus_id=current.focusId, field=request.field)
        raise NativeFocusContextError(
            "stale_objective",
            "The canonical Focus objective changed before this context could be attached.",
        )

    existing_turn_events = [
        event for event in list_events(limit=1000) if event.sourceTurnId == source_turn_id
    ]
    field_values = list(getattr(current, request.field))
    if existing_turn_events:
        matching_context_events = [
            event
            for event in existing_turn_events
            if event.focusId == current.focusId
            and str(event.payload.get("field", "")) == request.field
            and str(event.payload.get("value", "")).casefold()
            == request.value.casefold()
        ]
        if len(matching_context_events) != 1 or not _contains(
            field_values,
            request.value,
        ):
            _health("failed", "source_turn_conflict", source_turn_id=source_turn_id, active_focus_id=current.focusId, field=request.field)
            raise NativeFocusContextError(
                "source_turn_conflict",
                "This source turn is already attached to a different canonical Focus change.",
            )
        _health("reused", source_turn_id=source_turn_id, active_focus_id=current.focusId, field=request.field)
        return _verified_result(
            request=request,
            state=current,
            source_turn_id=source_turn_id,
            outcome="reused",
        )

    already_present = _contains(field_values, request.value)
    plan = TurnPlan(
        route=TurnRoute.FOCUS_ACTION,
        focusOperations=[
            FocusOperation(
                kind=FocusOperationKind.ADD_LIST_ITEM,
                field=_FIELD_ENUM[request.field],
                value=request.value,
                confidence=1.0,
                reason="Explicit user-supplied durable Focus context.",
            )
        ],
        responseIntent=ResponseIntent(
            acknowledge="",
            answerDirectly=False,
            attachToFocus=True,
        ),
        confidence=1.0,
        reason="Verified native Focus context accumulation.",
    )
    updated = apply_turn_plan(
        plan,
        message=request.value,
        turn_id=source_turn_id,
        source="native-focus-context",
    )
    persisted = _contains(list(getattr(updated, request.field)), request.value)
    active_matches = (
        updated.focusId == request.expectedFocusId and updated.status in _OPEN_STATUSES
    )
    objective_preserved = updated.objective == request.expectedObjective
    turn_events = [
        event for event in list_events(limit=1000) if event.sourceTurnId == source_turn_id
    ]
    context_events = [
        event
        for event in turn_events
        if event.focusId == request.expectedFocusId
        and str(event.payload.get("field", "")) == request.field
        and str(event.payload.get("value", "")).casefold() == request.value.casefold()
    ]
    source_unique = len(context_events) == 1
    if not (active_matches and objective_preserved and persisted and source_unique):
        _health("failed", "verification_failed", source_turn_id=source_turn_id, active_focus_id=updated.focusId, field=request.field)
        raise NativeFocusContextError(
            "verification_failed",
            "Canonical Focus state did not verify the exact context item without replacing the objective.",
        )

    outcome: Literal["added", "reused"] = "reused" if already_present else "added"
    _health(outcome, source_turn_id=source_turn_id, active_focus_id=updated.focusId, field=request.field)
    return _verified_result(
        request=request,
        state=updated,
        source_turn_id=source_turn_id,
        outcome=outcome,
    )
