from __future__ import annotations

from app.focus import store as focus_store
from app.focus import summary as relationship_store
from app.focus.models import FocusEvent, FocusEventType

_RELATIONSHIP_LOCK = relationship_store._RELATIONSHIP_LOCK
_read_relationships_unlocked = relationship_store._read_relationships_unlocked
_open_focus_ids = relationship_store._open_focus_ids


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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


def _resume_parent_by_focus_id(events: list[FocusEvent]) -> dict[str, str]:
    parents: dict[str, str] = {}
    for event in events:
        if event.type != FocusEventType.FOCUS_STARTED:
            continue
        focus_id = event.focusId.strip()
        resumed_from_focus_id = str(
            event.payload.get("resumedFromFocusId", "")
        ).strip()
        if focus_id and resumed_from_focus_id:
            parents[focus_id] = resumed_from_focus_id
    return parents


def _focus_lineage_ids(
    events: list[FocusEvent],
    active_focus_id: str,
) -> list[str]:
    parents = _resume_parent_by_focus_id(events)
    lineage: list[str] = []
    seen: set[str] = set()
    focus_id = active_focus_id.strip()

    while focus_id and focus_id not in seen:
        lineage.append(focus_id)
        seen.add(focus_id)
        focus_id = parents.get(focus_id, "").strip()

    return lineage


def get_active_focus_lineage_linked_task_ids() -> set[str]:
    """Return verified task membership inherited by the sole open Focus.

    Resume creates a new canonical Focus ID and records the prior ID in the
    ``resumedFromFocusId`` payload. Task receipts remain immutable under the ID
    that originally verified them. Read-time lineage traversal lets the resumed
    Focus continue using those tasks without copying receipts, changing source
    turn ownership, or writing to the quarantined legacy session projection.
    """

    with focus_store._STORE_LOCK:
        events = list(focus_store._read_log_unlocked().events)
        open_focus_ids = _open_focus_ids(events)
        if len(open_focus_ids) != 1:
            return set()
        lineage_ids = _focus_lineage_ids(events, open_focus_ids[0])

        with _RELATIONSHIP_LOCK:
            document = _read_relationships_unlocked()
            linked_task_ids: set[str] = set()
            for focus_id in lineage_ids:
                for record in _task_relationship_records(document, focus_id):
                    linked_task_ids.update(_string_list(record.get("taskIds")))
            return linked_task_ids
