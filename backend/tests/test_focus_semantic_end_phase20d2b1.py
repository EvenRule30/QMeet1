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
            "title": "Treehouse planning",
            "objective": "Choose the building materials",
            "tags": ["mode:planning"],
            "status": "active",
        },
    )()


def _inactive_state() -> object:
    return type(
        "State",
        (),
        {
            "focusId": "",
            "title": "",
            "objective": "",
            "tags": [],
            "status": "inactive",
        },
    )()


class SemanticFocusEndPhase20D2B1Tests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_end_overrides_model_not_lifecycle(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.NOT_LIFECYCLE,
            confidence=0.91,
            reason="The model missed the terminal instruction.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            decision = await classify_semantic_focus_lifecycle("End my focus")

        self.assertEqual(decision.intent, SemanticLifecycleIntent.END)
        self.assertFalse(decision.forceEnd)
        self.assertGreaterEqual(decision.confidence, 0.95)

    async def test_explicit_completion_overrides_model_end(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.END,
            confidence=0.9,
            reason="The model chose a generic terminal transition.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            decision = await classify_semantic_focus_lifecycle(
                "I completed this focus"
            )

        self.assertEqual(decision.intent, SemanticLifecycleIntent.COMPLETE)
        self.assertFalse(decision.forceEnd)

    async def test_complete_focus_anyway_sets_force_end(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.COMPLETE,
            confidence=0.98,
            reason="The user explicitly completed the Focus.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            decision = await classify_semantic_focus_lifecycle(
                "Complete this focus anyway"
            )

        self.assertEqual(decision.intent, SemanticLifecycleIntent.COMPLETE)
        self.assertTrue(decision.forceEnd)

    async def test_replacement_phrase_is_not_misclassified_as_completion(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.START,
            title="Working on the garden",
            confidence=0.97,
            reason="The user established a new durable context.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            decision = await classify_semantic_focus_lifecycle(
                "I am done with this topic and want to work on the garden"
            )

        self.assertEqual(decision.intent, SemanticLifecycleIntent.START)
        self.assertEqual(decision.title, "Working on the garden")

    async def test_summary_and_end_is_blocked_before_model_execution(self) -> None:
        classifier = AsyncMock(
            side_effect=AssertionError("Compound summary/end must be blocked first.")
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=classifier,
        ):
            result = await semantic_focus_lifecycle_preflight(
                SemanticFocusLifecyclePreflightRequest(
                    message="Save a summary and end this focus",
                    sourceTurnId="turn-summary-end",
                )
            )

        self.assertEqual(result.bridgeVersion, SEMANTIC_LIFECYCLE_BRIDGE_VERSION)
        self.assertEqual(result.intent, "clarify")
        self.assertTrue(result.possibleMutation)
        self.assertIn("separate verified receipts", result.message)
        classifier.assert_not_awaited()

    async def test_negated_end_is_acknowledged_without_model_call(self) -> None:
        classifier = AsyncMock(
            side_effect=AssertionError("Explicit cancellation must not call the model.")
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=classifier,
        ):
            result = await semantic_focus_lifecycle_preflight(
                SemanticFocusLifecyclePreflightRequest(
                    message="Don't end my focus",
                    sourceTurnId="turn-cancel-end",
                )
            )

        self.assertEqual(result.intent, "cancelled")
        self.assertEqual(result.message, "Okay—no Focus change was made.")
        self.assertFalse(result.possibleMutation)
        classifier.assert_not_awaited()

    async def test_terminal_request_without_open_focus_is_blocked(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.END,
            confidence=0.98,
            reason="The user requested an end.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_inactive_state(),
        ):
            decision = await classify_semantic_focus_lifecycle("End my focus")

        self.assertEqual(decision.intent, SemanticLifecycleIntent.CLARIFY)
        self.assertIn("no active canonical Focus", decision.reason)

    async def test_preflight_returns_typed_completed_disposition(self) -> None:
        model_decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.COMPLETE,
            forceEnd=True,
            confidence=0.99,
            reason="The user explicitly completed it without a summary.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=model_decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=_active_state(),
        ):
            result = await semantic_focus_lifecycle_preflight(
                SemanticFocusLifecyclePreflightRequest(
                    message="Complete this focus anyway",
                    sourceTurnId="turn-complete-anyway",
                )
            )

        self.assertEqual(result.intent, "complete")
        self.assertTrue(result.forceEnd)
        self.assertFalse(result.summaryRequested)
        self.assertEqual(result.sourceTurnId, "turn-complete-anyway")


if __name__ == "__main__":
    unittest.main()
