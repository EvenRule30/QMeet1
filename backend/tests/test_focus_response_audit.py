from __future__ import annotations

import os
import json
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.focus.audit import build_response_audit, extract_visible_questions
from app.focus.response import (
    build_response_candidate,
    compose_response_candidate,
)
from app.focus.middleware import (
    FocusShadowMiddleware,
    _extract_sse_reply,
    _replay_receive,
)
from app.focus.models import (
    FocusEventType,
    FocusOperation,
    FocusOperationKind,
    PlannedToolCall,
    ResponseIntent,
    ToolName,
    TurnPlan,
    TurnRoute,
)
from app.focus.store import (
    apply_turn_plan,
    eligible_response_candidate_for_turn,
    guarded_response_decision_for_turn,
    guarded_tool_response_decision_for_turn,
    get_state,
    list_events,
    record_assistant_reply,
    record_tool_response_candidate,
    record_tool_result,
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

    def test_direct_candidate_removes_unsupported_calendar_availability(
        self,
    ) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    guidance=(
                        "The next step is to define the meeting outcome. "
                        "Since your calendar has one meeting and no other "
                        "events, you have time to do that now. "
                        "Then gather the materials needed for the decision."
                    ),
                ),
                confidence=1.0,
            )
        )

        self.assertTrue(candidate["eligibility"]["eligible"])
        self.assertIn(
            "The next step is to define the meeting outcome.",
            candidate["text"],
        )
        self.assertIn(
            "Then gather the materials needed for the decision.",
            candidate["text"],
        )
        self.assertNotIn("no other events", candidate["text"])
        self.assertEqual(
            candidate["repairs"],
            ["removed_unsupported_calendar_availability"],
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

    def test_response_intent_preserves_guidance_beyond_legacy_limit(
        self,
    ) -> None:
        long_guidance = (
            "Follow these complete instructions. "
            + ("Keep the procedure grounded and complete. " * 45)
            + "Finish the final step safely."
        )

        self.assertGreater(len(long_guidance), 1200)
        self.assertLess(len(long_guidance), 4000)

        intent = ResponseIntent(
            answerDirectly=True,
            guidance=long_guidance,
        )
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=intent,
                confidence=1.0,
            )
        )

        self.assertEqual(intent.guidance, long_guidance)
        self.assertIn(long_guidance, candidate["text"])
        self.assertTrue(candidate["text"].endswith(
            "Finish the final step safely."
        ))

    def test_candidate_preserves_numbered_list_formatting(self) -> None:
        candidate = compose_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    guidance=(
                        "Follow these steps:\n\n"
                        "1. Turn both vehicles off.\n"
                        "2. Connect the positive clamps."
                    ),
                ),
                confidence=1.0,
            )
        )

        self.assertIn(
            "Follow these steps:\n\n1. Turn both vehicles off.\n"
            "2. Connect the positive clamps.",
            candidate,
        )

    def test_candidate_rejects_malformed_truncated_procedure(self) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    guidance=(
                        "Here are the steps:\n\n"
                        "1. Turn both vehicles off.\n"
                        "2. Connect the red clamps.\n"
                        "3. Let the car run for 15-30 minutes before turning,2"
                    ),
                ),
                confidence=1.0,
            )
        )

        reasons = candidate["eligibility"]["reasons"]
        self.assertFalse(candidate["eligibility"]["eligible"])
        self.assertIn("unterminated_procedure", reasons)
        self.assertIn("malformed_trailing_fragment", reasons)

    def test_candidate_rejects_nonsequential_numbered_steps(self) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    guidance=(
                        "Follow these steps:\n\n"
                        "1. Turn both vehicles off.\n"
                        "3. Connect the positive clamps."
                    ),
                ),
                confidence=1.0,
            )
        )

        self.assertFalse(candidate["eligibility"]["eligible"])
        self.assertIn(
            "nonsequential_numbered_steps",
            candidate["eligibility"]["reasons"],
        )

    def test_candidate_accepts_complete_numbered_procedure(self) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    guidance=(
                        "Follow these steps:\n\n"
                        "1. Turn both vehicles off.\n"
                        "2. Connect the positive clamps.\n"
                        "3. Connect the final negative clamp to bare metal."
                    ),
                ),
                confidence=1.0,
            )
        )

        self.assertTrue(candidate["eligibility"]["eligible"])
        self.assertEqual(candidate["eligibility"]["reasons"], [])

    def test_candidate_rejects_unbalanced_delimiters(self) -> None:
        candidate = build_response_candidate(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    guidance=(
                        "Follow these steps:\n\n"
                        "1. Turn both vehicles off.\n"
                        "2. Connect the positive clamp (red."
                    ),
                ),
                confidence=1.0,
            )
        )

        self.assertFalse(candidate["eligibility"]["eligible"])
        self.assertIn(
            "unbalanced_delimiters",
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

    def test_guarded_selector_returns_current_eligible_candidate(
        self,
    ) -> None:
        turn_id = "turn-guarded-selector"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose starting problem",
                        objective="Restore reliable starting.",
                    ),
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=True,
                    guidance="Check the battery terminals first.",
                ),
                confidence=1.0,
            ),
            message="Help me diagnose the car.",
            turn_id=turn_id,
            source="unit-test",
        )

        candidate = eligible_response_candidate_for_turn(turn_id)

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.sourceTurnId, turn_id)
        self.assertEqual(
            candidate.payload["text"],
            "Check the battery terminals first.",
        )

    def test_guarded_selector_rejects_ineligible_candidate(self) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose starting problem",
                        objective="Restore reliable starting.",
                    ),
                ],
                responseIntent=ResponseIntent(
                    guidance="Begin diagnosis.",
                ),
                confidence=1.0,
            ),
            message="Help me diagnose the car.",
            turn_id="turn-selector-focus",
            source="unit-test",
        )

        turn_id = "turn-selector-ineligible"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    attachToFocus=True,
                    guidance="Your calendar is clear.",
                ),
                confidence=1.0,
            ),
            message="What next?",
            turn_id=turn_id,
            source="unit-test",
        )

        self.assertIsNone(
            eligible_response_candidate_for_turn(turn_id)
        )

    def test_guarded_selector_rejects_unattached_off_topic_candidate(
        self,
    ) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose starting problem",
                        objective="Restore reliable starting.",
                    ),
                ],
                responseIntent=ResponseIntent(
                    attachToFocus=True,
                    guidance="Begin diagnosis.",
                ),
                confidence=1.0,
            ),
            message="Help me diagnose the car.",
            turn_id="turn-off-topic-focus",
            source="unit-test",
        )

        turn_id = "turn-off-topic-chat"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=False,
                    guidance="I do not have a dog.",
                ),
                confidence=1.0,
            ),
            message="What is your dog's last name?",
            turn_id=turn_id,
            source="unit-test",
        )

        candidates = [
            event
            for event in list_events()
            if event.type == FocusEventType.RESPONSE_CANDIDATE
            and event.sourceTurnId == turn_id
        ]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].focusId, "")
        self.assertFalse(candidates[0].payload["attachToFocus"])
        self.assertIsNone(
            eligible_response_candidate_for_turn(turn_id)
        )

    def test_guarded_selector_accepts_explicit_related_direct_reply(
        self,
    ) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose starting problem",
                        objective="Restore reliable starting.",
                    ),
                ],
                responseIntent=ResponseIntent(
                    attachToFocus=True,
                    guidance="Begin diagnosis.",
                ),
                confidence=1.0,
            ),
            message="Help me diagnose the car.",
            turn_id="turn-related-focus",
            source="unit-test",
        )

        turn_id = "turn-related-direct"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=True,
                    guidance="Repeat the complete diagnostic instructions.",
                ),
                confidence=1.0,
            ),
            message="Repeat the instructions.",
            turn_id=turn_id,
            source="unit-test",
        )

        candidate = eligible_response_candidate_for_turn(turn_id)
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertTrue(candidate.payload["attachToFocus"])

    def test_guarded_decision_explains_unattached_candidate(self) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose starting problem",
                        objective="Restore reliable starting.",
                    ),
                ],
                responseIntent=ResponseIntent(
                    attachToFocus=True,
                    guidance="Begin diagnosis.",
                ),
                confidence=1.0,
            ),
            message="Help me diagnose the car.",
            turn_id="turn-decision-focus",
            source="unit-test",
        )

        turn_id = "turn-decision-off-topic"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=False,
                    guidance="I do not have a dog.",
                ),
                confidence=1.0,
            ),
            message="What is your dog's last name?",
            turn_id=turn_id,
            source="unit-test",
        )

        decision = guarded_response_decision_for_turn(turn_id)
        self.assertIsNone(decision.candidate)
        self.assertEqual(
            decision.fallbackReason,
            "not_attached_to_focus",
        )
        self.assertEqual(decision.fallbackDetails, ())

    def test_guarded_decision_exposes_candidate_ineligibility(self) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose starting problem",
                        objective="Restore reliable starting.",
                    ),
                ],
                responseIntent=ResponseIntent(
                    attachToFocus=True,
                    guidance="Begin diagnosis.",
                ),
                confidence=1.0,
            ),
            message="Help me diagnose the car.",
            turn_id="turn-ineligible-focus",
            source="unit-test",
        )

        turn_id = "turn-ineligible-details"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=True,
                    guidance="Your calendar is clear.",
                ),
                confidence=1.0,
            ),
            message="What next?",
            turn_id=turn_id,
            source="unit-test",
        )

        decision = guarded_response_decision_for_turn(turn_id)
        self.assertIsNone(decision.candidate)
        self.assertEqual(
            decision.fallbackReason,
            "candidate_ineligible",
        )
        self.assertIn(
            "calendar_availability_without_tool",
            decision.fallbackDetails,
        )

    def test_assistant_reply_persists_guarded_fallback_telemetry(
        self,
    ) -> None:
        turn_id = self._create_turn()

        record_assistant_reply(
            text="Legacy fallback response.",
            source_turn_id=turn_id,
            source="chat-visible-response",
            transport="json",
            fallback_reason="candidate_ineligible",
            fallback_details=("unterminated_procedure",),
        )

        reply_event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ASSISTANT_REPLIED
        )
        self.assertEqual(
            reply_event.payload["guardedFallback"],
            {
                "used": True,
                "reason": "candidate_ineligible",
                "details": ["unterminated_procedure"],
            },
        )
        self.assertEqual(
            reply_event.payload["audit"]["guardedFallbackReason"],
            "candidate_ineligible",
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



    def test_tool_result_candidate_preserves_citations(self) -> None:
        turn_id = "turn-tool-result-candidate"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Research starter symptoms",
                        objective="Find evidence for the diagnosis.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        attachToFocus=True,
                        reason="Find relevant automotive sources.",
                    )
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=False,
                    attachToFocus=True,
                    acknowledge="Searching now.",
                ),
                confidence=1.0,
            ),
            message="Search for current starter symptoms.",
            turn_id=turn_id,
            source="unit-test",
        )
        record_tool_result(
            tool=ToolName.SEARCH,
            success=True,
            summary="A single click often points to the starter circuit.",
            result_ids=["https://example.com/starter"],
            source_turn_id=turn_id,
        )
        candidate = record_tool_response_candidate(
            tool=ToolName.SEARCH,
            success=True,
            query="single click no start",
            summary="A single click often points to the starter circuit.",
            recommendation="Inspect the battery connections first.",
            steps=["Check terminal tightness."],
            sources=[
                {
                    "title": "Starter diagnosis",
                    "url": "https://example.com/starter",
                    "domain": "example.com",
                }
            ],
            source_turn_id=turn_id,
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.payload["stage"], "tool_result")
        self.assertTrue(candidate.payload["eligibility"]["eligible"])
        self.assertEqual(
            candidate.payload["citations"][0]["url"],
            "https://example.com/starter",
        )
        self.assertIn(
            "[Starter diagnosis](https://example.com/starter)",
            candidate.payload["text"],
        )

        decision = guarded_tool_response_decision_for_turn(
            turn_id,
            tool=ToolName.SEARCH,
        )
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.candidate, candidate)

    def test_tool_result_candidate_requires_citations(self) -> None:
        turn_id = "turn-tool-result-no-citations"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Research starter symptoms",
                        objective="Find evidence for the diagnosis.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        attachToFocus=True,
                    )
                ],
                confidence=1.0,
            ),
            message="Search for starter symptoms.",
            turn_id=turn_id,
            source="unit-test",
        )
        record_tool_result(
            tool=ToolName.SEARCH,
            success=True,
            summary="A result without citations.",
            result_ids=[],
            source_turn_id=turn_id,
        )
        record_tool_response_candidate(
            tool=ToolName.SEARCH,
            success=True,
            query="starter symptoms",
            summary="A result without citations.",
            sources=[],
            source_turn_id=turn_id,
        )

        decision = guarded_tool_response_decision_for_turn(turn_id)
        self.assertFalse(decision.eligible)
        self.assertEqual(decision.fallbackReason, "candidate_ineligible")
        self.assertIn("missing_tool_citations", decision.fallbackDetails)


    def test_calendar_candidate_lists_verified_events_without_free_time_claim(
        self,
    ) -> None:
        turn_id = "turn-calendar-events"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Prepare for meetings",
                        objective="Prepare for today's scheduled meetings.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.CALENDAR_READ,
                        attachToFocus=True,
                    )
                ],
                confidence=1.0,
            ),
            message="Read my calendar for today.",
            turn_id=turn_id,
            source="unit-test",
        )
        record_tool_result(
            tool=ToolName.CALENDAR_READ,
            success=True,
            summary="One event returned.",
            result_ids=["event-1"],
            source_turn_id=turn_id,
        )
        candidate = record_tool_response_candidate(
            tool=ToolName.CALENDAR_READ,
            success=True,
            calendar_connected=True,
            calendar_view="today",
            calendar_events=[
                {
                    "id": "event-1",
                    "title": "Client review",
                    "time": "10:00 AM",
                    "location": "Room A",
                }
            ],
            source_turn_id=turn_id,
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertTrue(candidate.payload["eligibility"]["eligible"])
        self.assertIn("10:00 AM — Client review", candidate.payload["text"])
        self.assertNotIn("calendar is clear", candidate.payload["text"])
        self.assertEqual(
            candidate.payload["toolEvidence"]["eventCount"],
            1,
        )
        decision = guarded_tool_response_decision_for_turn(
            turn_id,
            tool=ToolName.CALENDAR_READ,
        )
        self.assertTrue(decision.eligible)

    def test_empty_connected_calendar_can_make_verified_clear_claim(
        self,
    ) -> None:
        turn_id = "turn-calendar-empty"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Plan today's work",
                        objective="Plan around today's schedule.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.CALENDAR_READ,
                        attachToFocus=True,
                    )
                ],
                confidence=1.0,
            ),
            message="Read my calendar for today.",
            turn_id=turn_id,
            source="unit-test",
        )
        record_tool_result(
            tool=ToolName.CALENDAR_READ,
            success=True,
            summary="No events returned.",
            result_ids=[],
            source_turn_id=turn_id,
        )
        candidate = record_tool_response_candidate(
            tool=ToolName.CALENDAR_READ,
            success=True,
            calendar_connected=True,
            calendar_view="today",
            calendar_events=[],
            source_turn_id=turn_id,
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertTrue(candidate.payload["eligibility"]["eligible"])
        self.assertIn("calendar is clear", candidate.payload["text"])
        record_assistant_reply(
            text=candidate.payload["text"],
            source_turn_id=turn_id,
            source="focus-tool-visible-response",
            transport="calendar-json",
        )
        reply = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ASSISTANT_REPLIED
        )
        self.assertEqual(reply.payload["audit"]["findings"], [])

    def test_disconnected_calendar_candidate_is_rejected(self) -> None:
        turn_id = "turn-calendar-disconnected"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Plan today's work",
                        objective="Plan around today's schedule.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.CALENDAR_READ,
                        attachToFocus=True,
                    )
                ],
                confidence=1.0,
            ),
            message="Read my calendar for today.",
            turn_id=turn_id,
            source="unit-test",
        )
        record_tool_result(
            tool=ToolName.CALENDAR_READ,
            success=True,
            summary="Calendar is disconnected.",
            result_ids=[],
            source_turn_id=turn_id,
        )
        record_tool_response_candidate(
            tool=ToolName.CALENDAR_READ,
            success=True,
            calendar_connected=False,
            calendar_view="today",
            calendar_events=[],
            source_turn_id=turn_id,
        )

        decision = guarded_tool_response_decision_for_turn(
            turn_id,
            tool=ToolName.CALENDAR_READ,
        )
        self.assertFalse(decision.eligible)
        self.assertIn(
            decision.fallbackReason,
            {"calendar_not_connected", "candidate_ineligible"},
        )


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


class FocusGuardedResponseMiddlewareTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._event_file = (
            Path(self._temporary_directory.name)
            / "qmeet_focus_guarded_test.json"
        )
        self._environment_patch = patch.dict(
            os.environ,
            {
                "QMEET_FOCUS_FILE": str(self._event_file),
                "QMEET_FOCUS_MODE": "shadow",
                "QMEET_FOCUS_RESPONSE_MODE": "guarded",
            },
            clear=False,
        )
        self._environment_patch.start()
        reset_store()

    def tearDown(self) -> None:
        self._environment_patch.stop()
        self._temporary_directory.cleanup()

    @staticmethod
    def _scope(
        path: str,
        turn_id: str,
        *,
        method: str = "POST",
        query_string: bytes = b"",
    ) -> dict:
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": query_string,
            "root_path": "",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-qmeet-turn-id", turn_id.encode("ascii")),
            ],
        }

    @staticmethod
    def _receive_for(message: str):
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {
                    "type": "http.request",
                    "body": json.dumps(
                        {"message": message}
                    ).encode("utf-8"),
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        return receive

    @staticmethod
    def _receive_payload(payload: dict):
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {
                    "type": "http.request",
                    "body": json.dumps(payload).encode("utf-8"),
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        return receive

    def _create_candidate(self, turn_id: str, text: str) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Guarded response test",
                        objective="Verify guarded response delivery.",
                    ),
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=True,
                    guidance=text,
                ),
                confidence=1.0,
            ),
            message="Start the guarded response test.",
            turn_id=turn_id,
            source="unit-test",
        )

    async def test_guarded_json_candidate_bypasses_legacy_app(self) -> None:
        turn_id = "turn-guarded-json"
        candidate_text = "Use the canonical guarded response."
        self._create_candidate(turn_id, candidate_text)
        legacy_called = False

        async def legacy_app(scope, receive, send):
            nonlocal legacy_called
            legacy_called = True
            raise AssertionError("Legacy app should not run.")

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        middleware = FocusShadowMiddleware(legacy_app)

        with (
            patch(
                "app.focus.middleware.prepare_background_chat_message",
                return_value=("context", "visible"),
            ),
            patch(
                "app.focus.middleware.record_background_assistant_reply"
            ) as record_background,
        ):
            await middleware(
                self._scope("/api/chat", turn_id),
                self._receive_for("Show the answer."),
                send,
            )

        self.assertFalse(legacy_called)
        response_body = b"".join(
            message.get("body", b"")
            for message in sent_messages
            if message["type"] == "http.response.body"
        )
        payload = json.loads(response_body.decode("utf-8"))
        self.assertEqual(payload["reply"], candidate_text)
        record_background.assert_called_once_with(candidate_text)

        reply_events = [
            event
            for event in list_events()
            if event.type == FocusEventType.ASSISTANT_REPLIED
            and event.sourceTurnId == turn_id
        ]
        self.assertEqual(len(reply_events), 1)
        self.assertEqual(
            reply_events[0].source,
            "focus-visible-response",
        )
        self.assertEqual(
            reply_events[0].payload["audit"]["findings"],
            [],
        )

    async def test_guarded_sse_candidate_uses_existing_stream_shape(
        self,
    ) -> None:
        turn_id = "turn-guarded-sse"
        candidate_text = "Canonical streamed response."
        self._create_candidate(turn_id, candidate_text)

        async def legacy_app(scope, receive, send):
            raise AssertionError("Legacy app should not run.")

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        middleware = FocusShadowMiddleware(legacy_app)

        with (
            patch(
                "app.focus.middleware.prepare_background_chat_message",
                return_value=("context", "visible"),
            ),
            patch(
                "app.focus.middleware.record_background_assistant_reply"
            ),
        ):
            await middleware(
                self._scope("/api/chat/stream", turn_id),
                self._receive_for("Show the streamed answer."),
                send,
            )

        response_body = b"".join(
            message.get("body", b"")
            for message in sent_messages
            if message["type"] == "http.response.body"
        )
        self.assertEqual(
            _extract_sse_reply(response_body),
            candidate_text,
        )


    async def test_guarded_search_injects_tool_response_and_citations(
        self,
    ) -> None:
        turn_id = "turn-guarded-search"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Research starter symptoms",
                        objective="Find evidence for the diagnosis.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        attachToFocus=True,
                        reason="Find current sources.",
                    )
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=False,
                    attachToFocus=True,
                    acknowledge="Searching now.",
                ),
                confidence=1.0,
            ),
            message="Search for single-click no-start causes.",
            turn_id=turn_id,
            source="unit-test",
        )

        async def search_app(scope, receive, send):
            body = json.dumps(
                {
                    "ok": True,
                    "query": "single-click no-start causes",
                    "summary": "A single click often points to the starter circuit.",
                    "recommendation": "Inspect the battery terminals first.",
                    "steps": ["Check terminal tightness."],
                    "sources": [
                        {
                            "title": "Starter diagnosis",
                            "url": "https://example.com/starter",
                            "domain": "example.com",
                        }
                    ],
                    "provider": "test",
                    "message": "Search completed.",
                }
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                    "more_body": False,
                }
            )

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        middleware = FocusShadowMiddleware(search_app)
        with (
            patch("app.focus.middleware._start_observation"),
            patch(
                "app.focus.middleware._wait_for_guarded_observation",
                new=AsyncMock(return_value=True),
            ),
        ):
            await middleware(
                self._scope("/api/search", turn_id),
                self._receive_payload(
                    {"query": "single-click no-start causes"}
                ),
                send,
            )

        response_start = next(
            message
            for message in sent_messages
            if message["type"] == "http.response.start"
        )
        self.assertEqual(
            dict(response_start["headers"])[b"x-qmeet-response-source"],
            b"focus-tool-guarded",
        )
        response_body = b"".join(
            message.get("body", b"")
            for message in sent_messages
            if message["type"] == "http.response.body"
        )
        payload = json.loads(response_body.decode("utf-8"))
        self.assertEqual(
            payload["focusResponse"]["responseSource"],
            "focus-tool-guarded",
        )
        self.assertEqual(
            payload["focusResponse"]["citations"][0]["url"],
            "https://example.com/starter",
        )
        self.assertIn(
            "Starter diagnosis",
            payload["focusResponse"]["text"],
        )

        reply_event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ASSISTANT_REPLIED
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(
            reply_event.source,
            "focus-tool-visible-response",
        )
        self.assertEqual(reply_event.payload["audit"]["findings"], [])


    async def test_background_calendar_refresh_bypasses_focus_pipeline(
        self,
    ) -> None:
        turn_id = "turn-background-calendar-refresh"

        async def calendar_app(scope, receive, send):
            body = json.dumps(
                {
                    "ok": True,
                    "connected": True,
                    "view": "today",
                    "events": [],
                    "message": "Calendar synchronized.",
                }
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                    "more_body": False,
                }
            )

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        middleware = FocusShadowMiddleware(calendar_app)
        await middleware(
            self._scope(
                "/api/calendar/events",
                turn_id,
                method="GET",
                query_string=b"view=today",
            ),
            self._receive_payload({}),
            send,
        )

        response_body = b"".join(
            message.get("body", b"")
            for message in sent_messages
            if message["type"] == "http.response.body"
        )
        payload = json.loads(response_body.decode("utf-8"))
        self.assertNotIn("focusResponse", payload)
        self.assertEqual(list_events(), [])

    async def test_guarded_calendar_injects_verified_response_and_keeps_events(
        self,
    ) -> None:
        turn_id = "turn-guarded-calendar"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Prepare for meetings",
                        objective="Prepare for today's meetings.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.CALENDAR_READ,
                        attachToFocus=True,
                    )
                ],
                confidence=1.0,
            ),
            message="Read my calendar for today.",
            turn_id=turn_id,
            source="unit-test",
        )

        async def calendar_app(scope, receive, send):
            body = json.dumps(
                {
                    "ok": True,
                    "configured": True,
                    "connected": True,
                    "source": "google",
                    "view": "today",
                    "events": [
                        {
                            "id": "event-1",
                            "title": "Client review",
                            "dateKey": "2026-07-29",
                            "time": "10:00 AM",
                            "createdAt": "2026-07-28T10:00:00-07:00",
                            "source": "google",
                            "location": "Room A",
                            "allDay": False,
                        }
                    ],
                    "message": "Loaded one Google Calendar event.",
                }
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                    "more_body": False,
                }
            )

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        middleware = FocusShadowMiddleware(calendar_app)
        with patch(
            "app.focus.middleware._wait_for_guarded_observation",
            new=AsyncMock(return_value=True),
        ):
            await middleware(
                {
                    **self._scope(
                        "/api/calendar/events",
                        turn_id,
                        method="GET",
                        query_string=b"view=today",
                    ),
                    "headers": [
                        *self._scope(
                            "/api/calendar/events",
                            turn_id,
                            method="GET",
                            query_string=b"view=today",
                        )["headers"],
                        (
                            b"x-qmeet-calendar-read-intent",
                            b"explicit",
                        ),
                    ],
                },
                self._receive_payload({}),
                send,
            )

        response_body = b"".join(
            message.get("body", b"")
            for message in sent_messages
            if message["type"] == "http.response.body"
        )
        payload = json.loads(response_body.decode("utf-8"))
        self.assertEqual(payload["events"][0]["title"], "Client review")
        self.assertEqual(
            payload["focusResponse"]["tool"],
            "calendar_read",
        )
        self.assertEqual(payload["focusResponse"]["citations"], [])
        self.assertIn("Client review", payload["focusResponse"]["text"])
        self.assertNotIn(
            "calendar is clear",
            payload["focusResponse"]["text"],
        )

        reply_event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ASSISTANT_REPLIED
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(
            reply_event.source,
            "focus-tool-visible-response",
        )
        self.assertEqual(reply_event.payload["transport"], "calendar-json")
        self.assertEqual(reply_event.payload["audit"]["findings"], [])


    async def test_calendar_fallback_records_response_selection(
        self,
    ) -> None:
        turn_id = "turn-calendar-unattached"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.CALENDAR_READ,
                        attachToFocus=False,
                    )
                ],
                confidence=1.0,
            ),
            message="Read my calendar for today.",
            turn_id=turn_id,
            source="unit-test",
        )

        async def calendar_app(scope, receive, send):
            body = json.dumps(
                {
                    "ok": True,
                    "connected": True,
                    "view": "today",
                    "events": [],
                    "message": "No events today.",
                }
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                    "more_body": False,
                }
            )

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        middleware = FocusShadowMiddleware(calendar_app)
        with patch(
            "app.focus.middleware._wait_for_guarded_observation",
            new=AsyncMock(return_value=True),
        ):
            await middleware(
                {
                    **self._scope(
                        "/api/calendar/events",
                        turn_id,
                        method="GET",
                        query_string=b"view=today",
                    ),
                    "headers": [
                        *self._scope(
                            "/api/calendar/events",
                            turn_id,
                            method="GET",
                            query_string=b"view=today",
                        )["headers"],
                        (
                            b"x-qmeet-calendar-read-intent",
                            b"explicit",
                        ),
                    ],
                },
                self._receive_payload({}),
                send,
            )

        selection = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.RESPONSE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(
            selection.payload["reason"],
            "tool_not_attached_to_focus",
        )
        self.assertEqual(
            selection.payload["responseSource"],
            "calendar-legacy-readout",
        )

    async def test_missing_candidate_falls_back_to_legacy_app(
        self,
    ) -> None:
        turn_id = "turn-guarded-fallback"
        legacy_called = False

        async def legacy_app(scope, receive, send):
            nonlocal legacy_called
            legacy_called = True
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (
                            b"content-type",
                            b"application/json; charset=utf-8",
                        )
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": json.dumps(
                        {
                            "reply": "Legacy fallback response.",
                            "state": "speaking",
                        }
                    ).encode("utf-8"),
                    "more_body": False,
                }
            )

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        middleware = FocusShadowMiddleware(legacy_app)

        with (
            patch(
                "app.focus.middleware._start_observation"
            ),
            patch(
                "app.focus.middleware._wait_for_guarded_observation",
                new=AsyncMock(return_value=False),
            ),
        ):
            await middleware(
                self._scope("/api/chat", turn_id),
                self._receive_for("Use fallback."),
                send,
            )

        self.assertTrue(legacy_called)
        response_body = b"".join(
            message.get("body", b"")
            for message in sent_messages
            if message["type"] == "http.response.body"
        )
        payload = json.loads(response_body.decode("utf-8"))
        self.assertEqual(
            payload["reply"],
            "Legacy fallback response.",
        )
        response_start = next(
            message
            for message in sent_messages
            if message["type"] == "http.response.start"
        )
        headers = dict(response_start.get("headers", []))
        self.assertEqual(
            headers[b"x-qmeet-fallback-reason"],
            b"observation_timeout",
        )

        await asyncio.sleep(0)
        reply_events = [
            event
            for event in list_events()
            if event.type == FocusEventType.ASSISTANT_REPLIED
            and event.sourceTurnId == turn_id
        ]
        self.assertEqual(len(reply_events), 1)
        self.assertEqual(
            reply_events[0].payload["guardedFallback"]["reason"],
            "observation_timeout",
        )


    async def test_work_context_failure_records_fallback_reason(self) -> None:
        turn_id = "turn-guarded-work-context-fallback"
        self._create_candidate(turn_id, "Canonical response.")

        async def legacy_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8")
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": json.dumps(
                        {
                            "reply": "Legacy after work-context failure.",
                            "state": "speaking",
                        }
                    ).encode("utf-8"),
                    "more_body": False,
                }
            )

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        middleware = FocusShadowMiddleware(legacy_app)

        with patch(
            "app.focus.middleware._prepare_guarded_work_context",
            return_value=False,
        ):
            await middleware(
                self._scope("/api/chat", turn_id),
                self._receive_for("Show the answer."),
                send,
            )

        response_start = next(
            message
            for message in sent_messages
            if message["type"] == "http.response.start"
        )
        self.assertEqual(
            dict(response_start["headers"])[
                b"x-qmeet-fallback-reason"
            ],
            b"work_context_sync_failed",
        )

        await asyncio.sleep(0)
        reply_event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ASSISTANT_REPLIED
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(
            reply_event.payload["guardedFallback"]["reason"],
            "work_context_sync_failed",
        )



class FocusGuardedRouteMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._event_file = (
            Path(self._temporary_directory.name)
            / "qmeet_focus_route_test.json"
        )
        self._environment_patch = patch.dict(
            os.environ,
            {
                "QMEET_FOCUS_FILE": str(self._event_file),
                "QMEET_FOCUS_MODE": "shadow",
                "QMEET_FOCUS_RESPONSE_MODE": "shadow",
                "QMEET_FOCUS_ROUTE_MODE": "guarded",
                "QMEET_FOCUS_ROUTE_MIN_CONFIDENCE": "0.9",
            },
            clear=False,
        )
        self._environment_patch.start()
        reset_store()

    def tearDown(self) -> None:
        self._environment_patch.stop()
        self._temporary_directory.cleanup()

    @staticmethod
    def _scope(turn_id: str) -> dict:
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/command/interpret",
            "raw_path": b"/api/command/interpret",
            "query_string": b"",
            "root_path": "",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-qmeet-turn-id", turn_id.encode("ascii")),
            ],
        }

    @staticmethod
    def _receive(message: str):
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {
                    "type": "http.request",
                    "body": json.dumps({"message": message}).encode("utf-8"),
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        return receive

    @staticmethod
    def _legacy_app(payload: dict, status: int = 200):
        async def app(scope, receive, send):
            body = json.dumps(payload).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                    "more_body": False,
                }
            )

        return app

    async def _run(self, *, turn_id: str, message: str, legacy_payload: dict):
        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        middleware = FocusShadowMiddleware(self._legacy_app(legacy_payload))
        with (
            patch("app.focus.middleware._start_observation"),
            patch(
                "app.focus.middleware._wait_for_guarded_observation",
                new=AsyncMock(return_value=True),
            ),
        ):
            await middleware(
                self._scope(turn_id),
                self._receive(message),
                send,
            )
        return sent_messages

    async def test_guarded_route_takes_over_chat_agreement(self) -> None:
        turn_id = "turn-route-middleware-chat"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    guidance="Explain the next step.",
                ),
                confidence=0.97,
            ),
            message="Explain the next step in my current focus.",
            turn_id=turn_id,
            source="unit-test",
        )
        legacy_payload = {
            "intent": "chat",
            "action": "none",
            "confidence": 0.92,
            "frontendCommand": "",
            "payload": {},
            "reason": "Legacy router selected normal chat.",
        }

        sent = await self._run(
            turn_id=turn_id,
            message="Explain the next step in my current focus.",
            legacy_payload=legacy_payload,
        )

        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(headers[b"x-qmeet-route-source"], b"focus-guarded")
        event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ROUTE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(event.payload["routeClass"], "chat")
        self.assertEqual(event.payload["outcome"], "takeover")

    async def test_route_bridge_repairs_fuzzy_search_chat_response(self) -> None:
        turn_id = "turn-route-bridge-search"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        requiresConfirmation=False,
                    )
                ],
                confidence=1.0,
            ),
            message=(
                "Could you look up the current electric vehicle tax "
                "credits for me?"
            ),
            turn_id=turn_id,
            source="unit-test",
        )

        sent = await self._run(
            turn_id=turn_id,
            message=(
                "Could you look up the current electric vehicle tax "
                "credits for me?"
            ),
            legacy_payload={
                "intent": "chat",
                "action": "none",
                "confidence": 0.8,
                "frontendCommand": "",
                "payload": {},
                "reason": "Legacy model mislabeled Search as chat.",
            },
        )

        response_start = next(
            item for item in sent if item["type"] == "http.response.start"
        )
        headers = dict(response_start["headers"])
        self.assertEqual(headers[b"x-qmeet-route-source"], b"focus-guarded")
        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["intent"], "command")
        self.assertEqual(payload["action"], "prepare_search")
        self.assertEqual(
            payload["frontendCommand"],
            "search for current electric vehicle tax credits",
        )

    async def test_route_bridge_repairs_fuzzy_calendar_read_chat_response(
        self,
    ) -> None:
        turn_id = "turn-route-bridge-calendar-read"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.CALENDAR_READ,
                        requiresConfirmation=False,
                    )
                ],
                confidence=1.0,
            ),
            message="Could you check what is on my calendar today?",
            turn_id=turn_id,
            source="unit-test",
        )

        sent = await self._run(
            turn_id=turn_id,
            message="Could you check what is on my calendar today?",
            legacy_payload={
                "intent": "chat",
                "action": "none",
                "confidence": 0.8,
                "frontendCommand": "",
                "payload": {},
                "reason": "Legacy model mislabeled Calendar read as chat.",
            },
        )

        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(headers[b"x-qmeet-route-source"], b"focus-guarded")
        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["action"], "read_calendar")
        self.assertEqual(
            payload["frontendCommand"],
            "what's on my calendar today",
        )

    async def test_route_bridge_repairs_visual_history_chat_response(self) -> None:
        turn_id = "turn-route-bridge-visual-history"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.VISUAL_READ,
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                confidence=1.0,
            ),
            message="Could you show my recent visual observations?",
            turn_id=turn_id,
            source="command-interpret-shadow",
        )

        sent = await self._run(
            turn_id=turn_id,
            message="Could you show my recent visual observations?",
            legacy_payload={
                "intent": "chat",
                "action": "none",
                "confidence": 0.8,
                "frontendCommand": "",
                "payload": {},
                "reason": "Legacy model mislabeled visual history as chat.",
            },
        )

        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(headers[b"x-qmeet-route-source"], b"focus-guarded")
        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["intent"], "command")
        self.assertEqual(payload["action"], "read_visual_history")
        self.assertEqual(
            payload["frontendCommand"],
            "show visual observations",
        )
        self.assertEqual(payload["payload"], {"mode": "history"})

        event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ROUTE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(event.payload["outcome"], "takeover")
        self.assertEqual(event.payload["routeClass"], "visual_read")

    async def test_route_bridge_restores_notes_read(self) -> None:
        turn_id = "turn-route-bridge-notes-read"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.NOTES_READ,
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                confidence=1.0,
            ),
            message="Could you summarize my notes?",
            turn_id=turn_id,
            source="command-interpret-shadow",
        )

        sent = await self._run(
            turn_id=turn_id,
            message="Could you summarize my notes?",
            legacy_payload={
                "intent": "chat",
                "action": "none",
                "confidence": 0.8,
                "frontendCommand": "",
                "payload": {},
                "reason": "Legacy model mislabeled Notes read as chat.",
            },
        )

        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(headers[b"x-qmeet-route-source"], b"focus-guarded")
        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["intent"], "command")
        self.assertEqual(payload["action"], "read_notes")
        self.assertEqual(payload["frontendCommand"], "read my notes")
        self.assertEqual(payload["payload"], {"surface": "notes"})

        event = next(
            event for event in reversed(list_events())
            if event.type == FocusEventType.ROUTE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(event.payload["outcome"], "takeover")
        self.assertEqual(event.payload["routeClass"], "notes_read")

    async def test_route_bridge_restores_tasks_read(self) -> None:
        turn_id = "turn-route-bridge-tasks-read"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.TASKS_READ,
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                confidence=1.0,
            ),
            message="Could you show me my open tasks?",
            turn_id=turn_id,
            source="command-interpret-shadow",
        )

        sent = await self._run(
            turn_id=turn_id,
            message="Could you show me my open tasks?",
            legacy_payload={
                "intent": "chat",
                "action": "none",
                "confidence": 0.8,
                "frontendCommand": "",
                "payload": {},
                "reason": "Legacy model mislabeled Tasks read as chat.",
            },
        )

        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(headers[b"x-qmeet-route-source"], b"focus-guarded")
        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["action"], "read_memory")
        self.assertEqual(payload["frontendCommand"], "read memory")
        self.assertEqual(payload["payload"], {"surface": "tasks"})

    async def test_route_bridge_restores_protected_task_completion(self) -> None:
        turn_id = "turn-route-bridge-task-complete"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.MEMORY_WRITE,
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                confidence=1.0,
            ),
            message="Could you mark the budget task done?",
            turn_id=turn_id,
            source="command-interpret-shadow",
        )

        sent = await self._run(
            turn_id=turn_id,
            message="Could you mark the budget task done?",
            legacy_payload={
                "intent": "chat",
                "action": "none",
                "confidence": 0.8,
                "frontendCommand": "",
                "payload": {},
                "reason": "Legacy model mislabeled task completion as chat.",
            },
        )

        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(
            headers[b"x-qmeet-route-fallback"],
            b"protected_legacy_route",
        )
        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["action"], "mark_task_done")
        self.assertEqual(payload["frontendCommand"], "mark task budget done")
        self.assertEqual(
            payload["payload"],
            {"operation": "complete_task", "value": "budget"},
        )

        event = next(
            event for event in reversed(list_events())
            if event.type == FocusEventType.ROUTE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(event.payload["outcome"], "fallback")
        self.assertEqual(event.payload["reason"], "protected_legacy_route")
        self.assertEqual(event.payload["legacyAction"], "mark_task_done")

    async def test_route_bridge_preserves_named_task_when_legacy_command_is_vague(
        self,
    ) -> None:
        turn_id = "turn-route-bridge-task-target-preservation"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.MEMORY_WRITE,
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                confidence=1.0,
            ),
            message="Could you mark the budget task done?",
            turn_id=turn_id,
            source="command-interpret-shadow",
        )

        sent = await self._run(
            turn_id=turn_id,
            message="Could you mark the budget task done?",
            legacy_payload={
                "intent": "command",
                "action": "mark_task_done",
                "confidence": 1.0,
                "frontendCommand": "mark task done",
                "payload": {"operation": "complete_task"},
                "reason": "Legacy model recognized completion but lost the title.",
            },
        )

        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(
            headers[b"x-qmeet-route-fallback"],
            b"protected_legacy_route",
        )
        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["action"], "mark_task_done")
        self.assertEqual(payload["frontendCommand"], "mark task budget done")
        self.assertEqual(
            payload["payload"],
            {"operation": "complete_task", "value": "budget"},
        )
        self.assertIn("preserved the named task target", payload["reason"])

        event = next(
            event for event in reversed(list_events())
            if event.type == FocusEventType.ROUTE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(event.payload["outcome"], "fallback")
        self.assertEqual(event.payload["reason"], "protected_legacy_route")
        self.assertEqual(event.payload["legacyAction"], "mark_task_done")

    async def test_route_bridge_restores_protected_visual_delete(self) -> None:
        turn_id = "turn-route-bridge-visual-delete"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.VISUAL_WRITE,
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                confidence=1.0,
            ),
            message="Could you delete my last visual observation?",
            turn_id=turn_id,
            source="command-interpret-shadow",
        )

        sent = await self._run(
            turn_id=turn_id,
            message="Could you delete my last visual observation?",
            legacy_payload={
                "intent": "chat",
                "action": "none",
                "confidence": 0.8,
                "frontendCommand": "",
                "payload": {},
                "reason": "Legacy model mislabeled visual deletion as chat.",
            },
        )

        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(
            headers[b"x-qmeet-route-fallback"],
            b"protected_legacy_route",
        )
        self.assertNotIn(b"x-qmeet-route-source", headers)

        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["intent"], "command")
        self.assertEqual(
            payload["action"],
            "delete_last_visual_observation",
        )
        self.assertEqual(
            payload["frontendCommand"],
            "delete last visual observation",
        )
        self.assertEqual(payload["payload"], {"operation": "delete_last"})

        event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ROUTE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(event.payload["outcome"], "fallback")
        self.assertEqual(event.payload["reason"], "protected_legacy_route")
        self.assertEqual(
            event.payload["legacyAction"],
            "delete_last_visual_observation",
        )

    async def test_route_bridge_restores_calendar_write_confirmation(self) -> None:
        turn_id = "turn-route-bridge-calendar-write"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.CALENDAR_WRITE,
                        requiresConfirmation=True,
                        attachToFocus=False,
                    )
                ],
                confidence=1.0,
            ),
            message=(
                "Could you schedule a work meeting tomorrow at "
                "3:00 p.m.?"
            ),
            turn_id=turn_id,
            source="unit-test",
        )

        sent = await self._run(
            turn_id=turn_id,
            message=(
                "Could you schedule a work meeting tomorrow at "
                "3:00 p.m.?"
            ),
            legacy_payload={
                "intent": "chat",
                "action": "none",
                "confidence": 0.8,
                "frontendCommand": "",
                "payload": {},
                "reason": "Legacy model mislabeled Calendar write as chat.",
            },
        )

        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(
            headers[b"x-qmeet-route-fallback"],
            b"confirmation_gated_legacy_route",
        )
        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["intent"], "command")
        self.assertEqual(payload["action"], "add_calendar_event")
        self.assertEqual(
            payload["frontendCommand"],
            "schedule a meeting tomorrow at 3:00 PM called work meeting",
        )
        event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ROUTE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(
            event.payload["reason"],
            "confirmation_gated_legacy_route",
        )
        self.assertEqual(event.payload["legacyAction"], "add_calendar_event")

    async def test_guarded_route_takes_over_safe_search_agreement(self) -> None:
        turn_id = "turn-route-middleware-search"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        requiresConfirmation=False,
                    )
                ],
                confidence=1.0,
            ),
            message="Search for current electric vehicle tax credits.",
            turn_id=turn_id,
            source="unit-test",
        )
        legacy_payload = {
            "intent": "command",
            "action": "prepare_search",
            "confidence": 0.95,
            "frontendCommand": "search for current electric vehicle tax credits",
            "payload": {"query": "current electric vehicle tax credits"},
            "reason": "Legacy router selected Search.",
        }

        sent = await self._run(
            turn_id=turn_id,
            message="Search for current electric vehicle tax credits.",
            legacy_payload=legacy_payload,
        )

        response_start = next(
            item for item in sent if item["type"] == "http.response.start"
        )
        headers = dict(response_start["headers"])
        self.assertEqual(headers[b"x-qmeet-route-source"], b"focus-guarded")
        body = b"".join(
            item.get("body", b"")
            for item in sent
            if item["type"] == "http.response.body"
        )
        self.assertEqual(json.loads(body.decode("utf-8")), legacy_payload)

        event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ROUTE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(event.payload["outcome"], "takeover")
        self.assertEqual(event.payload["routeClass"], "search")
        self.assertEqual(event.payload["responseSource"], "focus-route-guarded")

    async def test_guarded_route_takes_over_calendar_read_agreement(self) -> None:
        turn_id = "turn-route-middleware-calendar"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.CALENDAR_READ,
                        requiresConfirmation=False,
                    )
                ],
                confidence=0.99,
            ),
            message="Read my calendar for today.",
            turn_id=turn_id,
            source="unit-test",
        )
        sent = await self._run(
            turn_id=turn_id,
            message="Read my calendar for today.",
            legacy_payload={
                "intent": "command",
                "action": "read_calendar",
                "confidence": 0.97,
                "frontendCommand": "show today's calendar",
                "payload": {"view": "today"},
                "reason": "Legacy router selected Calendar read.",
            },
        )
        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(headers[b"x-qmeet-route-source"], b"focus-guarded")

    async def test_guarded_route_falls_back_on_disagreement(self) -> None:
        turn_id = "turn-route-middleware-disagreement"
        apply_turn_plan(
            TurnPlan(route=TurnRoute.RESPOND, confidence=1.0),
            message="Explain the next step.",
            turn_id=turn_id,
            source="unit-test",
        )
        sent = await self._run(
            turn_id=turn_id,
            message="Explain the next step.",
            legacy_payload={
                "intent": "command",
                "action": "prepare_search",
                "confidence": 0.95,
                "frontendCommand": "search for the next step",
                "payload": {},
                "reason": "Legacy selected Search.",
            },
        )
        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(
            headers[b"x-qmeet-route-fallback"],
            b"route_disagreement",
        )
        event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.ROUTE_SELECTION
            and event.sourceTurnId == turn_id
        )
        self.assertEqual(event.payload["outcome"], "fallback")
        self.assertEqual(event.payload["reason"], "route_disagreement")

    async def test_guarded_route_preserves_confirmation_gated_write(self) -> None:
        turn_id = "turn-route-middleware-write"
        apply_turn_plan(
            TurnPlan(route=TurnRoute.RESPOND, confidence=1.0),
            message="Schedule a meeting tomorrow at 3 PM.",
            turn_id=turn_id,
            source="unit-test",
        )
        sent = await self._run(
            turn_id=turn_id,
            message="Schedule a meeting tomorrow at 3 PM.",
            legacy_payload={
                "intent": "command",
                "action": "add_calendar_event",
                "confidence": 0.98,
                "frontendCommand": "add event tomorrow at 3:00 PM called meeting",
                "payload": {},
                "reason": "Calendar write requires frontend confirmation.",
            },
        )
        headers = dict(next(
            item for item in sent if item["type"] == "http.response.start"
        )["headers"])
        self.assertEqual(
            headers[b"x-qmeet-route-fallback"],
            b"confirmation_gated_legacy_route",
        )


if __name__ == "__main__":
    unittest.main()
