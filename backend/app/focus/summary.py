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
from app.focus.models import FocusEvent, FocusEventType, FocusStatus


_SUMMARY_SOURCE = "focus-native-summary"
_RELATIONSHIP_LOCK = RLock()
_HEALTH_LOCK = RLock()
_RELATIONSHIP_VERSION = 1
_HEALTH_VERSION = 1


class NativeFocusSummaryNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=140)
    content: str = Field(min_length=1, max_length=2000)
    createdAt: str = Field(min_length=1, max_length=80)

    @field_validator("id", "createdAt")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("value cannot be blank")
        return cleaned

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("content cannot be blank")
        return cleaned


class NativeFocusSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedFocusId: str = Field(min_length=1, max_length=120)
    note: NativeFocusSummaryNote
    sourceTurnId: str = Field(min_length=1, max_length=120)

    @field_validator("expectedFocusId", "sourceTurnId")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("value cannot be blank")
        return cleaned


class NativeFocusSummaryVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activeFocusMatches: bool = False
    notePersisted: bool = False
    relationshipPersisted: bool = False
    sourceTurnUnique: bool = False
    details: list[str] = Field(default_factory=list)


class NativeFocusSummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    operation: Literal["save_focus_summary"] = "save_focus_summary"
    outcome: Literal["saved", "reused"]
    verified: bool
    focusId: str
    focusTitle: str
    summary: str
    note: NativeFocusSummaryNote
    receiptId: str
    sourceTurnId: str
    verification: NativeFocusSummaryVerification
    telemetryRecorded: bool = False
    message: str


class NativeFocusSummaryError(Exception):
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


def _relationship_file() -> Path:
    override = os.getenv("QMEET_FOCUS_RELATIONSHIPS_FILE", "").strip()
    return Path(override) if override else _backend_root() / "data" / "qmeet_focus_relationships.json"


def _health_file() -> Path:
    override = os.getenv("QMEET_FOCUS_SUMMARY_HEALTH_FILE", "").strip()
    return Path(override) if override else _backend_root() / "data" / "qmeet_focus_summary_health.json"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _empty_relationships() -> dict[str, object]:
    return {
        "version": _RELATIONSHIP_VERSION,
        "updatedAt": "",
        "summariesByFocusId": {},
    }


def _empty_health() -> dict[str, object]:
    return {
        "version": _HEALTH_VERSION,
        "updatedAt": "",
        "saveFocusSummary": {
            "attemptCount": 0,
            "savedCount": 0,
            "reusedCount": 0,
            "verifiedCount": 0,
            "failedCount": 0,
            "verificationFailedCount": 0,
            "writeFailedCount": 0,
            "lastOutcome": "",
            "lastFailureCode": "",
            "lastFocusId": "",
            "lastNoteId": "",
            "lastSourceTurnId": "",
            "lastUpdatedAt": "",
        },
    }


def _read_json(path: Path, default: dict[str, object]) -> dict[str, object]:
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise NativeFocusSummaryError(
            "relationship_read_failed",
            "QMeet could not read the Focus summary relationship store.",
            status_code=500,
        ) from exc
    return parsed if isinstance(parsed, dict) else json.loads(json.dumps(default))


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


def _read_relationships_unlocked() -> dict[str, object]:
    document = _read_json(_relationship_file(), _empty_relationships())
    summaries = document.get("summariesByFocusId")
    if not isinstance(summaries, dict):
        document["summariesByFocusId"] = {}
    return document


def _write_relationships_unlocked(document: dict[str, object]) -> None:
    document["version"] = _RELATIONSHIP_VERSION
    document["updatedAt"] = _now_iso()
    _atomic_write_json(_relationship_file(), document)


def _read_health_unlocked() -> dict[str, object]:
    document = _read_json(_health_file(), _empty_health())
    summary = document.get("saveFocusSummary")
    if not isinstance(summary, dict):
        document["saveFocusSummary"] = _empty_health()["saveFocusSummary"]
    return document


