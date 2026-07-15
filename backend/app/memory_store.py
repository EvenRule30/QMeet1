from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4


MEMORY_FILE_VERSION = 4
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


def _empty_payload() -> dict:
    return {"tasks": [], "recentActions": [], "notes": []}


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

    return {
        "tasks": [_task for _task in (_sanitize_task(task) for task in tasks) if _task],
        "recentActions": [
            _action
            for _action in (_sanitize_action(action) for action in recent_actions)
            if _action
        ][:24],
        "notes": [_note for _note in (_sanitize_note(note) for note in notes) if _note],
    }


def _read_payload() -> dict:
    with _STORE_LOCK:
        return _read_payload_unlocked()


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON by replacing the old file in one filesystem operation.

    This avoids leaving qmeet_memory.json truncated or half-written if the backend
    process is interrupted while a save is in progress.
    """

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
    }


def _write_payload_unlocked(
    tasks: list[dict],
    recent_actions: list[dict] | None = None,
    notes: list[dict] | None = None,
) -> dict:
    existing_payload: dict | None = None
    if recent_actions is None or notes is None:
        existing_payload = _read_payload_unlocked()

    if recent_actions is None:
        recent_actions = existing_payload["recentActions"] if existing_payload else []

    if notes is None:
        notes = existing_payload["notes"] if existing_payload else []

    payload = _build_payload(tasks, recent_actions, notes)

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
) -> dict:
    with _STORE_LOCK:
        return _write_payload_unlocked(tasks, recent_actions, notes)


def get_memory_status() -> dict:
    with _STORE_LOCK:
        payload = _read_payload_unlocked()
        tasks = payload["tasks"]
        completed_count = sum(1 for task in tasks if task.get("completedAt"))

        return {
            "ok": True,
            "provider": "local-json",
            "configured": True,
            "path": str(_memory_file()),
            "taskCount": len(tasks),
            "completedCount": completed_count,
            "actionCount": len(payload["recentActions"]),
            "noteCount": len(payload["notes"]),
            "message": "QMeet memory, notes, and work context are stored in a local backend JSON file.",
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
            "message": "Memory context loaded from the backend.",
        }


def replace_memory_context(tasks: list[dict], recent_actions: list[dict], notes: list[dict]) -> dict:
    with _STORE_LOCK:
        payload = _write_payload_unlocked(tasks, recent_actions, notes)
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": payload["tasks"],
            "recentActions": payload["recentActions"],
            "notes": payload["notes"],
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
        payload = _write_payload_unlocked(tasks, existing["recentActions"], existing["notes"])
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
        payload = _write_payload_unlocked(tasks, existing["recentActions"], existing["notes"])

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

        _write_payload_unlocked(next_tasks, existing["recentActions"], existing["notes"])
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
        payload = _write_payload_unlocked(existing["tasks"], recent_actions, existing["notes"])
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
        payload = _write_payload_unlocked(existing["tasks"], next_actions, existing["notes"])
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

        _write_payload_unlocked(existing["tasks"], next_actions, existing["notes"])
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
        _write_payload_unlocked(existing["tasks"], [], existing["notes"])
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
        payload = _write_payload_unlocked(existing["tasks"], existing["recentActions"], notes)
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
        payload = _write_payload_unlocked(existing["tasks"], existing["recentActions"], notes)
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

        _write_payload_unlocked(existing["tasks"], existing["recentActions"], next_notes)
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
        _write_payload_unlocked(existing["tasks"], existing["recentActions"], [])
        return {
            "ok": True,
            "provider": "local-json",
            "removedCount": removed_count,
            "notes": [],
            "message": f"Cleared {removed_count} note{'s' if removed_count != 1 else ''}.",
        }


def clear_memory_context() -> dict:
    with _STORE_LOCK:
        existing = _read_payload_unlocked()
        removed_tasks = len(existing["tasks"])
        removed_actions = len(existing["recentActions"])
        removed_notes = len(existing["notes"])
        _write_payload_unlocked([], [], [])
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": [],
            "recentActions": [],
            "notes": [],
            "removedTaskCount": removed_tasks,
            "removedActionCount": removed_actions,
            "removedNoteCount": removed_notes,
            "message": "Cleared all backend memory, notes, and work context.",
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
            "message": "Memory export loaded from the backend.",
        }


def import_memory_context(tasks: list[dict], recent_actions: list[dict], notes: list[dict]) -> dict:
    with _STORE_LOCK:
        payload = _write_payload_unlocked(tasks, recent_actions, notes)
        return {
            "ok": True,
            "provider": "local-json",
            "tasks": payload["tasks"],
            "recentActions": payload["recentActions"],
            "notes": payload["notes"],
            "message": "Imported memory, notes, and work context into the backend.",
        }
