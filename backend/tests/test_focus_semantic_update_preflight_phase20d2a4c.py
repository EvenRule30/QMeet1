from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.focus.semantic_update_intent import (
    BRIDGE_VERSION,
    SemanticFocusUpdateDecision,
    SemanticUpdateIntent,
)
from app.focus.semantic_update_preflight import (
    SemanticFocusUpdatePreflightRequest,
    semantic_focus_update_preflight,
)


class SemanticFocusUpdatePreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_returns_typed_fields_without_success_prose(self) -> None:
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.UPDATE,
            title="treehouse construction",
            objective="choose the building materials",
            objectiveSpecified=True,
            mode="planning",
            confidence=0.97,
            reason="Current-Focus update.",
        )
        with patch(
            "app.focus.semantic_update_preflight.get_semantic_focus_update_decision",
            new=AsyncMock(return_value=decision),
        ):
            result = await semantic_focus_update_preflight(
                SemanticFocusUpdatePreflightRequest(
                    message="call this session treehouse construction and make the goal choose the building materials",
                    sourceTurnId="turn-update",
                )
            )

        self.assertEqual(BRIDGE_VERSION, "phase20d2a4c")
        self.assertEqual(result.intent, "update")
        self.assertTrue(result.possibleUpdate)
        self.assertEqual(result.title, "treehouse construction")
        self.assertEqual(result.objective, "choose the building materials")
        self.assertTrue(result.objectiveSpecified)
        self.assertEqual(result.mode, "planning")
        self.assertEqual(result.message, "")

    async def test_clarification_blocks_fallthrough(self) -> None:
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.CLARIFY,
            confidence=0.55,
            reason="Missing requested value.",
        )
        with patch(
            "app.focus.semantic_update_preflight.get_semantic_focus_update_decision",
            new=AsyncMock(return_value=decision),
        ):
            result = await semantic_focus_update_preflight(
                SemanticFocusUpdatePreflightRequest(
                    message="change this focus",
                    sourceTurnId="turn-clarify",
                )
            )

        self.assertEqual(result.intent, "clarify")
        self.assertTrue(result.possibleUpdate)
        self.assertIn("Focus was not changed", result.message)

    async def test_unrelated_chat_remains_not_update(self) -> None:
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.NOT_UPDATE,
            confidence=0.99,
            reason="The user requested design advice.",
        )
        with patch(
            "app.focus.semantic_update_preflight.get_semantic_focus_update_decision",
            new=AsyncMock(return_value=decision),
        ):
            result = await semantic_focus_update_preflight(
                SemanticFocusUpdatePreflightRequest(
                    message="help me compare cedar and pine",
                    sourceTurnId="turn-chat",
                )
            )

        self.assertEqual(result.intent, "not_update")
        self.assertFalse(result.possibleUpdate)
        self.assertEqual(result.title, "")
        self.assertFalse(result.objectiveSpecified)


if __name__ == "__main__":
    unittest.main()
