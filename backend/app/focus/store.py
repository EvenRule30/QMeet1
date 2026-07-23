from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Iterable
from uuid import uuid4

from app.focus.models import (
    FocusEvent,
    FocusEventLog,
    FocusEventType,
    FocusField,
    FocusOperation,
    FocusOperationKind,
    FocusState,
    FocusStatus,
    LegacyFocusSeed,
    PendingAction,
    PendingQuestion,
    PlannedToolCall,
    ToolName,
    TurnPlan,
)


_STORE_LOCK = RLock()
_MAX_EVENTS = 4000

_STRING_FIELDS = {
    FocusField.TITLE.value,
    FocusField.OBJECTIVE.value,
    FocusField.DELIVERABLE.value,
    FocusField.SUBJECT.value,
    FocusField.NEXT_ACTION.value,
}

_LIST_FIELDS = {
    FocusField.STAKEHOLDERS.value,
    FocusField.REQUIREMENTS.value,
    FocusField.CONSTRAINTS.value,
    FocusField.PREFERENCES.value,
    FocusField.DECISIONS.value,
    FocusField.KNOWN_FACTS.value,
    FocusField.MILESTONES.value,
    FocusField.COMPLETED_MILESTONES.value,
    FocusField.TAGS.value,
}


class FocusStoreError(Exception):
    """Safe error raised by the Focus event store."""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _new_focus_id() -> str:
    return f"focus-{uuid4().hex}"


def _stable_focus_id_from_event(event: FocusEvent) -> str:
    """Return a deterministic fallback ID for older malformed event logs.

    New events always persist a real Focus ID. This fallback only exists so an
    already-written legacy_imported or focus_started event with a blank ID can
    still be replayed without generating a different UUID on every reduction.
    """

    payload_focus_id = str(event.payload.get("focusId", "")).strip()
    if event.focusId.strip():
        return event.focusId.strip()
    if payload_focus_id:
        return payload_focus_id

    event_suffix = event.id.removeprefix("focus-event-").strip()
    if event_suffix:
        return f"focus-{event_suffix}"
    return "focus-unknown-event"