def _record_health(
    *,
    outcome: str,
    focus_id: str,
    note_id: str,
    source_turn_id: str,
    failure_code: str = "",
    verified: bool = False,
) -> bool:
    try:
        with _HEALTH_LOCK:
            document = _read_health_unlocked()
            summary = document["saveFocusSummary"]
            assert isinstance(summary, dict)
            summary["attemptCount"] = int(summary.get("attemptCount", 0)) + 1
            if outcome == "saved":
                summary["savedCount"] = int(summary.get("savedCount", 0)) + 1
            elif outcome == "reused":
                summary["reusedCount"] = int(summary.get("reusedCount", 0)) + 1
            elif outcome == "failed":
                summary["failedCount"] = int(summary.get("failedCount", 0)) + 1
            if verified:
                summary["verifiedCount"] = int(summary.get("verifiedCount", 0)) + 1
            if failure_code == "verification_failed":
                summary["verificationFailedCount"] = int(
                    summary.get("verificationFailedCount", 0)
                ) + 1
            if failure_code == "write_failed":
                summary["writeFailedCount"] = int(
                    summary.get("writeFailedCount", 0)
                ) + 1
            summary["lastOutcome"] = outcome
            summary["lastFailureCode"] = failure_code
            summary["lastFocusId"] = focus_id
            summary["lastNoteId"] = note_id
            summary["lastSourceTurnId"] = source_turn_id
            summary["lastUpdatedAt"] = _now_iso()
            document["updatedAt"] = _now_iso()
            _atomic_write_json(_health_file(), document)
        return True
    except Exception:
        return False


def get_native_focus_summary_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        return _read_health_unlocked()


def reset_native_focus_summary_health() -> dict[str, object]:
    with _HEALTH_LOCK:
        document = _empty_health()
        _atomic_write_json(_health_file(), document)
        return document


def _open_focus_ids(events: list[FocusEvent]) -> list[str]:
    open_by_id: dict[str, bool] = {}
    order: list[str] = []
    for event in events:
        focus_id = event.focusId.strip() or str(event.payload.get("focusId", "")).strip()
        if not focus_id:
            continue
        if event.type == FocusEventType.LEGACY_IMPORTED:
            status = str(event.payload.get("status", "active")).strip()
            open_by_id[focus_id] = status not in {
                FocusStatus.INACTIVE.value,
                FocusStatus.COMPLETE.value,
            }
        elif event.type == FocusEventType.FOCUS_STARTED:
            open_by_id[focus_id] = True
        elif event.type in {
            FocusEventType.FOCUS_ENDED,
            FocusEventType.FOCUS_COMPLETED,
        }:
            open_by_id[focus_id] = False
        if focus_id not in order:
            order.append(focus_id)
    return [focus_id for focus_id in order if open_by_id.get(focus_id) is True]


def _relationship_records(document: dict[str, object], focus_id: str) -> list[dict[str, object]]:
    summaries = document.get("summariesByFocusId")
    if not isinstance(summaries, dict):
        return []
    raw_records = summaries.get(focus_id)
    if not isinstance(raw_records, list):
        return []
    return [record for record in raw_records if isinstance(record, dict)]


def _find_source_turn_record(
    document: dict[str, object],
    source_turn_id: str,
) -> tuple[str, dict[str, object]] | None:
    summaries = document.get("summariesByFocusId")
    if not isinstance(summaries, dict):
        return None
    for focus_id, raw_records in summaries.items():
        if not isinstance(focus_id, str) or not isinstance(raw_records, list):
            continue
        for raw_record in raw_records:
            if not isinstance(raw_record, dict):
                continue
            if str(raw_record.get("sourceTurnId", "")).strip() == source_turn_id:
                return focus_id, raw_record
    return None


def _persist_memory_note_unlocked(
    *,
    memory_before: dict,
    note: NativeFocusSummaryNote,
) -> dict:
    existing_note = next(
        (
            item
            for item in memory_before["notes"]
            if str(item.get("id", "")).strip() == note.id
        ),
        None,
    )
    if existing_note is not None:
        if (
            str(existing_note.get("content", "")).strip() != note.content
            or str(existing_note.get("createdAt", "")).strip() != note.createdAt
        ):
            raise NativeFocusSummaryError(
                "note_id_conflict",
                "A different Note already uses the requested summary Note id.",
            )
        return existing_note

    note_payload = note.model_dump(mode="json")
    next_notes = [note_payload, *memory_before["notes"]]
    memory_store._write_payload_unlocked(
        memory_before["tasks"],
        memory_before["recentActions"],
        next_notes,
        memory_before["activeSession"],
        memory_before["recentFocusSessions"],
        memory_before["visualContext"],
        preserve_active_session=False,
        preserve_recent_focus_sessions=False,
        preserve_visual_context=False,
    )
    return note_payload


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


