from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.focus.models import FocusState, FocusStatus, ObserveTurnRequest
from app.focus.semantic_update_intent import (
    SemanticFocusUpdateDecision,
    SemanticUpdateIntent,
)
from app.focus import semantic_update_observation as observation_module


ACTIVE_STATE = FocusState(
    focusId="focus-treehouse",
    title="building a treehouse",
    objective="",
    status=FocusStatus.ACTIVE,
    tags=["mode:general"],
)


class SemanticFocusUpdateObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_decision_is_recorded_but_not_applied(self) -> None:
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.UPDATE,
            title="treehouse construction",
            confidence=0.95,
            reason="The user renamed the current Focus.",
        )
        original = AsyncMock()
        recorded = []

        with (
            patch.object(
                observation_module,
                "_ORIGINAL_OBSERVE_TURN",
                new=original,
            ),
            patch.object(
                observation_module,
                "get_semantic_focus_update_decision",
                new=AsyncMock(return_value=decision),
            ),
            patch.object(observation_module, "get_state", return_value=ACTIVE_STATE),
            patch.object(observation_module, "has_turn", return_value=False),
            patch.object(
                observation_module,
                "append_events",
                side_effect=lambda events: recorded.extend(events),
            ),
        ):
            plan, state = (
                await observation_module._observe_turn_with_semantic_update_deferral(
                    ObserveTurnRequest(
                        message="the work I am doing should be called treehouse construction",
                        source="command-interpret-shadow",
                        apply=True,
                    ),
                    turn_id="turn-observe-update",
                )
            )

        self.assertEqual(state.focusId, ACTIVE_STATE.focusId)
        self.assertEqual(len(plan.focusOperations), 1)
        self.assertEqual(plan.focusOperations[0].value, "treehouse construction")
        self.assertEqual(original.await_count, 0)
        self.assertEqual(len(recorded), 1)
        policy = recorded[0].payload["executionPolicy"]
        self.assertTrue(policy["nativeFocusUpdateDeferred"])
        self.assertTrue(policy["responseCandidateSuppressed"])
        self.assertEqual(policy["semanticIntent"], "update")

    async def test_clarification_decision_is_also_deferred(self) -> None:
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.CLARIFY,
            confidence=0.52,
            reason="Missing requested title.",
        )
        recorded = []
        with (
            patch.object(
                observation_module,
                "_ORIGINAL_OBSERVE_TURN",
                new=AsyncMock(),
            ) as original,
            patch.object(
                observation_module,
                "get_semantic_focus_update_decision",
                new=AsyncMock(return_value=decision),
            ),
            patch.object(observation_module, "get_state", return_value=ACTIVE_STATE),
            patch.object(observation_module, "has_turn", return_value=False),
            patch.object(
                observation_module,
                "append_events",
                side_effect=lambda events: recorded.extend(events),
            ),
        ):
            await observation_module._observe_turn_with_semantic_update_deferral(
                ObserveTurnRequest(
                    message="rename this",
                    source="command-interpret-shadow",
                    apply=True,
                ),
                turn_id="turn-observe-clarify",
            )

        original.assert_not_awaited()
        self.assertEqual(
            recorded[0].payload["executionPolicy"]["semanticIntent"],
            "clarify",
        )

    async def test_non_update_delegates_to_existing_observer(self) -> None:
        decision = SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.NOT_UPDATE,
            confidence=0.99,
            reason="Normal chat.",
        )
        expected_plan = object()
        expected_state = object()
        original = AsyncMock(return_value=(expected_plan, expected_state))

        with (
            patch.object(
                observation_module,
                "_ORIGINAL_OBSERVE_TURN",
                new=original,
            ),
            patch.object(
                observation_module,
                "get_semantic_focus_update_decision",
                new=AsyncMock(return_value=decision),
            ),
            patch.object(observation_module, "has_turn", return_value=False),
        ):
            result = await observation_module._observe_turn_with_semantic_update_deferral(
                ObserveTurnRequest(
                    message="help me choose lumber",
                    source="command-interpret-shadow",
                    apply=True,
                ),
                turn_id="turn-normal",
            )

        self.assertEqual(result, (expected_plan, expected_state))
        original.assert_awaited_once()

    async def test_other_sources_keep_original_observer(self) -> None:
        expected = (object(), object())
        original = AsyncMock(return_value=expected)
        with patch.object(
            observation_module,
            "_ORIGINAL_OBSERVE_TURN",
            new=original,
        ):
            result = await observation_module._observe_turn_with_semantic_update_deferral(
                ObserveTurnRequest(
                    message="continue the focus",
                    source="chat-request-shadow",
                    apply=True,
                ),
                turn_id="turn-chat",
            )

        self.assertEqual(result, expected)
        original.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
