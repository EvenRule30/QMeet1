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
    NativeFocusTasksRequest,
    get_active_focus_linked_task_ids,
    get_native_focus_task_health,
    link_focus_tasks_verified,
    reset_native_focus_task_health,
)


class FocusTaskRelationshipResiliencePhase20G1Tests(unittest.TestCase):
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
        self._relationships_path = Path(
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
        self._focus = start_focus_verified(
            NativeFocusStartRequest(
                title="Plan a vacation",
                objective="Choose dates and a destination",
                mode="planning",
                tags=[],
                sourceTurnId="start-resilience-focus",
            )
        )
        self._request = NativeFocusTasksRequest(
            expectedFocusId=self._focus.activeFocus.focusId,
            taskTitles=[
                "Choose travel dates",
                "Choose a destination",
                "Compare travel costs",
            ],
            sourceTurnId="resilient-task-turn",
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

    def test_missing_task_records_repair_existing_verified_receipt(self) -> None:
        first = link_focus_tasks_verified(self._request)
        first_task_ids = [task.id for task in first.tasks]
        self._remove_all_memory_tasks()

        repaired = link_focus_tasks_verified(self._request)

        self.assertEqual(repaired.outcome, "created")
        self.assertTrue(repaired.verified)
        self.assertEqual(repaired.receiptId, first.receiptId)
        self.assertNotEqual([task.id for task in repaired.tasks], first_task_ids)
        self.assertEqual(
            [task.title for task in repaired.tasks],
            self._request.taskTitles,
        )
        self.assertIn("Restored", repaired.message)
        self.assertTrue(repaired.verification.tasksPersisted)
        self.assertTrue(repaired.verification.relationshipPersisted)
        self.assertTrue(repaired.verification.sourceTurnUnique)

        relationships = json.loads(
            self._relationships_path.read_text(encoding="utf-8")
        )
        records = relationships["tasksByFocusId"][self._focus.activeFocus.focusId]
        matching = [
            record
            for record in records
            if record["sourceTurnId"] == self._request.sourceTurnId
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(
            matching[0]["taskIds"],
            [task.id for task in repaired.tasks],
        )

        health = get_native_focus_task_health()["linkFocusTasks"]
        self.assertEqual(health["attemptCount"], 2)
        self.assertEqual(health["verifiedCount"], 2)
        self.assertEqual(health["failedCount"], 0)
        self.assertEqual(health["lastOutcome"], "created")
        self.assertEqual(health["lastFailureCode"], "")

    def test_active_focus_linked_task_ids_follow_current_receipt(self) -> None:
        first = link_focus_tasks_verified(self._request)
        self.assertEqual(
            get_active_focus_linked_task_ids(),
            {task.id for task in first.tasks},
        )

        self._remove_all_memory_tasks()
        repaired = link_focus_tasks_verified(self._request)
        self.assertEqual(
            get_active_focus_linked_task_ids(),
            {task.id for task in repaired.tasks},
        )


if __name__ == "__main__":
    unittest.main()
