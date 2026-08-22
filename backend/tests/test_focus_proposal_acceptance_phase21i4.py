import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.focus.models import FocusEventType, FocusStatus  # noqa: E402
from app.focus_proposal import (  # noqa: E402
    accept_pending_focus_next_action,
    clear_pending_focus_proposal,
    get_pending_focus_proposal,
    is_natural_proposal_acceptance,
    remember_focus_next_action_proposal,
)


class FocusProposalAcceptancePhase21I4Tests(unittest.TestCase):
    def setUp(self):
        clear_pending_focus_proposal()

    def tearDown(self):
        clear_pending_focus_proposal()

    @staticmethod
    def _brief_context(*, next_action=""):
        return {
            "activeFocus": {
                "focusId": "focus-cake",
                "title": "Baking a chocolate cake",
                "objective": "",
                "nextAction": next_action,
                "status": "active",
            }
        }

    @staticmethod
    def _state(*, focus_id="focus-cake", next_action="", status=FocusStatus.ACTIVE):
        return SimpleNamespace(
            focusId=focus_id,
            nextAction=next_action,
            status=status,
        )

    def test_natural_short_acceptance_language_is_supported(self):
        positives = (
            "okay let's do it",
            "yeah let's do that",
            "sounds good",
            "okay",
            "go with that",
            "let's start there",
            "go ahead",
            "do it",
        )
        for message in positives:
            with self.subTest(message=message):
                self.assertTrue(is_natural_proposal_acceptance(message))

        for message in (
            "show my tasks",
            "what is my focus",
            "actually let's work on my invoices",
            "okay but first show my calendar",
        ):
            with self.subTest(message=message):
                self.assertFalse(is_natural_proposal_acceptance(message))

    def test_daily_brief_can_remember_one_concrete_focus_next_step(self):
        proposal = remember_focus_next_action_proposal(
            self._brief_context(),
            (
                "Since your cake Focus does not have a next step yet, "
                "I'd start by choosing a chocolate cake recipe. "
                "After that, you can work through your other tasks."
            ),
        )

        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.focus_id, "focus-cake")
        self.assertEqual(proposal.next_action, "choosing a chocolate cake recipe")
        self.assertEqual(proposal.expected_next_action, "")
        self.assertIsNotNone(get_pending_focus_proposal())

    def test_ambiguous_or_existing_next_action_does_not_create_proposal(self):
        ambiguous = remember_focus_next_action_proposal(
            self._brief_context(),
            "I'd start by choosing a recipe or gathering ingredients.",
        )
        self.assertIsNone(ambiguous)
        self.assertIsNone(get_pending_focus_proposal())

        existing = remember_focus_next_action_proposal(
            self._brief_context(next_action="Preheat the oven"),
            "I'd start by choosing a recipe.",
        )
        self.assertIsNone(existing)
        self.assertIsNone(get_pending_focus_proposal())

    def test_any_unrelated_next_turn_expires_the_proposal_even_without_shadow_router(self):
        remember_focus_next_action_proposal(
            self._brief_context(),
            "I'd start by choosing a chocolate cake recipe.",
        )
        self.assertIsNotNone(get_pending_focus_proposal())

        result = accept_pending_focus_next_action("show my tasks")

        self.assertIsNone(result)
        self.assertIsNone(get_pending_focus_proposal())

    @patch("app.focus_proposal.append_events")
    @patch("app.focus_proposal.get_state")
    def test_canonical_focus_change_or_existing_next_action_blocks_acceptance(
        self,
        get_state,
        append_events,
    ):
        remember_focus_next_action_proposal(
            self._brief_context(),
            "I'd start by choosing a chocolate cake recipe.",
        )
        get_state.return_value = self._state(focus_id="different-focus")

        result = accept_pending_focus_next_action("okay let's do it")

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertFalse(result.changed)
        self.assertIn("no longer current", result.message)
        append_events.assert_not_called()
        self.assertIsNone(get_pending_focus_proposal())

    @patch("app.focus_proposal.append_events")
    @patch("app.focus_proposal.get_state")
    def test_acceptance_appends_one_canonical_next_action_event_and_verifies_it(
        self,
        get_state,
        append_events,
    ):
        remember_focus_next_action_proposal(
            self._brief_context(),
            "I'd start by choosing a chocolate cake recipe.",
        )
        get_state.side_effect = (
            self._state(next_action=""),
            self._state(next_action="choosing a chocolate cake recipe"),
        )

        result = accept_pending_focus_next_action(
            "okay let's do it",
            source_turn_id="turn-accept-cake",
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertTrue(result.changed)
        self.assertEqual(result.focus_id, "focus-cake")
        self.assertEqual(result.next_action, "choosing a chocolate cake recipe")
        self.assertIn("your Focus next step is now", result.message)
        append_events.assert_called_once()
        event = append_events.call_args.args[0][0]
        self.assertEqual(event.focusId, "focus-cake")
        self.assertEqual(event.type, FocusEventType.NEXT_ACTION_SET)
        self.assertEqual(
            event.payload,
            {"value": "choosing a chocolate cake recipe"},
        )
        self.assertEqual(event.sourceTurnId, "turn-accept-cake")
        self.assertEqual(event.source, "daily-brief-proposal-acceptance")
        self.assertIsNone(get_pending_focus_proposal())

        # The proposal was consumed before the write, so a repeated short reply
        # cannot apply the same mutation twice.
        second = accept_pending_focus_next_action("okay let's do it")
        self.assertIsNone(second)
        append_events.assert_called_once()

    def test_i4_is_wired_before_generic_conversation_and_after_daily_brief_ownership(self):
        daily_source = (BACKEND / "app" / "daily_brief.py").read_text(encoding="utf-8")
        shadow_source = (BACKEND / "app" / "routers" / "agent_shadow.py").read_text(
            encoding="utf-8"
        )
        chat_source = (BACKEND / "app" / "routers" / "chat.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("remember_focus_next_action_proposal(context, full_reply)", daily_source)
        self.assertIn('phrase the first recommendation as "I\'d start by <one action>."', daily_source)
        self.assertIn("clear_pending_focus_proposal()", daily_source)

        daily_floor_index = shadow_source.index("apply_daily_brief_ownership_floor(")
        proposal_floor_index = shadow_source.index(
            "apply_focus_proposal_ownership_floor(",
            daily_floor_index,
        )
        return_index = shadow_source.index(
            "if repaired_decision is response.decision:",
            proposal_floor_index,
        )
        self.assertLess(daily_floor_index, proposal_floor_index)
        self.assertLess(proposal_floor_index, return_index)

        proposal_index = chat_source.index("accept_pending_focus_next_action")
        brief_index = chat_source.index("is_daily_brief_request(message)", proposal_index)
        self.assertLess(proposal_index, brief_index)
        self.assertIn(
            "accept_pending_focus_next_action,\n                req.userMessage",
            chat_source,
        )


if __name__ == "__main__":
    unittest.main()
