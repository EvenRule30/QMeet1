from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus import store
from app.focus.context_hygiene import (
    question_answered_by_context,
    question_answered_by_focus_update,
)
from app.focus.lifecycle import NativeFocusUpdateRequest, update_focus_verified
from app.focus.models import (
    FocusEventType,
    FocusOperation,
    FocusOperationKind,
    PendingQuestion,
    ResponseIntent,
    TurnPlan,
    TurnRoute,
)
from app.focus.pending_question_resolution import (
    resolve_pending_question_after_verified_update,
)


class FocusPendingQuestionResolutionPhase20W3Tests(unittest.TestCase):
    def _seed_focus_with_success_question(self) -> tuple[str, str]:
        started = store.apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="prepare for an interview",
                    )
                ],
                responseIntent=ResponseIntent(attachToFocus=True),
            ),
            message="start a focus to prepare for an interview",
            turn_id="phase20w3-start",
            source="phase20w3-test",
        )
        store.apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.SET_PENDING_QUESTION,
                        target="follow_up",
                        question=(
                            "What result would make preparing for your interview "
                            "feel successful to you?"
                        ),
                    )
                ],
                responseIntent=ResponseIntent(attachToFocus=True),
            ),
            message="ask success question",
            turn_id="phase20w3-question",
            source="phase20w3-test",
        )
        return started.focusId, started.objective

    def test_generic_success_question_is_not_cleared_by_unrelated_preference(self) -> None:
        question = PendingQuestion(
            target="follow_up",
            question="What result would make this focus successful?",
            askedAt="2026-08-07T21:25:00-07:00",
        )
        self.assertFalse(
            question_answered_by_context(
                question,
                field="preferences",
                value="concise answers",
            )
        )
        self.assertFalse(
            question_answered_by_context(
                question,
                field="requirements",
                value="practice behavioral questions",
            )
        )
        self.assertTrue(
            question_answered_by_context(
                question,
                field="knownFacts",
                value="A successful interview means giving strong examples",
            )
        )

    def test_only_objective_update_resolves_generic_success_question(self) -> None:
        question = PendingQuestion(
            target="follow_up",
            question="What result would make this focus successful?",
            askedAt="2026-08-07T21:25:00-07:00",
        )
        self.assertTrue(
            question_answered_by_focus_update(
                question,
                field="objective",
                value="feel confident and prepare strong examples",
            )
        )
        self.assertFalse(
            question_answered_by_focus_update(
                question,
                field="title",
                value="interview preparation",
            )
        )
        self.assertFalse(
            question_answered_by_focus_update(
                question,
                field="mode",
                value="general",
            )
        )

    def test_verified_goal_update_clears_exact_pending_success_question(self) -> None:
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
                focus_id, _ = self._seed_focus_with_success_question()
                request = NativeFocusUpdateRequest(
                    expectedFocusId=focus_id,
                    objective="feel confident and prepare strong examples",
                    sourceTurnId="phase20w3-goal-update",
                )

                lifecycle_result = update_focus_verified(request)
                self.assertIsNotNone(lifecycle_result.activeFocus.pendingQuestion)

                result = resolve_pending_question_after_verified_update(
                    request,
                    lifecycle_result,
                )
                state = store.get_state()

                self.assertTrue(result.verified)
                self.assertEqual(result.activeFocus.focusId, focus_id)
                self.assertEqual(
                    result.activeFocus.objective,
                    "feel confident and prepare strong examples",
                )
                self.assertIsNone(result.activeFocus.pendingQuestion)
                self.assertIsNone(state.pendingQuestion)
                self.assertNotEqual(
                    state.nextAction,
                    "What result would make preparing for your interview feel successful to you?",
                )
                self.assertIn(
                    "Answered the current Focus question",
                    result.message,
                )

                clear_events = [
                    event
                    for event in store.list_events(limit=200)
                    if event.type == FocusEventType.QUESTION_CLEARED
                    and event.source == "focus-native-goal-question-resolution"
                ]
                self.assertEqual(len(clear_events), 1)
                self.assertEqual(clear_events[0].focusId, focus_id)
                self.assertEqual(
                    clear_events[0].sourceTurnId,
                    "phase20w3-goal-update:goal-question",
                )

    def test_title_update_does_not_clear_success_question(self) -> None:
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
                focus_id, _ = self._seed_focus_with_success_question()
                request = NativeFocusUpdateRequest(
                    expectedFocusId=focus_id,
                    title="interview preparation",
                    sourceTurnId="phase20w3-title-update",
                )
                lifecycle_result = update_focus_verified(request)
                result = resolve_pending_question_after_verified_update(
                    request,
                    lifecycle_result,
                )

                self.assertIsNotNone(result.activeFocus.pendingQuestion)
                self.assertIsNotNone(store.get_state().pendingQuestion)
                self.assertNotIn(
                    "Answered the current Focus question",
                    result.message,
                )

    def test_router_runs_resolution_before_returning_update_result(self) -> None:
        root = Path(__file__).resolve().parents[2]
        router_source = (
            root / "backend/app/routers/focus_lifecycle.py"
        ).read_text(encoding="utf-8")
        update_call = "result = update_focus_verified(request)"
        resolution_call = (
            "result = resolve_pending_question_after_verified_update(request, result)"
        )
        self.assertIn(update_call, router_source)
        self.assertIn(resolution_call, router_source)
        self.assertLess(
            router_source.index(update_call),
            router_source.index(resolution_call),
        )


if __name__ == "__main__":
    unittest.main()