def _verify_summary(
    *,
    focus_id: str,
    note: NativeFocusSummaryNote,
    source_turn_id: str,
    receipt_id: str,
) -> NativeFocusSummaryVerification:
    focus_events = list(focus_store._read_log_unlocked().events)
    focus_state = focus_store.reduce_events(focus_events)
    open_focus_ids = _open_focus_ids(focus_events)
    memory_after = memory_store._read_payload_unlocked()
    relationship_after = _read_relationships_unlocked()

    active_focus_matches = (
        focus_state.focusId == focus_id
        and focus_state.status not in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
        and open_focus_ids == [focus_id]
    )
    note_persisted = any(
        str(item.get("id", "")).strip() == note.id
        and str(item.get("content", "")).strip() == note.content
        and str(item.get("createdAt", "")).strip() == note.createdAt
        for item in memory_after["notes"]
    )
    matching_records = [
        record
        for record in _relationship_records(relationship_after, focus_id)
        if str(record.get("receiptId", "")).strip() == receipt_id
        and str(record.get("noteId", "")).strip() == note.id
        and str(record.get("contentHash", "")).strip() == _content_hash(note.content)
        and str(record.get("sourceTurnId", "")).strip() == source_turn_id
    ]
    relationship_persisted = len(matching_records) == 1
    all_turn_matches: list[tuple[str, dict[str, object]]] = []
    summaries = relationship_after.get("summariesByFocusId")
    if isinstance(summaries, dict):
        for candidate_focus_id, raw_records in summaries.items():
            if not isinstance(raw_records, list):
                continue
            for raw_record in raw_records:
                if (
                    isinstance(raw_record, dict)
                    and str(raw_record.get("sourceTurnId", "")).strip()
                    == source_turn_id
                ):
                    all_turn_matches.append((str(candidate_focus_id), raw_record))
    source_turn_unique = len(all_turn_matches) == 1

    details: list[str] = []
    if not active_focus_matches:
        details.append("The expected Focus is not the sole current canonical Focus.")
    if not note_persisted:
        details.append("The summary Note was not persisted exactly.")
    if not relationship_persisted:
        details.append("The Focus summary relationship was not persisted exactly.")
    if not source_turn_unique:
        details.append("The source turn does not identify exactly one summary receipt.")

    return NativeFocusSummaryVerification(
        activeFocusMatches=active_focus_matches,
        notePersisted=note_persisted,
        relationshipPersisted=relationship_persisted,
        sourceTurnUnique=source_turn_unique,
        details=details,
    )


def _verification_passed(verification: NativeFocusSummaryVerification) -> bool:
    return (
        verification.activeFocusMatches
        and verification.notePersisted
        and verification.relationshipPersisted
        and verification.sourceTurnUnique
    )


