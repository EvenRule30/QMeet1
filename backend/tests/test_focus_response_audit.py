from __future__ import annotations

import os
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus.audit import build_response_audit, extract_visible_questions
from app.focus.response import (
    build_response_candidate,
    compose_response_candidate,
)
from app.focus.middleware import _replay_receive
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
                confidence=1.0,
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


    def test_compose_response_candidate_uses_validated_intent(self) -> None:
        candidate = compose_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    acknowledge="Noted that you do not have a voltmeter.",
                    answerDirectly=False,
                    askQuestion="Do you have jumper cables available?",
                ),
            )
        )

        self.assertEqual(
            candidate,
            (
                "Noted that you do not have a voltmeter.\n\n"
                "Do you have jumper cables available?"
            ),
        )

    def test_tool_turn_does_not_create_direct_response_candidate(self) -> None:
        from app.focus.models import PlannedToolCall, ToolName

        candidate = compose_response_candidate(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        reason="Search for current information.",
                    )
                ],
                responseIntent=ResponseIntent(
                    acknowledge="Searching now.",
                    answerDirectly=False,
                ),
            )
        )

        self.assertEqual(candidate, "")

    def test_plan_records_observational_response_candidate(self) -> None:
        turn_id = "turn-response-candidate"

        before = get_state()
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose car trouble",
                        objective="Restore reliable starting.",
                    )
                ],
                responseIntent=ResponseIntent(
                    acknowledge="Noted.",
                    answerDirectly=False,
                    askQuestion="Do you have jumper cables available?",
                ),
                confidence=1.0,
            ),
            message="I do not have a voltmeter.",
            turn_id=turn_id,
            source="unit-test",
        )
        after_plan = get_state()

        candidates = [
            event
            for event in list_events()
            if event.type == FocusEventType.RESPONSE_CANDIDATE
            and event.sourceTurnId == turn_id
        ]

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0].payload["text"],
            "Noted.\n\nDo you have jumper cables available?",
        )
        self.assertTrue(
            candidates[0].payload["eligibility"]["eligible"]
        )
        self.assertEqual(
            candidates[0].payload["eligibility"]["reasons"],
            [],
        )

        # Replaying an observational candidate must not alter the projected
        # state beyond the real plan operations.
        self.assertNotEqual(before.focusId, after_plan.focusId)
        replayed = get_state()
        self.assertEqual(after_plan, replayed)

    def test_audit_exposes_candidate_text(self) -> None:
        turn_id = self._create_turn()

        audit = build_response_audit(
            "Your calendar is clear. What do you observe?",
            list_events(),
            source_turn_id=turn_id,
        )

        self.assertEqual(
            audit["candidateText"],
            "Do you have access to a voltmeter?",
        )



    def test_candidate_eligibility_rejects_low_confidence(self) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    guidance="Try the next troubleshooting step.",
                ),
                confidence=0.60,
            )
        )

        self.assertFalse(candidate["eligibility"]["eligible"])
        self.assertIn(
            "confidence_below_threshold",
            candidate["eligibility"]["reasons"],
        )

    def test_candidate_eligibility_rejects_promised_instructions_without_delivery(
        self,
    ) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    acknowledge=(
                        "You confirmed you want instructions for jump starting "
                        "your car."
                    ),
                    answerDirectly=True,
                    guidance=(
                        "I'll provide step-by-step instructions on how to jump "
                        "start your car safely. Please ensure you have a second "
                        "vehicle with a good battery before beginning."
                    ),
                    askQuestion="Do you have a second vehicle available?",
                ),
                confidence=1.0,
            )
        )

        self.assertFalse(candidate["eligibility"]["eligible"])
        self.assertIn(
            "direct_answer_promised_not_delivered",
            candidate["eligibility"]["reasons"],
        )
        self.assertNotRegex(
            candidate["components"]["guidance"],
            r"(?:^|[.!?]\\s+)(?:first|second|third|finally)\\s*[, :]\\s+",
        )

    def test_candidate_eligibility_accepts_delivered_procedure(self) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    guidance=(
                        "I'll walk you through it. First, park the vehicles "
                        "without letting them touch. Second, turn both vehicles "
                        "off before connecting the cables."
                    ),
                ),
                confidence=1.0,
            )
        )

        self.assertTrue(candidate["eligibility"]["eligible"])
        self.assertNotIn(
            "direct_answer_promised_not_delivered",
            candidate["eligibility"]["reasons"],
        )

    def test_candidate_eligibility_rejects_direct_answer_deferred_to_offer(
        self,
    ) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                responseIntent=ResponseIntent(
                    acknowledge=(
                        "You've confirmed you have a second vehicle."
                    ),
                    answerDirectly=True,
                    guidance=(
                        "Ensure both vehicles are turned off before "
                        "connecting the cables."
                    ),
                    askQuestion=(
                        "Would you like step-by-step instructions on "
                        "how to jump start your car?"
                    ),
                ),
                confidence=1.0,
            )
        )

        self.assertFalse(candidate["eligibility"]["eligible"])
        self.assertIn(
            "direct_answer_deferred_to_offer",
            candidate["eligibility"]["reasons"],
        )

    def test_candidate_eligibility_allows_offer_after_delivered_procedure(
        self,
    ) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    guidance=(
                        "First, park the vehicles without letting them touch. "
                        "Second, turn both vehicles off before connecting "
                        "the cables."
                    ),
                    askQuestion=(
                        "Would you like help checking the result afterward?"
                    ),
                ),
                confidence=1.0,
            )
        )

        self.assertTrue(candidate["eligibility"]["eligible"])
        self.assertNotIn(
            "direct_answer_deferred_to_offer",
            candidate["eligibility"]["reasons"],
        )

    def test_candidate_eligibility_rejects_tool_backed_claim(self) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    guidance="Your calendar is clear, so you can do this now.",
                ),
                confidence=1.0,
            )
        )

        self.assertFalse(candidate["eligibility"]["eligible"])
        self.assertIn(
            "calendar_availability_without_tool",
            candidate["eligibility"]["reasons"],
        )

    def test_audit_exposes_candidate_eligibility(self) -> None:
        turn_id = self._create_turn()

        audit = build_response_audit(
            "Do you have access to a voltmeter?",
            list_events(),
            source_turn_id=turn_id,
        )

        self.assertTrue(audit["candidateEligible"])
        self.assertEqual(audit["candidateIneligibilityReasons"], [])



class FocusMiddlewareReceiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_replay_receive_delegates_after_replaying_body(self) -> None:
        delegated = asyncio.Event()

        async def original_receive():
            delegated.set()
            return {"type": "http.disconnect"}

        receive = _replay_receive(
            b'{"message":"hello"}',
            original_receive,
        )

        first = await receive()
        self.assertEqual(first["type"], "http.request")
        self.assertEqual(first["body"], b'{"message":"hello"}')
        self.assertFalse(first["more_body"])

        second = await receive()
        self.assertEqual(second, {"type": "http.disconnect"})
        self.assertTrue(delegated.is_set())

    async def test_replay_receive_does_not_spin_after_body(self) -> None:
        release_disconnect = asyncio.Event()

        async def original_receive():
            await release_disconnect.wait()
            return {"type": "http.disconnect"}

        receive = _replay_receive(b"{}", original_receive)
        await receive()

        pending_receive = asyncio.create_task(receive())
        await asyncio.sleep(0)

        self.assertFalse(pending_receive.done())

        release_disconnect.set()
        self.assertEqual(
            await pending_receive,
            {"type": "http.disconnect"},
        )


if __name__ == "__main__":
    unittest.main()
