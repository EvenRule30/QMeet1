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


def _read_payload() -> dict:
    path = _memory_file()

    if not path.exists():
        return {"tasks": []}

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MemoryStoreError(
            f"QMeet memory file is invalid JSON: {path}"
        ) from exc
    except Exception as exc:
        raise MemoryStoreError("QMeet could not read the memory file.") from exc

    if not isinstance(parsed, dict):
        return {"tasks": []}

    tasks = parsed.get("tasks", [])
    if not isinstance(tasks, list):
        tasks = []

    return {"tasks": [_task for _task in (_sanitize_task(task) for task in tasks) if _task]}


def _write_payload(tasks: list[dict]) -> None:
    path = _memory_file()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updatedAt": _now_iso(),
            "tasks": [_task for _task in (_sanitize_task(task) for task in tasks) if _task],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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
        "message": "QMeet memory is stored in a local backend JSON file.",
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
    clean_tasks = [_task for _task in (_sanitize_task(task) for task in tasks) if _task]
    _write_payload(clean_tasks)

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
    _write_payload(tasks)

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

    _write_payload(updated_tasks)

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

    _write_payload(next_tasks)

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

    _write_payload(next_tasks)

    return {
        "ok": True,
        "provider": "local-json",
        "removedCount": removed_count,
        "tasks": next_tasks,
        "message": f"Cleared {removed_count} completed task{'s' if removed_count != 1 else ''}.",
    }
