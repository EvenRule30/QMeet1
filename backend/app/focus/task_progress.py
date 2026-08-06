from __future__ import annotations

import copy
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import memory_store
from app.focus import store as focus_store
from app.focus import summary as relationship_store
from app.focus.models import FocusEvent, FocusEventType, FocusState, FocusStatus
from app.focus.task_lineage import (
    _focus_lineage_ids,
    _string_list,
    _task_relationship_records,
)

_PROGRESS_SOURCE = "focus-task-progress-bridge"
_MAX_TASKS_PER_PROGRESS = 5
_RELATIONSHIP_LOCK = relationship_store._RELATIONSHIP_LOCK
_read_relationships_unlocked = relationship_store._read_relationships_unlocked
_open_focus_ids = relationship_store._open_focus_ids


class NativeFocusTaskProgressTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=140)
    title: str = Field(min_length=1, max_length=240)
    completedAt: str = Field(min_length=1, max_length=80)

    @field_validator("id", "title", "completedAt")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("value cannot be blank")
        return cleaned


class NativeFocusTaskProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedFocusId: str = Field(min_length=1, max_length=120)
    tasks: list[NativeFocusTaskProgressTarget] = Field(
        min_length=1,
        max_length=_MAX_TASKS_PER_PROGRESS,
    )
    sourceTurnId: str = Field(min_length=1, max_length=120)
    confirmed: bool = False

    @field_validator("expectedFocusId", "sourceTurnId")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("value cannot be blank")
        return cleaned

    @field_validator("tasks")
    @classmethod
    def unique_tasks(
        cls,
        tasks: list[NativeFocusTaskProgressTarget],
    ) -> list[NativeFocusTaskProgressTarget]:
        unique: list[NativeFocusTaskProgressTarget] = []
        seen: set[str] = set()
        for task in tasks:
            if task.id in seen:
                continue
            seen.add(task.id)
            unique.append(task)
        if not unique:
            raise ValueError("at least one task is required")
        return unique


class NativeFocusTaskProgressVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activeFocusMatches: bool = False
    linkedTaskMembershipVerified: bool = False
    tasksCompleted: bool = False
    canonicalProgressRecorded: bool = False
    focusContinuityPreserved: bool = False
    sourceTurnUnique: bool = False
    details: list[str] = Field(default_factory=list)


class NativeFocusTaskProgressResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    operation: Literal["record_focus_task_progress"] = (
        "record_focus_task_progress"
    )
    outcome: Literal["recorded", "reused"]
    verified: bool
    focusId: str
    focusTitle: str
    tasks: list[NativeFocusTaskProgressTarget]
    nextAction: str
    allLinkedTasksComplete: bool
    sourceTurnId: str
    state: FocusState
    verification: NativeFocusTaskProgressVerification
    message: str


class NativeFocusTaskProgressError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _restore_memory_unlocked(memory_before: dict) -> None:
    memory_store._write_payload_unlocked(
        memory_before["tasks"],
        memory_before["recentActions"],
        memory_before["notes"],
        memory_before["activeSession"],
        memory_before["recentFocusSessions"],
        memory_before["visualContext"],
        preserve_active_session=False,
        preserve_recent_focus_sessions=False,
        preserve_visual_context=False,
    )


def _write_completed_tasks_unlocked(
    memory_before: dict,
    targets: list[NativeFocusTaskProgressTarget],
) -> list[dict[str, object]]:
    target_by_id = {target.id: target for target in targets}
    next_tasks: list[dict[str, object]] = []
    for raw_task in memory_before["tasks"]:
        task = dict(raw_task)
        target = target_by_id.get(str(task.get("id", "")).strip())
        if target is not None:
            task["completedAt"] = target.completedAt
        next_tasks.append(task)

    memory_store._write_payload_unlocked(
        next_tasks,
        memory_before["recentActions"],
        memory_before["notes"],
        memory_before["activeSession"],
        memory_before["recentFocusSessions"],
        memory_before["visualContext"],
        preserve_active_session=False,
        preserve_recent_focus_sessions=False,
        preserve_visual_context=False,
    )
    return next_tasks


