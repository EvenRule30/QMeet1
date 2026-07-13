from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4


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


def _read_payload() -> dict:
    path = _memory_file()

    if not path.exists():
        return {"tasks": [], "recentActions": [], "notes": []}

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MemoryStoreError(
            f"QMeet memory file is invalid JSON: {path}"
        ) from exc
    except Exception as exc:
        raise MemoryStoreError("QMeet could not read the memory file.") from exc

    if not isinstance(parsed, dict):
        return {"tasks": [], "recentActions": [], "notes": []}

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


def _write_payload(
    tasks: list[dict],
    recent_actions: list[dict] | None = None,
    notes: list[dict] | None = None,
) -> None:
    path = _memory_file()
    existing_payload: dict | None = None

    if recent_actions is None or notes is None:
        existing_payload = _read_payload()

    if recent_actions is None:
        recent_actions = existing_payload["recentActions"] if existing_payload else []

    if notes is None:
        notes = existing_payload["notes"] if existing_payload else []

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 3,
            "updatedAt": _now_iso(),
            "tasks": [_task for _task in (_sanitize_task(task) for task in tasks) if _task],
            "recentActions": [
                _action
                for _action in (_sanitize_action(action) for action in recent_actions)
                if _action
            ][:24],
            "notes": [_note for _note in (_sanitize_note(note) for note in notes) if _note],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except MemoryStoreError:
        raise
    except Exception as exc:
        raise MemoryStoreError("QMeet could not write the memory file.") from exc


def get_memory_status() -> dict:
    payload = _read_payload()
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
    payload = _read_payload()

    return {
        "ok": True,
        "provider": "local-json",
        "tasks": payload["tasks"],
        "recentActions": payload["recentActions"],
        "notes": payload["notes"],
        "message": "Memory context loaded from the backend.",
    }


def replace_memory_context(tasks: list[dict], recent_actions: list[dict], notes: list[dict]) -> dict:
    clean_tasks = [_task for _task in (_sanitize_task(task) for task in tasks) if _task]
    clean_actions = [
        _action for _action in (_sanitize_action(action) for action in recent_actions) if _action
    ][:24]
    clean_notes = [_note for _note in (_sanitize_note(note) for note in notes) if _note]
    _write_payload(clean_tasks, clean_actions, clean_notes)

    return {
        "ok": True,
        "provider": "local-json",
        "tasks": clean_tasks,
        "recentActions": clean_actions,
        "notes": clean_notes,
        "message": "Memory context saved to the backend.",
    }


def list_memory_tasks() -> dict:
    payload = _read_payload()

    return {
        "ok": True,
        "provider": "local-json",
        "tasks": payload["tasks"],
        "message": "Memory tasks loaded from the backend.",
    }


def replace_memory_tasks(tasks: list[dict]) -> dict:
    payload = _read_payload()
    clean_tasks = [_task for _task in (_sanitize_task(task) for task in tasks) if _task]
    _write_payload(clean_tasks, payload["recentActions"])

    return {
        "ok": True,
        "provider": "local-json",
        "tasks": clean_tasks,
        "message": "Memory tasks saved to the backend.",
    }


def create_memory_task(title: str) -> dict:
    clean_title = (title or "").strip()
    if not clean_title:
        raise MemoryStoreError("Task title cannot be empty.")

    payload = _read_payload()
    task = {
        "id": _new_task_id(),
        "title": clean_title,
        "createdAt": _now_iso(),
    }

    tasks = [task, *payload["tasks"]]
    _write_payload(tasks, payload["recentActions"])

    return {
        "ok": True,
        "provider": "local-json",
        "tasks": tasks,
        "message": f"Saved task: {clean_title}.",
    }


def update_memory_task(task_id: str, title: str = "", completed_at: str | None = None) -> dict:
    clean_task_id = (task_id or "").strip()
    if not clean_task_id:
        raise MemoryStoreError("Task id cannot be empty.")

    payload = _read_payload()
    found = False
    updated_tasks: list[dict] = []

    for task in payload["tasks"]:
        if task["id"] != clean_task_id:
            updated_tasks.append(task)
            continue

        found = True
        updated_task = dict(task)

        clean_title = (title or "").strip()
        if clean_title:
            updated_task["title"] = clean_title

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

    _write_payload(updated_tasks, payload["recentActions"])

    return {
        "ok": True,
        "provider": "local-json",
        "tasks": updated_tasks,
        "message": "Memory task updated.",
    }


def delete_memory_task(task_id: str) -> dict:
    clean_task_id = (task_id or "").strip()
    if not clean_task_id:
        raise MemoryStoreError("Task id cannot be empty.")

    payload = _read_payload()
    next_tasks = [task for task in payload["tasks"] if task["id"] != clean_task_id]

    if len(next_tasks) == len(payload["tasks"]):
        raise MemoryStoreError("Memory task was not found.")

    _write_payload(next_tasks, payload["recentActions"])

    return {
        "ok": True,
        "provider": "local-json",
        "deletedTaskId": clean_task_id,
        "message": "Memory task deleted.",
    }


def clear_completed_memory_tasks() -> dict:
    payload = _read_payload()
    next_tasks = [task for task in payload["tasks"] if not task.get("completedAt")]
    removed_count = len(payload["tasks"]) - len(next_tasks)

    _write_payload(next_tasks, payload["recentActions"])

    return {
        "ok": True,
        "provider": "local-json",
        "removedCount": removed_count,
        "tasks": next_tasks,
        "message": f"Cleared {removed_count} completed task{'s' if removed_count != 1 else ''}.",
    }


