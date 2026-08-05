from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import memory_store
from app.focus import store as focus_store
from app.focus.lifecycle import NativeFocusStartRequest, start_focus_verified
from app.focus.tasks import (
    NativeFocusTasksError,
    NativeFocusTasksRequest,
    NativeFocusTasksVerification,
    get_native_focus_task_health,
    link_focus_tasks_verified,
    reset_native_focus_task_health,
)


class NativeFocusTasksPhase20E2BTests(unittest.TestCase):
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
        reset_native_focus_task_health()
        self._start = start_focus_verified(
            NativeFocusStartRequest(
                title="Plan a vacation",
                objective="Choose dates and a destination",
                mode="planning",
                tags=[],
                sourceTurnId="start-task-focus",
            )
        )

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
        turn: str = "task-turn",
        titles: list[str] | None = None,
    ) -> NativeFocusTasksRequest:
        return NativeFocusTasksRequest(
            expectedFocusId=self._start.activeFocus.focusId,
            taskTitles=titles
            or [
                "Define the finished outcome for Plan a vacation",
                "Break Choose dates and a destination into visible milestones",
                "Identify blockers or dependencies for Plan a vacation",
                "Choose the first action you can do in 10 minutes",
            ],
            sourceTurnId=turn,
        )

    def test_creates_exact_tasks_and_verified_focus_relationship(self) -> None:
        request = self._request()
        result = link_focus_tasks_verified(request)

        self.assertTrue(result.ok)
        self.assertTrue(result.verified)
        self.assertEqual(result.outcome, "created")
        self.assertEqual(result.focusId, self._start.activeFocus.focusId)
        self.assertEqual([task.title for task in result.tasks], request.taskTitles)
        self.assertEqual(len(result.createdTaskIds), len(request.taskTitles))
        self.assertTrue(result.verification.activeFocusMatches)
        self.assertTrue(result.verification.tasksPersisted)
        self.assertTrue(result.verification.relationshipPersisted)
        self.assertTrue(result.verification.sourceTurnUnique)

        persisted = memory_store.list_memory_tasks()["tasks"]
        self.assertEqual(
            [task["id"] for task in persisted[: len(result.tasks)]],
            [task.id for task in result.tasks],
        )
        relationships = json.loads(
            self._relationship_path.read_text(encoding="utf-8")
        )
        records = relationships["tasksByFocusId"][result.focusId]
        self.assertEqual(records[0]["receiptId"], result.receiptId)
        self.assertEqual(records[0]["taskIds"], [task.id for task in result.tasks])
        self.assertIn("Created and linked", result.message)

    def test_task_receipt_preserves_existing_summary_relationships(self) -> None:
        existing_summary = {
            "receiptId": "focus-summary-existing",
            "focusId": self._start.activeFocus.focusId,
            "noteId": "note-existing",
            "sourceTurnId": "summary-turn-existing",
        }
        self._relationship_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "updatedAt": "2026-08-05T12:00:00-07:00",
                    "summariesByFocusId": {
                        self._start.activeFocus.focusId: existing_summary
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        result = link_focus_tasks_verified(self._request())

        relationships = json.loads(
            self._relationship_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            relationships["summariesByFocusId"][result.focusId],
            existing_summary,
        )
        self.assertEqual(
            relationships["tasksByFocusId"][result.focusId][0]["receiptId"],
            result.receiptId,
        )

    def test_same_source_turn_and_titles_are_idempotent(self) -> None:
        first = link_focus_tasks_verified(self._request())
        second = link_focus_tasks_verified(self._request())

        self.assertEqual(first.outcome, "created")
        self.assertEqual(second.outcome, "reused")
        self.assertEqual(first.receiptId, second.receiptId)
        self.assertEqual(
            [task.id for task in first.tasks],
            [task.id for task in second.tasks],
        )
        self.assertEqual(
            len(memory_store.list_memory_tasks()["tasks"]),
            len(first.tasks),
        )

    def test_same_source_turn_with_different_titles_is_conflict(self) -> None:
        first = link_focus_tasks_verified(self._request())
        with self.assertRaises(NativeFocusTasksError) as caught:
            link_focus_tasks_verified(
                self._request(titles=["A different task title"])
            )

        self.assertEqual(caught.exception.code, "source_turn_conflict")
        self.assertEqual(
            len(memory_store.list_memory_tasks()["tasks"]),
            len(first.tasks),
        )

    def test_stale_focus_is_rejected_before_task_write(self) -> None:
        replacement = start_focus_verified(
            NativeFocusStartRequest(
                title="Prepare quarterly review",
                objective="Finish the review deck",
                mode="planning",
                tags=[],
                sourceTurnId="replace-before-tasks",
            )
        )
        self.assertNotEqual(
            replacement.activeFocus.focusId,
            self._start.activeFocus.focusId,
        )

        with self.assertRaises(NativeFocusTasksError) as caught:
            link_focus_tasks_verified(self._request())

        self.assertEqual(caught.exception.code, "stale_focus")
        self.assertEqual(memory_store.list_memory_tasks()["tasks"], [])

    def test_existing_open_tasks_are_linked_without_duplication(self) -> None:
        existing_task = {
            "id": "task-existing-vacation",
            "title": "Choose the first action you can do in 10 minutes",
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

        result = link_focus_tasks_verified(
            self._request(titles=[existing_task["title"]])
        )

        self.assertEqual(result.outcome, "linked")
        self.assertEqual(result.createdTaskIds, [])
        self.assertEqual(result.tasks[0].id, existing_task["id"])
        self.assertEqual(len(memory_store.list_memory_tasks()["tasks"]), 1)

    def test_completed_matching_task_is_not_reused(self) -> None:
        completed_task = {
            "id": "task-completed-vacation",
            "title": "Choose the first action you can do in 10 minutes",
            "createdAt": "2026-08-05T11:00:00-07:00",
            "completedAt": "2026-08-05T11:30:00-07:00",
        }
        with memory_store._STORE_LOCK:
            before = memory_store._read_payload_unlocked()
            memory_store._write_payload_unlocked(
                [completed_task],
                before["recentActions"],
                before["notes"],
                before["activeSession"],
                before["recentFocusSessions"],
                before["visualContext"],
                preserve_active_session=False,
                preserve_recent_focus_sessions=False,
                preserve_visual_context=False,
            )

        result = link_focus_tasks_verified(
            self._request(titles=[completed_task["title"]])
        )

        self.assertEqual(result.outcome, "created")
        self.assertNotEqual(result.tasks[0].id, completed_task["id"])
        self.assertEqual(len(memory_store.list_memory_tasks()["tasks"]), 2)

    def test_relationship_write_failure_rolls_back_new_tasks(self) -> None:
        from app.focus import tasks as tasks_module

        original_write = tasks_module._write_relationships_unlocked
        calls = 0

        def fail_first_write(document):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("forced relationship write failure")
            return original_write(document)

        with patch.object(
            tasks_module,
            "_write_relationships_unlocked",
            side_effect=fail_first_write,
        ):
            with self.assertRaises(NativeFocusTasksError) as caught:
                link_focus_tasks_verified(self._request())

        self.assertEqual(caught.exception.code, "write_failed")
        self.assertEqual(memory_store.list_memory_tasks()["tasks"], [])

    def test_failed_postcondition_rolls_back_tasks_and_relationship(self) -> None:
        from app.focus import tasks as tasks_module

        failed = NativeFocusTasksVerification(
            activeFocusMatches=True,
            tasksPersisted=True,
            relationshipPersisted=False,
            sourceTurnUnique=True,
            details=["forced verification failure"],
        )
        with patch.object(tasks_module, "_verify_tasks", return_value=failed):
            with self.assertRaises(NativeFocusTasksError) as caught:
                link_focus_tasks_verified(self._request())

        self.assertEqual(caught.exception.code, "verification_failed")
        self.assertEqual(memory_store.list_memory_tasks()["tasks"], [])
        relationship_document = (
            self._relationship_path.read_text(encoding="utf-8")
            if self._relationship_path.exists()
            else ""
        )
        self.assertNotIn("task-turn", relationship_document)

    def test_health_is_aggregated_and_persistent(self) -> None:
        link_focus_tasks_verified(self._request())
        link_focus_tasks_verified(self._request())
        health = get_native_focus_task_health()["linkFocusTasks"]

        self.assertEqual(health["attemptCount"], 2)
        self.assertEqual(health["createdCount"], 1)
        self.assertEqual(health["reusedCount"], 1)
        self.assertEqual(health["verifiedCount"], 2)
        self.assertEqual(health["failedCount"], 0)


if __name__ == "__main__":
    unittest.main()