def save_focus_summary_verified(
    request: NativeFocusSummaryRequest,
) -> NativeFocusSummaryResult:
    focus_id = request.expectedFocusId.strip()
    source_turn_id = request.sourceTurnId.strip()
    note = request.note
    content_hash = _content_hash(note.content)

    try:
        with focus_store._STORE_LOCK:
            focus_document = focus_store._read_log_unlocked()
            focus_state = focus_store.reduce_events(list(focus_document.events))
            if (
                focus_state.focusId != focus_id
                or focus_state.status in {FocusStatus.INACTIVE, FocusStatus.COMPLETE}
                or _open_focus_ids(list(focus_document.events)) != [focus_id]
            ):
                raise NativeFocusSummaryError(
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
                            and str(existing_record.get("noteId", "")).strip()
                            == note.id
                            and str(existing_record.get("contentHash", "")).strip()
                            == content_hash
                        )
                        if not same_request:
                            raise NativeFocusSummaryError(
                                "source_turn_conflict",
                                "This source turn already belongs to a different Focus summary receipt.",
                            )
                        receipt_id = str(existing_record.get("receiptId", "")).strip()
                        verification = _verify_summary(
                            focus_id=focus_id,
                            note=note,
                            source_turn_id=source_turn_id,
                            receipt_id=receipt_id,
                        )
                        if not _verification_passed(verification):
                            raise NativeFocusSummaryError(
                                "verification_failed",
                                "The existing Focus summary receipt did not verify canonically.",
                            )
                        telemetry = _record_health(
                            outcome="reused",
                            focus_id=focus_id,
                            note_id=note.id,
                            source_turn_id=source_turn_id,
                            verified=True,
                        )
                        return NativeFocusSummaryResult(
                            ok=True,
                            outcome="reused",
                            verified=True,
                            focusId=focus_id,
                            focusTitle=focus_state.title,
                            summary=note.content,
                            note=note,
                            receiptId=receipt_id,
                            sourceTurnId=source_turn_id,
                            verification=verification,
                            telemetryRecorded=telemetry,
                            message=f"Focus summary is already saved for {focus_state.title}.",
                        )

                    receipt_id = f"focus-summary-{hashlib.sha256(f'{focus_id}:{source_turn_id}:{note.id}'.encode('utf-8')).hexdigest()[:24]}"
                    attachment = {
                        "receiptId": receipt_id,
                        "focusId": focus_id,
                        "noteId": note.id,
                        "contentHash": content_hash,
                        "createdAt": note.createdAt,
                        "sourceTurnId": source_turn_id,
                        "source": _SUMMARY_SOURCE,
                    }

                    try:
                        _persist_memory_note_unlocked(
                            memory_before=memory_before,
                            note=note,
                        )
                        relationships_after = json.loads(
                            json.dumps(relationships_before)
                        )
                        summaries = relationships_after.setdefault(
                            "summariesByFocusId",
                            {},
                        )
                        if not isinstance(summaries, dict):
                            summaries = {}
                            relationships_after["summariesByFocusId"] = summaries
                        records = _relationship_records(relationships_after, focus_id)
                        summaries[focus_id] = [attachment, *records][:24]
                        _write_relationships_unlocked(relationships_after)
                    except NativeFocusSummaryError:
                        _restore_memory_unlocked(memory_before)
                        _write_relationships_unlocked(relationships_before)
                        raise
                    except Exception as exc:
                        try:
                            _restore_memory_unlocked(memory_before)
                            _write_relationships_unlocked(relationships_before)
                        except Exception:
                            pass
                        raise NativeFocusSummaryError(
                            "write_failed",
                            "QMeet could not persist the Focus summary receipt.",
                            status_code=500,
                        ) from exc

                    verification = _verify_summary(
                        focus_id=focus_id,
                        note=note,
                        source_turn_id=source_turn_id,
                        receipt_id=receipt_id,
                    )
                    if not _verification_passed(verification):
                        _restore_memory_unlocked(memory_before)
                        _write_relationships_unlocked(relationships_before)
                        _record_health(
                            outcome="failed",
                            focus_id=focus_id,
                            note_id=note.id,
                            source_turn_id=source_turn_id,
                            failure_code="verification_failed",
                        )
                        raise NativeFocusSummaryError(
                            "verification_failed",
                            "Canonical state did not verify the Focus summary receipt.",
                        )

                    telemetry = _record_health(
                        outcome="saved",
                        focus_id=focus_id,
                        note_id=note.id,
                        source_turn_id=source_turn_id,
                        verified=True,
                    )
                    return NativeFocusSummaryResult(
                        ok=True,
                        outcome="saved",
                        verified=True,
                        focusId=focus_id,
                        focusTitle=focus_state.title,
                        summary=note.content,
                        note=note,
                        receiptId=receipt_id,
                        sourceTurnId=source_turn_id,
                        verification=verification,
                        telemetryRecorded=telemetry,
                        message=f"Saved Focus summary as a Note for {focus_state.title}.",
                    )
    except NativeFocusSummaryError as exc:
        if exc.code not in {"verification_failed"}:
            _record_health(
                outcome="failed",
                focus_id=focus_id,
                note_id=note.id,
                source_turn_id=source_turn_id,
                failure_code=("write_failed" if exc.code == "write_failed" else exc.code),
            )
        raise
    except Exception as exc:
        _record_health(
            outcome="failed",
            focus_id=focus_id,
            note_id=note.id,
            source_turn_id=source_turn_id,
            failure_code="write_failed",
        )
        raise NativeFocusSummaryError(
            "write_failed",
            "QMeet could not save the Focus summary.",
            status_code=500,
        ) from exc
