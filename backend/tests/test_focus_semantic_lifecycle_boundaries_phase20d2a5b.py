from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.focus.semantic_lifecycle_preflight import (
    SEMANTIC_LIFECYCLE_BRIDGE_VERSION,
    SemanticFocusLifecycleDecision,
    SemanticFocusLifecyclePreflightRequest,
    SemanticLifecycleIntent,
    classify_semantic_focus_lifecycle,
    semantic_focus_lifecycle_preflight,
)


def _active_state() -> object:
    return type(
        "State",
        (),
        {
            "focusId": "focus-current",
            "title": "Building the prototype",
            "objective": "Complete the first working version",
            "tags": ["mode:general"],
            "status": "active",
        },
    )()


class SemanticLifecycleBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_switch_my_focus_is_replacement_even_if_model_says_update(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.UPDATE,
            title="Studying for the exam",
            confidence=0.96,
            reason="The user changed what they are focusing on.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            decision = await classify_semantic_focus_lifecycle(
                "Switch my focus to studying for the exam"
            )

        self.assertEqual(decision.intent, SemanticLifecycleIntent.START)
        self.assertEqual(decision.title, "Studying for the exam")
        self.assertIsNone(decision.mode)

    async def test_title_word_planning_does_not_change_mode(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.UPDATE,
            title="Treehouse planning",
            mode="planning",
            confidence=0.98,
            reason="The user renamed the current session.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            decision = await classify_semantic_focus_lifecycle(
                "Call this session treehouse planning"
            )

        self.assertEqual(decision.intent, SemanticLifecycleIntent.UPDATE)
        self.assertEqual(decision.title, "Treehouse planning")
        self.assertIsNone(decision.mode)

    async def test_explicit_mode_language_preserves_mode_update(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.UPDATE,
            mode="planning",
            confidence=0.99,
            reason="The user explicitly requested planning mode.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            decision = await classify_semantic_focus_lifecycle(
                "Switch this work into planning mode"
            )

        self.assertEqual(decision.intent, SemanticLifecycleIntent.UPDATE)
        self.assertEqual(decision.mode, "planning")

    async def test_focus_mode_language_is_update_not_replacement(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.START,
            title="Research",
            mode="research",
            confidence=0.97,
            reason="The user used switch language.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            decision = await classify_semantic_focus_lifecycle(
                "Switch my focus into research mode"
            )

        self.assertEqual(decision.intent, SemanticLifecycleIntent.UPDATE)
        self.assertEqual(decision.mode, "research")

    async def test_current_session_title_language_corrects_false_start(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.START,
            title="Treehouse construction",
            confidence=0.96,
            reason="The model overclassified a title change.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            decision = await classify_semantic_focus_lifecycle(
                "The work I am doing should be called treehouse construction"
            )

        self.assertEqual(decision.intent, SemanticLifecycleIntent.UPDATE)
        self.assertEqual(decision.title, "Treehouse construction")

    async def test_negated_start_is_acknowledged_without_model_call(self) -> None:
        classifier = AsyncMock(
            side_effect=AssertionError("The model should not classify an explicit cancellation.")
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=classifier,
        ):
            result = await semantic_focus_lifecycle_preflight(
                SemanticFocusLifecyclePreflightRequest(
                    message="Don't start a new Focus",
                    sourceTurnId="turn-cancel-1",
                )
            )

        self.assertEqual(result.bridgeVersion, SEMANTIC_LIFECYCLE_BRIDGE_VERSION)
        self.assertEqual(result.intent, "cancelled")
        self.assertEqual(result.message, "Okay—no Focus change was made.")
        self.assertFalse(result.possibleMutation)
        classifier.assert_not_awaited()

    async def test_capability_question_remains_non_lifecycle(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.NOT_LIFECYCLE,
            confidence=0.99,
            reason="The user asked a capability question.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ):
            decision = await classify_semantic_focus_lifecycle(
                "Can a Focus be renamed?"
            )

        self.assertEqual(decision.intent, SemanticLifecycleIntent.NOT_LIFECYCLE)


if __name__ == "__main__":
    unittest.main()