def event_file() -> Path:
    configured = os.getenv("QMEET_FOCUS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "qmeet_focus.json"


def _empty_log() -> FocusEventLog:
    return FocusEventLog(version=1, updatedAt=_now_iso(), events=[])


def _read_log_unlocked() -> FocusEventLog:
    path = event_file()
    if not path.exists():
        return _empty_log()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return FocusEventLog.model_validate(payload)
    except Exception as exc:
        raise FocusStoreError(
            f"Focus event log could not be read: {path}"
        ) from exc


def _atomic_write_unlocked(document: FocusEventLog) -> None:
    path = event_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    document.updatedAt = _now_iso()

    if len(document.events) > _MAX_EVENTS:
        document.events = document.events[-_MAX_EVENTS:]

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
        json.dump(document.model_dump(mode="json"), handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        temporary_path.replace(path)
    except Exception as exc:
        if handle is not None:
            handle.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise FocusStoreError(
            f"Focus event log could not be written: {path}"
        ) from exc


def _new_event(
    event_type: FocusEventType,
    *,
    focus_id: str = "",
    payload: dict | None = None,
    source_turn_id: str = "",
    source: str = "",
    confidence: float = 1.0,
) -> FocusEvent:
    return FocusEvent(
        id=f"focus-event-{uuid4().hex}",
        focusId=focus_id,
        type=event_type,
        payload=payload or {},
        sourceTurnId=source_turn_id,
        source=source,
        confidence=max(0.0, min(1.0, confidence)),
        createdAt=_now_iso(),
    )


def append_events(events: Iterable[FocusEvent]) -> list[FocusEvent]:
    items = list(events)
    if not items:
        return []

    with _STORE_LOCK:
        document = _read_log_unlocked()
        existing_ids = {event.id for event in document.events}

        for event in items:
            if event.id in existing_ids:
                continue
            document.events.append(event)
            existing_ids.add(event.id)

        _atomic_write_unlocked(document)

    return items


def list_events(limit: int = 200) -> list[FocusEvent]:
    safe_limit = max(1, min(limit, 1000))
    with _STORE_LOCK:
        events = _read_log_unlocked().events
    return events[-safe_limit:]


def event_count() -> int:
    with _STORE_LOCK:
        return len(_read_log_unlocked().events)


def _append_unique(values: list[str], candidate: str, limit: int = 80) -> None:
    item = " ".join(candidate.split()).strip()
    if not item:
        return

    key = item.casefold()
    if any(existing.casefold() == key for existing in values):
        return

    values.append(item)
    if len(values) > limit:
        del values[:-limit]


def _remove_casefold(values: list[str], candidate: str) -> None:
    key = " ".join(candidate.split()).strip().casefold()
    if not key:
        return
    values[:] = [value for value in values if value.casefold() != key]


def _state_from_seed(
    seed_payload: dict,
    *,
    fallback_focus_id: str,
    fallback_timestamp: str,
) -> FocusState:
    seed = LegacyFocusSeed.model_validate(seed_payload)
    focus_id = seed.focusId.strip() or fallback_focus_id
    created_at = seed.createdAt or fallback_timestamp
    updated_at = seed.updatedAt or fallback_timestamp

    return FocusState(
        focusId=focus_id,
        title=seed.title,
        objective=seed.objective,
        deliverable=seed.deliverable,
        subject=seed.subject,
        stakeholders=seed.stakeholders,
        requirements=seed.requirements,
        constraints=seed.constraints,
        preferences=seed.preferences,
        decisions=seed.decisions,
        knownFacts=seed.knownFacts,
        milestones=seed.milestones,
        completedMilestones=seed.completedMilestones,
        nextAction=seed.nextAction,
        status=seed.status,
        tags=seed.tags,
        createdAt=created_at,
        updatedAt=updated_at,
    )


def reduce_events(events: Iterable[FocusEvent]) -> FocusState:
    """Project the append-only event log into the current Focus state.

    Reduction must be deterministic. No UUID or current timestamp is generated
    here; every replay of the same events returns the same state.
    """

    state = FocusState()

    for event in events:
        payload = event.payload
        event_time = event.createdAt

        if event.type == FocusEventType.LEGACY_IMPORTED:
            state = _state_from_seed(
                payload,
                fallback_focus_id=_stable_focus_id_from_event(event),
                fallback_timestamp=event_time,
            )
            if event.sourceTurnId:
                state.lastTurnId = event.sourceTurnId
            continue

        if event.type == FocusEventType.FOCUS_STARTED:
            state = FocusState(
                focusId=_stable_focus_id_from_event(event),
                title=str(payload.get("title", "")).strip(),
                objective=str(payload.get("objective", "")).strip(),
                tags=list(payload.get("tags", [])),
                status=FocusStatus.CLARIFYING,
                createdAt=event_time,
                updatedAt=event_time,
                lastTurnId=event.sourceTurnId,
            )
            continue

        if (
            state.status == FocusStatus.INACTIVE
            and event.type != FocusEventType.TURN_PLANNED
        ):
            continue

        if event.type == FocusEventType.FOCUS_RESCOPED:
            title = str(payload.get("title", "")).strip()
            objective = str(payload.get("objective", "")).strip()

            if title:
                state.title = title
            if objective:
                state.objective = objective
            for tag in payload.get("tags", []):
                _append_unique(state.tags, str(tag), 24)

            state.status = FocusStatus.CLARIFYING

        elif event.type == FocusEventType.FIELD_SET:
            field = str(payload.get("field", ""))
            value = " ".join(str(payload.get("value", "")).split()).strip()

            if field in _STRING_FIELDS:
                setattr(state, field, value)
            elif field == FocusField.STATUS.value:
                try:
                    state.status = FocusStatus(value)
                except ValueError:
                    pass

        elif event.type == FocusEventType.LIST_ITEM_ADDED:
            field = str(payload.get("field", ""))
            value = str(payload.get("value", ""))
            if field in _LIST_FIELDS:
                _append_unique(getattr(state, field), value)

        elif event.type == FocusEventType.LIST_ITEM_REMOVED:
            field = str(payload.get("field", ""))
            value = str(payload.get("value", ""))
            if field in _LIST_FIELDS:
                _remove_casefold(getattr(state, field), value)

        elif event.type == FocusEventType.QUESTION_SET:
            state.pendingQuestion = PendingQuestion(
                target=str(payload.get("target", "")).strip(),
                question=str(payload.get("question", "")).strip(),
                askedAt=event_time,
            )
            if state.status != FocusStatus.COMPLETE:
                state.status = FocusStatus.CLARIFYING

        elif event.type == FocusEventType.QUESTION_CLEARED:
            state.pendingQuestion = None
            if state.status == FocusStatus.CLARIFYING:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.ACTION_SET:
            state.pendingAction = PendingAction(
                kind=str(payload.get("kind", "")).strip(),
                description=str(payload.get("description", "")).strip(),
                createdAt=event_time,
            )
            if state.status != FocusStatus.COMPLETE:
                state.status = FocusStatus.WAITING

        elif event.type == FocusEventType.ACTION_CLEARED:
            state.pendingAction = None
            if state.status == FocusStatus.WAITING:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.NEXT_ACTION_SET:
            state.nextAction = str(payload.get("value", "")).strip()

        elif event.type == FocusEventType.PROGRESS_RECORDED:
            _append_unique(
                state.completedMilestones,
                str(payload.get("value", "")),
            )
            if state.status not in {FocusStatus.COMPLETE, FocusStatus.WAITING}:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.MILESTONE_COMPLETED:
            value = str(payload.get("value", "")).strip()
            _remove_casefold(state.milestones, value)
            _append_unique(state.completedMilestones, value)
            if state.status not in {FocusStatus.COMPLETE, FocusStatus.WAITING}:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.TOOL_REQUESTED:
            tool = str(payload.get("tool", "")).strip()
            state.pendingAction = PendingAction(
                kind=tool,
                description=str(payload.get("reason", "")).strip(),
                createdAt=event_time,
            )
            state.status = FocusStatus.WAITING

        elif event.type == FocusEventType.TOOL_COMPLETED:
            tool = str(payload.get("tool", "")).strip()
            summary = str(payload.get("summary", "")).strip()
            state.pendingAction = None
            _append_unique(
                state.completedMilestones,
                summary or f"{tool.replace('_', ' ').title()} completed.",
            )
            if state.status != FocusStatus.COMPLETE:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.TOOL_FAILED:
            state.pendingAction = None
            summary = str(payload.get("summary", "")).strip()
            if summary:
                _append_unique(state.knownFacts, summary)
            if state.status != FocusStatus.COMPLETE:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.FOCUS_COMPLETED:
            state.status = FocusStatus.COMPLETE
            state.pendingQuestion = None
            state.pendingAction = None
            state.nextAction = str(payload.get("nextAction", "")).strip()

        elif event.type == FocusEventType.FOCUS_ENDED:
            state.status = FocusStatus.INACTIVE
            state.pendingQuestion = None
            state.pendingAction = None
            state.nextAction = ""

        state.updatedAt = event_time
        if event.sourceTurnId:
            state.lastTurnId = event.sourceTurnId

    return state


def get_state() -> FocusState:
    with _STORE_LOCK:
        events = list(_read_log_unlocked().events)
    return reduce_events(events)


def reset_store() -> FocusState:
    with _STORE_LOCK:
        _atomic_write_unlocked(_empty_log())
    return FocusState()


def has_turn(turn_id: str) -> bool:
    if not turn_id:
        return False

    with _STORE_LOCK:
        return any(
            event.sourceTurnId == turn_id
            and event.type == FocusEventType.TURN_PLANNED
            for event in _read_log_unlocked().events
        )


def seed_from_legacy(seed: LegacyFocusSeed | None) -> FocusState:
    if seed is None:
        return get_state()

    with _STORE_LOCK:
        document = _read_log_unlocked()
        current = reduce_events(document.events)

        if current.status != FocusStatus.INACTIVE:
            return current

        focus_id = seed.focusId.strip() or _new_focus_id()
        seed_payload = seed.model_dump(mode="json")
        seed_payload["focusId"] = focus_id

        event = _new_event(
            FocusEventType.LEGACY_IMPORTED,
            focus_id=focus_id,
            payload=seed_payload,
            source="legacy-bootstrap",
        )
        document.events.append(event)
        _atomic_write_unlocked(document)
        return reduce_events(document.events)


def _events_from_operation(
    operation: FocusOperation,
    *,
    focus_id: str,
    turn_id: str,
    source: str,
) -> list[FocusEvent]:
    common = {
        "focus_id": focus_id,
        "source_turn_id": turn_id,
        "source": source,
        "confidence": operation.confidence,
    }

    kind = operation.kind

    if kind == FocusOperationKind.START_FOCUS:
        return [
            _new_event(
                FocusEventType.FOCUS_STARTED,
                payload={
                    "title": operation.title or operation.value,
                    "objective": operation.objective,
                    "tags": operation.tags,
                },
                **common,
            )
        ]

    if kind == FocusOperationKind.RESCOPE_FOCUS:
        return [
            _new_event(
                FocusEventType.FOCUS_RESCOPED,
                payload={
                    "title": operation.title or operation.value,
                    "objective": operation.objective,
                    "tags": operation.tags,
                },
                **common,
            )
        ]

    if kind == FocusOperationKind.SET_FIELD and operation.field:
        event_type = (
            FocusEventType.NEXT_ACTION_SET
            if operation.field == FocusField.NEXT_ACTION
            else FocusEventType.FIELD_SET
        )
        return [
            _new_event(
                event_type,
                payload={
                    "field": operation.field.value,
                    "value": operation.value,
                },
                **common,
            )
        ]

    if kind in {
        FocusOperationKind.ADD_LIST_ITEM,
        FocusOperationKind.REMOVE_LIST_ITEM,
    } and operation.field:
        event_type = (
            FocusEventType.LIST_ITEM_ADDED
            if kind == FocusOperationKind.ADD_LIST_ITEM
            else FocusEventType.LIST_ITEM_REMOVED
        )
        values = operation.values or ([operation.value] if operation.value else [])
        return [
            _new_event(
                event_type,
                payload={"field": operation.field.value, "value": value},
                **common,
            )
            for value in values
        ]

    if kind == FocusOperationKind.SET_PENDING_QUESTION:
        return [
            _new_event(
                FocusEventType.QUESTION_SET,
                payload={
                    "target": operation.target,
                    "question": operation.question,
                },
                **common,
            )
        ]

    if kind == FocusOperationKind.CLEAR_PENDING_QUESTION:
        return [_new_event(FocusEventType.QUESTION_CLEARED, **common)]

    if kind == FocusOperationKind.SET_PENDING_ACTION:
        return [
            _new_event(
                FocusEventType.ACTION_SET,
                payload={
                    "kind": operation.target,
                    "description": operation.value,
                },
                **common,
            )
        ]

    if kind == FocusOperationKind.CLEAR_PENDING_ACTION:
        return [_new_event(FocusEventType.ACTION_CLEARED, **common)]

    if kind == FocusOperationKind.SET_NEXT_ACTION:
        return [
            _new_event(
                FocusEventType.NEXT_ACTION_SET,
                payload={"value": operation.value},
                **common,
            )
        ]

    if kind == FocusOperationKind.RECORD_PROGRESS:
        values = operation.values or ([operation.value] if operation.value else [])
        return [
            _new_event(
                FocusEventType.PROGRESS_RECORDED,
                payload={"value": value},
                **common,
            )
            for value in values
        ]

    if kind == FocusOperationKind.COMPLETE_MILESTONE:
        values = operation.values or ([operation.value] if operation.value else [])
        return [
            _new_event(
                FocusEventType.MILESTONE_COMPLETED,
                payload={"value": value},
                **common,
            )
            for value in values
        ]

    if kind == FocusOperationKind.MARK_FOCUS_COMPLETE:
        return [
            _new_event(
                FocusEventType.FOCUS_COMPLETED,
                payload={"nextAction": operation.value},
                **common,
            )
        ]

    if kind == FocusOperationKind.END_FOCUS:
        return [_new_event(FocusEventType.FOCUS_ENDED, **common)]

    return []


def _tool_request_event(
    tool_call: PlannedToolCall,
    *,
    focus_id: str,
    turn_id: str,
    source: str,
    confidence: float,
) -> FocusEvent:
    return _new_event(
        FocusEventType.TOOL_REQUESTED,
        focus_id=focus_id,
        payload={
            "tool": tool_call.tool.value,
            "reason": tool_call.reason,
            "arguments": [
                argument.model_dump(mode="json")
                for argument in tool_call.arguments
            ],
            "requiresConfirmation": tool_call.requiresConfirmation,
        },
        source_turn_id=turn_id,
        source=source,
        confidence=confidence,
    )


def _automatic_question_event(
    plan: TurnPlan,
    *,
    focus_id: str,
    turn_id: str,
    source: str,
) -> FocusEvent | None:
    question = " ".join(plan.responseIntent.askQuestion.split()).strip()
    if not question or not focus_id:
        return None

    explicitly_set = any(
        operation.kind == FocusOperationKind.SET_PENDING_QUESTION
        for operation in plan.focusOperations
    )
    if explicitly_set:
        return None

    return _new_event(
        FocusEventType.QUESTION_SET,
        focus_id=focus_id,
        payload={"target": "follow_up", "question": question},
        source_turn_id=turn_id,
        source=source,
        confidence=plan.confidence,
    )


def apply_turn_plan(
    plan: TurnPlan,
    *,
    message: str,
    turn_id: str,
    source: str,
) -> FocusState:
    if turn_id and has_turn(turn_id):
        return get_state()

    current = get_state()
    current_focus_id = current.focusId.strip()

    start_focus_ids = {
        index: _new_focus_id()
        for index, operation in enumerate(plan.focusOperations)
        if operation.kind == FocusOperationKind.START_FOCUS
    }
    first_started_focus_id = next(iter(start_focus_ids.values()), "")

    turn_focus_id = current_focus_id or first_started_focus_id
    active_focus_id = current_focus_id
    active_focus_is_open = bool(active_focus_id) and current.status not in {
        FocusStatus.INACTIVE,
        FocusStatus.COMPLETE,
    }
    focus_accepts_question = active_focus_is_open

    events: list[FocusEvent] = [
        _new_event(
            FocusEventType.TURN_PLANNED,
            focus_id=turn_focus_id,
            payload={
                "message": message,
                "route": plan.route.value,
                "reason": plan.reason,
                "plan": plan.model_dump(mode="json"),
            },
            source_turn_id=turn_id,
            source=source,
            confidence=plan.confidence,
        )
    ]

    for index, operation in enumerate(plan.focusOperations):
        if operation.kind == FocusOperationKind.START_FOCUS:
            operation_focus_id = start_focus_ids[index]

            # A FocusState represents one current durable objective. Starting a
            # different focus therefore closes the currently open one even when
            # the model omitted an explicit end_focus operation. This keeps the
            # event history truthful without relying on planner consistency.
            if active_focus_id and active_focus_is_open:
                events.append(
                    _new_event(
                        FocusEventType.FOCUS_ENDED,
                        focus_id=active_focus_id,
                        payload={
                            "reason": "superseded_by_new_focus",
                            "newFocusId": operation_focus_id,
                        },
                        source_turn_id=turn_id,
                        source=source,
                        confidence=operation.confidence,
                    )
                )
                active_focus_is_open = False
                focus_accepts_question = False
        else:
            operation_focus_id = active_focus_id or turn_focus_id

        operation_events = _events_from_operation(
            operation,
            focus_id=operation_focus_id,
            turn_id=turn_id,
            source=source,
        )
        events.extend(operation_events)

        if operation.kind == FocusOperationKind.START_FOCUS:
            active_focus_id = operation_focus_id
            active_focus_is_open = True
            focus_accepts_question = True
        elif operation.kind in {
            FocusOperationKind.END_FOCUS,
            FocusOperationKind.MARK_FOCUS_COMPLETE,
        }:
            active_focus_is_open = False
            focus_accepts_question = False

    if focus_accepts_question:
        question_event = _automatic_question_event(
            plan,
            focus_id=active_focus_id,
            turn_id=turn_id,
            source=source,
        )
        if question_event is not None:
            events.append(question_event)

    tool_focus_id = active_focus_id or turn_focus_id
    for tool_call in plan.toolCalls:
        if tool_call.tool == ToolName.NONE:
            continue
        events.append(
            _tool_request_event(
                tool_call,
                focus_id=tool_focus_id,
                turn_id=turn_id,
                source=source,
                confidence=plan.confidence,
            )
        )

    append_events(events)
    return get_state()


def _focus_id_for_tool_result(
    events: list[FocusEvent],
    source_turn_id: str,
) -> str:
    """Resolve a tool result to the Focus that requested it.

    One-off tools may legitimately have no durable Focus, in which case the
    returned ID is blank but the event is still preserved for turn tracing.
    """

    if source_turn_id:
        for event in reversed(events):
            if event.sourceTurnId != source_turn_id:
                continue
            if event.type == FocusEventType.TOOL_REQUESTED:
                return event.focusId.strip()

        for event in reversed(events):
            if event.sourceTurnId == source_turn_id and event.focusId.strip():
                return event.focusId.strip()

    return reduce_events(events).focusId.strip()


def record_tool_result(
    *,
    tool: ToolName,
    success: bool,
    summary: str,
    result_ids: list[str] | None = None,
    source_turn_id: str = "",
    source: str = "tool-result",
) -> FocusState:
    with _STORE_LOCK:
        document = _read_log_unlocked()
        focus_id = _focus_id_for_tool_result(
            document.events,
            source_turn_id,
        )

        event = _new_event(
            FocusEventType.TOOL_COMPLETED
            if success
            else FocusEventType.TOOL_FAILED,
            focus_id=focus_id,
            payload={
                "tool": tool.value,
                "summary": summary,
                "resultIds": result_ids or [],
            },
            source_turn_id=source_turn_id,
            source=source,
        )
        document.events.append(event)
        _atomic_write_unlocked(document)
        return reduce_events(document.events)
