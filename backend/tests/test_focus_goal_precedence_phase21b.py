from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"
RECEIPT = ROOT / "src" / "app" / "lib" / "focusToolReceipt.ts"
CONVERSATION_LANE = ROOT / "backend" / "app" / "conversation_lane.py"


class FocusGoalPrecedencePhase21BTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app_source = APP.read_text(encoding="utf-8")
        cls.receipt_source = RECEIPT.read_text(encoding="utf-8")
        cls.lane_source = CONVERSATION_LANE.read_text(encoding="utf-8")

    def test_verified_reused_focus_receipt_is_normalized_before_tool_card(self) -> None:
        normalize_index = self.app_source.index(
            "confirmationContent = normalizeVerifiedFocusToolReceipt("
        )
        tool_message_index = self.app_source.index(
            "const confirmationMsg = createAssistantMessage(", normalize_index
        )
        continuation_index = self.app_source.index(
            "await continueAfterVerifiedToolUpdate({", normalize_index
        )
        self.assertLess(normalize_index, tool_message_index)
        self.assertLess(normalize_index, continuation_index)

    def test_goal_noop_receipt_names_the_goal_instead_of_only_the_focus_title(self) -> None:
        self.assertIn("commandMatch.command !== 'update-focus-session'", self.receipt_source)
        self.assertIn("Focus goal already matches: ${goal}.", self.receipt_source)
        self.assertIn("Focus title already matches: ${title}.", self.receipt_source)
        self.assertIn("Focus mode already matches: ${mode}.", self.receipt_source)

    def test_receipt_normalizer_only_refines_verified_generic_reuse_text(self) -> None:
        self.assertIn("GENERIC_FOCUS_REUSED_PREFIX", self.receipt_source)
        self.assertIn("return receipt;", self.receipt_source)
        self.assertNotIn("fetch(", self.receipt_source)
        self.assertNotIn("localStorage", self.receipt_source)

    def test_current_canonical_objective_is_primary_focus_direction(self) -> None:
        self.assertIn(
            "the current canonical objective is the primary direction",
            self.lane_source,
        )
        self.assertIn(
            "pending Focus coaching question is optional advisory context, never a prerequisite",
            self.lane_source,
        )

    def test_pending_question_cannot_invent_a_blocker_before_current_goal(self) -> None:
        self.assertIn(
            'Never invent a blocker such as "first decide X" solely because a pending question exists.',
            self.lane_source,
        )
        self.assertIn(
            "If the current objective says to gather sources, draft, practice, plan, or otherwise move forward, make progress on that objective now.",
            self.lane_source,
        )


if __name__ == "__main__":
    unittest.main()
