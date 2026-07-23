from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus.audit import build_response_audit, extract_visible_questions
from app.focus.models import (
    FocusEventType,
    FocusOperation,
    FocusOperationKind,
    ResponseIntent,
    TurnPlan,
    TurnRoute,
)
from app.focus.store import (
    apply_turn_plan,
    get_state,
    list_events,
    record_assistant_reply,
    reset_store,
)


class FocusResponseAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._event_file = (
            Path(self._temporary_directory.name) / "qmeet_focus_test.json"
        )
        self._environment_patch = patch.dict(
            os.environ,
            {"QMEET_FOCUS_FILE": str(self._event_file)},
            clear=False,
        )
        self._environment_patch.start()
        reset_store()

    def tearDown(self) -> None:
        self._environment_patch.stop()
        self._temporary_directory.cleanup()

    def _create_turn(self) -> str:
        turn_id = "turn-response-audit"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose car trouble",
                        objective="Restore reliable starting.",
                    ),
                    FocusOperation(
                        kind=FocusOperationKind.SET_PENDING_QUESTION,
                        target="battery_tool",
                        question="Do you have access to a voltmeter?",
                    ),
                ],
                responseIntent=ResponseIntent(
                    askQuestion="Do you have access to a voltmeter?",
                ),
            ),
            message="I have not tested the battery.",
            turn_id=turn_id,
            source="unit-test",
        )
        return turn_id

    def test_extracts_multiple_visible_questions(self) -> None:
        questions = extract_visible_questions(
            "Do you have a voltmeter? Do you need help finding one?"
        )
        self.assertEqual(len(questions), 2)

    def test_audit_flags_question_mismatch_and_calendar_claim(self) -> None:
        turn_id = self._create_turn()
        audit = build_response_audit(
            (
                "Your calendar looks open, so you can do this now. "
                "Do you have access to one or need help finding a place?"
            ),
            list_events(),
            source_turn_id=turn_id,
        )

        codes = {finding["code"] for finding in audit["findings"]}
        self.assertIn("question_mismatch", codes)
        self.assertIn("calendar_claim_without_tool_evidence", codes)
        self.assertFalse(audit["questionMatch"])

    def test_matching_visible_question_has_no_question_finding(self) -> None:
        turn_id = self._create_turn()
        audit = build_response_audit(
            "Do you have access to a voltmeter?",
            list_events(),
            source_turn_id=turn_id,
        )

        codes = {finding["code"] for finding in audit["findings"]}
        self.assertNotIn("question_mismatch", codes)
        self.assertTrue(audit["questionMatch"])

    def test_recorded_reply_does_not_mutate_focus_state(self) -> None:
        turn_id = self._create_turn()
        before = get_state()

        after = record_assistant_reply(
            text=(
                "Your calendar looks open. "
                "Do you have access to a voltmeter?"
            ),
            source_turn_id=turn_id,
            transport="sse",
            response_status=200,
        )

        self.assertEqual(after, before)
        reply_events = [
            event
            for event in list_events()
            if event.type == FocusEventType.ASSISTANT_REPLIED
        ]
        self.assertEqual(len(reply_events), 1)
        self.assertEqual(reply_events[0].sourceTurnId, turn_id)
        self.assertEqual(reply_events[0].focusId, before.focusId)
        self.assertEqual(reply_events[0].payload["transport"], "sse")


if __name__ == "__main__":
    unittest.main()
