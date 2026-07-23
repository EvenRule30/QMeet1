from __future__ import annotations

import unittest

from app.focus.models import (
    FocusField,
    FocusOperation,
    FocusOperationKind,
    ResponseIntent,
    TurnPlan,
    TurnRoute,
)
from app.focus.planner import (
    _plan_question_errors,
    _question_is_atomic,
    _strip_invalid_follow_up,
)


class FocusPlannerQuestionValidationTests(unittest.TestCase):
    def test_single_question_is_atomic(self) -> None:
        self.assertTrue(
            _question_is_atomic(
                "Has the car's battery been tested recently?"
            )
        )

    def test_disjunctive_question_is_not_atomic(self) -> None:
        self.assertFalse(
            _question_is_atomic(
                "Have you tested or recently replaced the car's battery?"
            )
        )

    def test_different_question_locations_are_rejected(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.FOCUS_ACTION,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.SET_PENDING_QUESTION,
                    target="battery_test",
                    question="Has the battery been tested recently?",
                )
            ],
            responseIntent=ResponseIntent(
                askQuestion="How old is the battery?",
            ),
        )

        errors = _plan_question_errors(plan)

        self.assertTrue(
            any("more than one distinct" in error for error in errors)
        )

    def test_invalid_follow_up_is_removed_without_losing_state_updates(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.FOCUS_ACTION,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.KNOWN_FACTS,
                    value=(
                        "The dashboard lights do not dim when attempting "
                        "to start the car."
                    ),
                ),
                FocusOperation(
                    kind=FocusOperationKind.CLEAR_PENDING_QUESTION,
                ),
                FocusOperation(
                    kind=FocusOperationKind.SET_PENDING_QUESTION,
                    target="battery_history",
                    question=(
                        "Have you tested or recently replaced the car's "
                        "battery?"
                    ),
                ),
            ],
            responseIntent=ResponseIntent(
                guidance="Continue troubleshooting the starting problem.",
                askQuestion=(
                    "Have you tested or recently replaced the car's battery?"
                ),
            ),
            reason="The user answered the prior diagnostic question.",
        )

        repaired = _strip_invalid_follow_up(
            plan,
            _plan_question_errors(plan),
        )

        self.assertEqual(
            [operation.kind for operation in repaired.focusOperations],
            [
                FocusOperationKind.ADD_LIST_ITEM,
                FocusOperationKind.CLEAR_PENDING_QUESTION,
            ],
        )
        self.assertEqual(repaired.responseIntent.askQuestion, "")
        self.assertEqual(
            repaired.responseIntent.guidance,
            "Continue troubleshooting the starting problem.",
        )
        self.assertIn(
            "Follow-up omitted after atomic-question validation",
            repaired.reason,
        )


if __name__ == "__main__":
    unittest.main()
