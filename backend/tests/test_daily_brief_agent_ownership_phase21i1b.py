import unittest
from pathlib import Path

from app.daily_brief_ownership import apply_daily_brief_ownership_floor
from app.qmeet_agent_shadow import AgentShadowDecision


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = REPO_ROOT / "backend" / "app" / "routers" / "agent_shadow.py"


class DailyBriefAgentOwnershipPhase21I1BTests(unittest.TestCase):
    def _task_read_decision(self) -> AgentShadowDecision:
        return AgentShadowDecision(
            turnOwner="tasks",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="tasks",
            proposedAction="read-memory",
            proposedArguments={"scope": "global"},
            responsePlan="Read the task list.",
            confidence=0.94,
            reason="The model interpreted the request as task planning.",
        )

    def test_exact_live_day_planning_request_overrides_task_read(self):
        repaired = apply_daily_brief_ownership_floor(
            "what should I do today?",
            self._task_read_decision(),
        )

        self.assertEqual(repaired.turnOwner, "general_chat")
        self.assertEqual(repaired.disposition, "conversation")
        self.assertEqual(repaired.proposedCapability, "none")
        self.assertEqual(repaired.proposedAction, "conversation.respond")
        self.assertEqual(repaired.proposedArguments, {})
        self.assertFalse(repaired.focusRelevant)
        self.assertIn("Daily Brief", repaired.reason)

    def test_other_daily_brief_phrases_also_override_single_capability_reads(self):
        for message in (
            "plan my day",
            "what are my priorities for today?",
            "daily brief",
            "what should I work on today?",
        ):
            with self.subTest(message=message):
                repaired = apply_daily_brief_ownership_floor(
                    message,
                    self._task_read_decision(),
                )
                self.assertEqual(repaired.disposition, "conversation")
                self.assertEqual(repaired.proposedAction, "conversation.respond")

    def test_generic_focus_next_turn_is_not_stolen(self):
        original = AgentShadowDecision(
            turnOwner="focus",
            focusRelevant=True,
            disposition="conversation",
            proposedCapability="focus",
            proposedAction="focus.help",
            proposedArguments={},
            responsePlan="Continue the active Focus.",
            confidence=0.9,
            reason="Active Focus continuation.",
        )

        repaired = apply_daily_brief_ownership_floor("what should I do next?", original)
        self.assertIs(repaired, original)

    def test_explicit_task_read_is_not_stolen(self):
        original = self._task_read_decision()
        repaired = apply_daily_brief_ownership_floor("show my tasks", original)
        self.assertIs(repaired, original)

    def test_router_applies_daily_brief_floor_after_single_capability_repairs(self):
        source = ROUTER_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "from app.daily_brief_ownership import apply_daily_brief_ownership_floor",
            source,
        )
        calendar_index = source.index("apply_calendar_range_read_ownership_floor(")
        brief_index = source.index("apply_daily_brief_ownership_floor(", calendar_index)
        return_index = source.index("if repaired_decision is response.decision:", brief_index)
        self.assertLess(calendar_index, brief_index)
        self.assertLess(brief_index, return_index)


if __name__ == "__main__":
    unittest.main()
