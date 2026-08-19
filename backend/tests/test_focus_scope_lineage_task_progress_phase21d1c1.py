from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLANNER = ROOT / "backend" / "app" / "focus" / "planner.py"
TASK_PROGRESS = ROOT / "backend" / "app" / "focus" / "task_progress.py"


class FocusScopeLineageTaskProgressPhase21D1CTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.planner_source = PLANNER.read_text(encoding="utf-8")
        cls.progress_source = TASK_PROGRESS.read_text(encoding="utf-8")

    def test_replacement_files_remain_valid_python(self) -> None:
        ast.parse(self.planner_source)
        ast.parse(self.progress_source)

    def test_planner_recent_event_evidence_is_scoped_to_current_focus(self) -> None:
        self.assertIn(
            'def _recent_event_summary(focus_id: str = "")',
            self.planner_source,
        )
        self.assertIn(
            "if normalized_focus_id and event.focusId != normalized_focus_id:",
            self.planner_source,
        )
        self.assertIn(
            '"recentFocusEvents": _recent_event_summary(state.focusId)',
            self.planner_source,
        )

    def test_unscoped_recent_event_helper_remains_available_for_diagnostics(self) -> None:
        summary_start = self.planner_source.index(
            'def _recent_event_summary(focus_id: str = "")'
        )
        planner_input_start = self.planner_source.index(
            "def _planner_input(",
            summary_start,
        )
        summary_block = self.planner_source[summary_start:planner_input_start]

        self.assertIn("normalized_focus_id = focus_id.strip()", summary_block)
        self.assertIn("for event in list_events(limit=24):", summary_block)
        self.assertIn(
            "if normalized_focus_id and event.focusId != normalized_focus_id:",
            summary_block,
        )

    def test_automatic_follow_up_is_identified_by_canonical_question_target(self) -> None:
        helper_start = self.progress_source.index(
            "def _supports_question_clear_event("
        )
        helper_end = self.progress_source.index(
            "def _restore_memory_unlocked(",
            helper_start,
        )
        helper = self.progress_source[helper_start:helper_end]

        self.assertIn(
            'getattr(FocusEventType, "QUESTION_CLEARED", None)',
            helper,
        )
        self.assertIn("focus_state.pendingQuestion", helper)
        self.assertIn("pending_question.target", helper)
        self.assertIn('== "follow_up"', helper)
        self.assertIn(
            "def _should_repair_automatic_follow_up(",
            helper,
        )
        self.assertIn(
            "_supports_question_clear_event()",
            helper,
        )

    def test_pending_action_still_outranks_task_sequence(self) -> None:
        start = self.progress_source.index("def _build_progress_events(")
        end = self.progress_source.index(
            "def _verify_progress_unlocked(",
            start,
        )
        block = self.progress_source[start:end]

        pending_action = block.index("if focus_state.pendingAction is not None:")
        explicit_question = block.index(
            "focus_state.pendingQuestion is not None",
            pending_action,
        )
        auto_question = block.index(
            "if _should_repair_automatic_follow_up(focus_state):",
            explicit_question,
        )
        next_action = block.index(
            "FocusEventType.NEXT_ACTION_SET",
            auto_question,
        )

        self.assertLess(pending_action, explicit_question)
        self.assertLess(explicit_question, auto_question)
        self.assertLess(auto_question, next_action)

    def test_explicit_focus_question_is_preserved(self) -> None:
        start = self.progress_source.index("def _build_progress_events(")
        end = self.progress_source.index(
            "def _verify_progress_unlocked(",
            start,
        )
        block = self.progress_source[start:end]

        self.assertIn(
            "focus_state.pendingQuestion is not None\n"
            "        and not _should_repair_automatic_follow_up(focus_state)",
            block,
        )
        self.assertIn("FocusEventType.FIELD_SET", block)
        self.assertIn(
            'payload={"field": "status", "value": "clarifying"}',
            block,
        )

    def test_new_progress_clears_only_automatic_follow_up_before_advancing(self) -> None:
        start = self.progress_source.index("def _build_progress_events(")
        end = self.progress_source.index(
            "def _verify_progress_unlocked(",
            start,
        )
        block = self.progress_source[start:end]

        auto_question = block.index(
            "if _should_repair_automatic_follow_up(focus_state):"
        )
        cleared = block.index(
            "FocusEventType.QUESTION_CLEARED",
            auto_question,
        )
        next_action = block.index(
            "FocusEventType.NEXT_ACTION_SET",
            cleared,
        )

        self.assertLess(auto_question, cleared)
        self.assertLess(cleared, next_action)

    def test_verifier_has_explicit_repair_mode(self) -> None:
        verify_start = self.progress_source.index(
            "def _verify_progress_unlocked("
        )
        verify_end = self.progress_source.index(
            "def _verification_passed(",
            verify_start,
        )
        verify_block = self.progress_source[verify_start:verify_end]

        self.assertIn(
            "repair_automatic_follow_up: bool = False",
            verify_block,
        )
        self.assertIn(
            "repair_follow_up = (\n"
            "        repair_automatic_follow_up\n"
            "        and _should_repair_automatic_follow_up(state_before)",
            verify_block,
        )
        self.assertIn(
            "focus_state.pendingQuestion is None",
            verify_block,
        )
        self.assertIn(
            "focus_state.nextAction == expected_next_action",
            verify_block,
        )

    def test_reused_progress_keeps_historical_semantics_but_new_write_repairs(self) -> None:
        reused_marker = self.progress_source.index(
            "if all_existing_turn_events:"
        )
        write_marker = self.progress_source.index(
            "next_memory_tasks = _write_completed_tasks_unlocked(",
            reused_marker,
        )
        reused_block = self.progress_source[reused_marker:write_marker]

        self.assertIn(
            "verification, reused_state = _verify_progress_unlocked(",
            reused_block,
        )
        self.assertNotIn(
            "repair_automatic_follow_up=",
            reused_block,
        )

        new_write_block = self.progress_source[write_marker:]
        self.assertIn(
            "repair_automatic_follow_up = (",
            new_write_block,
        )
        self.assertIn(
            "repair_automatic_follow_up=repair_automatic_follow_up",
            new_write_block,
        )

    def test_new_progress_uses_linked_task_sequence_after_auto_follow_up(self) -> None:
        write_marker = self.progress_source.index(
            "next_memory_tasks = _write_completed_tasks_unlocked("
        )
        new_write_block = self.progress_source[write_marker:]

        self.assertIn(
            "next_action = (\n"
            '                    _normalize_text(remaining[0].get("title", ""))',
            new_write_block,
        )
        self.assertIn(
            "and not repair_automatic_follow_up",
            new_write_block,
        )
        self.assertIn(
            "else next_action",
            new_write_block,
        )

    def test_older_event_vocabularies_preserve_pending_question_behavior(self) -> None:
        helper_start = self.progress_source.index(
            "def _supports_question_clear_event("
        )
        helper_end = self.progress_source.index(
            "def _restore_memory_unlocked(",
            helper_start,
        )
        helper = self.progress_source[helper_start:helper_end]

        self.assertIn(
            'return getattr(FocusEventType, "QUESTION_CLEARED", None) is not None',
            helper,
        )
        build_start = self.progress_source.index("def _build_progress_events(")
        build_end = self.progress_source.index(
            "def _verify_progress_unlocked(",
            build_start,
        )
        build_block = self.progress_source[build_start:build_end]
        self.assertIn(
            "not _should_repair_automatic_follow_up(focus_state)",
            build_block,
        )


if __name__ == "__main__":
    unittest.main()