def _lineage_task_snapshots(
    relationships: dict[str, object],
    lineage_ids: list[str],
) -> dict[str, dict[str, str]]:
    snapshots: dict[str, dict[str, str]] = {}
    for focus_id in lineage_ids:
        for record in _task_relationship_records(relationships, focus_id):
            raw_tasks = record.get("tasks")
            if not isinstance(raw_tasks, list):
                continue
            for raw_task in raw_tasks:
                if not isinstance(raw_task, dict):
                    continue
                task_id = str(raw_task.get("id", "")).strip()
                title = _normalize_text(raw_task.get("title", ""))
                created_at = str(raw_task.get("createdAt", "")).strip()
                if task_id and title and task_id not in snapshots:
                    snapshots[task_id] = {
                        "id": task_id,
                        "title": title,
                        "createdAt": created_at,
                    }
    return snapshots


def _lineage_linked_task_ids(
    relationships: dict[str, object],
    lineage_ids: list[str],
) -> set[str]:
    linked: set[str] = set()
    for focus_id in lineage_ids:
        for record in _task_relationship_records(relationships, focus_id):
            linked.update(_string_list(record.get("taskIds")))
    return linked


def _relationship_source_turn_matches(
    relationships: dict[str, object],
    source_turn_id: str,
) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for bucket_name, raw_by_focus in relationships.items():
        if not bucket_name.endswith("ByFocusId") or not isinstance(raw_by_focus, dict):
            continue
        for focus_id, raw_records in raw_by_focus.items():
            if not isinstance(raw_records, list):
                continue
            for raw_record in raw_records:
                if (
                    isinstance(raw_record, dict)
                    and str(raw_record.get("sourceTurnId", "")).strip()
                    == source_turn_id
                ):
                    matches.append((bucket_name, str(focus_id)))
    return matches


def _validate_targets(
    *,
    targets: list[NativeFocusTaskProgressTarget],
    linked_task_ids: set[str],
    snapshots_by_id: dict[str, dict[str, str]],
    memory_before: dict,
) -> None:
    memory_by_id = {
        str(task.get("id", "")).strip(): task
        for task in memory_before["tasks"]
        if isinstance(task, dict)
    }
    for target in targets:
        if target.id not in linked_task_ids:
            raise NativeFocusTaskProgressError(
                "task_not_linked",
                "The completed task is not linked to the active canonical Focus.",
            )
        snapshot = snapshots_by_id.get(target.id)
        memory_task = memory_by_id.get(target.id)
        if snapshot is None or memory_task is None:
            raise NativeFocusTaskProgressError(
                "task_not_found",
                "The linked Focus task could not be verified in Memory.",
                status_code=404,
            )
        expected_title = _normalize_text(snapshot.get("title", ""))
        memory_title = _normalize_text(memory_task.get("title", ""))
        if (
            expected_title.casefold() != target.title.casefold()
            or memory_title.casefold() != target.title.casefold()
        ):
            raise NativeFocusTaskProgressError(
                "task_identity_mismatch",
                "The completed task title did not match the verified Focus task receipt.",
            )


def _remaining_open_linked_tasks(
    memory_tasks: list[dict[str, object]],
    linked_task_ids: set[str],
) -> list[dict[str, object]]:
    return [
        task
        for task in memory_tasks
        if str(task.get("id", "")).strip() in linked_task_ids
        and not str(task.get("completedAt", "")).strip()
    ]


def _bridge_turn_events(
    events: list[FocusEvent],
    source_turn_id: str,
) -> list[FocusEvent]:
    return [
        event
        for event in events
        if event.sourceTurnId == source_turn_id
        and event.source == _PROGRESS_SOURCE
    ]


def _request_task_ids(
    targets: list[NativeFocusTaskProgressTarget],
) -> list[str]:
    return [target.id for target in targets]


def _event_task_ids(events: list[FocusEvent]) -> list[str]:
    return [
        str(event.payload.get("taskId", "")).strip()
        for event in events
        if event.type == FocusEventType.MILESTONE_COMPLETED
        and str(event.payload.get("taskId", "")).strip()
    ]


