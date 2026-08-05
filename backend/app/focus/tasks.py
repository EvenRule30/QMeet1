from __future__ import annotations

import hashlib
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
from app.focus import summary as relationship_store
from app.focus.models import FocusStatus

_TASK_SOURCE = "focus-native-tasks"
_HEALTH_LOCK = RLock()
_HEALTH_VERSION = 1
_MAX_TASKS_PER_RECEIPT = 5
_MAX_RECEIPTS_PER_FOCUS = 48

# Summary and task attachments intentionally share one relationship document and lock.
_RELATIONSHIP_LOCK = relationship_store._RELATIONSHIP_LOCK
_read_relationships_unlocked = relationship_store._read_relationships_unlocked
_write_relationships_unlocked = relationship_store._write_relationships_unlocked
_open_focus_ids = relationship_store._open_focus_ids


class NativeFocusTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=140)
    title: str = Field(min_length=1, max_length=240)
    createdAt: str = Field(min_length=1, max_length=80)
    completedAt: str | None = Field(default=None, max_length=80)

    @field_validator("id", "createdAt")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("value cannot be blank")
        return cleaned

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("task title cannot be blank")
        return cleaned

    @field_validator("completedAt")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        return cleaned or None


class NativeFocusTasksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedFocusId: str = Field(min_length=1, max_length=120)
    taskTitles: list[str] = Field(min_length=1, max_length=_MAX_TASKS_PER_RECEIPT)
    sourceTurnId: str = Field(min_length=1, max_length=120)

    @field_validator("expectedFocusId", "sourceTurnId")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("value cannot be blank")
        return cleaned

    @field_validator("taskTitles")
    @classmethod
    def clean_task_titles(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            title = " ".join(str(value or "").split()).strip()
            if not title:
                raise ValueError("task title cannot be blank")
            if len(title) > 240:
                raise ValueError("task title is too long")
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(title)
        if not cleaned:
            raise ValueError("at least one task title is required")
        return cleaned[:_MAX_TASKS_PER_RECEIPT]


class NativeFocusTasksVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activeFocusMatches: bool = False
    tasksPersisted: bool = False
    relationshipPersisted: bool = False
    sourceTurnUnique: bool = False
    details: list[str] = Field(default_factory=list)


class NativeFocusTasksResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    operation: Literal["link_focus_tasks"] = "link_focus_tasks"
    outcome: Literal["created", "linked", "reused"]
    verified: bool
    focusId: str
    focusTitle: str
    tasks: list[NativeFocusTask]
    memoryTasks: list[NativeFocusTask]
    createdTaskIds: list[str]
    receiptId: str
    linkedAt: str
    sourceTurnId: str
    verification: NativeFocusTasksVerification
    telemetryRecorded: bool = False
    message: str


class NativeFocusTasksError(Exception):
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
    override = os.getenv("QMEET_FOCUS_TASK_HEALTH_FILE", "").strip()
    return Path(override) if override else _backend_root() / "data" / "qmeet_focus_task_health.json"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    tmp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            json.dump(payload, tmp_file, indent=2)
            tmp_file.write("\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _empty_health() -> dict[str, object]:
    return {
        "version": _HEALTH_VERSION,
        "updatedAt": "",
        "linkFocusTasks": {
            "attemptCount": 0,
            "createdCount": 0,
            "linkedCount": 0,
            "reusedCount": 0,
            "verifiedCount": 0,
            "failedCount": 0,
            "verificationFailedCount": 0,
            "writeFailedCount": 0,
            "lastOutcome": "",
            "lastFailureCode": "",
            "lastFocusId": "",
            "lastTaskIds": [],
            "lastSourceTurnId": "",
            "lastUpdatedAt": "",
        },
    }


def _read_health_unlocked() -> dict[str, object]:
    path = _health_file()
    if not path.exists():
        return _empty_health()
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_health()
    if not isinstance(parsed, dict):
        return _empty_health()
    if not isinstance(parsed.get("linkFocusTasks"), dict):
        parsed["linkFocusTasks"] = _empty_health()["linkFocusTasks"]
    return parsed


def _record_health(
    *,
    outcome: str,
    focus_id: str,
    task_ids: list[str],
    source_turn_id: str,
    failure_code: str = "",
    verified: bool = False,
) -> bool:
    try:
        with _HEALTH_LOCK:
            document = _read_health_unlocked()
            health = document["linkFocusTasks"]
            assert isinstance(health, dict)
            health["attemptCount"] = int(health.get("attemptCount", 0)) + 1
            counter = {
                "created": "createdCount",
                "linked": "linkedCount",
                "reused": "reusedCount",
                "failed": "failedCount",
            }.get(outcome)
            if counter:
                health[counter] = int(health.get(counter, 0)) + 1
            if verified:
                health["verifiedCount"] = int(health.get("verifiedCount", 0)) + 1
            if failure_code == "verification_failed":
                health["verificationFailedCount"] = int(
                    health.get("verificationFailedCount", 0)
                ) + 1
            if failure_code == "write_failed":
                health["writeFailedCount"] = int(health.get("writeFailedCount", 0)) + 1
            health["lastOutcome"] = outcome
            health["lastFailureCode"] = failure_code
            health["lastFocusId"] = focus_id
            health["lastTaskIds"] = task_ids
            health["lastSourceTurnId"] = source_turn_id
            health["lastUpdatedAt"] = _now_iso()
            document["updatedAt"] = _now_iso()
            _atomic_write_json(_health_file(), document)
        return True
    except Exception:
        return False


def get_native_focus_task_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        return _read_health_unlocked()


def reset_native_focus_task_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        document = _empty_health()
        _atomic_write_json(_health_file(), document)
        return document


def _normalize_title(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _titles_hash(titles: list[str]) -> str:
    canonical = json.dumps(
        [title.casefold() for title in titles],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _task_core(task: dict[str, object]) -> dict[str, str]:
    return {
        "id": str(task.get("id", "")).strip(),
        "title": _normalize_title(task.get("title", "")),
        "createdAt": str(task.get("createdAt", "")).strip(),
    }


def _task_identity_hash(tasks: list[dict[str, object]]) -> str:
    canonical = json.dumps(
        [_task_core(task) for task in tasks],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _task_relationship_records(
    document: dict[str, object],
    focus_id: str,
) -> list[dict[str, object]]:
    tasks_by_focus = document.get("tasksByFocusId")
    if not isinstance(tasks_by_focus, dict):
        return []
    raw_records = tasks_by_focus.get(focus_id)
    if not isinstance(raw_records, list):
        return []
    return [record for record in raw_records if isinstance(record, dict)]


def _find_source_turn_record(
    document: dict[str, object],
    source_turn_id: str,
) -> tuple[str, dict[str, object]] | None:
    tasks_by_focus = document.get("tasksByFocusId")
    if not isinstance(tasks_by_focus, dict):
        return None
    for focus_id, raw_records in tasks_by_focus.items():
        if not isinstance(focus_id, str) or not isinstance(raw_records, list):
            continue
        for raw_record in raw_records:
            if (
                isinstance(raw_record, dict)
                and str(raw_record.get("sourceTurnId", "")).strip() == source_turn_id
            ):
                return focus_id, raw_record
    return None


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


def _select_or_create_tasks(
    memory_before: dict,
    requested_titles: list[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[str]]:
    existing_tasks = [dict(task) for task in memory_before["tasks"]]
    available_by_title: dict[str, list[dict[str, object]]] = {}
    for task in existing_tasks:
        if str(task.get("completedAt", "")).strip():
            continue
        key = _normalize_title(task.get("title", "")).casefold()
        if key:
            available_by_title.setdefault(key, []).append(task)

    selected: list[dict[str, object]] = []
    created: list[dict[str, object]] = []
    used_ids: set[str] = set()
    for title in requested_titles:
        key = title.casefold()
        reusable = next(
            (
                task
                for task in available_by_title.get(key, [])
                if str(task.get("id", "")).strip() not in used_ids
            ),
            None,
        )
        if reusable is not None:
            task = _task_core(reusable)
        else:
            task = {
                "id": memory_store._new_task_id(),
                "title": title,
                "createdAt": _now_iso(),
            }
            created.append(task)
        used_ids.add(task["id"])
        selected.append(task)

    next_tasks = [*created, *existing_tasks]
    return selected, next_tasks, [task["id"] for task in created]


def _record_task_snapshots(record: dict[str, object]) -> list[dict[str, object]]:
    raw_tasks = record.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    snapshots: list[dict[str, object]] = []
    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            continue
        core = _task_core(raw_task)
        if all(core.values()):
            snapshots.append(core)
    return snapshots


def _verify_tasks(
    *,
    focus_id: str,
    tasks: list[dict[str, object]],
    requested_titles: list[str],
    source_turn_id: str,
    receipt_id: str,
) -> NativeFocusTasksVerification:
    focus_events = list(focus_store._read_log_unlocked().events)
    focus_state = focus_store.reduce_events(focus_events)
    open_focus_ids = _open_focus_ids(focus_events)
    memory_after = memory_store._read_payload_unlocked()
    relationships_after = _read_relationships_unlocked()

    active_focus_matches = (
        focus_state.focusId == focus_id
        and focus_state.status not in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
        and open_focus_ids == [focus_id]
    )

    persisted_by_id = {
        str(item.get("id", "")).strip(): item for item in memory_after["tasks"]
    }
    tasks_persisted = bool(tasks) and all(
        task["id"] in persisted_by_id
        and _task_core(persisted_by_id[task["id"]]) == _task_core(task)
        for task in tasks
    )

    requested_hash = _titles_hash(requested_titles)
    identity_hash = _task_identity_hash(tasks)
    matching_records = [
        record
        for record in _task_relationship_records(relationships_after, focus_id)
        if str(record.get("receiptId", "")).strip() == receipt_id
        and str(record.get("focusId", "")).strip() == focus_id
        and str(record.get("sourceTurnId", "")).strip() == source_turn_id
        and str(record.get("source", "")).strip() == _TASK_SOURCE
        and bool(str(record.get("linkedAt", "")).strip())
        and _string_list(record.get("taskIds")) == [task["id"] for task in tasks]
        and str(record.get("requestedTitlesHash", "")).strip() == requested_hash
        and str(record.get("taskIdentityHash", "")).strip() == identity_hash
        and _record_task_snapshots(record) == [_task_core(task) for task in tasks]
    ]
    relationship_persisted = len(matching_records) == 1

    source_turn_matches: list[tuple[str, dict[str, object]]] = []
    tasks_by_focus = relationships_after.get("tasksByFocusId")
    if isinstance(tasks_by_focus, dict):
        for candidate_focus_id, raw_records in tasks_by_focus.items():
            if not isinstance(raw_records, list):
                continue
            for raw_record in raw_records:
                if (
                    isinstance(raw_record, dict)
                    and str(raw_record.get("sourceTurnId", "")).strip()
                    == source_turn_id
                ):
                    source_turn_matches.append((str(candidate_focus_id), raw_record))
    source_turn_unique = len(source_turn_matches) == 1

    details: list[str] = []
    if not active_focus_matches:
        details.append("The expected Focus is not the sole current canonical Focus.")
    if not tasks_persisted:
        details.append("The exact Focus task records were not persisted.")
    if not relationship_persisted:
        details.append("The Focus-to-task relationship was not persisted exactly.")
    if not source_turn_unique:
        details.append("The source turn does not identify exactly one task receipt.")

    return NativeFocusTasksVerification(
        activeFocusMatches=active_focus_matches,
        tasksPersisted=tasks_persisted,
        relationshipPersisted=relationship_persisted,
        sourceTurnUnique=source_turn_unique,
        details=details,
    )


def _verification_passed(verification: NativeFocusTasksVerification) -> bool:
    return (
        verification.activeFocusMatches
        and verification.tasksPersisted
        and verification.relationshipPersisted
        and verification.sourceTurnUnique
    )


def _result_tasks(raw_tasks: list[dict[str, object]]) -> list[NativeFocusTask]:
    return [NativeFocusTask.model_validate(task) for task in raw_tasks]


def get_active_focus_linked_task_ids() -> set[str]:
    """Return task IDs protected by the sole open canonical Focus.

    Compatibility memory writes may still replace ordinary Tasks, but they must not
    silently delete task records that a verified open Focus receipt still owns.
    """

    with focus_store._STORE_LOCK:
        events = list(focus_store._read_log_unlocked().events)
        open_focus_ids = _open_focus_ids(events)
        if len(open_focus_ids) != 1:
            return set()
        focus_id = open_focus_ids[0]
        with _RELATIONSHIP_LOCK:
            document = _read_relationships_unlocked()
            protected: set[str] = set()
            for record in _task_relationship_records(document, focus_id):
                protected.update(_string_list(record.get("taskIds")))
            return protected


def _replace_source_turn_attachment(
    document: dict[str, object],
    *,
    focus_id: str,
    source_turn_id: str,
    attachment: dict[str, object],
) -> dict[str, object]:
    next_document = json.loads(json.dumps(document))
    tasks_by_focus = next_document.setdefault("tasksByFocusId", {})
    if not isinstance(tasks_by_focus, dict):
        tasks_by_focus = {}
        next_document["tasksByFocusId"] = tasks_by_focus
    records = _task_relationship_records(next_document, focus_id)
    replaced = False
    next_records: list[dict[str, object]] = []
    for record in records:
        if (
            not replaced
            and str(record.get("sourceTurnId", "")).strip() == source_turn_id
        ):
            next_records.append(attachment)
            replaced = True
        else:
            next_records.append(record)
    if not replaced:
        next_records.insert(0, attachment)
    tasks_by_focus[focus_id] = next_records[:_MAX_RECEIPTS_PER_FOCUS]
    return next_document


def _build_task_attachment(
    *,
    focus_id: str,
    source_turn_id: str,
    requested_hash: str,
    tasks: list[dict[str, object]],
    created_task_ids: list[str],
    receipt_id: str,
    linked_at: str,
) -> dict[str, object]:
    return {
        "receiptId": receipt_id,
        "focusId": focus_id,
        "tasks": [_task_core(task) for task in tasks],
        "taskIds": [task["id"] for task in tasks],
        "createdTaskIds": created_task_ids,
        "requestedTitlesHash": requested_hash,
        "taskIdentityHash": _task_identity_hash(tasks),
        "linkedAt": linked_at,
        "sourceTurnId": source_turn_id,
        "source": _TASK_SOURCE,
    }


def link_focus_tasks_verified(
    request: NativeFocusTasksRequest,
) -> NativeFocusTasksResult:
    focus_id = request.expectedFocusId.strip()
    source_turn_id = request.sourceTurnId.strip()
    requested_titles = list(request.taskTitles)
    requested_hash = _titles_hash(requested_titles)
    task_ids_for_health: list[str] = []

    try:
        with focus_store._STORE_LOCK:
            focus_document = focus_store._read_log_unlocked()
            focus_events = list(focus_document.events)
            focus_state = focus_store.reduce_events(focus_events)
            if (
                focus_state.focusId != focus_id
                or focus_state.status in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
                or _open_focus_ids(focus_events) != [focus_id]
            ):
                raise NativeFocusTasksError(
                    "stale_focus",
                    "The displayed Focus is not the current canonical Focus.",
                )

            with _RELATIONSHIP_LOCK:
                with memory_store._STORE_LOCK:
                    memory_before = memory_store._read_payload_unlocked()
                    relationships_before = _read_relationships_unlocked()
                    existing_turn = _find_source_turn_record(
                        relationships_before,
                        source_turn_id,
                    )
                    if existing_turn is not None:
                        existing_focus_id, existing_record = existing_turn
                        same_request = (
                            existing_focus_id == focus_id
                            and str(
                                existing_record.get("requestedTitlesHash", "")
                            ).strip()
                            == requested_hash
                        )
                        if not same_request:
                            raise NativeFocusTasksError(
                                "source_turn_conflict",
                                "This source turn already belongs to a different Focus task receipt.",
                            )
                        task_snapshots = _record_task_snapshots(existing_record)
                        receipt_id = str(existing_record.get("receiptId", "")).strip()
                        linked_at = str(existing_record.get("linkedAt", "")).strip()
                        task_ids_for_health = [task["id"] for task in task_snapshots]
                        verification = _verify_tasks(
                            focus_id=focus_id,
                            tasks=task_snapshots,
                            requested_titles=requested_titles,
                            source_turn_id=source_turn_id,
                            receipt_id=receipt_id,
                        )
                        if not _verification_passed(verification):
                            repairable_missing_tasks = (
                                verification.activeFocusMatches
                                and verification.relationshipPersisted
                                and verification.sourceTurnUnique
                                and not verification.tasksPersisted
                            )
                            if not repairable_missing_tasks:
                                _record_health(
                                    outcome="failed",
                                    focus_id=focus_id,
                                    task_ids=task_ids_for_health,
                                    source_turn_id=source_turn_id,
                                    failure_code="verification_failed",
                                )
                                raise NativeFocusTasksError(
                                    "verification_failed",
                                    "The existing Focus task receipt did not verify canonically.",
                                )

                            selected_tasks, next_memory_tasks, created_task_ids = (
                                _select_or_create_tasks(memory_before, requested_titles)
                            )
                            task_ids_for_health = [
                                task["id"] for task in selected_tasks
                            ]
                            linked_at = _now_iso()
                            repaired_attachment = _build_task_attachment(
                                focus_id=focus_id,
                                source_turn_id=source_turn_id,
                                requested_hash=requested_hash,
                                tasks=selected_tasks,
                                created_task_ids=created_task_ids,
                                receipt_id=receipt_id,
                                linked_at=linked_at,
                            )
                            try:
                                memory_store._write_payload_unlocked(
                                    next_memory_tasks,
                                    memory_before["recentActions"],
                                    memory_before["notes"],
                                    memory_before["activeSession"],
                                    memory_before["recentFocusSessions"],
                                    memory_before["visualContext"],
                                    preserve_active_session=False,
                                    preserve_recent_focus_sessions=False,
                                    preserve_visual_context=False,
                                )
                                repaired_relationships = _replace_source_turn_attachment(
                                    relationships_before,
                                    focus_id=focus_id,
                                    source_turn_id=source_turn_id,
                                    attachment=repaired_attachment,
                                )
                                _write_relationships_unlocked(repaired_relationships)
                            except Exception as exc:
                                try:
                                    _restore_memory_unlocked(memory_before)
                                    _write_relationships_unlocked(relationships_before)
                                except Exception:
                                    pass
                                raise NativeFocusTasksError(
                                    "write_failed",
                                    "QMeet could not repair the Focus task receipt.",
                                    status_code=500,
                                ) from exc

                            verification = _verify_tasks(
                                focus_id=focus_id,
                                tasks=selected_tasks,
                                requested_titles=requested_titles,
                                source_turn_id=source_turn_id,
                                receipt_id=receipt_id,
                            )
                            if not _verification_passed(verification):
                                _restore_memory_unlocked(memory_before)
                                _write_relationships_unlocked(relationships_before)
                                _record_health(
                                    outcome="failed",
                                    focus_id=focus_id,
                                    task_ids=task_ids_for_health,
                                    source_turn_id=source_turn_id,
                                    failure_code="verification_failed",
                                )
                                raise NativeFocusTasksError(
                                    "verification_failed",
                                    "Canonical state did not verify the repaired Focus task receipt.",
                                )

                            memory_after = memory_store._read_payload_unlocked()
                            outcome: Literal["created", "linked"] = (
                                "created" if created_task_ids else "linked"
                            )
                            telemetry = _record_health(
                                outcome=outcome,
                                focus_id=focus_id,
                                task_ids=task_ids_for_health,
                                source_turn_id=source_turn_id,
                                verified=True,
                            )
                            action = "Restored" if created_task_ids else "Relinked"
                            return NativeFocusTasksResult(
                                ok=True,
                                outcome=outcome,
                                verified=True,
                                focusId=focus_id,
                                focusTitle=focus_state.title,
                                tasks=_result_tasks(selected_tasks),
                                memoryTasks=_result_tasks(memory_after["tasks"]),
                                createdTaskIds=created_task_ids,
                                receiptId=receipt_id,
                                linkedAt=linked_at,
                                sourceTurnId=source_turn_id,
                                verification=verification,
                                telemetryRecorded=telemetry,
                                message=(
                                    f"{action} {len(selected_tasks)} verified task"
                                    f"{'s' if len(selected_tasks) != 1 else ''} for {focus_state.title}."
                                ),
                            )
                        memory_after = memory_store._read_payload_unlocked()
                        telemetry = _record_health(
                            outcome="reused",
                            focus_id=focus_id,
                            task_ids=task_ids_for_health,
                            source_turn_id=source_turn_id,
                            verified=True,
                        )
                        return NativeFocusTasksResult(
                            ok=True,
                            outcome="reused",
                            verified=True,
                            focusId=focus_id,
                            focusTitle=focus_state.title,
                            tasks=_result_tasks(task_snapshots),
                            memoryTasks=_result_tasks(memory_after["tasks"]),
                            createdTaskIds=_string_list(
                                existing_record.get("createdTaskIds")
                            ),
                            receiptId=receipt_id,
                            linkedAt=linked_at,
                            sourceTurnId=source_turn_id,
                            verification=verification,
                            telemetryRecorded=telemetry,
                            message=f"Focus tasks are already verified and linked for {focus_state.title}.",
                        )

                    selected_tasks, next_memory_tasks, created_task_ids = (
                        _select_or_create_tasks(memory_before, requested_titles)
                    )
                    task_ids_for_health = [task["id"] for task in selected_tasks]
                    linked_at = _now_iso()
                    receipt_id = (
                        "focus-tasks-"
                        + hashlib.sha256(
                            f"{focus_id}:{source_turn_id}:{requested_hash}".encode("utf-8")
                        ).hexdigest()[:24]
                    )
                    attachment = _build_task_attachment(
                        focus_id=focus_id,
                        source_turn_id=source_turn_id,
                        requested_hash=requested_hash,
                        tasks=selected_tasks,
                        created_task_ids=created_task_ids,
                        receipt_id=receipt_id,
                        linked_at=linked_at,
                    )
                    try:
                        memory_store._write_payload_unlocked(
                            next_memory_tasks,
                            memory_before["recentActions"],
                            memory_before["notes"],
                            memory_before["activeSession"],
                            memory_before["recentFocusSessions"],
                            memory_before["visualContext"],
                            preserve_active_session=False,
                            preserve_recent_focus_sessions=False,
                            preserve_visual_context=False,
                        )
                        relationships_after = json.loads(
                            json.dumps(relationships_before)
                        )
                        tasks_by_focus = relationships_after.setdefault(
                            "tasksByFocusId",
                            {},
                        )
                        if not isinstance(tasks_by_focus, dict):
                            tasks_by_focus = {}
                            relationships_after["tasksByFocusId"] = tasks_by_focus
                        records = _task_relationship_records(
                            relationships_after,
                            focus_id,
                        )
                        tasks_by_focus[focus_id] = [
                            attachment,
                            *records,
                        ][:_MAX_RECEIPTS_PER_FOCUS]
                        _write_relationships_unlocked(relationships_after)
                    except NativeFocusTasksError:
                        _restore_memory_unlocked(memory_before)
                        _write_relationships_unlocked(relationships_before)
                        raise
                    except Exception as exc:
                        try:
                            _restore_memory_unlocked(memory_before)
                            _write_relationships_unlocked(relationships_before)
                        except Exception:
                            pass
                        raise NativeFocusTasksError(
                            "write_failed",
                            "QMeet could not persist the Focus task receipt.",
                            status_code=500,
                        ) from exc

                    verification = _verify_tasks(
                        focus_id=focus_id,
                        tasks=selected_tasks,
                        requested_titles=requested_titles,
                        source_turn_id=source_turn_id,
                        receipt_id=receipt_id,
                    )
                    if not _verification_passed(verification):
                        _restore_memory_unlocked(memory_before)
                        _write_relationships_unlocked(relationships_before)
                        _record_health(
                            outcome="failed",
                            focus_id=focus_id,
                            task_ids=task_ids_for_health,
                            source_turn_id=source_turn_id,
                            failure_code="verification_failed",
                        )
                        raise NativeFocusTasksError(
                            "verification_failed",
                            "Canonical state did not verify the Focus task receipt.",
                        )

                    memory_after = memory_store._read_payload_unlocked()
                    outcome: Literal["created", "linked"] = (
                        "created" if created_task_ids else "linked"
                    )
                    telemetry = _record_health(
                        outcome=outcome,
                        focus_id=focus_id,
                        task_ids=task_ids_for_health,
                        source_turn_id=source_turn_id,
                        verified=True,
                    )
                    if outcome == "created":
                        message = (
                            f"Created and linked {len(selected_tasks)} verified task"
                            f"{'s' if len(selected_tasks) != 1 else ''} to {focus_state.title}."
                        )
                    else:
                        message = (
                            f"Linked {len(selected_tasks)} existing verified task"
                            f"{'s' if len(selected_tasks) != 1 else ''} to {focus_state.title}."
                        )
                    return NativeFocusTasksResult(
                        ok=True,
                        outcome=outcome,
                        verified=True,
                        focusId=focus_id,
                        focusTitle=focus_state.title,
                        tasks=_result_tasks(selected_tasks),
                        memoryTasks=_result_tasks(memory_after["tasks"]),
                        createdTaskIds=created_task_ids,
                        receiptId=receipt_id,
                        linkedAt=linked_at,
                        sourceTurnId=source_turn_id,
                        verification=verification,
                        telemetryRecorded=telemetry,
                        message=message,
                    )
    except NativeFocusTasksError as exc:
        if exc.code != "verification_failed":
            _record_health(
                outcome="failed",
                focus_id=focus_id,
                task_ids=task_ids_for_health,
                source_turn_id=source_turn_id,
                failure_code=("write_failed" if exc.code == "write_failed" else exc.code),
            )
        raise
    except Exception as exc:
        _record_health(
            outcome="failed",
            focus_id=focus_id,
            task_ids=task_ids_for_health,
            source_turn_id=source_turn_id,
            failure_code="write_failed",
        )
        raise NativeFocusTasksError(
            "write_failed",
            "QMeet could not create and link the Focus tasks.",
            status_code=500,
        ) from exc
