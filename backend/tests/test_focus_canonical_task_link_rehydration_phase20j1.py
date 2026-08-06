from __future__ import annotations

import unittest
from pathlib import Path


class FocusCanonicalTaskLinkRehydrationPhase20J1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.router_source = (
            root / "backend/app/routers/focus.py"
        ).read_text(encoding="utf-8")
        cls.lineage_source = (
            root / "backend/app/focus/task_lineage.py"
        ).read_text(encoding="utf-8")
        cls.projection_source = (
            root / "src/app/lib/canonicalFocusProjection.ts"
        ).read_text(encoding="utf-8")
        cls.natural_completion_source = (
            root / "src/app/lib/naturalTaskCompletion.ts"
        ).read_text(encoding="utf-8")

    def test_state_response_exposes_verified_active_focus_task_membership(self) -> None:
        source = self.router_source
        self.assertIn(
            "from app.focus.task_lineage import (",
            source,
        )
        self.assertIn(
            "get_active_focus_lineage_linked_task_ids",
            source,
        )
        self.assertIn(
            '"linkedTaskIds": _ordered_active_focus_linked_task_ids()',
            source,
        )
        self.assertIn(
            "linked_task_ids = get_active_focus_lineage_linked_task_ids()",
            source,
        )

    def test_router_uses_memory_only_for_stable_display_order(self) -> None:
        source = self.router_source
        self.assertIn("memory_store.list_memory_tasks()", source)
        self.assertIn("if task_id in linked_task_ids", source)
        self.assertIn("ordered_ids.append(task_id)", source)
        self.assertIn("ordered_ids.extend(sorted(linked_task_ids - seen))", source)

    def test_state_read_does_not_mutate_task_or_focus_ownership(self) -> None:
        state_block = self.router_source.split('@router.get("/state")', 1)[1]
        state_block = state_block.split('@router.get("/events")', 1)[0]
        self.assertNotIn("link_focus_tasks_verified", state_block)
        self.assertNotIn("_write_", state_block)
        self.assertNotIn("replace_memory", state_block)
        self.assertNotIn("/api/memory/session", state_block)

    def test_lineage_read_does_not_copy_or_rewrite_receipts(self) -> None:
        source = self.lineage_source
        self.assertIn('event.payload.get("resumedFromFocusId", "")', source)
        self.assertIn('document.get("tasksByFocusId")', source)
        self.assertIn('record.get("taskIds")', source)
        self.assertNotIn("_write_relationships_unlocked", source)
        self.assertNotIn("link_focus_tasks_verified", source)
        self.assertNotIn("sourceTurnId", source)

    def test_projection_requires_and_normalizes_canonical_task_ids(self) -> None:
        source = self.projection_source
        self.assertIn("linkedTaskIds: string[];", source)
        self.assertIn("function normalizeLinkedTaskIds", source)
        self.assertIn("!Array.isArray(payload.linkedTaskIds)", source)
        self.assertIn(
            "linkedTaskIds: normalizeLinkedTaskIds(canonicalLinkedTaskIds)",
            source,
        )

    def test_projection_does_not_restore_links_from_stale_session_metadata(self) -> None:
        source = self.projection_source
        self.assertNotIn("exactSource?.linkedTaskIds", source)
        self.assertNotIn("currentSession?.linkedTaskIds", source)
        self.assertIn("canonicalSnapshot.linkedTaskIds", source)

    def test_natural_completion_still_uses_rehydrated_linked_ids(self) -> None:
        source = self.natural_completion_source
        self.assertIn("activeSession.linkedTaskIds", source)
        self.assertIn("linkedTaskIds", source)
        self.assertIn("!task.completedAt", source)


if __name__ == "__main__":
    unittest.main()
