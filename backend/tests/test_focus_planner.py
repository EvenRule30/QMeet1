from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.focus.models import (
    FocusField,
    FocusOperation,
    FocusOperationKind,
    ResponseIntent,
    TurnPlan,
    TurnRoute,
)
from app.focus.planner import (
    _compact_recent_event_payload,
    _plan_question_errors,
    _recent_event_summary,
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


class FocusPlannerContextTests(unittest.TestCase):
    def test_turn_summary_preserves_prior_user_request(self) -> None:
        compact = _compact_recent_event_payload(
            "turn_planned",
            {
                "message": "Yes, please give me the instructions.",
                "route": "respond",
                "reason": "The user accepted the offered instructions.",
                "plan": {
                    "responseIntent": {
                        "acknowledge": "Understood.",
                        "answerDirectly": True,
                        "attachToFocus": True,
                        "guidance": "Provide the requested instructions.",
                        "askQuestion": "Do you have a second vehicle available?",
                    }
                },
            },
        )

        self.assertEqual(
            compact["message"],
            "Yes, please give me the instructions.",
        )
        self.assertTrue(
            compact["responseIntent"]["answerDirectly"]
        )
        self.assertTrue(
            compact["responseIntent"]["attachToFocus"]
        )
        self.assertEqual(
            compact["responseIntent"]["askQuestion"],
            "Do you have a second vehicle available?",
        )

    def test_assistant_reply_summary_excludes_legacy_visible_text(self) -> None:
        compact = _compact_recent_event_payload(
            "assistant_replied",
            {
                "text": (
                    "Your calendar looks open. "
                    "Describe the symptoms again."
                ),
                "audit": {
                    "expectedQuestion": (
                        "Do you have a second vehicle available?"
                    ),
                    "questionMatch": False,
                    "candidateEligible": True,
                    "findings": [
                        {"code": "question_mismatch"},
                        {
                            "code": (
                                "calendar_claim_without_tool_evidence"
                            )
                        },
                    ],
                },
            },
        )

        self.assertNotIn("text", compact)
        self.assertEqual(
            compact["audit"]["expectedQuestion"],
            "Do you have a second vehicle available?",
        )
        self.assertEqual(
            compact["audit"]["findings"],
            [
                "question_mismatch",
                "calendar_claim_without_tool_evidence",
            ],
        )

    def test_recent_summary_keeps_canonical_intent_not_legacy_prose(
        self,
    ) -> None:
        events = [
            SimpleNamespace(
                type=SimpleNamespace(value="turn_planned"),
                payload={
                    "message": "Yes, please give me the instructions.",
                    "route": "respond",
                    "plan": {
                        "responseIntent": {
                            "answerDirectly": True,
                            "attachToFocus": True,
                            "guidance": (
                                "Provide jump-start instructions after "
                                "the prerequisite is answered."
                            ),
                            "askQuestion": (
                                "Do you have a second vehicle available?"
                            ),
                        }
                    },
                },
                createdAt="2026-07-23T15:45:44-07:00",
            ),
            SimpleNamespace(
                type=SimpleNamespace(value="assistant_replied"),
                payload={
                    "text": (
                        "Your calendar looks open. "
                        "Describe the symptoms again."
                    ),
                    "audit": {
                        "expectedQuestion": (
                            "Do you have a second vehicle available?"
                        ),
                        "questionMatch": False,
                        "findings": [
                            {"code": "question_mismatch"},
                        ],
                    },
                },
                createdAt="2026-07-23T15:45:45-07:00",
            ),
        ]

        with patch(
            "app.focus.planner.list_events",
            return_value=events,
        ):
            summary = _recent_event_summary()

        self.assertEqual(
            summary[0]["payload"]["message"],
            "Yes, please give me the instructions.",
        )
        self.assertTrue(
            summary[0]["payload"]["responseIntent"]["attachToFocus"]
        )
        self.assertNotIn("text", summary[1]["payload"])
        self.assertEqual(
            summary[1]["payload"]["audit"]["findings"],
            ["question_mismatch"],
        )


if __name__ == "__main__":
    unittest.main()