def _build_progress_events(
    *,
    focus_id: str,
    targets: list[NativeFocusTaskProgressTarget],
    source_turn_id: str,
    focus_state: FocusState,
    next_action: str,
) -> list[FocusEvent]:
    events = [
        focus_store._new_event(
            FocusEventType.MILESTONE_COMPLETED,
            focus_id=focus_id,
            payload={
                "value": target.title,
                "taskId": target.id,
                "completedAt": target.completedAt,
            },
            source_turn_id=source_turn_id,
            source=_PROGRESS_SOURCE,
        )
        for target in targets
    ]
    if focus_state.pendingAction is not None:
        # MILESTONE_COMPLETED already preserves WAITING. Do not replace the
        # pending action or its canonical next step.
        return events
    if focus_state.pendingQuestion is not None:
        # MILESTONE_COMPLETED activates non-waiting Focuses. Restore the
        # clarifying status without re-emitting QUESTION_SET, which would
        # incorrectly change the question's askedAt timestamp.
        events.append(
            focus_store._new_event(
                FocusEventType.FIELD_SET,
                focus_id=focus_id,
                payload={"field": "status", "value": "clarifying"},
                source_turn_id=source_turn_id,
                source=_PROGRESS_SOURCE,
            )
        )
        return events
    events.append(
        focus_store._new_event(
            FocusEventType.NEXT_ACTION_SET,
            focus_id=focus_id,
            payload={"value": next_action},
            source_turn_id=source_turn_id,
            source=_PROGRESS_SOURCE,
        )
    )
    return events


def _verify_progress_unlocked(
    *,
    expected_focus_id: str,
    targets: list[NativeFocusTaskProgressTarget],
    source_turn_id: str,
    linked_task_ids: set[str],
    state_before: FocusState,
    expected_next_action: str,
) -> tuple[NativeFocusTaskProgressVerification, FocusState]:
    focus_document = focus_store._read_log_unlocked()
    focus_events = list(focus_document.events)
    focus_state = focus_store.reduce_events(focus_events)
    memory_after = memory_store._read_payload_unlocked()
    relationships_after = _read_relationships_unlocked()
    all_turn_events = [
        event for event in focus_events if event.sourceTurnId == source_turn_id
    ]
    bridge_events = _bridge_turn_events(focus_events, source_turn_id)
    memory_by_id = {
        str(task.get("id", "")).strip(): task
        for task in memory_after["tasks"]
        if isinstance(task, dict)
    }

    active_focus_matches = (
        focus_state.focusId == expected_focus_id
        and focus_state.status not in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
        and _open_focus_ids(focus_events) == [expected_focus_id]
    )
    linked_task_membership_verified = all(
        target.id in linked_task_ids for target in targets
    )
    tasks_completed = all(
        target.id in memory_by_id
        and _normalize_text(memory_by_id[target.id].get("title", "")).casefold()
        == target.title.casefold()
        and str(memory_by_id[target.id].get("completedAt", "")).strip()
        == target.completedAt
        for target in targets
    )
    requested_ids = _request_task_ids(targets)
    canonical_progress_recorded = (
        _event_task_ids(bridge_events) == requested_ids
        and all(
            any(
                milestone.casefold() == target.title.casefold()
                for milestone in focus_state.completedMilestones
            )
            for target in targets
        )
    )
    if state_before.pendingAction is not None:
        focus_continuity_preserved = (
            focus_state.pendingAction == state_before.pendingAction
            and focus_state.pendingQuestion == state_before.pendingQuestion
            and focus_state.nextAction == state_before.nextAction
            and focus_state.status == FocusStatus.WAITING
        )
    elif state_before.pendingQuestion is not None:
        focus_continuity_preserved = (
            focus_state.pendingQuestion == state_before.pendingQuestion
            and focus_state.pendingAction == state_before.pendingAction
            and focus_state.nextAction == state_before.nextAction
            and focus_state.status == FocusStatus.CLARIFYING
        )
    else:
        focus_continuity_preserved = (
            focus_state.pendingQuestion is None
            and focus_state.pendingAction is None
            and focus_state.nextAction == expected_next_action
            and focus_state.status not in {
                FocusStatus.INACTIVE,
                FocusStatus.COMPLETE,
            }
        )
    source_turn_unique = (
        bool(bridge_events)
        and len(all_turn_events) == len(bridge_events)
        and len(_event_task_ids(bridge_events)) == len(targets)
        and not _relationship_source_turn_matches(
            relationships_after,
            source_turn_id,
        )
    )

    details: list[str] = []
    if not active_focus_matches:
        details.append("The expected Focus is not the sole open canonical Focus.")
    if not linked_task_membership_verified:
        details.append("At least one completed task is not in the verified Focus lineage.")
    if not tasks_completed:
        details.append("The exact linked task completion was not persisted in Memory.")
    if not canonical_progress_recorded:
        details.append("Canonical Focus progress was not recorded exactly once per task.")
    if not focus_continuity_preserved:
        details.append("The pending question, pending action, or next action was not preserved safely.")
    if not source_turn_unique:
        details.append("The source turn does not identify one exclusive progress event group.")

    return (
        NativeFocusTaskProgressVerification(
            activeFocusMatches=active_focus_matches,
            linkedTaskMembershipVerified=linked_task_membership_verified,
            tasksCompleted=tasks_completed,
            canonicalProgressRecorded=canonical_progress_recorded,
            focusContinuityPreserved=focus_continuity_preserved,
            sourceTurnUnique=source_turn_unique,
            details=details,
        ),
        focus_state,
    )


