from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4


MEMORY_FILE_VERSION = 6
SESSION_MODES = {"general", "coding", "meeting", "planning", "research", "personal"}
_STORE_LOCK = RLock()


class MemoryStoreError(Exception):
    """Safe memory-store error that can be shown in the UI."""


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _memory_file() -> Path:
    return _backend_root() / "data" / "qmeet_memory.json"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _new_task_id() -> str:
    return f"task-{int(datetime.now().timestamp() * 1000)}-{uuid4().hex[:10]}"


def _new_action_id() -> str:
    return f"action-{int(datetime.now().timestamp() * 1000)}-{uuid4().hex[:10]}"


def _new_note_id() -> str:
    return f"note-{int(datetime.now().timestamp() * 1000)}-{uuid4().hex[:10]}"


def _new_session_id() -> str:
    return f"session-{int(datetime.now().timestamp() * 1000)}-{uuid4().hex[:10]}"


def _empty_payload() -> dict:
    return {
        "tasks": [],
        "recentActions": [],
        "notes": [],
        "activeSession": None,
        "recentFocusSessions": [],
    }


def _coerce_string_list(raw: object, max_items: int = 24) -> list[str]:
    if not isinstance(raw, list):
        return []

    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        values.append(value[:140])
        seen.add(value)
        if len(values) >= max_items:
            break
    return values


