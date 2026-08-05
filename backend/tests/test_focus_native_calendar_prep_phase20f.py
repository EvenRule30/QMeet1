from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import memory_store
from app.focus import store as focus_store
from app.focus.calendar_prep import (
    NativeCalendarFocusPrepError,
    NativeCalendarFocusPrepRequest,
    NativeCalendarFocusPrepVerification,
    build_calendar_focus_objective,
    build_calendar_focus_title,
    build_calendar_prep_task_titles,
    get_native_calendar_focus_prep_health,
    prepare_calendar_focus_verified,
    reset_native_calendar_focus_prep_health,
)
from app.focus.lifecycle import (
    NativeFocusStartRequest,
    reset_native_focus_lifecycle_health,
    start_focus_verified,
)
from app.focus.tasks import (
    NativeFocusTasksError,
    reset_native_focus_task_health,
)


class NativeCalendarFocusPrepPhase20FTests(unittest.TestCase):
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
        self._relationship_path = Path(
            os.environ["QMEET_FOCUS_RELATIONSHIPS_FILE"]
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

    def tearDown(self) -> None:
        self._memory_file_patcher.stop()
        for name, value in self._previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._temp_dir.cleanup()

    def _request(
        self,
        *,
        turn: str = "calendar-prep-turn",
        event_id: str = "google-event-42",
        title: str = "Vacation planning meeting",
    ) -> NativeCalendarFocusPrepRequest:
        return NativeCalendarFocusPrepRequest(
            event={
                "id": event_id,
                "title": title,
                "dateKey": "2026-08-06",
                "time": "10:00 AM",
                "createdAt": "2026-08-05T13:45:00-07:00",
                "source": "google",
                "googleEventId": "google-42",
                "start": "2026-08-06T10:00:00-07:00",
                "end": "2026-08-06T10:30:00-07:00",
                "location": "Video call",
                "description": "Choose dates and a destination.",
                "allDay": False,
                "calendarId": "primary",
            },
            sourceTurnId=turn,
        )

    def _canonical_state(self):
        return focus_store.reduce_events(focus_store.list_events(limit=1000))

    def test_persists_exact_focus_tasks_and_relationship_as_one_receipt(self) -> None:
        request = self._request()
        result = prepare_calendar_focus_verified(request)

        self.assertTrue(result.ok)
        self.assertTrue(result.verified)
        self.assertEqual(result.operation, "prepare_calendar_focus")
        self.assertEqual(result.outcome, "created")
        self.assertEqual(result.sourceTurnId, request.sourceTurnId)
        self.assertEqual(
            result.focusReceipt.activeFocus.title,
            build_calendar_focus_title(request.event),
        )
        self.assertEqual(
            result.focusReceipt.activeFocus.objective,
            build_calendar_focus_objective(request.event),
        )
        self.assertEqual(
            [task.title for task in result.taskReceipt.tasks],
            build_calendar_prep_task_titles(request.event),
        )
        self.assertTrue(result.verification.focusReceiptVerified)
        self.assertTrue(result.verification.taskReceiptVerified)
        self.assertTrue(result.verification.activeFocusMatches)
        self.assertTrue(result.verification.exactTasksPersisted)
        self.assertTrue(result.verification.relationshipPersisted)
        self.assertTrue(result.verification.sourceTurnUnique)
        self.assertTrue(result.verification.rollbackProtected)

        canonical = self._canonical_state()
        self.assertEqual(canonical.focusId, result.focusReceipt.activeFocus.focusId)
        self.assertEqual(canonical.title, result.focusReceipt.activeFocus.title)
        persisted_tasks = memory_store.list_memory_tasks()["tasks"]
        self.assertEqual(
            [task["id"] for task in persisted_tasks[:5]],
            [task.id for task in result.taskReceipt.tasks],
        )
        relationships = json.loads(
            self._relationship_path.read_text(encoding="utf-8")
        )
        records = relationships["tasksByFocusId"][canonical.focusId]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["sourceTurnId"], request.sourceTurnId)
        self.assertEqual(
            records[0]["taskIds"],
            [task.id for task in result.taskReceipt.tasks],
        )

    def test_same_source_turn_is_idempotent(self) -> None:
        request = self._request()
        first = prepare_calendar_focus_verified(request)
        second = prepare_calendar_focus_verified(request)

        self.assertEqual(first.outcome, "created")
        self.assertEqual(second.outcome, "reused")
        self.assertEqual(
            first.focusReceipt.activeFocus.focusId,
            second.focusReceipt.activeFocus.focusId,
        )
        self.assertEqual(first.taskReceipt.receiptId, second.taskReceipt.receiptId)
        self.assertEqual(
            [task.id for task in first.taskReceipt.tasks],
            [task.id for task in second.taskReceipt.tasks],
        )
        self.assertEqual(len(memory_store.list_memory_tasks()["tasks"]), 5)
        relationships = json.loads(
            self._relationship_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            len(
                relationships["tasksByFocusId"]
                [first.focusReceipt.activeFocus.focusId]
            ),
            1,
        )

    def test_existing_open_tasks_are_linked_without_duplication(self) -> None:
        request = self._request()
        titles = build_calendar_prep_task_titles(request.event)
        existing = [
            {
                "id": f"task-existing-{index}",
                "title": title,
                "createdAt": f"2026-08-05T12:0{index}:00-07:00",
            }
            for index, title in enumerate(titles)
        ]
        with memory_store._STORE_LOCK:
            before = memory_store._read_payload_unlocked()
            memory_store._write_payload_unlocked(
                existing,
                before["recentActions"],
                before["notes"],
                before["activeSession"],
                before["recentFocusSessions"],
                before["visualContext"],
                preserve_active_session=False,
                preserve_recent_focus_sessions=False,
                preserve_visual_context=False,
            )

        result = prepare_calendar_focus_verified(request)

        self.assertEqual(result.outcome, "linked")
        self.assertEqual(result.taskReceipt.createdTaskIds, [])
        self.assertEqual(
            [task.id for task in result.taskReceipt.tasks],
            [task["id"] for task in existing],
        )
        self.assertEqual(len(memory_store.list_memory_tasks()["tasks"]), 5)

    def test_changed_event_with_same_source_turn_is_rejected_and_rolled_back(self) -> None:
        first = prepare_calendar_focus_verified(self._request())
        events_before = [
            event.model_dump(mode="json")
            for event in focus_store.list_events(limit=1000)
        ]
        tasks_before = memory_store.list_memory_tasks()["tasks"]
        relationships_before = self._relationship_path.read_text(encoding="utf-8")

        with self.assertRaises(NativeCalendarFocusPrepError) as caught:
            prepare_calendar_focus_verified(
                self._request(title="A different meeting title")
            )

        self.assertEqual(caught.exception.code, "source_turn_conflict")
        self.assertEqual(
            [event.model_dump(mode="json") for event in focus_store.list_events(1000)],
            events_before,
        )
        self.assertEqual(memory_store.list_memory_tasks()["tasks"], tasks_before)
        self.assertEqual(
            self._relationship_path.read_text(encoding="utf-8"),
            relationships_before,
        )
        self.assertEqual(self._canonical_state().focusId, first.focusReceipt.activeFocus.focusId)

    def test_task_failure_rolls_back_focus_memory_and_relationships(self) -> None:
        existing_focus = start_focus_verified(
            NativeFocusStartRequest(
                title="Existing work",
                objective="Preserve this Focus",
                mode="planning",
                tags=[],
                sourceTurnId="existing-focus-turn",
            )
        )
        existing_task = {
            "id": "task-before-calendar-prep",
            "title": "Existing task",
            "createdAt": "2026-08-05T12:00:00-07:00",
        }
        with memory_store._STORE_LOCK:
            before = memory_store._read_payload_unlocked()
            memory_store._write_payload_unlocked(
                [existing_task],
                before["recentActions"],
                before["notes"],
                before["activeSession"],
                before["recentFocusSessions"],
                before["visualContext"],
                preserve_active_session=False,
                preserve_recent_focus_sessions=False,
                preserve_visual_context=False,
            )
        existing_relationships = {
            "version": 1,
            "updatedAt": "2026-08-05T12:00:00-07:00",
            "summariesByFocusId": {
                existing_focus.activeFocus.focusId: {
                    "receiptId": "summary-existing",
                    "focusId": existing_focus.activeFocus.focusId,
                    "noteId": "note-existing",
                    "sourceTurnId": "summary-existing-turn",
                }
            },
        }
        self._relationship_path.write_text(
            json.dumps(existing_relationships, indent=2) + "\n",
            encoding="utf-8",
        )
        events_before = [
            event.model_dump(mode="json")
            for event in focus_store.list_events(limit=1000)
        ]

        forced = NativeFocusTasksError(
            "write_failed",
            "forced task write failure",
            status_code=500,
        )
        with patch(
            "app.focus.calendar_prep.link_focus_tasks_verified",
            side_effect=forced,
        ):
            with self.assertRaises(NativeCalendarFocusPrepError) as caught:
                prepare_calendar_focus_verified(self._request(turn="rollback-turn"))

        self.assertEqual(caught.exception.code, "write_failed")
        self.assertEqual(
            [event.model_dump(mode="json") for event in focus_store.list_events(1000)],
            events_before,
        )
        self.assertEqual(memory_store.list_memory_tasks()["tasks"], [existing_task])
        self.assertEqual(
            json.loads(self._relationship_path.read_text(encoding="utf-8")),
            existing_relationships,
        )
        canonical = self._canonical_state()
        self.assertEqual(canonical.focusId, existing_focus.activeFocus.focusId)
        self.assertEqual(canonical.title, "Existing work")

    def test_failed_combined_postcondition_rolls_back_all_canonical_stores(self) -> None:
        failed = NativeCalendarFocusPrepVerification(
            focusReceiptVerified=True,
            taskReceiptVerified=True,
            activeFocusMatches=True,
            exactTasksPersisted=True,
            relationshipPersisted=False,
            sourceTurnUnique=True,
            rollbackProtected=True,
            details=["forced verification failure"],
        )
        with patch(
            "app.focus.calendar_prep._verify_combined_receipt",
            return_value=failed,
        ):
            with self.assertRaises(NativeCalendarFocusPrepError) as caught:
                prepare_calendar_focus_verified(
                    self._request(turn="verification-rollback-turn")
                )

        self.assertEqual(caught.exception.code, "verification_failed")
        self.assertEqual(focus_store.list_events(limit=1000), [])
        self.assertEqual(memory_store.list_memory_tasks()["tasks"], [])
        relationship_text = (
            self._relationship_path.read_text(encoding="utf-8")
            if self._relationship_path.exists()
            else ""
        )
        self.assertNotIn("verification-rollback-turn", relationship_text)

    def test_existing_summary_relationship_is_preserved(self) -> None:
        existing_summary = {
            "receiptId": "focus-summary-existing",
            "focusId": "focus-historical",
            "noteId": "note-existing",
            "sourceTurnId": "summary-turn-existing",
        }
        self._relationship_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "updatedAt": "2026-08-05T12:00:00-07:00",
                    "summariesByFocusId": {
                        "focus-historical": existing_summary,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        result = prepare_calendar_focus_verified(self._request())

        relationships = json.loads(
            self._relationship_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            relationships["summariesByFocusId"]["focus-historical"],
            existing_summary,
        )
        self.assertEqual(
            len(
                relationships["tasksByFocusId"]
                [result.focusReceipt.activeFocus.focusId]
            ),
            1,
        )

    def test_calendar_health_records_success_failure_and_rollback(self) -> None:
        prepare_calendar_focus_verified(self._request())
        with self.assertRaises(NativeCalendarFocusPrepError):
            prepare_calendar_focus_verified(
                self._request(title="Conflicting calendar event")
            )

        health = get_native_calendar_focus_prep_health()["prepareCalendarFocus"]
        self.assertEqual(health["attemptCount"], 2)
        self.assertEqual(health["createdCount"], 1)
        self.assertEqual(health["verifiedCount"], 1)
        self.assertEqual(health["failedCount"], 1)
        self.assertEqual(health["rollbackCount"], 1)
        self.assertEqual(health["lastOutcome"], "failed")
        self.assertEqual(health["lastFailureCode"], "source_turn_conflict")


if __name__ == "__main__":
    unittest.main()