def _verification_passed(
    verification: NativeFocusTaskProgressVerification,
) -> bool:
    return (
        verification.activeFocusMatches
        and verification.linkedTaskMembershipVerified
        and verification.tasksCompleted
        and verification.canonicalProgressRecorded
        and verification.focusContinuityPreserved
        and verification.sourceTurnUnique
    )


def record_focus_task_progress_verified(
    request: NativeFocusTaskProgressRequest,
) -> NativeFocusTaskProgressResult:
    if not request.confirmed:
        raise NativeFocusTaskProgressError(
            "confirmation_required",
            "Confirmed task completion is required before Focus progress can be recorded.",
            status_code=400,
        )

    focus_id = request.expectedFocusId
    source_turn_id = request.sourceTurnId
    targets = list(request.tasks)

    with focus_store._STORE_LOCK:
        focus_document = focus_store._read_log_unlocked()
        focus_before = copy.deepcopy(focus_document)
        focus_events = list(focus_document.events)
        focus_state = focus_store.reduce_events(focus_events)
        if (
            focus_state.focusId != focus_id
            or focus_state.status in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
            or _open_focus_ids(focus_events) != [focus_id]
        ):
            raise NativeFocusTaskProgressError(
                "stale_focus",
                "The displayed Focus is not the sole current canonical Focus.",
            )

        lineage_ids = _focus_lineage_ids(focus_events, focus_id)
        with _RELATIONSHIP_LOCK:
            relationships = _read_relationships_unlocked()
            linked_task_ids = _lineage_linked_task_ids(
                relationships,
                lineage_ids,
            )
            snapshots_by_id = _lineage_task_snapshots(
                relationships,
                lineage_ids,
            )
            if _relationship_source_turn_matches(relationships, source_turn_id):
                raise NativeFocusTaskProgressError(
                    "source_turn_conflict",
                    "This source turn already belongs to a different Focus relationship operation.",
                )

            with memory_store._STORE_LOCK:
                memory_before = memory_store._read_payload_unlocked()
                _validate_targets(
                    targets=targets,
                    linked_task_ids=linked_task_ids,
                    snapshots_by_id=snapshots_by_id,
                    memory_before=memory_before,
                )

                all_existing_turn_events = [
                    event
                    for event in focus_events
                    if event.sourceTurnId == source_turn_id
                ]
                if all_existing_turn_events:
                    existing_bridge_events = _bridge_turn_events(
                        focus_events,
                        source_turn_id,
                    )
                    if (
                        len(existing_bridge_events) != len(all_existing_turn_events)
                        or _event_task_ids(existing_bridge_events)
                        != _request_task_ids(targets)
                        or any(event.focusId != focus_id for event in existing_bridge_events)
                    ):
                        raise NativeFocusTaskProgressError(
                            "source_turn_conflict",
                            "This source turn already belongs to a different Focus operation.",
                        )
                    remaining = _remaining_open_linked_tasks(
                        memory_before["tasks"],
                        linked_task_ids,
                    )
                    expected_next_action = (
                        focus_state.nextAction
                        if focus_state.pendingQuestion is not None
                        or focus_state.pendingAction is not None
                        else (
                            _normalize_text(remaining[0].get("title", ""))
                            if remaining
                            else "Review the completed Focus tasks and complete the Focus when ready."
                        )
                    )
                    verification, reused_state = _verify_progress_unlocked(
                        expected_focus_id=focus_id,
                        targets=targets,
                        source_turn_id=source_turn_id,
                        linked_task_ids=linked_task_ids,
                        state_before=focus_state,
                        expected_next_action=expected_next_action,
                    )
                    if not _verification_passed(verification):
                        raise NativeFocusTaskProgressError(
                            "verification_failed",
                            "The existing Focus task-progress event group did not verify canonically.",
                        )
                    return NativeFocusTaskProgressResult(
                        ok=True,
                        outcome="reused",
                        verified=True,
                        focusId=focus_id,
                        focusTitle=reused_state.title,
                        tasks=targets,
                        nextAction=reused_state.nextAction,
                        allLinkedTasksComplete=not remaining,
                        sourceTurnId=source_turn_id,
                        state=reused_state,
                        verification=verification,
                        message="Focus task progress was already recorded and verified.",
                    )

                next_memory_tasks = _write_completed_tasks_unlocked(
                    memory_before,
                    targets,
                )
                remaining = _remaining_open_linked_tasks(
                    next_memory_tasks,
                    linked_task_ids,
                )
                next_action = (
                    _normalize_text(remaining[0].get("title", ""))
                    if remaining
                    else "Review the completed Focus tasks and complete the Focus when ready."
                )
                progress_events = _build_progress_events(
                    focus_id=focus_id,
                    targets=targets,
                    source_turn_id=source_turn_id,
                    focus_state=focus_state,
                    next_action=next_action,
                )
                try:
                    focus_document.events.extend(progress_events)
                    focus_store._atomic_write_unlocked(focus_document)
                    verification, verified_state = _verify_progress_unlocked(
                        expected_focus_id=focus_id,
                        targets=targets,
                        source_turn_id=source_turn_id,
                        linked_task_ids=linked_task_ids,
                        state_before=focus_state,
                        expected_next_action=(
                            focus_state.nextAction
                            if focus_state.pendingQuestion is not None
                            or focus_state.pendingAction is not None
                            else next_action
                        ),
                    )
                    if not _verification_passed(verification):
                        raise NativeFocusTaskProgressError(
                            "verification_failed",
                            "Canonical state did not verify the Focus task progress.",
                        )
                except Exception as exc:
                    try:
                        _restore_memory_unlocked(memory_before)
                        focus_store._atomic_write_unlocked(focus_before)
                    except Exception:
                        pass
                    if isinstance(exc, NativeFocusTaskProgressError):
                        raise
                    raise NativeFocusTaskProgressError(
                        "write_failed",
                        "QMeet could not persist verified Focus task progress.",
                        status_code=500,
                    ) from exc

                return NativeFocusTaskProgressResult(
                    ok=True,
                    outcome="recorded",
                    verified=True,
                    focusId=focus_id,
                    focusTitle=verified_state.title,
                    tasks=targets,
                    nextAction=verified_state.nextAction,
                    allLinkedTasksComplete=not remaining,
                    sourceTurnId=source_turn_id,
                    state=verified_state,
                    verification=verification,
                    message=(
                        f"Recorded verified Focus progress for {len(targets)} completed "
                        f"task{'s' if len(targets) != 1 else ''}."
                    ),
                )