def _sanitize_task(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None

    title = str(raw.get("title", "")).strip()
    if not title:
        return None

    created_at = str(raw.get("createdAt") or raw.get("created_at") or "").strip()
    if not created_at:
        created_at = _now_iso()

    task = {
        "id": str(raw.get("id") or _new_task_id()).strip() or _new_task_id(),
        "title": title,
        "createdAt": created_at,
    }

    completed_at = raw.get("completedAt", raw.get("completed_at"))
    if isinstance(completed_at, str) and completed_at.strip():
        task["completedAt"] = completed_at.strip()

    return task


def _sanitize_action(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None

    label = str(raw.get("label", "")).strip()
    if not label:
        return None

    detail = str(raw.get("detail", "")).strip()
    created_at = str(raw.get("createdAt") or raw.get("created_at") or "").strip()
    if not created_at:
        created_at = _now_iso()

    return {
        "id": str(raw.get("id") or _new_action_id()).strip() or _new_action_id(),
        "label": label[:80],
        "detail": detail[:180],
        "createdAt": created_at,
    }


def _sanitize_note(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None

    content = str(raw.get("content", "")).strip()
    if not content:
        return None

    created_at = str(raw.get("createdAt") or raw.get("created_at") or "").strip()
    if not created_at:
        created_at = _now_iso()

    return {
        "id": str(raw.get("id") or _new_note_id()).strip() or _new_note_id(),
        "content": content[:2000],
        "createdAt": created_at,
    }


def _sanitize_active_session(raw: object) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None

    title = str(raw.get("title", "")).strip()
    goal = str(raw.get("goal", "")).strip()
    if not title and not goal:
        return None

    now = _now_iso()
    raw_mode = str(raw.get("mode") or "general").strip().lower()
    mode = raw_mode if raw_mode in SESSION_MODES else "general"
    started_at = str(raw.get("startedAt") or raw.get("started_at") or "").strip() or now
    updated_at = str(raw.get("updatedAt") or raw.get("updated_at") or "").strip() or now

    session = {
        "id": str(raw.get("id") or _new_session_id()).strip() or _new_session_id(),
        "title": title[:120] or goal[:120] or "Focus session",
        "mode": mode,
        "goal": goal[:500],
        "startedAt": started_at,
        "updatedAt": updated_at,
        "pinnedNoteIds": _coerce_string_list(
            raw.get("pinnedNoteIds", raw.get("pinned_note_ids", [])),
            max_items=24,
        ),
        "linkedTaskIds": _coerce_string_list(
            raw.get("linkedTaskIds", raw.get("linked_task_ids", [])),
            max_items=24,
        ),
    }

    summary = str(raw.get("summary", "")).strip()
    if summary:
        session["summary"] = summary[:2000]

    return session



def _sanitize_recent_focus_session(raw: object) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None

    title = str(raw.get("title", "")).strip()
    goal = str(raw.get("goal", "")).strip()
    if not title and not goal:
        return None

    now = _now_iso()
    raw_mode = str(raw.get("mode") or "general").strip().lower()
    mode = raw_mode if raw_mode in SESSION_MODES else "general"
    started_at = str(raw.get("startedAt") or raw.get("started_at") or "").strip() or now
    ended_at = (
        str(raw.get("endedAt") or raw.get("ended_at") or raw.get("updatedAt") or raw.get("updated_at") or "").strip()
        or now
    )

    pinned_note_ids = _coerce_string_list(
        raw.get("pinnedNoteIds", raw.get("pinned_note_ids", [])),
        max_items=24,
    )
    linked_task_ids = _coerce_string_list(
        raw.get("linkedTaskIds", raw.get("linked_task_ids", [])),
        max_items=24,
    )

    session = {
        "id": str(raw.get("id") or _new_session_id()).strip() or _new_session_id(),
        "title": title[:120] or goal[:120] or "Focus session",
        "mode": mode,
        "goal": goal[:500],
        "startedAt": started_at,
        "endedAt": ended_at,
        "pinnedNoteIds": pinned_note_ids,
        "linkedTaskIds": linked_task_ids,
    }

    summary = str(raw.get("summary", "")).strip()
    if summary:
        session["summary"] = summary[:2000]

    summary_note_id = str(raw.get("summaryNoteId", raw.get("summary_note_id", ""))).strip()
    if summary_note_id:
        session["summaryNoteId"] = summary_note_id[:140]
    elif pinned_note_ids:
        session["summaryNoteId"] = pinned_note_ids[0]

    return session


def _sanitize_recent_focus_sessions(raw: object, max_items: int = 24) -> list[dict]:
    if not isinstance(raw, list):
        return []

    sessions: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        session = _sanitize_recent_focus_session(item)
        if not session:
            continue
        session_id = session["id"]
        if session_id in seen:
            continue
        sessions.append(session)
        seen.add(session_id)
        if len(sessions) >= max_items:
            break
    return sessions


def _archive_active_session(
    active_session: dict | None,
    recent_focus_sessions: list[dict],
    ended_at: str | None = None,
) -> list[dict]:
    clean_active_session = _sanitize_active_session(active_session)
    if not clean_active_session:
        return _sanitize_recent_focus_sessions(recent_focus_sessions)

    ended_at = ended_at or _now_iso()
    archived = _sanitize_recent_focus_session({**clean_active_session, "endedAt": ended_at})
    if not archived:
        return _sanitize_recent_focus_sessions(recent_focus_sessions)

    existing = _sanitize_recent_focus_sessions(recent_focus_sessions)
    next_sessions = [archived]
    next_sessions.extend(session for session in existing if session["id"] != archived["id"])
    return next_sessions[:24]


def _read_payload_unlocked() -> dict:
    path = _memory_file()
    if not path.exists():
        return _empty_payload()

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MemoryStoreError(f"QMeet memory file is invalid JSON: {path}") from exc
    except Exception as exc:
        raise MemoryStoreError("QMeet could not read the memory file.") from exc

    if not isinstance(parsed, dict):
        return _empty_payload()

    tasks = parsed.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []

    recent_actions = parsed.get("recentActions", parsed.get("recent_actions", []))
    if not isinstance(recent_actions, list):
        recent_actions = []

    notes = parsed.get("notes", [])
    if not isinstance(notes, list):
        notes = []

    active_session = parsed.get("activeSession", parsed.get("active_session"))

    recent_focus_sessions = parsed.get(
        "recentFocusSessions",
        parsed.get("recent_focus_sessions", []),
    )

    return {
        "tasks": [_task for _task in (_sanitize_task(task) for task in tasks) if _task],
        "recentActions": [
            _action
            for _action in (_sanitize_action(action) for action in recent_actions)
            if _action
        ][:24],
        "notes": [_note for _note in (_sanitize_note(note) for note in notes) if _note],
        "activeSession": _sanitize_active_session(active_session),
        "recentFocusSessions": _sanitize_recent_focus_sessions(recent_focus_sessions),
    }


def _read_payload() -> dict:
    with _STORE_LOCK:
        return _read_payload_unlocked()


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON by replacing the old file in one filesystem operation."""

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


def _build_payload(
    tasks: list[dict],
    recent_actions: list[dict],
    notes: list[dict],
    active_session: dict | None = None,
    recent_focus_sessions: list[dict] | None = None,
) -> dict:
    return {
        "version": MEMORY_FILE_VERSION,
        "updatedAt": _now_iso(),
        "tasks": [_task for _task in (_sanitize_task(task) for task in tasks) if _task],
        "recentActions": [
            _action
            for _action in (_sanitize_action(action) for action in recent_actions)
            if _action
        ][:24],
        "notes": [_note for _note in (_sanitize_note(note) for note in notes) if _note],
        "activeSession": _sanitize_active_session(active_session),
        "recentFocusSessions": _sanitize_recent_focus_sessions(recent_focus_sessions or []),
    }


def _write_payload_unlocked(
    tasks: list[dict],
    recent_actions: list[dict] | None = None,
    notes: list[dict] | None = None,
    active_session: dict | None = None,
    recent_focus_sessions: list[dict] | None = None,
    preserve_active_session: bool = True,
    preserve_recent_focus_sessions: bool = True,
) -> dict:
    existing_payload: dict | None = None
    if (
        recent_actions is None
        or notes is None
        or preserve_active_session
        or preserve_recent_focus_sessions
    ):
        existing_payload = _read_payload_unlocked()

    if recent_actions is None:
        recent_actions = existing_payload["recentActions"] if existing_payload else []

    if notes is None:
        notes = existing_payload["notes"] if existing_payload else []

    if preserve_active_session and active_session is None:
        active_session = existing_payload["activeSession"] if existing_payload else None

    if preserve_recent_focus_sessions and recent_focus_sessions is None:
        recent_focus_sessions = existing_payload["recentFocusSessions"] if existing_payload else []

    payload = _build_payload(
        tasks,
        recent_actions,
        notes,
        active_session,
        recent_focus_sessions,
    )

    try:
        _atomic_write_json(_memory_file(), payload)
    except MemoryStoreError:
        raise
    except Exception as exc:
        raise MemoryStoreError("QMeet could not write the memory file.") from exc

    return payload


def _write_payload(
    tasks: list[dict],
    recent_actions: list[dict] | None = None,
    notes: list[dict] | None = None,
    active_session: dict | None = None,
    recent_focus_sessions: list[dict] | None = None,
    preserve_active_session: bool = True,
    preserve_recent_focus_sessions: bool = True,
) -> dict:
    with _STORE_LOCK:
        return _write_payload_unlocked(
            tasks,
            recent_actions,
            notes,
            active_session,
            recent_focus_sessions,
            preserve_active_session=preserve_active_session,
            preserve_recent_focus_sessions=preserve_recent_focus_sessions,
        )


def get_memory_status() -> dict:
    with _STORE_LOCK:
        payload = _read_payload_unlocked()
        tasks = payload["tasks"]
        completed_count = sum(1 for task in tasks if task.get("completedAt"))
        active_session = payload["activeSession"]

        return {
            "ok": True,
            "provider": "local-json",
            "configured": True,
            "path": str(_memory_file()),
            "taskCount": len(tasks),
            "completedCount": completed_count,
            "actionCount": len(payload["recentActions"]),
            "noteCount": len(payload["notes"]),
            "activeSessionSet": active_session is not None,
            "activeSessionTitle": active_session.get("title", "") if active_session else "",
            "recentFocusSessionCount": len(payload["recentFocusSessions"]),
            "lastFocusSessionTitle": payload["recentFocusSessions"][0].get("title", "")
            if payload["recentFocusSessions"]
            else "",
            "message": "QMeet memory, notes, work context, active session, and recent focus history are stored in a local backend JSON file.",
        }


def get_memory_context() -> dict:
    with _STORE_LOCK:
        payload = _read_payload_unlocked()
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": payload["tasks"],
            "recentActions": payload["recentActions"],
            "notes": payload["notes"],
            "activeSession": payload["activeSession"],
            "recentFocusSessions": payload["recentFocusSessions"],
            "message": "Memory context loaded from the backend.",
        }


def replace_memory_context(
    tasks: list[dict],
    recent_actions: list[dict],
    notes: list[dict],
    active_session: dict | None = None,
    recent_focus_sessions: list[dict] | None = None,
) -> dict:
    """Replace the frontend-owned memory context without losing focus history.

    The React memory hook saves the whole task/action/note/activeSession context on a
    debounce, but it does not yet own recentFocusSessions. Phase 13D v1 archived a
    session when DELETE /api/memory/session was called, then the next debounced
    /api/memory/context save could immediately overwrite recentFocusSessions with [].

    Treat omitted recent_focus_sessions as backend-owned state to preserve. If an
    existing active session transitions to None through this context save, archive it
    here too, so every clear path records history.
    """

    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        next_recent_focus_sessions = (
            existing["recentFocusSessions"]
            if recent_focus_sessions is None
            else recent_focus_sessions
        )

        if existing["activeSession"] is not None and active_session is None:
            next_recent_focus_sessions = _archive_active_session(
                existing["activeSession"],
                next_recent_focus_sessions,
            )

        payload = _write_payload_unlocked(
            tasks,
            recent_actions,
            notes,
            active_session,
            next_recent_focus_sessions,
            preserve_active_session=False,
            preserve_recent_focus_sessions=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": payload["tasks"],
            "recentActions": payload["recentActions"],
            "notes": payload["notes"],
            "activeSession": payload["activeSession"],
            "recentFocusSessions": payload["recentFocusSessions"],
            "message": "Memory context saved to the backend.",
        }


def list_memory_tasks() -> dict:
    with _STORE_LOCK:
        payload = _read_payload_unlocked()
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": payload["tasks"],
            "message": "Memory tasks loaded from the backend.",
        }


def replace_memory_tasks(tasks: list[dict]) -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        payload = _write_payload_unlocked(
            tasks,
            existing["recentActions"],
            existing["notes"],
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": payload["tasks"],
            "message": "Memory tasks saved to the backend.",
        }


def create_memory_task(title: str) -> dict:
    clean_title = (title or "").strip()
    if not clean_title:
        raise MemoryStoreError("Task title cannot be empty.")

    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        task = {
            "id": _new_task_id(),
            "title": clean_title,
            "createdAt": _now_iso(),
        }
        tasks = [task, *existing["tasks"]]
        payload = _write_payload_unlocked(
            tasks,
            existing["recentActions"],
            existing["notes"],
            existing["activeSession"],
            preserve_active_session=False,
        )

        return {
            "ok": True,
            "provider": "local-json",
            "tasks": payload["tasks"],
            "message": f"Saved task: {clean_title}.",
        }


def update_memory_task(
    task_id: str,
    title: str = "",
    completed_at: str | None = None,
    update_completed_at: bool = True,
) -> dict:
    clean_task_id = (task_id or "").strip()
    if not clean_task_id:
        raise MemoryStoreError("Task id cannot be empty.")

    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        found = False
        updated_tasks: list[dict] = []

        for task in existing["tasks"]:
            if task["id"] != clean_task_id:
                updated_tasks.append(task)
                continue

            found = True
            updated_task = dict(task)
            clean_title = (title or "").strip()
            if clean_title:
                updated_task["title"] = clean_title

            if update_completed_at:
                if completed_at is None:
                    updated_task.pop("completedAt", None)
                elif isinstance(completed_at, str):
                    clean_completed_at = completed_at.strip()
                    if clean_completed_at:
                        updated_task["completedAt"] = clean_completed_at
                    else:
                        updated_task.pop("completedAt", None)

            updated_tasks.append(updated_task)

        if not found:
            raise MemoryStoreError("Memory task was not found.")

        payload = _write_payload_unlocked(
            updated_tasks,
            existing["recentActions"],
            existing["notes"],
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": payload["tasks"],
            "message": "Memory task updated.",
        }


def delete_memory_task(task_id: str) -> dict:
    clean_task_id = (task_id or "").strip()
    if not clean_task_id:
        raise MemoryStoreError("Task id cannot be empty.")

    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        next_tasks = [task for task in existing["tasks"] if task["id"] != clean_task_id]
        if len(next_tasks) == len(existing["tasks"]):
            raise MemoryStoreError("Memory task was not found.")

        _write_payload_unlocked(
            next_tasks,
            existing["recentActions"],
            existing["notes"],
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "deletedTaskId": clean_task_id,
            "message": "Memory task deleted.",
        }


def clear_completed_memory_tasks() -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        next_tasks = [task for task in existing["tasks"] if not task.get("completedAt")]
        removed_count = len(existing["tasks"]) - len(next_tasks)
        payload = _write_payload_unlocked(
            next_tasks,
            existing["recentActions"],
            existing["notes"],
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "removedCount": removed_count,
            "tasks": payload["tasks"],
            "message": f"Cleared {removed_count} completed task{'s' if removed_count != 1 else ''}.",
        }


def list_recent_actions() -> dict:
    with _STORE_LOCK:
        payload = _read_payload_unlocked()
        return {
            "ok": True,
            "provider": "local-json",
            "recentActions": payload["recentActions"],
            "message": "Recent actions loaded from the backend.",
        }


def replace_recent_actions(recent_actions: list[dict]) -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        payload = _write_payload_unlocked(
            existing["tasks"],
            recent_actions,
            existing["notes"],
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "recentActions": payload["recentActions"],
            "message": "Recent actions saved to the backend.",
        }


def create_recent_action(label: str, detail: str = "") -> dict:
    clean_label = (label or "").strip()
    if not clean_label:
        raise MemoryStoreError("Recent action label cannot be empty.")

    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        action = _sanitize_action(
            {
                "id": _new_action_id(),
                "label": clean_label,
                "detail": detail or "",
                "createdAt": _now_iso(),
            }
        )
        if not action:
            raise MemoryStoreError("Recent action could not be saved.")

        next_actions = [action, *existing["recentActions"]][:24]
        payload = _write_payload_unlocked(
            existing["tasks"],
            next_actions,
            existing["notes"],
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "recentActions": payload["recentActions"],
            "message": "Recent action saved.",
        }


def delete_recent_action(action_id: str) -> dict:
    clean_action_id = (action_id or "").strip()
    if not clean_action_id:
        raise MemoryStoreError("Recent action id cannot be empty.")

    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        next_actions = [
            action for action in existing["recentActions"] if action["id"] != clean_action_id
        ]
        if len(next_actions) == len(existing["recentActions"]):
            raise MemoryStoreError("Recent action was not found.")

        _write_payload_unlocked(
            existing["tasks"],
            next_actions,
            existing["notes"],
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "deletedActionId": clean_action_id,
            "message": "Recent action deleted.",
        }


def clear_recent_actions() -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        removed_count = len(existing["recentActions"])
        _write_payload_unlocked(
            existing["tasks"],
            [],
            existing["notes"],
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "removedCount": removed_count,
            "recentActions": [],
            "message": f"Cleared {removed_count} recent action{'s' if removed_count != 1 else ''}.",
        }


def list_memory_notes() -> dict:
    with _STORE_LOCK:
        payload = _read_payload_unlocked()
        return {
            "ok": True,
            "provider": "local-json",
            "notes": payload["notes"],
            "message": "Memory notes loaded from the backend.",
        }


def replace_memory_notes(notes: list[dict]) -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        payload = _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            notes,
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "notes": payload["notes"],
            "message": "Memory notes saved to the backend.",
        }


def create_memory_note(content: str) -> dict:
    clean_content = (content or "").strip()
    if not clean_content:
        raise MemoryStoreError("Note content cannot be empty.")

    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        note = {
            "id": _new_note_id(),
            "content": clean_content[:2000],
            "createdAt": _now_iso(),
        }
        notes = [note, *existing["notes"]]
        payload = _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            notes,
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "notes": payload["notes"],
            "message": "Saved note to backend memory.",
        }


def delete_memory_note(note_id: str) -> dict:
    clean_note_id = (note_id or "").strip()
    if not clean_note_id:
        raise MemoryStoreError("Note id cannot be empty.")

    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        next_notes = [note for note in existing["notes"] if note["id"] != clean_note_id]
        if len(next_notes) == len(existing["notes"]):
            raise MemoryStoreError("Memory note was not found.")

        _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            next_notes,
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "deletedNoteId": clean_note_id,
            "message": "Memory note deleted.",
        }


def clear_memory_notes() -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        removed_count = len(existing["notes"])
        _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            [],
            existing["activeSession"],
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "removedCount": removed_count,
            "notes": [],
            "message": f"Cleared {removed_count} note{'s' if removed_count != 1 else ''}.",
        }


def get_active_session() -> dict:
    with _STORE_LOCK:
        payload = _read_payload_unlocked()
        return {
            "ok": True,
            "provider": "local-json",
            "activeSession": payload["activeSession"],
            "message": "Active session loaded from backend memory.",
        }


def replace_active_session(active_session: dict | None) -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        next_session = _sanitize_active_session(active_session)
        next_recent_focus_sessions = existing["recentFocusSessions"]

        if existing["activeSession"] is not None and next_session is None:
            next_recent_focus_sessions = _archive_active_session(
                existing["activeSession"],
                next_recent_focus_sessions,
            )

        payload = _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            existing["notes"],
            next_session,
            next_recent_focus_sessions,
            preserve_active_session=False,
            preserve_recent_focus_sessions=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "activeSession": payload["activeSession"],
            "recentFocusSessions": payload["recentFocusSessions"],
            "message": "Active session saved to backend memory."
            if payload["activeSession"]
            else "Active session archived and cleared from backend memory.",
        }


def update_active_session(
    title: str | None = None,
    mode: str | None = None,
    goal: str | None = None,
    pinned_note_ids: list[str] | None = None,
    linked_task_ids: list[str] | None = None,
    summary: str | None = None,
    update_summary: bool = False,
) -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        active_session = dict(existing["activeSession"] or {})
        if not active_session:
            active_session = {
                "id": _new_session_id(),
                "title": "Focus session",
                "mode": "general",
                "goal": "",
                "startedAt": _now_iso(),
                "pinnedNoteIds": [],
                "linkedTaskIds": [],
            }

        if title is not None:
            clean_title = title.strip()
            if clean_title:
                active_session["title"] = clean_title[:120]

        if mode is not None:
            clean_mode = mode.strip().lower()
            if clean_mode in SESSION_MODES:
                active_session["mode"] = clean_mode

        if goal is not None:
            active_session["goal"] = goal.strip()[:500]

        if pinned_note_ids is not None:
            active_session["pinnedNoteIds"] = _coerce_string_list(pinned_note_ids, max_items=24)

        if linked_task_ids is not None:
            active_session["linkedTaskIds"] = _coerce_string_list(linked_task_ids, max_items=24)

        if update_summary:
            clean_summary = (summary or "").strip()
            if clean_summary:
                active_session["summary"] = clean_summary[:2000]
            else:
                active_session.pop("summary", None)

        active_session["updatedAt"] = _now_iso()
        clean_session = _sanitize_active_session(active_session)
        if not clean_session:
            raise MemoryStoreError("Active session title or goal cannot be empty.")

        payload = _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            existing["notes"],
            clean_session,
            preserve_active_session=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "activeSession": payload["activeSession"],
            "message": "Active session updated in backend memory.",
        }


def clear_active_session() -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        had_session = existing["activeSession"] is not None
        next_recent_focus_sessions = _archive_active_session(
            existing["activeSession"],
            existing["recentFocusSessions"],
        )
        payload = _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            existing["notes"],
            None,
            next_recent_focus_sessions,
            preserve_active_session=False,
            preserve_recent_focus_sessions=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "activeSession": None,
            "recentFocusSessions": payload["recentFocusSessions"],
            "archivedFocusSession": payload["recentFocusSessions"][0] if had_session and payload["recentFocusSessions"] else None,
            "removedActiveSession": had_session,
            "message": "Active session archived and cleared from backend memory."
            if had_session
            else "No active session was set.",
        }


def list_recent_focus_sessions() -> dict:
    with _STORE_LOCK:
        payload = _read_payload_unlocked()
        return {
            "ok": True,
            "provider": "local-json",
            "recentFocusSessions": payload["recentFocusSessions"],
            "message": "Recent focus sessions loaded from backend memory.",
        }


def replace_recent_focus_sessions(recent_focus_sessions: list[dict]) -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        payload = _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            existing["notes"],
            existing["activeSession"],
            recent_focus_sessions,
            preserve_active_session=False,
            preserve_recent_focus_sessions=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "recentFocusSessions": payload["recentFocusSessions"],
            "message": "Recent focus sessions saved to backend memory.",
        }


def delete_recent_focus_session(session_id: str) -> dict:
    clean_session_id = (session_id or "").strip()
    if not clean_session_id:
        raise MemoryStoreError("Recent focus session id cannot be empty.")

    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        next_sessions = [
            session
            for session in existing["recentFocusSessions"]
            if session["id"] != clean_session_id
        ]
        if len(next_sessions) == len(existing["recentFocusSessions"]):
            raise MemoryStoreError("Recent focus session was not found.")

        _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            existing["notes"],
            existing["activeSession"],
            next_sessions,
            preserve_active_session=False,
            preserve_recent_focus_sessions=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "deletedRecentFocusSessionId": clean_session_id,
            "message": "Recent focus session deleted.",
        }


def clear_recent_focus_sessions() -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        removed_count = len(existing["recentFocusSessions"])
        _write_payload_unlocked(
            existing["tasks"],
            existing["recentActions"],
            existing["notes"],
            existing["activeSession"],
            [],
            preserve_active_session=False,
            preserve_recent_focus_sessions=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "removedCount": removed_count,
            "recentFocusSessions": [],
            "message": f"Cleared {removed_count} recent focus session{'s' if removed_count != 1 else ''}.",
        }


def clear_memory_context() -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        removed_tasks = len(existing["tasks"])
        removed_actions = len(existing["recentActions"])
        removed_notes = len(existing["notes"])
        removed_session = existing["activeSession"] is not None
        removed_focus_sessions = len(existing["recentFocusSessions"])
        _write_payload_unlocked(
            [],
            [],
            [],
            None,
            [],
            preserve_active_session=False,
            preserve_recent_focus_sessions=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": [],
            "recentActions": [],
            "notes": [],
            "activeSession": None,
            "recentFocusSessions": [],
            "removedTaskCount": removed_tasks,
            "removedActionCount": removed_actions,
            "removedNoteCount": removed_notes,
            "removedActiveSession": removed_session,
            "removedRecentFocusSessionCount": removed_focus_sessions,
            "message": "Cleared all backend memory, notes, work context, active session, and focus history.",
        }


def export_memory_context() -> dict:
    with _STORE_LOCK:
        payload = _read_payload_unlocked()
        return {
            "ok": True,
            "provider": "local-json",
            "version": MEMORY_FILE_VERSION,
            "exportedAt": _now_iso(),
            "tasks": payload["tasks"],
            "recentActions": payload["recentActions"],
            "notes": payload["notes"],
            "activeSession": payload["activeSession"],
            "recentFocusSessions": payload["recentFocusSessions"],
            "message": "Memory export loaded from the backend.",
        }


def import_memory_context(
    tasks: list[dict],
    recent_actions: list[dict],
    notes: list[dict],
    active_session: dict | None = None,
    recent_focus_sessions: list[dict] | None = None,
) -> dict:
    with _STORE_LOCK:
        payload = _write_payload_unlocked(
            tasks,
            recent_actions,
            notes,
            active_session,
            recent_focus_sessions,
            preserve_active_session=False,
            preserve_recent_focus_sessions=False,
        )
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": payload["tasks"],
            "recentActions": payload["recentActions"],
            "notes": payload["notes"],
            "activeSession": payload["activeSession"],
            "recentFocusSessions": payload["recentFocusSessions"],
            "message": "Imported memory, notes, work context, active session, and focus history into the backend.",
        }
