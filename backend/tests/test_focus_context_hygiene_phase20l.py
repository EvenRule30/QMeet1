from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus.context import (
    NativeFocusContextRequest,
    add_focus_context_verified,
)
from app.focus.context_hygiene import (
    duplicate_values_to_remove,
    question_answered_by_context,
    semantically_equivalent,
)
from app.focus.models import (
    FocusField,
    FocusOperation,
    FocusOperationKind,
    PendingQuestion,
    ResponseIntent,
    TurnPlan,
    TurnRoute,
)
from app.focus import store


class FocusContextHygienePhase20LTests(unittest.TestCase):
    def test_semantic_duplicate_examples_are_equivalent(self) -> None:
        pairs = [
            (
                "A warm destination was found.",
                "The user has found a warm destination for the planned weekend trip.",
            ),
            (
                "three days available",
                "The three available days for the trip have been confirmed.",
            ),
            (
                "Checked the trip plan against the $1,000 constraints.",
                "Check the plan against this constraint: Keep the total cost under $1,000",
            ),
        ]
        for left, right in pairs:
            with self.subTest(left=left):
                self.assertTrue(semantically_equivalent(left, right))

    def test_conflicting_constraint_polarity_is_not_equivalent(self) -> None:
        self.assertFalse(
            semantically_equivalent(
                "Keep the total cost under $1,000",
                "Keep the total cost over $1,000",
            )
        )

    def test_duplicate_cleanup_keeps_concise_canonical_values(self) -> None:
        values = [
            "three days available",
            "The three available days for the trip have been confirmed.",
            "A warm destination was found.",
            "The user has found a warm destination for the planned weekend trip.",
        ]
        removals = duplicate_values_to_remove(values)
        self.assertEqual(
            removals,
            [
                "The three available days for the trip have been confirmed.",
                "The user has found a warm destination for the planned weekend trip.",
            ],
        )

    def test_generic_success_question_accepts_preference_not_availability_fact(self) -> None:
        question = PendingQuestion(
            target="follow_up",
            question="What would make this trip a real success for you?",
            askedAt="2026-08-06T15:11:56-07:00",
        )
        self.assertTrue(
            question_answered_by_context(
                question,
                field="preferences",
                value="somewhere warm",
            )
        )
        self.assertFalse(
            question_answered_by_context(
                question,
                field="knownFacts",
                value="three days available",
            )
        )
        self.assertTrue(
            question_answered_by_context(
                question,
                field="knownFacts",
                value="A successful trip means relaxing on the beach",
            )
        )

    def test_frontend_verifies_the_returned_canonical_value(self) -> None:
        root = Path(__file__).resolve().parents[2]
        client = (
            root / "src/app/lib/nativeFocusContext.ts"
        ).read_text(encoding="utf-8")
        context_source = (
            root / "backend/app/focus/context.py"
        ).read_text(encoding="utf-8")
        self.assertIn("canonicalValue", context_source)
        self.assertIn("resultValue === value", client)
        self.assertIn("Boolean(canonicalValue)", client)
        self.assertIn("containsExact(contextValues, canonicalValue)", client)

    def test_verified_context_reuses_semantic_fact_and_clears_answered_question(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            focus_file = Path(temp_dir) / "focus.json"
            health_file = Path(temp_dir) / "context-health.json"
            with patch.dict(
                os.environ,
                {
                    "QMEET_FOCUS_FILE": str(focus_file),
                    "QMEET_FOCUS_CONTEXT_HEALTH_FILE": str(health_file),
                },
                clear=False,
            ):
                store.reset_store()
                started = store.apply_turn_plan(
                    TurnPlan(
                        route=TurnRoute.FOCUS_ACTION,
                        focusOperations=[
                            FocusOperation(
                                kind=FocusOperationKind.START_FOCUS,
                                title="plan a weekend trip",
                                objective="choose a destination, dates, and budget",
                            )
                        ],
                        responseIntent=ResponseIntent(attachToFocus=True),
                    ),
                    message="start a focus to plan a weekend trip",
                    turn_id="phase20l-start",
                    source="phase20l-test",
                )
                store.apply_turn_plan(
                    TurnPlan(
                        route=TurnRoute.FOCUS_ACTION,
                        focusOperations=[
                            FocusOperation(
                                kind=FocusOperationKind.ADD_LIST_ITEM,
                                field=FocusField.KNOWN_FACTS,
                                value="A warm destination was found.",
                            ),
                            FocusOperation(
                                kind=FocusOperationKind.ADD_LIST_ITEM,
                                field=FocusField.KNOWN_FACTS,
                                value=(
                                    "The user has found a warm destination for the "
                                    "planned weekend trip."
                                ),
                            ),
                            FocusOperation(
                                kind=FocusOperationKind.SET_PENDING_QUESTION,
                                target="follow_up",
                                question="What would make this trip a real success for you?",
                            ),
                        ],
                        responseIntent=ResponseIntent(attachToFocus=True),
                    ),
                    message="prepare context",
                    turn_id="phase20l-seed",
                    source="phase20l-test",
                )

                result = add_focus_context_verified(
                    NativeFocusContextRequest(
                        expectedFocusId=started.focusId,
                        expectedObjective=started.objective,
                        field="preferences",
                        value="somewhere warm",
                        sourceTurnId="phase20l-context",
                    )
                )
                state = store.get_state()

                self.assertTrue(result.verified)
                self.assertEqual(state.objective, started.objective)
                self.assertEqual(state.preferences, ["somewhere warm"])
                self.assertEqual(state.knownFacts, ["A warm destination was found."])
                self.assertIsNone(state.pendingQuestion)
                self.assertNotEqual(
                    state.nextAction,
                    "What would make this trip a real success for you?",
                )
                self.assertIn("Answered the current Focus question", result.message)

                reused = add_focus_context_verified(
                    NativeFocusContextRequest(
                        expectedFocusId=started.focusId,
                        expectedObjective=started.objective,
                        field="knownFacts",
                        value=(
                            "The user has found a warm destination for the "
                            "planned weekend trip."
                        ),
                        sourceTurnId="phase20l-reuse",
                    )
                )
                self.assertEqual(reused.outcome, "reused")
                self.assertEqual(
                    reused.canonicalValue,
                    "A warm destination was found.",
                )
                self.assertEqual(
                    store.get_state().knownFacts,
                    ["A warm destination was found."],
                )

                retried = add_focus_context_verified(
                    NativeFocusContextRequest(
                        expectedFocusId=started.focusId,
                        expectedObjective=started.objective,
                        field="knownFacts",
                        value=(
                            "The user has found a warm destination for the "
                            "planned weekend trip."
                        ),
                        sourceTurnId="phase20l-reuse",
                    )
                )
                self.assertEqual(retried.outcome, "reused")
                self.assertEqual(
                    retried.canonicalValue,
                    "A warm destination was found.",
                )


if __name__ == "__main__":
    unittest.main()
