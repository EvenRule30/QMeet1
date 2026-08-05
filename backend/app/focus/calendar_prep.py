from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import memory_store
from app.focus import store as focus_store
from app.focus.lifecycle import (
    NativeFocusLifecycleError,
    NativeFocusStartRequest,
    NativeFocusStartResult,
    NativeFocusVerification,
    start_focus_verified,
)
from app.focus.models import FocusEventType, FocusStatus
from app.focus.tasks import (
    NativeFocusTasksError,
    NativeFocusTasksRequest,
    NativeFocusTasksResult,
    _RELATIONSHIP_LOCK,
    _read_relationships_unlocked,
    link_focus_tasks_verified,
)

_HEALTH_LOCK = RLock()
_HEALTH_VERSION = 1


class NativeCalendarPrepEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=180)
    title: str = Field(min_length=1, max_length=180)
    dateKey: str = Field(default="", max_length=40)
    time: str = Field(default="", max_length=80)
    createdAt: str = Field(default="", max_length=80)
    source: Literal["local", "google"] = "google"
    googleEventId: str = Field(default="", max_length=240)
    start: str | None = Field(default=None, max_length=100)
    end: str | None = Field(default=None, max_length=100)
    location: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=4000)
    allDay: bool = False
    calendarId: str = Field(default="", max_length=240)

    @field_validator(
        "id",
        "title",
        "dateKey",
        "time",
        "createdAt",
        "googleEventId",
        "location",
        "description",
        "calendarId",
    )
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(str(value or "").split()).strip()

    @field_validator("start", "end")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        return cleaned or None


class NativeCalendarFocusPrepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: NativeCalendarPrepEvent
    sourceTurnId: str = Field(min_length=1, max_length=120)

    @field_validator("sourceTurnId")
    @classmethod
    def clean_source_turn_id(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("sourceTurnId cannot be blank")
        return cleaned


class NativeCalendarFocusPrepVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focusReceiptVerified: bool = False
    taskReceiptVerified: bool = False
    activeFocusMatches: bool = False
    exactTasksPersisted: bool = False
    relationshipPersisted: bool = False
    sourceTurnUnique: bool = False
    rollbackProtected: bool = True
    details: list[str] = Field(default_factory=list)


class NativeCalendarFocusPrepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    operation: Literal["prepare_calendar_focus"] = "prepare_calendar_focus"
    outcome: Literal["created", "linked", "reused"]
    verified: bool
    event: NativeCalendarPrepEvent
    focusReceipt: NativeFocusStartResult
    taskReceipt: NativeFocusTasksResult
    sourceTurnId: str
    verification: NativeCalendarFocusPrepVerification
    telemetryRecorded: bool = False
    message: str


class NativeCalendarFocusPrepError(Exception):
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


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _health_file() -> Path:
    configured = os.getenv("QMEET_FOCUS_CALENDAR_PREP_HEALTH_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _backend_root() / "data" / "qmeet_focus_calendar_prep_health.json"


def _relationship_file() -> Path:
    configured = os.getenv("QMEET_FOCUS_RELATIONSHIPS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _backend_root() / "data" / "qmeet_focus_relationships.json"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _empty_health() -> dict[str, object]:
    return {
        "version": _HEALTH_VERSION,
        "updatedAt": "",
        "prepareCalendarFocus": {
            "attemptCount": 0,
            "createdCount": 0,
            "linkedCount": 0,
            "reusedCount": 0,
            "verifiedCount": 0,
            "failedCount": 0,
            "rollbackCount": 0,
            "verificationFailedCount": 0,
            "lastOutcome": "",
            "lastFailureCode": "",
            "lastFocusId": "",
            "lastTaskIds": [],
            "lastCalendarEventId": "",
            "lastSourceTurnId": "",
            "lastUpdatedAt": "",
        },
    }


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _read_health_unlocked() -> dict[str, object]:
    path = _health_file()
    baseline = _empty_health()
    if not path.exists():
        return baseline
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return baseline
    if not isinstance(parsed, dict):
        return baseline
    incoming = parsed.get("prepareCalendarFocus")
    section = baseline["prepareCalendarFocus"]
    if isinstance(section, dict) and isinstance(incoming, dict):
        section.update(incoming)
    baseline["updatedAt"] = str(parsed.get("updatedAt", ""))
    return baseline


def _record_health(
    *,
    outcome: str,
    verified: bool,
    source_turn_id: str,
    event_id: str,
    focus_id: str = "",
    task_ids: list[str] | None = None,
    failure_code: str = "",
    rolled_back: bool = False,
) -> bool:
    try:
        with _HEALTH_LOCK:
            document = _read_health_unlocked()
            section = document["prepareCalendarFocus"]
            assert isinstance(section, dict)
            section["attemptCount"] = int(section.get("attemptCount", 0)) + 1
            count_key = {
                "created": "createdCount",
                "linked": "linkedCount",
                "reused": "reusedCount",
            }.get(outcome)
            if count_key:
                section[count_key] = int(section.get(count_key, 0)) + 1
            if verified:
                section["verifiedCount"] = int(section.get("verifiedCount", 0)) + 1
            else:
                section["failedCount"] = int(section.get("failedCount", 0)) + 1
            if rolled_back:
                section["rollbackCount"] = int(section.get("rollbackCount", 0)) + 1
            if failure_code == "verification_failed":
                section["verificationFailedCount"] = int(
                    section.get("verificationFailedCount", 0)
                ) + 1
            section["lastOutcome"] = outcome
            section["lastFailureCode"] = failure_code
            section["lastFocusId"] = focus_id
            section["lastTaskIds"] = list(task_ids or [])
            section["lastCalendarEventId"] = event_id
            section["lastSourceTurnId"] = source_turn_id
            section["lastUpdatedAt"] = _now_iso()
            document["updatedAt"] = _now_iso()
            _atomic_write_json(_health_file(), document)
        return True
    except Exception:
        return False


def get_native_calendar_focus_prep_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        return _read_health_unlocked()


def reset_native_calendar_focus_prep_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        document = _empty_health()
        _atomic_write_json(_health_file(), document)
        return document


def _event_title(event: NativeCalendarPrepEvent) -> str:
    return event.title.strip() or "Calendar event"


def build_calendar_focus_title(event: NativeCalendarPrepEvent) -> str:
    return f"Prepare for {_event_title(event)}"


def build_calendar_focus_objective(event: NativeCalendarPrepEvent) -> str:
    event_title = _event_title(event)
    time_label = event.time.strip() or "scheduled time"
    location_label = f" at {event.location.strip()}" if event.location.strip() else ""
    return (
        f"Prepare for {event_title} at {time_label}{location_label}. "
        "Review the event details, gather relevant notes, prepare questions, "
        "and identify next steps."
    )


def build_calendar_prep_task_titles(event: NativeCalendarPrepEvent) -> list[str]:
    event_title = _event_title(event)
    return [
        f"Review details for {event_title}",
        f"Gather relevant notes or documents for {event_title}",
        f"Prepare questions for {event_title}",
        f"Identify decisions or next steps needed for {event_title}",
        f"Capture follow-up items after {event_title}",
    ]


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


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _restore_relationship_file_unlocked(
    *,
    relationship_path: Path,
    existed_before: bool,
    bytes_before: bytes,
) -> None:
    if existed_before:
        _atomic_write_bytes(relationship_path, bytes_before)
        return
    relationship_path.unlink(missing_ok=True)


def _restore_transaction_unlocked(
    *,
    focus_before,
    memory_before: dict,
    relationship_path: Path,
    relationship_existed_before: bool,
    relationship_bytes_before: bytes,
) -> None:
    focus_store._atomic_write_unlocked(focus_before.model_copy(deep=True))
    _restore_memory_unlocked(memory_before)
    _restore_relationship_file_unlocked(
        relationship_path=relationship_path,
        existed_before=relationship_existed_before,
        bytes_before=relationship_bytes_before,
    )


def _canonical_open_focus_ids(events) -> list[str]:
    open_by_id: dict[str, bool] = {}
    order: list[str] = []
    for event in events:
        focus_id = event.focusId.strip() or str(event.payload.get("focusId", "")).strip()
        if not focus_id:
            continue
        if focus_id not in order:
            order.append(focus_id)
        if event.type in {FocusEventType.FOCUS_STARTED, FocusEventType.LEGACY_IMPORTED}:
            status = str(event.payload.get("status", FocusStatus.ACTIVE.value)).strip()
            open_by_id[focus_id] = status not in {
                FocusStatus.INACTIVE.value,
                FocusStatus.COMPLETE.value,
            }
        elif event.type in {FocusEventType.FOCUS_ENDED, FocusEventType.FOCUS_COMPLETED}:
            open_by_id[focus_id] = False
    return [focus_id for focus_id in order if open_by_id.get(focus_id)]


def _source_turn_cycle_number(base_source_turn_id: str, candidate: str) -> int | None:
    if candidate == base_source_turn_id:
        return 1
    prefix = f"{base_source_turn_id}-cycle-"
    if not candidate.startswith(prefix):
        return None
    raw_number = candidate[len(prefix):]
    if not raw_number.isdigit():
        return None
    number = int(raw_number)
    return number if number >= 2 else None


def _start_event_matches_calendar_request(event, request: NativeCalendarFocusPrepRequest) -> bool:
    expected_title = build_calendar_focus_title(request.event)
    expected_objective = build_calendar_focus_objective(request.event)
    tags = {str(tag).strip() for tag in event.payload.get("tags", [])}
    return (
        str(event.payload.get("title", "")).strip() == expected_title
        and str(event.payload.get("objective", "")).strip() == expected_objective
        and f"calendar-event:{request.event.id}" in tags
    )


def _resolve_calendar_source_turn(
    *,
    events,
    request: NativeCalendarFocusPrepRequest,
) -> tuple[str, object | None]:
    base_source_turn_id = request.sourceTurnId.strip()
    matching_starts = []
    highest_cycle = 0
    for event in events:
        if event.type != FocusEventType.FOCUS_STARTED:
            continue
        cycle_number = _source_turn_cycle_number(
            base_source_turn_id,
            event.sourceTurnId,
        )
        if cycle_number is None:
            continue
        if not _start_event_matches_calendar_request(event, request):
            raise NativeCalendarFocusPrepError(
                "source_turn_conflict",
                "This calendar preparation key already belongs to different event details.",
            )
        matching_starts.append(event)
        highest_cycle = max(highest_cycle, cycle_number)

    if not matching_starts:
        return base_source_turn_id, None

    open_focus_ids = set(_canonical_open_focus_ids(events))
    active_starts = [
        event for event in matching_starts if event.focusId in open_focus_ids
    ]
    if len(active_starts) > 1:
        raise NativeCalendarFocusPrepError(
            "verification_failed",
            "More than one active calendar preparation receipt matched this event.",
        )
    if active_starts:
        active_start = active_starts[0]
        return active_start.sourceTurnId, active_start

    next_cycle = max(2, highest_cycle + 1)
    suffix = f"-cycle-{next_cycle}"
    concrete_source_turn_id = f"{base_source_turn_id[:120 - len(suffix)]}{suffix}"
    return concrete_source_turn_id, None


def _reuse_active_calendar_focus_receipt(
    *,
    events,
    start_event,
    source_turn_id: str,
) -> NativeFocusStartResult:
    active_state = focus_store.reduce_events(events)
    open_focus_ids = _canonical_open_focus_ids(events)
    closed_focus_ids = [
        event.focusId
        for event in events
        if event.sourceTurnId == source_turn_id
        and event.type == FocusEventType.FOCUS_ENDED
        and str(event.payload.get("newFocusId", "")).strip() == start_event.focusId
    ]
    verification = NativeFocusVerification(
        activeFocusMatches=(
            active_state.focusId == start_event.focusId
            and active_state.status not in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
        ),
        exactlyOneFocusOpen=open_focus_ids == [start_event.focusId],
        startEventPersisted=True,
        previousFocusesClosed=all(
            focus_id not in open_focus_ids for focus_id in closed_focus_ids
        ),
        openFocusIds=open_focus_ids,
        details=[],
    )
    if not (
        verification.activeFocusMatches
        and verification.exactlyOneFocusOpen
        and verification.startEventPersisted
        and verification.previousFocusesClosed
    ):
        raise NativeCalendarFocusPrepError(
            "verification_failed",
            "The active calendar Focus could not be reused canonically.",
        )
    return NativeFocusStartResult(
        ok=True,
        outcome="reused",
        verified=True,
        activeFocus=active_state,
        previousFocusId=closed_focus_ids[0] if closed_focus_ids else "",
        closedFocusIds=closed_focus_ids,
        sourceTurnId=source_turn_id,
        verification=verification,
        telemetryRecorded=False,
        message=f"Focus is active: {active_state.title}.",
    )


def _count_start_events(source_turn_id: str) -> int:
    return sum(
        1
        for event in focus_store._read_log_unlocked().events
        if event.sourceTurnId == source_turn_id
        and event.type == FocusEventType.FOCUS_STARTED
    )


def _count_task_receipts(source_turn_id: str) -> int:
    document = _read_relationships_unlocked()
    raw_tasks_by_focus = document.get("tasksByFocusId")
    if not isinstance(raw_tasks_by_focus, dict):
        return 0
    return sum(
        1
        for records in raw_tasks_by_focus.values()
        if isinstance(records, list)
        for record in records
        if isinstance(record, dict)
        and str(record.get("sourceTurnId", "")).strip() == source_turn_id
    )


def _verify_combined_receipt(
    *,
    source_turn_id: str,
    requested_titles: list[str],
    focus_receipt: NativeFocusStartResult,
    task_receipt: NativeFocusTasksResult,
) -> NativeCalendarFocusPrepVerification:
    canonical = focus_store.reduce_events(list(focus_store._read_log_unlocked().events))
    open_ids = []
    open_by_id: dict[str, bool] = {}
    order: list[str] = []
    for event in focus_store._read_log_unlocked().events:
        focus_id = event.focusId.strip() or str(event.payload.get("focusId", "")).strip()
        if not focus_id:
            continue
        if event.type == FocusEventType.FOCUS_STARTED:
            open_by_id[focus_id] = True
        elif event.type in {FocusEventType.FOCUS_ENDED, FocusEventType.FOCUS_COMPLETED}:
            open_by_id[focus_id] = False
        elif event.type == FocusEventType.LEGACY_IMPORTED:
            status = str(event.payload.get("status", "active")).strip()
            open_by_id[focus_id] = status not in {
                FocusStatus.INACTIVE.value,
                FocusStatus.COMPLETE.value,
            }
        if focus_id not in order:
            order.append(focus_id)
    open_ids = [focus_id for focus_id in order if open_by_id.get(focus_id)]

    focus_verified = bool(
        focus_receipt.verified
        and focus_receipt.verification.activeFocusMatches
        and focus_receipt.verification.exactlyOneFocusOpen
        and focus_receipt.verification.startEventPersisted
        and focus_receipt.verification.previousFocusesClosed
    )
    task_verified = bool(
        task_receipt.verified
        and task_receipt.verification.activeFocusMatches
        and task_receipt.verification.tasksPersisted
        and task_receipt.verification.relationshipPersisted
        and task_receipt.verification.sourceTurnUnique
    )
    focus_id = focus_receipt.activeFocus.focusId
    active_matches = bool(
        canonical.focusId == focus_id
        and canonical.status not in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
        and open_ids == [focus_id]
        and task_receipt.focusId == focus_id
    )
    exact_tasks = [task.title for task in task_receipt.tasks] == requested_titles
    relationship_persisted = task_receipt.verification.relationshipPersisted
    source_turn_unique = bool(
        focus_receipt.sourceTurnId == source_turn_id
        and task_receipt.sourceTurnId == source_turn_id
        and _count_start_events(source_turn_id) == 1
        and _count_task_receipts(source_turn_id) == 1
    )
    details: list[str] = []
    if not focus_verified:
        details.append("The canonical Focus start receipt did not verify completely.")
    if not task_verified:
        details.append("The canonical Focus task receipt did not verify completely.")
    if not active_matches:
        details.append("The prepared Focus is not the sole current canonical Focus.")
    if not exact_tasks:
        details.append("The exact calendar preparation tasks were not persisted.")
    if not relationship_persisted:
        details.append("The Focus-to-task relationship was not persisted.")
    if not source_turn_unique:
        details.append("The source turn does not identify one start and one task receipt.")
    return NativeCalendarFocusPrepVerification(
        focusReceiptVerified=focus_verified,
        taskReceiptVerified=task_verified,
        activeFocusMatches=active_matches,
        exactTasksPersisted=exact_tasks,
        relationshipPersisted=relationship_persisted,
        sourceTurnUnique=source_turn_unique,
        rollbackProtected=True,
        details=details,
    )


def _verification_passed(
    verification: NativeCalendarFocusPrepVerification,
) -> bool:
    return (
        verification.focusReceiptVerified
        and verification.taskReceiptVerified
        and verification.activeFocusMatches
        and verification.exactTasksPersisted
        and verification.relationshipPersisted
        and verification.sourceTurnUnique
        and verification.rollbackProtected
    )


def prepare_calendar_focus_verified(
    request: NativeCalendarFocusPrepRequest,
) -> NativeCalendarFocusPrepResult:
    requested_source_turn_id = request.sourceTurnId.strip()
    source_turn_id = requested_source_turn_id
    event = request.event
    task_titles = build_calendar_prep_task_titles(event)
    focus_id_for_health = ""
    task_ids_for_health: list[str] = []
    rolled_back = False

    try:
        with focus_store._STORE_LOCK:
            with _RELATIONSHIP_LOCK:
                with memory_store._STORE_LOCK:
                    focus_before = focus_store._read_log_unlocked().model_copy(deep=True)
                    memory_before = json.loads(
                        json.dumps(memory_store._read_payload_unlocked())
                    )
                    relationship_path = _relationship_file()
                    relationship_existed_before = relationship_path.exists()
                    relationship_bytes_before = (
                        relationship_path.read_bytes()
                        if relationship_existed_before
                        else b""
                    )
                    relationships_before = json.loads(
                        json.dumps(_read_relationships_unlocked())
                    )
                    try:
                        source_turn_id, active_start_event = _resolve_calendar_source_turn(
                            events=list(focus_before.events),
                            request=request,
                        )
                        if active_start_event is not None:
                            focus_receipt = _reuse_active_calendar_focus_receipt(
                                events=list(focus_before.events),
                                start_event=active_start_event,
                                source_turn_id=source_turn_id,
                            )
                        else:
                            focus_receipt = start_focus_verified(
                                NativeFocusStartRequest(
                                    title=build_calendar_focus_title(event),
                                    objective=build_calendar_focus_objective(event),
                                    mode="meeting",
                                    tags=[
                                        "calendar-prep",
                                        f"calendar-event:{event.id}",
                                    ],
                                    sourceTurnId=source_turn_id,
                                )
                            )
                        focus_id_for_health = focus_receipt.activeFocus.focusId
                        task_receipt = link_focus_tasks_verified(
                            NativeFocusTasksRequest(
                                expectedFocusId=focus_id_for_health,
                                taskTitles=task_titles,
                                sourceTurnId=source_turn_id,
                            )
                        )
                        task_ids_for_health = [task.id for task in task_receipt.tasks]
                        verification = _verify_combined_receipt(
                            source_turn_id=source_turn_id,
                            requested_titles=task_titles,
                            focus_receipt=focus_receipt,
                            task_receipt=task_receipt,
                        )
                        if not _verification_passed(verification):
                            raise NativeCalendarFocusPrepError(
                                "verification_failed",
                                "The combined calendar Focus and task receipt did not verify canonically.",
                            )
                    except Exception:
                        _restore_transaction_unlocked(
                            focus_before=focus_before,
                            memory_before=memory_before,
                            relationship_path=relationship_path,
                            relationship_existed_before=relationship_existed_before,
                            relationship_bytes_before=relationship_bytes_before,
                        )
                        rolled_back = True
                        raise

        outcome: Literal["created", "linked", "reused"]
        if focus_receipt.outcome == "reused" and task_receipt.outcome == "reused":
            outcome = "reused"
        elif task_receipt.outcome == "linked":
            outcome = "linked"
        else:
            outcome = "created"
        telemetry = _record_health(
            outcome=outcome,
            verified=True,
            source_turn_id=source_turn_id,
            event_id=event.id,
            focus_id=focus_id_for_health,
            task_ids=task_ids_for_health,
        )
        if outcome == "reused":
            message = (
                f"Calendar preparation is already verified for {event.title}; "
                f"the Focus and {len(task_receipt.tasks)} linked tasks were reused."
            )
        elif focus_receipt.outcome == "reused" and task_receipt.outcome == "created":
            message = (
                f"Restored {len(task_receipt.tasks)} verified linked tasks for the "
                f"active meeting-prep Focus for {event.title}."
            )
        elif focus_receipt.outcome == "reused" and task_receipt.outcome == "linked":
            message = (
                f"Relinked {len(task_receipt.tasks)} existing verified tasks to the "
                f"active meeting-prep Focus for {event.title}."
            )
        elif outcome == "linked":
            message = (
                f"Started a verified meeting-prep Focus for {event.title} and linked "
                f"{len(task_receipt.tasks)} existing verified tasks."
            )
        else:
            message = (
                f"Started a verified meeting-prep Focus for {event.title} and created "
                f"{len(task_receipt.tasks)} linked tasks."
            )
        return NativeCalendarFocusPrepResult(
            ok=True,
            outcome=outcome,
            verified=True,
            event=event,
            focusReceipt=focus_receipt,
            taskReceipt=task_receipt,
            sourceTurnId=source_turn_id,
            verification=verification,
            telemetryRecorded=telemetry,
            message=message,
        )
    except NativeCalendarFocusPrepError as exc:
        _record_health(
            outcome="failed",
            verified=False,
            source_turn_id=source_turn_id,
            event_id=event.id,
            focus_id=focus_id_for_health,
            task_ids=task_ids_for_health,
            failure_code=exc.code,
            rolled_back=rolled_back,
        )
        raise
    except (NativeFocusLifecycleError, NativeFocusTasksError) as exc:
        _record_health(
            outcome="failed",
            verified=False,
            source_turn_id=source_turn_id,
            event_id=event.id,
            focus_id=focus_id_for_health,
            task_ids=task_ids_for_health,
            failure_code=exc.code,
            rolled_back=rolled_back,
        )
        raise NativeCalendarFocusPrepError(
            exc.code,
            exc.message,
            status_code=exc.status_code,
        ) from exc
    except Exception as exc:
        _record_health(
            outcome="failed",
            verified=False,
            source_turn_id=source_turn_id,
            event_id=event.id,
            focus_id=focus_id_for_health,
            task_ids=task_ids_for_health,
            failure_code="write_failed",
            rolled_back=rolled_back,
        )
        raise NativeCalendarFocusPrepError(
            "write_failed",
            "QMeet could not persist the combined calendar Focus transaction.",
            status_code=500,
        ) from exc
