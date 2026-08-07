from __future__ import annotations

import unittest
from pathlib import Path

from app.focus.context_hygiene import (
    duplicate_values_to_remove,
    equivalent_values_to_remove,
)


class FocusTaskProgressHygienePhase20LTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.progress_source = (
            root / "backend/app/focus/task_progress.py"
        ).read_text(encoding="utf-8")
        cls.context_source = (
            root / "backend/app/focus/context.py"
        ).read_text(encoding="utf-8")

    def test_task_title_replaces_semantically_duplicate_progress_variants(self) -> None:
        canonical_task = (
            "Check the plan against this constraint: "
            "Keep the total cost under $1,000"
        )
        existing = [
            "Checked the trip plan against the $1,000 constraints.",
            "Checked the plan against the $1,000 constraint.",
        ]
        self.assertEqual(
            equivalent_values_to_remove(existing, canonical_task),
            existing,
        )

    def test_known_fact_cleanup_is_conservative(self) -> None:
        values = [
            "three days available",
            "The three available days for the trip have been confirmed.",
            "The budget is under $1,000.",
        ]
        self.assertEqual(
            duplicate_values_to_remove(values),
            ["The three available days for the trip have been confirmed."],
        )

    def test_progress_bridge_emits_read_only_hygiene_events_before_progress(self) -> None:
        source = self.progress_source
        self.assertIn("def _hygiene_removal_events(", source)
        self.assertIn("FocusEventType.LIST_ITEM_REMOVED", source)
        self.assertIn("canonical_task_titles", source)
        self.assertIn("protected_titles", source)
        self.assertIn("snapshots_by_id[task_id]", source)
        self.assertLess(
            source.index("events = _hygiene_removal_events("),
            source.index("FocusEventType.MILESTONE_COMPLETED", source.index("def _build_progress_events(")),
        )
        self.assertNotIn("MARK_FOCUS_COMPLETE", source)

    def test_context_path_clears_only_an_answered_pending_question(self) -> None:
        source = self.context_source
        self.assertIn("question_answered_by_context(", source)
        self.assertIn("FocusOperationKind.CLEAR_PENDING_QUESTION", source)
        self.assertIn('getattr(current, "pendingAction", None) is None', source)
        self.assertIn('getattr(updated, "pendingQuestion", None)', source)
        self.assertIn('getattr(updated, "nextAction", "")', source)

    def test_context_source_turn_matches_only_one_added_context_event(self) -> None:
        source = self.context_source
        matching_start = source.index("def _matching_context_events(")
        matching_end = source.index("def add_focus_context_verified(", matching_start)
        matching_block = source[matching_start:matching_end]
        self.assertIn("FocusEventType.LIST_ITEM_ADDED", matching_block)
        self.assertIn("semantically_equivalent", matching_block)
        self.assertIn("len(context_events) == 1", source)
        self.assertIn('getattr(event, "source", _CONTEXT_SOURCE)', source)


if __name__ == "__main__":
    unittest.main()
