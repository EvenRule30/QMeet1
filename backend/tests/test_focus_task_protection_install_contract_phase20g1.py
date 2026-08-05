from __future__ import annotations

import unittest
from pathlib import Path


class FocusTaskProtectionInstallContractPhase20G1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        backend_root = Path(__file__).resolve().parents[1]
        repository_root = backend_root.parent
        cls.tasks = (backend_root / "app" / "focus" / "tasks.py").read_text(
            encoding="utf-8"
        )
        cls.calendar = (
            backend_root / "app" / "focus" / "calendar_prep.py"
        ).read_text(encoding="utf-8")
        cls.memory_router = (
            backend_root / "app" / "routers" / "memory.py"
        ).read_text(encoding="utf-8")
        cls.client = (
            repository_root / "src" / "app" / "lib" / "nativeCalendarFocusPrep.ts"
        ).read_text(encoding="utf-8")

    def test_existing_task_receipt_can_repair_missing_records(self) -> None:
        self.assertIn("repairable_missing_tasks", self.tasks)
        self.assertIn("_replace_source_turn_attachment", self.tasks)
        self.assertIn("_build_task_attachment", self.tasks)
        self.assertIn("Canonical state did not verify the repaired", self.tasks)
        self.assertIn("get_active_focus_linked_task_ids", self.tasks)

    def test_compatibility_memory_writes_preserve_active_linked_tasks(self) -> None:
        self.assertIn(
            "from app.focus.tasks import get_active_focus_linked_task_ids",
            self.memory_router,
        )
        self.assertGreaterEqual(
            self.memory_router.count("_preserve_active_focus_linked_tasks("),
            4,
        )
        self.assertIn("_retired_focus_task_delete", self.memory_router)
        self.assertIn("status_code=409", self.memory_router)
        self.assertIn("if _protected_focus_task(task_id)", self.memory_router)
        self.assertIn("task.get(\"completedAt\")", self.memory_router)

    def test_calendar_prep_can_start_a_new_verified_cycle(self) -> None:
        self.assertIn("_resolve_calendar_source_turn", self.calendar)
        self.assertIn("-cycle-", self.calendar)
        self.assertIn("_reuse_active_calendar_focus_receipt", self.calendar)
        self.assertIn("Restored", self.calendar)
        self.assertIn("Relinked", self.calendar)

    def test_frontend_accepts_only_backend_resolved_cycle_ids(self) -> None:
        self.assertIn("calendarSourceTurnBelongsToRequest", self.client)
        self.assertIn("resolvedSourceTurnId", self.client)
        self.assertIn(
            "isVerifiedNativeFocusStartResult(focusReceipt, resolvedSourceTurnId)",
            self.client,
        )
        self.assertIn("sourceTurnId: resolvedSourceTurnId", self.client)


if __name__ == "__main__":
    unittest.main()
