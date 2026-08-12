from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus import store
from app.focus.context_hygiene import (
    question_answered_by_focus_update,
    question_is_generic_outcome,
)
from app.focus.lifecycle import NativeFocusUpdateRequest, update_focus_verified
from app.focus.models import (
    FocusOperation,
    FocusOperationKind,
    PendingQuestion,
    ResponseIntent,
    TurnPlan,
    TurnRoute,
)
from app.focus.pending_question_resolution import (
    pending_outcome_objective_for_current_focus,
    pending_outcome_objective_from_message,
    resolve_pending_question_after_verified_update,
)
from app.focus.semantic_lifecycle_preflight import SemanticFocusLifecyclePreflightRequest
from app.routers.focus_lifecycle import interpret_semantic_focus_lifecycle


class FocusPendingOutcomeAnswerRoutingPhase20W4Tests(unittest.TestCase):
    def _seed_client_meeting(self) -> str:
        started = store.apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="prepare for a client meeting",
                    )
                ],
                responseIntent=ResponseIntent(attachToFocus=True),
            ),
            message="start a focus to prepare for a client meeting",
            turn_id="phase20w4-start",
            source="phase20w4-test",
        )
        store.apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.SET_PENDING_QUESTION,
                        target="follow_up",
                        question="What would you like this client meeting to accomplish?",
                    )
                ],
                responseIntent=ResponseIntent(attachToFocus=True),
            ),
            message="ask desired client meeting outcome",
            turn_id="phase20w4-question",
            source="phase20w4-test",
        )
        return started.focusId

    def test_accomplish_and_achieve_are_generic_outcome_questions(self) -> None:
        self.assertTrue(
            question_is_generic_outcome(
                "What would you like this client meeting to accomplish?"
            )
        )
        self.assertTrue(
            question_is_generic_outcome("What should this focus achieve?")
        )
        self.assertTrue(
            question_is_generic_outcome("What is the objective for this work?")
        )

    def test_natural_desired_outcome_is_extracted_only_for_outcome_question(self) -> None:
        outcome_question = PendingQuestion(
            target="follow_up",
            question="What would you like this client meeting to accomplish?",
            askedAt="2026-08-07T21:48:00-07:00",
        )
        participant_question = PendingQuestion(
            target="follow_up",
            question="Who will be involved in the meeting?",
            askedAt="2026-08-07T21:48:00-07:00",
        )

        self.assertEqual(
            pending_outcome_objective_from_message(
                outcome_question,
                "I want to present the progress of my app",
            ),
            "present the progress of my app",
        )
        self.assertEqual(
            pending_outcome_objective_from_message(
                outcome_question,
                "I'd like to get approval for the next phase",
            ),
            "get approval for the next phase",
        )
        self.assertEqual(
            pending_outcome_objective_from_message(
                outcome_question,
                "To align on the launch plan",
            ),
            "align on the launch plan",
        )
        self.assertIsNone(
            pending_outcome_objective_from_message(
                outcome_question,
                "I want concise answers",
            )
        )
        self.assertIsNone(
            pending_outcome_objective_from_message(
                outcome_question,
                "When is the meeting?",
            )
        )
        self.assertIsNone(
            pending_outcome_objective_from_message(
                outcome_question,
                "I'm meeting them tomorrow afternoon",
            )
        )
        self.assertIsNone(
            pending_outcome_objective_from_message(
                participant_question,
                "I want to present the progress of my app",
            )
        )

    def test_current_focus_helper_uses_canonical_pending_question(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "QMEET_FOCUS_FILE": str(Path(temp_dir) / "focus.json"),
                    "QMEET_FOCUS_LIFECYCLE_HEALTH_FILE": str(
                        Path(temp_dir) / "lifecycle-health.json"
                    ),
                },
                clear=False,
            ):
                store.reset_store()
                self._seed_client_meeting()

                self.assertEqual(
                    pending_outcome_objective_for_current_focus(
                        "I want to present the progress of my app"
                    ),
                    "present the progress of my app",
                )
                self.assertIsNone(
                    pending_outcome_objective_for_current_focus(
                        "I'm meeting them tomorrow afternoon"
                    )
                )

    def test_semantic_router_promotes_pending_outcome_answer_to_typed_goal_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "QMEET_FOCUS_FILE": str(Path(temp_dir) / "focus.json"),
                    "QMEET_FOCUS_LIFECYCLE_HEALTH_FILE": str(
                        Path(temp_dir) / "lifecycle-health.json"
                    ),
                },
                clear=False,
            ):
                store.reset_store()
                self._seed_client_meeting()

                result = asyncio.run(
                    interpret_semantic_focus_lifecycle(
                        SemanticFocusLifecyclePreflightRequest(
                            message="I want to present the progress of my app",
                            sourceTurnId="phase20w4-natural-outcome",
                        )
                    )
                )

                self.assertEqual(result.intent, "update")
                self.assertTrue(result.possibleMutation)
                self.assertTrue(result.objectiveSpecified)
                self.assertEqual(result.objective, "present the progress of my app")
                self.assertEqual(result.confidence, 1.0)
                self.assertEqual(result.reason, "phase20w4-pending-outcome-answer")
                # Interpretation is non-mutating; verified lifecycle execution owns writes.
                self.assertEqual(store.get_state().objective, "")
                self.assertIsNotNone(store.get_state().pendingQuestion)

    def test_verified_goal_update_clears_accomplish_question(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "QMEET_FOCUS_FILE": str(Path(temp_dir) / "focus.json"),
                    "QMEET_FOCUS_LIFECYCLE_HEALTH_FILE": str(
                        Path(temp_dir) / "lifecycle-health.json"
                    ),
                },
                clear=False,
            ):
                store.reset_store()
                focus_id = self._seed_client_meeting()
                pending = store.get_state().pendingQuestion
                self.assertIsNotNone(pending)
                self.assertTrue(
                    question_answered_by_focus_update(
                        pending,
                        field="objective",
                        value="present the progress of my app",
                    )
                )

                request = NativeFocusUpdateRequest(
                    expectedFocusId=focus_id,
                    objective="present the progress of my app",
                    sourceTurnId="phase20w4-goal-update",
                )
                lifecycle_result = update_focus_verified(request)
                result = resolve_pending_question_after_verified_update(
                    request,
                    lifecycle_result,
                )

                self.assertEqual(
                    result.activeFocus.objective,
                    "present the progress of my app",
                )
                self.assertIsNone(result.activeFocus.pendingQuestion)
                self.assertIsNone(store.get_state().pendingQuestion)
                self.assertIn(
                    "Answered the current Focus question",
                    result.message,
                )

    def test_router_checks_pending_outcome_before_generic_context_boundary(self) -> None:
        root = Path(__file__).resolve().parents[2]
        router_source = (
            root / "backend/app/routers/focus_lifecycle.py"
        ).read_text(encoding="utf-8")
        pending_call = (
            "pending_objective = pending_outcome_objective_for_current_focus(request.message)"
        )
        context_call = "context_signal = classify_focus_context(request.message)"
        self.assertIn(pending_call, router_source)
        self.assertIn(context_call, router_source)
        self.assertLess(router_source.index(pending_call), router_source.index(context_call))


if __name__ == "__main__":
    unittest.main()
