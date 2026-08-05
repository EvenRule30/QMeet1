from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch

from app.focus.semantic_lifecycle_preflight import (
    SEMANTIC_LIFECYCLE_BRIDGE_VERSION,
    SemanticFocusLifecycleDecision,
    SemanticFocusLifecyclePreflightRequest,
    SemanticLifecycleIntent,
    classify_semantic_focus_lifecycle,
    looks_like_semantic_focus_lifecycle_mutation,
    semantic_focus_lifecycle_preflight,
)


class SemanticFocusLifecyclePreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_natural_current_focus_rename_returns_typed_update(self) -> None:
        decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.UPDATE,
            title="Treehouse planning",
            confidence=0.97,
            reason="The user changed the current Focus title.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=decision),
        ):
            result = await semantic_focus_lifecycle_preflight(
                SemanticFocusLifecyclePreflightRequest(
                    message="Call this session treehouse planning",
                    sourceTurnId="turn-update-1",
                )
            )

        self.assertEqual(result.bridgeVersion, SEMANTIC_LIFECYCLE_BRIDGE_VERSION)
        self.assertEqual(result.intent, "update")
        self.assertEqual(result.title, "Treehouse planning")
        self.assertEqual(result.sourceTurnId, "turn-update-1")

    async def test_natural_new_priority_returns_typed_start(self) -> None:
        decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.START,
            title="Quarterly review preparation",
            mode="planning",
            confidence=0.95,
            reason="The user established a different durable priority.",
        )
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=decision),
        ):
            result = await semantic_focus_lifecycle_preflight(
                SemanticFocusLifecyclePreflightRequest(
                    message="My next priority is preparing the quarterly review",
                    sourceTurnId="turn-start-1",
                )
            )

        self.assertEqual(result.intent, "start")
        self.assertEqual(result.title, "Quarterly review preparation")
        # The word "preparing" or a planning-like title must not infer mode.
        # Mode changes require explicit mode language.
        self.assertIsNone(result.mode)
        self.assertTrue(result.possibleMutation)

    async def test_low_confidence_start_is_blocked(self) -> None:
        decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.START,
            title="Possible project",
            confidence=0.61,
            reason="The wording may indicate a new project.",
        )
        with patch.dict(
            os.environ,
            {"QMEET_SEMANTIC_FOCUS_START_MIN_CONFIDENCE": "0.82"},
        ), patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=decision),
        ):
            result = await classify_semantic_focus_lifecycle(
                "Maybe my next thing is a possible project"
            )

        self.assertEqual(result.intent, SemanticLifecycleIntent.CLARIFY)

    async def test_update_without_active_focus_is_blocked(self) -> None:
        decision = SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.UPDATE,
            title="Treehouse planning",
            confidence=0.96,
            reason="The user requested a title update.",
        )
        empty_state = type(
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
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(return_value=decision),
        ), patch(
            "app.focus.semantic_lifecycle_preflight.get_state",
            return_value=empty_state,
        ):
            result = await classify_semantic_focus_lifecycle(
                "Call this session treehouse planning"
            )

        self.assertEqual(result.intent, SemanticLifecycleIntent.CLARIFY)

    async def test_classifier_failure_blocks_likely_mutation_language(self) -> None:
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ):
            result = await classify_semantic_focus_lifecycle(
                "I am done with this and want to work on the garden"
            )

        self.assertEqual(result.intent, SemanticLifecycleIntent.CLARIFY)
        self.assertIn("failed safely", result.reason)

    async def test_classifier_failure_leaves_unrelated_chat_alone(self) -> None:
        with patch(
            "app.focus.semantic_lifecycle_preflight._classify_with_model",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ):
            result = await classify_semantic_focus_lifecycle(
                "Compare cedar and pine for outdoor use"
            )

        self.assertEqual(result.intent, SemanticLifecycleIntent.NOT_LIFECYCLE)

    def test_safety_fallback_recognizes_update_and_start_language(self) -> None:
        positives = [
            "Call this session treehouse planning",
            "Make the goal of this work choose the materials",
            "Start a focus for writing the report",
            "Let's work on planning my vacation",
            "My next priority is preparing the quarterly review",
        ]
        for message in positives:
            with self.subTest(message=message):
                self.assertTrue(
                    looks_like_semantic_focus_lifecycle_mutation(message)
                )

    def test_safety_fallback_does_not_authorize_help_or_negation(self) -> None:
        negatives = [
            "Help me plan my vacation",
            "Give me ideas for naming my focus",
            "Don't start a new focus",
            "Can a focus be renamed?",
            "Compare cedar and pine",
        ]
        for message in negatives:
            with self.subTest(message=message):
                self.assertFalse(
                    looks_like_semantic_focus_lifecycle_mutation(message)
                )


if __name__ == "__main__":
    unittest.main()