def list_recent_actions() -> dict:
    payload = _read_payload()

    return {
        "ok": True,
        "provider": "local-json",
        "recentActions": payload["recentActions"],
        "message": "Recent actions loaded from the backend.",
    }


def replace_recent_actions(recent_actions: list[dict]) -> dict:
    payload = _read_payload()
    clean_actions = [
        _action for _action in (_sanitize_action(action) for action in recent_actions) if _action
    ][:24]

    _write_payload(payload["tasks"], clean_actions)

    return {
        "ok": True,
        "provider": "local-json",
        "recentActions": clean_actions,
        "message": "Recent actions saved to the backend.",
    }


def create_recent_action(label: str, detail: str = "") -> dict:
    clean_label = (label or "").strip()
    if not clean_label:
        raise MemoryStoreError("Recent action label cannot be empty.")

    payload = _read_payload()
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

    next_actions = [action, *payload["recentActions"]][:24]
    _write_payload(payload["tasks"], next_actions)

    return {
        "ok": True,
        "provider": "local-json",
        "recentActions": next_actions,
        "message": "Recent action saved.",
    }


def delete_recent_action(action_id: str) -> dict:
    clean_action_id = (action_id or "").strip()
    if not clean_action_id:
        raise MemoryStoreError("Recent action id cannot be empty.")

    payload = _read_payload()
    next_actions = [action for action in payload["recentActions"] if action["id"] != clean_action_id]

    if len(next_actions) == len(payload["recentActions"]):
        raise MemoryStoreError("Recent action was not found.")

    _write_payload(payload["tasks"], next_actions)

    return {
        "ok": True,
        "provider": "local-json",
        "deletedActionId": clean_action_id,
        "message": "Recent action deleted.",
    }


def clear_recent_actions() -> dict:
    payload = _read_payload()
    removed_count = len(payload["recentActions"])
    _write_payload(payload["tasks"], [])

    return {
        "ok": True,
        "provider": "local-json",
        "removedCount": removed_count,
        "recentActions": [],
        "message": f"Cleared {removed_count} recent action{'s' if removed_count != 1 else ''}.",
    }


def list_memory_notes() -> dict:
    payload = _read_payload()

    return {
        "ok": True,
        "provider": "local-json",
        "notes": payload["notes"],
        "message": "Memory notes loaded from the backend.",
    }


def replace_memory_notes(notes: list[dict]) -> dict:
    payload = _read_payload()
    clean_notes = [_note for _note in (_sanitize_note(note) for note in notes) if _note]
    _write_payload(payload["tasks"], payload["recentActions"], clean_notes)

    return {
        "ok": True,
        "provider": "local-json",
        "notes": clean_notes,
        "message": "Memory notes saved to the backend.",
    }


def create_memory_note(content: str) -> dict:
    clean_content = (content or "").strip()
    if not clean_content:
        raise MemoryStoreError("Note content cannot be empty.")

    payload = _read_payload()
    note = {
        "id": _new_note_id(),
        "content": clean_content[:2000],
        "createdAt": _now_iso(),
    }

    notes = [note, *payload["notes"]]
    _write_payload(payload["tasks"], payload["recentActions"], notes)

    return {
        "ok": True,
        "provider": "local-json",
        "notes": notes,
        "message": "Saved note to backend memory.",
    }


def delete_memory_note(note_id: str) -> dict:
    clean_note_id = (note_id or "").strip()
    if not clean_note_id:
        raise MemoryStoreError("Note id cannot be empty.")

    payload = _read_payload()
    next_notes = [note for note in payload["notes"] if note["id"] != clean_note_id]

    if len(next_notes) == len(payload["notes"]):
        raise MemoryStoreError("Memory note was not found.")

    _write_payload(payload["tasks"], payload["recentActions"], next_notes)

    return {
        "ok": True,
        "provider": "local-json",
        "deletedNoteId": clean_note_id,
        "message": "Memory note deleted.",
    }


def clear_memory_notes() -> dict:
    payload = _read_payload()
    removed_count = len(payload["notes"])
    _write_payload(payload["tasks"], payload["recentActions"], [])

    return {
        "ok": True,
        "provider": "local-json",
        "removedCount": removed_count,
        "notes": [],
        "message": f"Cleared {removed_count} note{'s' if removed_count != 1 else ''}.",
    }


def clear_memory_context() -> dict:
    payload = _read_payload()
    removed_tasks = len(payload["tasks"])
    removed_actions = len(payload["recentActions"])
    removed_notes = len(payload["notes"])

    _write_payload([], [], [])

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
    payload = _read_payload()

    return {
        "ok": True,
        "provider": "local-json",
        "version": 4,
        "exportedAt": _now_iso(),
        "tasks": payload["tasks"],
        "recentActions": payload["recentActions"],
        "notes": payload["notes"],
        "message": "Memory export loaded from the backend.",
    }


def import_memory_context(tasks: list[dict], recent_actions: list[dict], notes: list[dict]) -> dict:
    clean_tasks = [_task for _task in (_sanitize_task(task) for task in tasks) if _task]
    clean_actions = [
        _action for _action in (_sanitize_action(action) for action in recent_actions) if _action
    ][:24]
    clean_notes = [_note for _note in (_sanitize_note(note) for note in notes) if _note]

    _write_payload(clean_tasks, clean_actions, clean_notes)

    return {
        "ok": True,
        "provider": "local-json",
        "tasks": clean_tasks,
        "recentActions": clean_actions,
        "notes": clean_notes,
        "message": "Imported memory, notes, and work context into the backend.",
    }
