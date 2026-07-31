from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.focus import store as focus_store
from app.focus.models import FocusEvent, FocusEventType, FocusState, FocusStatus


_NATIVE_LIFECYCLE_SOURCE = "focus-native-lifecycle"
_HEALTH_LOCK = RLock()


class NativeFocusStartRequest(BaseModel):
    """Deterministic input for the first backend-native Focus lifecycle write."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=180)
    objective: str = Field(default="", max_length=500)
    mode: str = Field(default="", max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=12)
    sourceTurnId: str = Field(min_length=1, max_length=120)

    @field_validator("title", "objective", "mode", "sourceTurnId")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.split()).strip()

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            item = " ".join(str(raw).split()).strip()
            key = item.casefold()
            if not item or key in seen:
                continue
            seen.add(key)
            result.append(item[:80])
        return result[:12]


class NativeFocusVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activeFocusMatches: bool = False
    exactlyOneFocusOpen: bool = False
    startEventPersisted: bool = False
    previousFocusesClosed: bool = False
    openFocusIds: list[str] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)


class NativeFocusStartResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    operation: Literal["start_focus"] = "start_focus"
    outcome: Literal["started", "replaced", "reused"]
    verified: bool
    activeFocus: FocusState
    previousFocusId: str = ""
    closedFocusIds: list[str] = Field(default_factory=list)
    sourceTurnId: str
    verification: NativeFocusVerification
    telemetryRecorded: bool = False
    message: str


class NativeFocusLifecycleError(Exception):
    """A safe lifecycle error that never authorizes mutation-success wording."""

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


def _health_file() -> Path:
    configured = os.getenv("QMEET_FOCUS_LIFECYCLE_HEALTH_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "qmeet_focus_lifecycle_health.json"


def _empty_health() -> dict[str, object]:
    return {
        "version": 1,
        "updatedAt": "",
        "startFocus": {
            "attemptCount": 0,
            "startedCount": 0,
            "replacedCount": 0,
            "reusedCount": 0,
            "verifiedCount": 0,
            "failedCount": 0,
            "verificationFailedCount": 0,
            "writeFailedCount": 0,
            "lastOutcome": "",
            "lastFailureCode": "",
            "lastSourceTurnId": "",
            "lastActiveFocusId": "",
            "lastPreviousFocusId": "",
            "lastUpdatedAt": "",
        },
    }


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
    baseline_start = baseline["startFocus"]
    incoming_start = payload.get("startFocus")
    if isinstance(baseline_start, dict) and isinstance(incoming_start, dict):
        baseline_start.update(incoming_start)
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


def _record_health(
    *,
    outcome: str,
    verified: bool,
    source_turn_id: str,
    active_focus_id: str = "",
    previous_focus_id: str = "",
    failure_code: str = "",
) -> bool:
    try:
        with _HEALTH_LOCK:
            document = _read_health_unlocked()
            summary = document.get("startFocus")
            if not isinstance(summary, dict):
                document = _empty_health()
                summary = document["startFocus"]
            assert isinstance(summary, dict)

            summary["attemptCount"] = int(summary.get("attemptCount", 0)) + 1
            count_key = {
                "started": "startedCount",
                "replaced": "replacedCount",
                "reused": "reusedCount",
            }.get(outcome)
            if count_key:
                summary[count_key] = int(summary.get(count_key, 0)) + 1
            if verified:
                summary["verifiedCount"] = int(summary.get("verifiedCount", 0)) + 1
            else:
                summary["failedCount"] = int(summary.get("failedCount", 0)) + 1
            if failure_code == "verification_failed":
                summary["verificationFailedCount"] = int(
                    summary.get("verificationFailedCount", 0)
                ) + 1
            if failure_code == "write_failed":
                summary["writeFailedCount"] = int(summary.get("writeFailedCount", 0)) + 1

            summary["lastOutcome"] = outcome
            summary["lastFailureCode"] = failure_code
            summary["lastSourceTurnId"] = source_turn_id
            summary["lastActiveFocusId"] = active_focus_id
            summary["lastPreviousFocusId"] = previous_focus_id
            summary["lastUpdatedAt"] = _now_iso()
            _atomic_write_health_unlocked(document)
        return True
    except Exception:
        return False


def get_native_focus_lifecycle_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        return _read_health_unlocked()


def reset_native_focus_lifecycle_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        document = _empty_health()
        _atomic_write_health_unlocked(document)
        return document


def _open_focus_ids(events: list[FocusEvent]) -> list[str]:
    open_by_id: dict[str, bool] = {}
    order: list[str] = []

    for event in events:
        focus_id = event.focusId.strip()
        if not focus_id:
            payload_focus_id = str(event.payload.get("focusId", "")).strip()
            focus_id = payload_focus_id
        if not focus_id:
            continue

        if event.type == FocusEventType.LEGACY_IMPORTED:
            raw_status = str(event.payload.get("status", FocusStatus.ACTIVE.value)).strip()
            open_by_id[focus_id] = raw_status not in {
                FocusStatus.INACTIVE.value,
                FocusStatus.COMPLETE.value,
            }
            if focus_id not in order:
                order.append(focus_id)
        elif event.type == FocusEventType.FOCUS_STARTED:
            open_by_id[focus_id] = True
            if focus_id not in order:
                order.append(focus_id)
        elif event.type in {
            FocusEventType.FOCUS_ENDED,
            FocusEventType.FOCUS_COMPLETED,
        }:
            open_by_id[focus_id] = False
            if focus_id not in order:
                order.append(focus_id)

    return [focus_id for focus_id in order if open_by_id.get(focus_id) is True]


def _matching_turn_start(
    events: list[FocusEvent],
    source_turn_id: str,
) -> FocusEvent | None:
    for event in reversed(events):
        if (
            event.type == FocusEventType.FOCUS_STARTED
            and event.sourceTurnId == source_turn_id
        ):
            return event
    return None


def _verify_postcondition(
    *,
    events: list[FocusEvent],
    expected_focus_id: str,
    expected_title: str,
    expected_objective: str,
    start_event_id: str,
    closed_focus_ids: list[str],
    close_event_ids: list[str],
) -> NativeFocusVerification:
    state = focus_store.reduce_events(events)
    open_focus_ids = _open_focus_ids(events)
    event_ids = {event.id for event in events}

    active_matches = (
        state.focusId == expected_focus_id
        and state.title.casefold() == expected_title.casefold()
        and state.objective.casefold() == expected_objective.casefold()
        and state.status not in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
    )
    exactly_one_open = open_focus_ids == [expected_focus_id]
    start_persisted = start_event_id in event_ids
    previous_closed = all(event_id in event_ids for event_id in close_event_ids)
    previous_closed = previous_closed and all(
        focus_id not in open_focus_ids for focus_id in closed_focus_ids
    )

    details: list[str] = []
    if not active_matches:
        details.append("Canonical active Focus does not match the requested Focus.")
    if not exactly_one_open:
        details.append(
            "Canonical lifecycle history does not contain exactly one open Focus."
        )
    if not start_persisted:
        details.append("The canonical focus_started event was not persisted.")
    if not previous_closed:
        details.append("One or more previously open Focuses were not closed.")

    return NativeFocusVerification(
        activeFocusMatches=active_matches,
        exactlyOneFocusOpen=exactly_one_open,
        startEventPersisted=start_persisted,
        previousFocusesClosed=previous_closed,
        openFocusIds=open_focus_ids,
        details=details,
    )


def _verification_passed(verification: NativeFocusVerification) -> bool:
    return (
        verification.activeFocusMatches
        and verification.exactlyOneFocusOpen
        and verification.startEventPersisted
        and verification.previousFocusesClosed
    )


def _success_message(outcome: str, title: str) -> str:
    if outcome == "replaced":
        return f"Started a new Focus: {title}. The previous Focus was moved to history."
    if outcome == "reused":
        return f"Focus is active: {title}."
    return f"Started Focus: {title}."


def start_focus_verified(request: NativeFocusStartRequest) -> NativeFocusStartResult:
    """Start or replace a Focus and authorize success only after canonical proof.

    This deliberately uses the existing Focus store's lock and atomic writer so
    the close-and-start event pair is one transaction. It is the narrow Phase
    20D1 seam; update, completion, resume, Calendar, and visual writes remain
    outside this executor.
    """

    title = request.title.strip()
    objective = request.objective.strip()
    source_turn_id = request.sourceTurnId.strip()
    tags = list(request.tags)
    if request.mode:
        mode_tag = f"mode:{request.mode.casefold()}"
        if mode_tag.casefold() not in {tag.casefold() for tag in tags}:
            tags.append(mode_tag)
    tags = tags[:12]

    try:
        with focus_store._STORE_LOCK:
            document = focus_store._read_log_unlocked()
            existing_events = list(document.events)
            before_state = focus_store.reduce_events(existing_events)
            existing_start = _matching_turn_start(existing_events, source_turn_id)

            if existing_start is not None:
                existing_title = str(existing_start.payload.get("title", "")).strip()
                existing_objective = str(
                    existing_start.payload.get("objective", "")
                ).strip()
                closed_focus_ids = [
                    event.focusId
                    for event in existing_events
                    if event.sourceTurnId == source_turn_id
                    and event.type == FocusEventType.FOCUS_ENDED
                    and str(event.payload.get("newFocusId", "")).strip()
                    == existing_start.focusId
                ]
                close_event_ids = [
                    event.id
                    for event in existing_events
                    if event.sourceTurnId == source_turn_id
                    and event.type == FocusEventType.FOCUS_ENDED
                    and event.focusId in closed_focus_ids
                ]
                verification = _verify_postcondition(
                    events=existing_events,
                    expected_focus_id=existing_start.focusId,
                    expected_title=existing_title,
                    expected_objective=existing_objective,
                    start_event_id=existing_start.id,
                    closed_focus_ids=closed_focus_ids,
                    close_event_ids=close_event_ids,
                )
                if (
                    existing_title.casefold() != title.casefold()
                    or existing_objective.casefold() != objective.casefold()
                    or not _verification_passed(verification)
                ):
                    _record_health(
                        outcome="failed",
                        verified=False,
                        source_turn_id=source_turn_id,
                        active_focus_id=before_state.focusId,
                        previous_focus_id=closed_focus_ids[0]
                        if closed_focus_ids
                        else "",
                        failure_code="source_turn_conflict",
                    )
                    raise NativeFocusLifecycleError(
                        "source_turn_conflict",
                        "This Focus start turn already has a different or superseded canonical result.",
                    )

                outcome: Literal["started", "replaced", "reused"] = "reused"
                active_state = focus_store.reduce_events(existing_events)
                telemetry_recorded = _record_health(
                    outcome=outcome,
                    verified=True,
                    source_turn_id=source_turn_id,
                    active_focus_id=active_state.focusId,
                    previous_focus_id=closed_focus_ids[0]
                    if closed_focus_ids
                    else "",
                )
                return NativeFocusStartResult(
                    ok=True,
                    outcome=outcome,
                    verified=True,
                    activeFocus=active_state,
                    previousFocusId=closed_focus_ids[0]
                    if closed_focus_ids
                    else "",
                    closedFocusIds=closed_focus_ids,
                    sourceTurnId=source_turn_id,
                    verification=verification,
                    telemetryRecorded=telemetry_recorded,
                    message=_success_message(outcome, active_state.title),
                )

            open_focus_ids = _open_focus_ids(existing_events)
            previous_focus_id = (
                before_state.focusId
                if before_state.focusId in open_focus_ids
                else (open_focus_ids[-1] if open_focus_ids else "")
            )
            outcome = "replaced" if open_focus_ids else "started"
            new_focus_id = focus_store._new_focus_id()

            close_events = [
                focus_store._new_event(
                    FocusEventType.FOCUS_ENDED,
                    focus_id=focus_id,
                    payload={
                        "reason": "superseded_by_new_focus",
                        "newFocusId": new_focus_id,
                        "nativeLifecycle": True,
                    },
                    source_turn_id=source_turn_id,
                    source=_NATIVE_LIFECYCLE_SOURCE,
                )
                for focus_id in open_focus_ids
            ]
            start_event = focus_store._new_event(
                FocusEventType.FOCUS_STARTED,
                focus_id=new_focus_id,
                payload={
                    "title": title,
                    "objective": objective,
                    "tags": tags,
                    "nativeLifecycle": True,
                    "nativeOutcome": outcome,
                },
                source_turn_id=source_turn_id,
                source=_NATIVE_LIFECYCLE_SOURCE,
            )
            candidate_events = [*existing_events, *close_events, start_event]
            verification = _verify_postcondition(
                events=candidate_events,
                expected_focus_id=new_focus_id,
                expected_title=title,
                expected_objective=objective,
                start_event_id=start_event.id,
                closed_focus_ids=open_focus_ids,
                close_event_ids=[event.id for event in close_events],
            )
            if not _verification_passed(verification):
                _record_health(
                    outcome="failed",
                    verified=False,
                    source_turn_id=source_turn_id,
                    active_focus_id=before_state.focusId,
                    previous_focus_id=previous_focus_id,
                    failure_code="verification_failed",
                )
                raise NativeFocusLifecycleError(
                    "verification_failed",
                    "The proposed Focus transition did not satisfy canonical postconditions.",
                )

            document.events.extend([*close_events, start_event])
            focus_store._atomic_write_unlocked(document)

            persisted_document = focus_store._read_log_unlocked()
            persisted_events = list(persisted_document.events)
            persisted_verification = _verify_postcondition(
                events=persisted_events,
                expected_focus_id=new_focus_id,
                expected_title=title,
                expected_objective=objective,
                start_event_id=start_event.id,
                closed_focus_ids=open_focus_ids,
                close_event_ids=[event.id for event in close_events],
            )
            if not _verification_passed(persisted_verification):
                _record_health(
                    outcome="failed",
                    verified=False,
                    source_turn_id=source_turn_id,
                    active_focus_id=new_focus_id,
                    previous_focus_id=previous_focus_id,
                    failure_code="verification_failed",
                )
                raise NativeFocusLifecycleError(
                    "verification_failed",
                    "The Focus write completed, but canonical state could not verify it.",
                )

            active_state = focus_store.reduce_events(persisted_events)
    except NativeFocusLifecycleError:
        raise
    except focus_store.FocusStoreError as exc:
        _record_health(
            outcome="failed",
            verified=False,
            source_turn_id=source_turn_id,
            failure_code="write_failed",
        )
        raise NativeFocusLifecycleError(
            "write_failed",
            "The canonical Focus store could not persist the transition.",
            status_code=503,
        ) from exc
    except Exception as exc:
        _record_health(
            outcome="failed",
            verified=False,
            source_turn_id=source_turn_id,
            failure_code="write_failed",
        )
        raise NativeFocusLifecycleError(
            "write_failed",
            "The canonical Focus transition could not be completed.",
            status_code=503,
        ) from exc

    telemetry_recorded = _record_health(
        outcome=outcome,
        verified=True,
        source_turn_id=source_turn_id,
        active_focus_id=active_state.focusId,
        previous_focus_id=previous_focus_id,
    )
    return NativeFocusStartResult(
        ok=True,
        outcome=outcome,
        verified=True,
        activeFocus=active_state,
        previousFocusId=previous_focus_id,
        closedFocusIds=open_focus_ids,
        sourceTurnId=source_turn_id,
        verification=persisted_verification,
        telemetryRecorded=telemetry_recorded,
        message=_success_message(outcome, active_state.title),
    )
