from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app import memory_store
from app.focus import store as focus_store
from app.focus.calendar_prep import (
    NativeCalendarFocusPrepRequest,
    get_native_calendar_focus_prep_health,
    prepare_calendar_focus_verified,
    reset_native_calendar_focus_prep_health,
)
from app.focus.lifecycle import reset_native_focus_lifecycle_health
from app.focus.models import FocusEvent, FocusEventType
from app.focus.tasks import (
    get_native_focus_task_health,
    reset_native_focus_task_health,
)


class FocusCalendarRepreparePhase20G1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        root = Path(self._temp_dir.name)
        self._previous = {
            name: os.environ.get(name)
            for name in (
                "QMEET_FOCUS_FILE",
                "QMEET_FOCUS_LIFECYCLE_HEALTH_FILE",
                "QMEET_FOCUS_RELATIONSHIPS_FILE",
                "QMEET_FOCUS_TASK_HEALTH_FILE",
                "QMEET_FOCUS_CALENDAR_PREP_HEALTH_FILE",
            )
        }
        os.environ["QMEET_FOCUS_FILE"] = str(root / "qmeet_focus.json")
        os.environ["QMEET_FOCUS_LIFECYCLE_HEALTH_FILE"] = str(
            root / "qmeet_focus_lifecycle_health.json"
        )
        os.environ["QMEET_FOCUS_RELATIONSHIPS_FILE"] = str(
            root / "qmeet_focus_relationships.json"
        )
        os.environ["QMEET_FOCUS_TASK_HEALTH_FILE"] = str(
            root / "qmeet_focus_task_health.json"
        )
        os.environ["QMEET_FOCUS_CALENDAR_PREP_HEALTH_FILE"] = str(
            root / "qmeet_focus_calendar_prep_health.json"
        )
        self._memory_path = root / "qmeet_memory.json"
        self._memory_file_patcher = patch.object(
            memory_store,
            "_memory_file",
            return_value=self._memory_path,
        )
        self._memory_file_patcher.start()
        focus_store.reset_store()
        reset_native_focus_lifecycle_health()
        reset_native_focus_task_health()
        reset_native_calendar_focus_prep_health()
        self._request = NativeCalendarFocusPrepRequest(
            event={
                "id": "google-event-meeting",
                "title": "meeting",
                "dateKey": "2026-08-05",
                "time": "7:00 PM",
                "createdAt": "2026-08-05T14:15:00-07:00",
                "source": "google",
                "googleEventId": "google-meeting",
                "start": "2026-08-05T19:00:00-07:00",
                "end": "2026-08-05T19:30:00-07:00",
                "calendarId": "primary",
            },
            sourceTurnId="calendar-focus-meeting",
        )

    def tearDown(self) -> None:
        self._memory_file_patcher.stop()
        for name, value in self._previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._temp_dir.cleanup()

    def _remove_all_memory_tasks(self) -> None:
        with memory_store._STORE_LOCK:
            before = memory_store._read_payload_unlocked()
            memory_store._write_payload_unlocked(
                [],
                before["recentActions"],
                before["notes"],
                before["activeSession"],
                before["recentFocusSessions"],
                before["visualContext"],
                preserve_active_session=False,
                preserve_recent_focus_sessions=False,
                preserve_visual_context=False,
            )

    def _end_focus_for_test(self, focus_id: str) -> None:
        with focus_store._STORE_LOCK:
            document = focus_store._read_log_unlocked()
            document.events.append(
                FocusEvent(
                    id=f"event-{uuid4().hex}",
                    focusId=focus_id,
                    type=FocusEventType.FOCUS_ENDED,
                    payload={"status": "inactive"},
                    sourceTurnId="end-calendar-cycle-one",
                    source="phase20g1-test",
                    createdAt="2026-08-05T15:00:00-07:00",
                )
            )
            focus_store._atomic_write_unlocked(document)

    def test_active_calendar_receipt_repairs_deleted_tasks(self) -> None:
        first = prepare_calendar_focus_verified(self._request)
        first_ids = [task.id for task in first.taskReceipt.tasks]
        self._remove_all_memory_tasks()

        repaired = prepare_calendar_focus_verified(self._request)

        self.assertEqual(repaired.focusReceipt.outcome, "reused")
        self.assertEqual(repaired.taskReceipt.outcome, "created")
        self.assertEqual(repaired.outcome, "created")
        self.assertEqual(repaired.sourceTurnId, self._request.sourceTurnId)
        self.assertEqual(
            repaired.focusReceipt.activeFocus.focusId,
            first.focusReceipt.activeFocus.focusId,
        )
        self.assertNotEqual(
            [task.id for task in repaired.taskReceipt.tasks],
            first_ids,
        )
        self.assertIn("Restored", repaired.message)
        self.assertTrue(repaired.verification.taskReceiptVerified)
        self.assertTrue(repaired.verification.sourceTurnUnique)

        task_health = get_native_focus_task_health()["linkFocusTasks"]
        calendar_health = get_native_calendar_focus_prep_health()[
            "prepareCalendarFocus"
        ]
        self.assertEqual(task_health["failedCount"], 0)
        self.assertEqual(task_health["lastOutcome"], "created")
        self.assertEqual(calendar_health["failedCount"], 0)
        self.assertEqual(calendar_health["lastOutcome"], "created")

    def test_same_event_after_canonical_end_starts_new_cycle(self) -> None:
        first = prepare_calendar_focus_verified(self._request)
        self._end_focus_for_test(first.focusReceipt.activeFocus.focusId)
        self._remove_all_memory_tasks()

        second = prepare_calendar_focus_verified(self._request)

        self.assertEqual(second.sourceTurnId, "calendar-focus-meeting-cycle-2")
        self.assertEqual(second.focusReceipt.outcome, "started")
        self.assertEqual(second.taskReceipt.outcome, "created")
        self.assertNotEqual(
            second.focusReceipt.activeFocus.focusId,
            first.focusReceipt.activeFocus.focusId,
        )
        self.assertTrue(second.verification.focusReceiptVerified)
        self.assertTrue(second.verification.taskReceiptVerified)
        self.assertTrue(second.verification.sourceTurnUnique)
        self.assertEqual(
            len(memory_store.list_memory_tasks()["tasks"]),
            len(second.taskReceipt.tasks),
        )

        third = prepare_calendar_focus_verified(self._request)
        self.assertEqual(third.sourceTurnId, second.sourceTurnId)
        self.assertEqual(third.outcome, "reused")
        self.assertEqual(
            third.focusReceipt.activeFocus.focusId,
            second.focusReceipt.activeFocus.focusId,
        )


if __name__ == "__main__":
    unittest.main()
