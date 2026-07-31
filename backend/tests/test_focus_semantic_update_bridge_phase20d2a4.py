from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.focus.models import (
    FocusField,
    FocusOperation,
    FocusOperationKind,
    ResponseIntent,
    TurnPlan,
    TurnRoute,
)
from app.focus.semantic_update_bridge import (
    extract_semantic_focus_update,
    semantic_focus_update_command,
)
from app.focus.semantic_update_intent import (
    BRIDGE_VERSION,
    SemanticFocusUpdateDecision,
    SemanticUpdateIntent,
)


def _plan(
    *operations: FocusOperation,
    confidence: float = 0.96,
    response_text: str = "",
) -> TurnPlan:
    return TurnPlan(
        route=TurnRoute.FOCUS_ACTION,
        focusOperations=list(operations),
        responseIntent=ResponseIntent(
            acknowledge=response_text,
            answerDirectly=False,
            attachToFocus=True,
        ),
        confidence=confidence,
        reason="Semantic update extraction test plan.",
    )


class SemanticFocusUpdateExtractionTests(unittest.TestCase):
    """Keep the original planner-plan extractor covered for diagnostics."""

    def test_title_set_becomes_typed_update(self) -> None:
        update = extract_semantic_focus_update(
            _plan(
                FocusOperation(
                    kind=FocusOperationKind.SET_FIELD,
                    field=FocusField.TITLE,
                    value="chopping down a branch",
                    confidence=0.97,
                )
            )
        )

        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(update.title, "chopping down a branch")
        self.assertFalse(update.objective_specified)
        self.assertIsNone(update.mode)

    def test_rescope_can_extract_title_objective_and_mode(self) -> None:
        update = extract_semantic_focus_update(
            _plan(
                FocusOperation(
                    kind=FocusOperationKind.RESCOPE_FOCUS,
                    title="build a train station with legos",
                    objective="finish the central platform",
                    tags=["mode:planning"],
                    confidence=0.95,
                )
            )
        )

        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(update.title, "build a train station with legos")
        self.assertEqual(update.objective, "finish the central platform")
        self.assertTrue(update.objective_specified)
        self.assertEqual(update.mode, "planning")

    def test_start_end_and_complete_never_extract_as_update(self) -> None:
        for kind in (
            FocusOperationKind.START_FOCUS,
            FocusOperationKind.END_FOCUS,
            FocusOperationKind.MARK_FOCUS_COMPLETE,
        ):
            with self.subTest(kind=kind):
                operation = FocusOperation(
                    kind=kind,
                    title=(
                        "different work"
                        if kind == FocusOperationKind.START_FOCUS
                        else ""
                    ),
                    confidence=0.99,
                )
                self.assertIsNone(extract_semantic_focus_update(_plan(operation)))

    def test_conflicting_titles_are_rejected(self) -> None:
        self.assertIsNone(
            extract_semantic_focus_update(
                _plan(
                    FocusOperation(
                        kind=FocusOperationKind.SET_FIELD,
                        field=FocusField.TITLE,
                        value="first title",
                        confidence=0.95,
                    ),
                    FocusOperation(
                        kind=FocusOperationKind.SET_FIELD,
                        field=FocusField.TITLE,
                        value="second title",
                        confidence=0.95,
                    ),
                )
            )
        )


class SemanticFocusUpdateCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_natural_language_variants_share_one_typed_contract(self) -> None:
        variants = (
            "rename my focus to chopping down a branch",
            "call this session chopping down a branch",
            "the work I am doing should be called chopping down a branch",
            "change what I am working on to chopping down a branch",
        )
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.UPDATE,
            title="chopping down a branch",
            confidence=0.98,
            reason="The user renamed the current Focus.",
        )

        with patch(
            "app.focus.semantic_update_bridge.get_semantic_focus_update_decision",
            new=AsyncMock(return_value=decision),
        ) as classify:
            results = [
                await semantic_focus_update_command(
                    message,
                    source_turn_id=f"turn-{index}",
                )
                for index, message in enumerate(variants)
            ]

        self.assertEqual(classify.await_count, len(variants))
        for result in results:
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["intent"], "command")
            self.assertEqual(result["action"], "update_focus_session")
            self.assertEqual(
                result["frontendCommand"],
                "apply semantic focus update",
            )
            self.assertEqual(
                result["payload"]["title"],
                "chopping down a branch",
            )
            self.assertEqual(
                result["payload"]["semanticBridgeVersion"],
                BRIDGE_VERSION,
            )

    async def test_goal_and_mode_are_typed_without_generated_english(self) -> None:
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.UPDATE,
            objective="choose the building materials",
            objectiveSpecified=True,
            mode="planning",
            confidence=0.94,
            reason="The user changed the goal and mode.",
        )
        with patch(
            "app.focus.semantic_update_bridge.get_semantic_focus_update_decision",
            new=AsyncMock(return_value=decision),
        ):
            result = await semantic_focus_update_command(
                "make the goal of this work choose the building materials and switch this work into planning mode",
                source_turn_id="turn-goal-mode",
            )

        assert result is not None
        self.assertNotIn("title", result["payload"])
        self.assertEqual(
            result["payload"]["goal"],
            "choose the building materials",
        )
        self.assertEqual(result["payload"]["mode"], "planning")

    async def test_ambiguous_update_is_blocked_instead_of_sent_to_chat(self) -> None:
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.CLARIFY,
            confidence=0.61,
            reason="The requested new value was ambiguous.",
        )
        with patch(
            "app.focus.semantic_update_bridge.get_semantic_focus_update_decision",
            new=AsyncMock(return_value=decision),
        ):
            result = await semantic_focus_update_command(
                "change the focus somehow",
                source_turn_id="turn-ambiguous",
            )

        assert result is not None
        self.assertTrue(result["payload"]["semanticBridgeBlocked"])
        self.assertIn("could not verify", result["payload"]["message"])

    async def test_question_remains_normal_chat(self) -> None:
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.NOT_UPDATE,
            confidence=0.98,
            reason="The user asked for naming advice.",
        )
        with patch(
            "app.focus.semantic_update_bridge.get_semantic_focus_update_decision",
            new=AsyncMock(return_value=decision),
        ):
            result = await semantic_focus_update_command(
                "what should I rename my focus?",
                source_turn_id="turn-question",
            )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
