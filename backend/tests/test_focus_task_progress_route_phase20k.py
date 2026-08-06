from __future__ import annotations

import unittest
from pathlib import Path


class FocusTaskProgressRoutePhase20KTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.client_source = (
            root / "src/app/lib/focusTaskProgress.ts"
        ).read_text(encoding="utf-8")
        cls.router_source = (
            root / "backend/app/routers/focus.py"
        ).read_text(encoding="utf-8")
        cls.bridge_source = (
            root / "backend/app/focus/task_progress.py"
        ).read_text(encoding="utf-8")

    def test_confirmed_linked_task_completion_uses_verified_bridge(self) -> None:
        self.assertIn("commandRoute === 'confirmed'", self.app_source)
        self.assertIn("commandMatch.command === 'mark-task-done'", self.app_source)
        self.assertIn("routingActiveSession.linkedTaskIds.includes(task.id)", self.app_source)
        bridge_index = self.app_source.index("recordVerifiedFocusTaskProgress(")
        memory_handler_index = self.app_source.index("await handleMemoryCommand(")
        self.assertLess(bridge_index, memory_handler_index)

    def test_frontend_claims_progress_only_after_verified_response(self) -> None:
        self.assertIn("focusTaskProgressResult?.verified", self.app_source)
        self.assertIn("Focus progress updated.", self.app_source)
        self.assertIn("canonical Focus progress could not be verified", self.app_source)
        self.assertIn("payload.verified !== true", self.client_source)
        self.assertIn("payload.focusId !== expectedFocusId", self.client_source)

    def test_client_posts_confirmed_targets_to_focus_endpoint(self) -> None:
        self.assertIn("/api/focus/task-progress", self.client_source)
        self.assertIn("expectedFocusId", self.client_source)
        self.assertIn("sourceTurnId: createSourceTurnId()", self.client_source)
        self.assertIn("confirmed: true", self.client_source)

    def test_backend_route_never_returns_an_unverified_success(self) -> None:
        self.assertIn('"/task-progress"', self.router_source)
        self.assertIn("record_focus_task_progress_verified(request)", self.router_source)
        self.assertIn("if not result.verified", self.router_source)
        self.assertIn('"successClaimAllowed": False', self.router_source)

    def test_bridge_preserves_lock_order_and_rollback_guarantee(self) -> None:
        focus_lock = self.bridge_source.index("with focus_store._STORE_LOCK")
        relationship_lock = self.bridge_source.index("with _RELATIONSHIP_LOCK", focus_lock)
        memory_lock = self.bridge_source.index("with memory_store._STORE_LOCK", relationship_lock)
        self.assertLess(focus_lock, relationship_lock)
        self.assertLess(relationship_lock, memory_lock)
        self.assertIn("_restore_memory_unlocked(memory_before)", self.bridge_source)
        self.assertIn("focus_store._atomic_write_unlocked(focus_before)", self.bridge_source)

    def test_bridge_preserves_ownership_and_lineage_contracts(self) -> None:
        self.assertIn("_focus_lineage_ids", self.bridge_source)
        self.assertIn("_task_relationship_records", self.bridge_source)
        self.assertIn('"source_turn_conflict"', self.bridge_source)
        self.assertNotIn("requiredOperations", self.bridge_source)
        self.assertNotIn("legacy projection", self.bridge_source.casefold())

    def test_bridge_does_not_auto_complete_focus(self) -> None:
        self.assertNotIn("FocusEventType.FOCUS_COMPLETED", self.bridge_source)
        self.assertIn("complete the Focus when ready", self.bridge_source)
        self.assertIn("focusContinuityPreserved", self.bridge_source)


if __name__ == "__main__":
    unittest.main()
