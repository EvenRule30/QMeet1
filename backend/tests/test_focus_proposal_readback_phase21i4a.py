import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.focus_proposal_ownership import apply_focus_proposal_ownership_floor  # noqa: E402


class _Decision:
    def __init__(self, *, confidence=0.4):
        self.confidence = confidence
        self.updates = None

    def model_copy(self, *, update):
        clone = _Decision(confidence=update.get("confidence", self.confidence))
        clone.updates = update
        return clone


class FocusProposalReadbackPhase21I4ATests(unittest.TestCase):
    def test_orphaned_natural_acceptance_is_conversation_not_focus_mutation(self):
        decision = _Decision(confidence=0.72)
        with (
            patch(
                "app.focus_proposal_ownership.prepare_focus_proposal_turn",
                return_value=False,
            ),
            patch(
                "app.focus_proposal_ownership.is_natural_proposal_acceptance",
                return_value=True,
            ),
        ):
            repaired = apply_focus_proposal_ownership_floor(
                "okay lets do it",
                decision,
            )

        self.assertIsNot(repaired, decision)
        self.assertEqual(repaired.updates["turnOwner"], "general_chat")
        self.assertFalse(repaired.updates["focusRelevant"])
        self.assertEqual(repaired.updates["disposition"], "conversation")
        self.assertEqual(repaired.updates["proposedCapability"], "none")
        self.assertEqual(repaired.updates["proposedAction"], "conversation.respond")
        self.assertIn("do not mutate Focus", repaired.updates["responsePlan"])

    def test_fresh_acceptance_still_remains_focus_owned(self):
        decision = _Decision(confidence=0.72)
        with patch(
            "app.focus_proposal_ownership.prepare_focus_proposal_turn",
            return_value=True,
        ):
            repaired = apply_focus_proposal_ownership_floor(
                "okay lets do it",
                decision,
            )

        self.assertEqual(repaired.updates["turnOwner"], "focus")
        self.assertTrue(repaired.updates["focusRelevant"])
        self.assertEqual(repaired.updates["proposedCapability"], "focus")
        self.assertEqual(repaired.updates["proposedAction"], "focus.help")

    def test_non_acceptance_is_not_stolen(self):
        decision = _Decision(confidence=0.72)
        with (
            patch(
                "app.focus_proposal_ownership.prepare_focus_proposal_turn",
                return_value=False,
            ),
            patch(
                "app.focus_proposal_ownership.is_natural_proposal_acceptance",
                return_value=False,
            ),
        ):
            repaired = apply_focus_proposal_ownership_floor("show my tasks", decision)

        self.assertIs(repaired, decision)

    def test_focus_readout_uses_canonical_state_and_surfaces_next_action(self):
        helper = (
            ROOT / "src" / "app" / "lib" / "canonicalFocusReadout.ts"
        ).read_text(encoding="utf-8")
        memory = (
            ROOT / "src" / "app" / "commandHandlers" / "memory.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("/api/focus/state", helper)
        self.assertIn("nextAction", helper)
        self.assertIn("Next step: ${nextAction}.", helper)
        self.assertIn("readVerifiedFocusProjection", helper)

        self.assertIn(
            "import { readCanonicalFocusReadout } from '../lib/canonicalFocusReadout';",
            memory,
        )
        self.assertIn("commandMatch.command === 'read-focus-session'", memory)
        self.assertIn("await readCanonicalFocusReadout()", memory)
        self.assertIn("return handleMemoryCommandCore(commandMatch, deps);", memory)

    def test_canonical_focus_read_is_read_only(self):
        helper = (
            ROOT / "src" / "app" / "lib" / "canonicalFocusReadout.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("method: 'GET'", helper)
        self.assertNotIn("method: 'POST'", helper)
        self.assertNotIn("method: 'PATCH'", helper)
        self.assertNotIn("method: 'DELETE'", helper)


if __name__ == "__main__":
    unittest.main()
