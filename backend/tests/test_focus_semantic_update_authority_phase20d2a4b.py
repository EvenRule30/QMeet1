from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.focus.models import FocusState, FocusStatus
from app.focus import semantic_update_intent as intent_module
from app.focus.semantic_update_intent import (
    SemanticFocusUpdateDecision,
    SemanticUpdateIntent,
    clear_semantic_update_decision_cache,
    get_semantic_focus_update_decision,
)


ACTIVE_STATE = FocusState(
    focusId="focus-treehouse",
    title="building a treehouse",
    objective="",
    status=FocusStatus.ACTIVE,
    tags=["mode:general"],
)


class SemanticFocusUpdateAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        clear_semantic_update_decision_cache()

    async def asyncTearDown(self) -> None:
        clear_semantic_update_decision_cache()

    async def test_high_confidence_title_update_is_preserved(self) -> None:
        raw = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.UPDATE,
            title="designing a treehouse",
            confidence=0.94,
            reason="Rename request.",
        )
        with (
            patch.object(intent_module, "get_state", return_value=ACTIVE_STATE),
            patch.object(
                intent_module,
                "_classify_with_model",
                new=AsyncMock(return_value=raw),
            ),
        ):
            decision = await get_semantic_focus_update_decision(
                "rename my focus to designing a treehouse",
                source_turn_id="turn-title",
            )

        self.assertEqual(decision.intent, SemanticUpdateIntent.UPDATE)
        self.assertEqual(decision.title, "designing a treehouse")

    async def test_low_confidence_update_becomes_clarification(self) -> None:
        raw = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.UPDATE,
            title="treehouse thing",
            confidence=0.4,
            reason="Uncertain.",
        )
        with (
            patch.object(intent_module, "get_state", return_value=ACTIVE_STATE),
            patch.object(
                intent_module,
                "_classify_with_model",
                new=AsyncMock(return_value=raw),
            ),
        ):
            decision = await get_semantic_focus_update_decision(
                "change this to the treehouse thing",
                source_turn_id="turn-low",
            )

        self.assertEqual(decision.intent, SemanticUpdateIntent.CLARIFY)
        self.assertFalse(decision.has_changes())

    async def test_no_open_focus_blocks_update(self) -> None:
        inactive_state = ACTIVE_STATE.model_copy(
            update={"status": FocusStatus.COMPLETE}
        )
        raw = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.UPDATE,
            title="new title",
            confidence=0.95,
            reason="Rename request.",
        )
        with (
            patch.object(intent_module, "get_state", return_value=inactive_state),
            patch.object(
                intent_module,
                "_classify_with_model",
                new=AsyncMock(return_value=raw),
            ),
        ):
            decision = await get_semantic_focus_update_decision(
                "rename the focus to new title",
                source_turn_id="turn-inactive",
            )

        self.assertEqual(decision.intent, SemanticUpdateIntent.CLARIFY)

    async def test_classifier_failure_blocks_likely_mutation_language(self) -> None:
        with (
            patch.object(intent_module, "get_state", return_value=ACTIVE_STATE),
            patch.object(
                intent_module,
                "_classify_with_model",
                new=AsyncMock(side_effect=RuntimeError("offline")),
            ),
        ):
            decision = await get_semantic_focus_update_decision(
                "call this session treehouse planning",
                source_turn_id="turn-failure",
            )

        self.assertEqual(decision.intent, SemanticUpdateIntent.CLARIFY)

    async def test_classifier_failure_does_not_capture_unrelated_chat(self) -> None:
        with (
            patch.object(intent_module, "get_state", return_value=ACTIVE_STATE),
            patch.object(
                intent_module,
                "_classify_with_model",
                new=AsyncMock(side_effect=RuntimeError("offline")),
            ),
        ):
            decision = await get_semantic_focus_update_decision(
                "help me compare cedar and pine",
                source_turn_id="turn-chat",
            )

        self.assertEqual(decision.intent, SemanticUpdateIntent.NOT_UPDATE)

    async def test_same_turn_shares_one_model_call(self) -> None:
        raw = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.UPDATE,
            title="treehouse planning",
            confidence=0.96,
            reason="Rename request.",
        )
        classifier = AsyncMock(return_value=raw)
        with (
            patch.object(intent_module, "get_state", return_value=ACTIVE_STATE),
            patch.object(intent_module, "_classify_with_model", new=classifier),
        ):
            first, second = await asyncio.gather(
                get_semantic_focus_update_decision(
                    "call this session treehouse planning",
                    source_turn_id="turn-shared",
                ),
                get_semantic_focus_update_decision(
                    "call this session treehouse planning",
                    source_turn_id="turn-shared",
                ),
            )

        self.assertEqual(first.title, "treehouse planning")
        self.assertEqual(second.title, "treehouse planning")
        self.assertEqual(classifier.await_count, 1)


if __name__ == "__main__":
    unittest.main()
