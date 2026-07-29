from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.focus.models import (
    FocusField,
    FocusOperation,
    FocusOperationKind,
    FocusState,
    PlannedToolCall,
    ResponseIntent,
    TurnPlan,
    ToolName,
    TurnRoute,
)
from app.focus.planner import (
    _PLANNER_SYSTEM_PROMPT,
    _compact_recent_event_payload,
    _normalize_calendar_read_plan,
    _normalize_calendar_write_plan,
    _normalize_focus_read_plan,
    _normalize_memory_mutation_plan,
    _normalize_memory_read_plan,
    _normalize_visual_mutation_plan,
    _normalize_visual_read_plan,
    _plan_question_errors,
    _recent_event_summary,
    _question_is_atomic,
    _strip_invalid_follow_up,
)


class FocusPlannerCalendarToolContractTests(unittest.TestCase):
    def test_calendar_read_tool_is_available_and_prompted(self) -> None:
        self.assertEqual(ToolName.CALENDAR_READ.value, "calendar_read")
        self.assertEqual(ToolName.CALENDAR_WRITE.value, "calendar_write")
        self.assertEqual(ToolName.VISUAL_READ.value, "visual_read")
        self.assertEqual(ToolName.VISUAL_WRITE.value, "visual_write")
        self.assertEqual(ToolName.NOTES_READ.value, "notes_read")
        self.assertEqual(ToolName.TASKS_READ.value, "tasks_read")
        self.assertEqual(ToolName.MEMORY_WRITE.value, "memory_write")
        self.assertIn("calendar_read", _PLANNER_SYSTEM_PROMPT)
        self.assertIn("calendar_write", _PLANNER_SYSTEM_PROMPT)
        self.assertIn("visual_read", _PLANNER_SYSTEM_PROMPT)
        self.assertIn("visual_write", _PLANNER_SYSTEM_PROMPT)
        self.assertIn("notes_read", _PLANNER_SYSTEM_PROMPT)
        self.assertIn("tasks_read", _PLANNER_SYSTEM_PROMPT)
        self.assertIn("memory_write", _PLANNER_SYSTEM_PROMPT)
        self.assertIn("calendar-read-shadow", _PLANNER_SYSTEM_PROMPT)
        self.assertIn("Never fabricate tool", _PLANNER_SYSTEM_PROMPT)
        self.assertIn(
            "results, calendar contents, free time",
            _PLANNER_SYSTEM_PROMPT,
        )


class FocusPlannerMemoryRoutingNormalizationTests(unittest.TestCase):
    def test_notes_read_is_normalized_as_route_only_tool(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.RESPOND,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.KNOWN_FACTS,
                    value="This must not be stored.",
                )
            ],
            responseIntent=ResponseIntent(
                answerDirectly=True,
                attachToFocus=True,
                guidance="I will read your notes.",
            ),
            confidence=0.7,
        )

        normalized = _normalize_memory_read_plan(
            plan,
            source="command-interpret-shadow",
            message="Could you summarize my notes?",
        )

        self.assertEqual(normalized.route, TurnRoute.TOOL)
        self.assertEqual(normalized.focusOperations, [])
        self.assertEqual(normalized.toolCalls[0].tool, ToolName.NOTES_READ)
        self.assertFalse(normalized.toolCalls[0].requiresConfirmation)
        self.assertFalse(normalized.toolCalls[0].attachToFocus)
        self.assertEqual(
            {argument.key: argument.value for argument in normalized.toolCalls[0].arguments},
            {"surface": "notes"},
        )
        self.assertFalse(normalized.responseIntent.answerDirectly)
        self.assertGreaterEqual(normalized.confidence, 0.99)

    def test_tasks_read_is_normalized_as_route_only_tool(self) -> None:
        normalized = _normalize_memory_read_plan(
            TurnPlan(route=TurnRoute.RESPOND, confidence=0.8),
            source="command-interpret-shadow",
            message="Could you show me my open tasks?",
        )
        self.assertEqual(normalized.toolCalls[0].tool, ToolName.TASKS_READ)
        self.assertEqual(
            {argument.key: argument.value for argument in normalized.toolCalls[0].arguments},
            {"surface": "tasks"},
        )

    def test_task_mutation_is_not_normalized_as_read(self) -> None:
        plan = TurnPlan(route=TurnRoute.RESPOND, confidence=0.8)
        normalized = _normalize_memory_read_plan(
            plan,
            source="command-interpret-shadow",
            message="Could you mark the budget task done?",
        )
        self.assertEqual(normalized, plan)

    def test_task_completion_is_protected_route_only_write(self) -> None:
        normalized = _normalize_memory_mutation_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.ADD_LIST_ITEM,
                        field=FocusField.KNOWN_FACTS,
                        value="Must be suppressed.",
                    )
                ],
                confidence=0.8,
            ),
            source="command-interpret-shadow",
            message="Could you mark the budget task done?",
        )
        self.assertEqual(normalized.route, TurnRoute.TOOL)
        self.assertEqual(normalized.focusOperations, [])
        self.assertEqual(normalized.toolCalls[0].tool, ToolName.MEMORY_WRITE)
        self.assertFalse(normalized.toolCalls[0].requiresConfirmation)
        self.assertFalse(normalized.toolCalls[0].attachToFocus)
        self.assertEqual(
            {argument.key: argument.value for argument in normalized.toolCalls[0].arguments},
            {"operation": "complete_task", "value": "budget"},
        )



class FocusPlannerVisualReadNormalizationTests(unittest.TestCase):
    def test_visual_history_is_normalized_as_route_only_read(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.RESPOND,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.KNOWN_FACTS,
                    value="The user asked about visual history.",
                )
            ],
            responseIntent=ResponseIntent(
                answerDirectly=True,
                attachToFocus=True,
                guidance="I will inspect visual history.",
            ),
            confidence=0.8,
        )

        normalized = _normalize_visual_read_plan(
            plan,
            source="command-interpret-shadow",
            message="Could you show my recent visual observations?",
        )

        self.assertEqual(normalized.route, TurnRoute.TOOL)
        self.assertEqual(normalized.focusOperations, [])
        self.assertEqual(len(normalized.toolCalls), 1)
        tool_call = normalized.toolCalls[0]
        self.assertEqual(tool_call.tool, ToolName.VISUAL_READ)
        self.assertFalse(tool_call.requiresConfirmation)
        self.assertFalse(tool_call.attachToFocus)
        self.assertEqual(
            {argument.key: argument.value for argument in tool_call.arguments},
            {"mode": "history"},
        )
        self.assertFalse(normalized.responseIntent.answerDirectly)
        self.assertFalse(normalized.responseIntent.attachToFocus)
        self.assertGreaterEqual(normalized.confidence, 0.99)

    def test_visual_mutation_is_not_normalized_as_read(self) -> None:
        plan = TurnPlan(route=TurnRoute.RESPOND, confidence=0.95)

        normalized = _normalize_visual_read_plan(
            plan,
            source="command-interpret-shadow",
            message="Delete my last visual observation.",
        )

        self.assertEqual(normalized, plan)

    def test_visual_delete_is_normalized_as_protected_route_only_write(
        self,
    ) -> None:
        plan = TurnPlan(
            route=TurnRoute.RESPOND,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.KNOWN_FACTS,
                    value="The user wants a deletion.",
                )
            ],
            responseIntent=ResponseIntent(
                answerDirectly=True,
                attachToFocus=True,
                guidance="I cannot delete that.",
            ),
            confidence=0.8,
        )

        normalized = _normalize_visual_mutation_plan(
            plan,
            source="command-interpret-shadow",
            message="Could you delete my last visual observation?",
        )

        self.assertEqual(normalized.route, TurnRoute.TOOL)
        self.assertEqual(normalized.focusOperations, [])
        self.assertEqual(len(normalized.toolCalls), 1)
        tool_call = normalized.toolCalls[0]
        self.assertEqual(tool_call.tool, ToolName.VISUAL_WRITE)
        self.assertFalse(tool_call.requiresConfirmation)
        self.assertFalse(tool_call.attachToFocus)
        self.assertEqual(
            {argument.key: argument.value for argument in tool_call.arguments},
            {"operation": "delete_last"},
        )
        self.assertFalse(normalized.responseIntent.answerDirectly)
        self.assertFalse(normalized.responseIntent.attachToFocus)
        self.assertGreaterEqual(normalized.confidence, 0.99)


class FocusPlannerCalendarWriteNormalizationTests(unittest.TestCase):
    def test_calendar_write_cannot_be_recorded_as_attached_read(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.TOOL,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.MILESTONES,
                    value="Read the calendar.",
                )
            ],
            toolCalls=[
                PlannedToolCall(
                    tool=ToolName.CALENDAR_READ,
                    requiresConfirmation=False,
                    attachToFocus=True,
                )
            ],
            responseIntent=ResponseIntent(
                answerDirectly=True,
                attachToFocus=True,
                guidance="Reading the calendar.",
            ),
            confidence=1.0,
        )

        normalized = _normalize_calendar_write_plan(
            plan,
            source="command-interpret-shadow",
            message=(
                "Could you schedule a work meeting tomorrow at "
                "3:00 p.m.?"
            ),
        )

        self.assertEqual(normalized.route, TurnRoute.TOOL)
        self.assertEqual(normalized.focusOperations, [])
        self.assertEqual(len(normalized.toolCalls), 1)
        tool_call = normalized.toolCalls[0]
        self.assertEqual(tool_call.tool, ToolName.CALENDAR_WRITE)
        self.assertTrue(tool_call.requiresConfirmation)
        self.assertFalse(tool_call.attachToFocus)
        self.assertEqual(
            {argument.key: argument.value for argument in tool_call.arguments},
            {
                "day": "tomorrow",
                "time": "3:00 PM",
                "title": "work meeting",
            },
        )
        self.assertFalse(normalized.responseIntent.answerDirectly)
        self.assertFalse(normalized.responseIntent.attachToFocus)

    def test_non_write_command_plan_is_unchanged(self) -> None:
        plan = TurnPlan(route=TurnRoute.RESPOND, confidence=0.97)

        normalized = _normalize_calendar_write_plan(
            plan,
            source="command-interpret-shadow",
            message="Explain the next step in my focus.",
        )

        self.assertEqual(normalized, plan)


class FocusPlannerCalendarAttachmentTests(unittest.TestCase):
    def test_meeting_focus_repairs_calendar_attachment(self) -> None:
        state = FocusState(
            focusId="focus-meetings",
            title="Prepare for my meetings today",
            objective="Be ready for today's work meetings.",
            status="active",
        )
        plan = TurnPlan(
            route=TurnRoute.RESPOND,
            toolCalls=[],
        )

        normalized = _normalize_calendar_read_plan(
            plan,
            state=state,
            source="calendar-read-shadow",
            message="Read my calendar for today.",
        )

        self.assertEqual(normalized.route, TurnRoute.TOOL)
        self.assertEqual(len(normalized.toolCalls), 1)
        self.assertEqual(normalized.toolCalls[0].tool, ToolName.CALENDAR_READ)
        self.assertTrue(normalized.toolCalls[0].attachToFocus)

    def test_unrelated_focus_keeps_calendar_transient(self) -> None:
        state = FocusState(
            focusId="focus-car",
            title="Diagnose car trouble",
            objective="Restore reliable starting.",
            status="active",
        )
        plan = TurnPlan(
            route=TurnRoute.TOOL,
            toolCalls=[
                PlannedToolCall(
                    tool=ToolName.CALENDAR_READ,
                    attachToFocus=True,
                )
            ],
        )

        normalized = _normalize_calendar_read_plan(
            plan,
            state=state,
            source="calendar-read-shadow",
            message="Read my calendar for tomorrow.",
        )

        self.assertFalse(normalized.toolCalls[0].attachToFocus)
        self.assertEqual(normalized.toolCalls[0].arguments[0].value, "tomorrow")


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


class FocusPlannerFocusRecallNormalizationTests(unittest.TestCase):
    def test_focus_read_tool_is_available_and_prompted(self) -> None:
        self.assertEqual(ToolName.FOCUS_READ.value, "focus_read")
        self.assertIn("focus_read", _PLANNER_SYSTEM_PROMPT)

    def test_current_focus_read_is_route_only(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.FOCUS_ACTION,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.KNOWN_FACTS,
                    value="This read must not mutate Focus state.",
                )
            ],
            responseIntent=ResponseIntent(
                answerDirectly=True,
                attachToFocus=True,
                guidance="Do not expose this planner text.",
            ),
            confidence=0.51,
        )

        normalized = _normalize_focus_read_plan(
            plan,
            source="command-interpret-shadow",
            message="Could you tell me what my current focus is?",
        )

        self.assertEqual(normalized.route, TurnRoute.TOOL)
        self.assertEqual(normalized.focusOperations, [])
        self.assertEqual(len(normalized.toolCalls), 1)
        self.assertEqual(normalized.toolCalls[0].tool, ToolName.FOCUS_READ)
        self.assertEqual(
            normalized.toolCalls[0].arguments[0].model_dump(),
            {"key": "mode", "value": "current"},
        )
        self.assertFalse(normalized.toolCalls[0].requiresConfirmation)
        self.assertFalse(normalized.toolCalls[0].attachToFocus)
        self.assertFalse(normalized.responseIntent.answerDirectly)
        self.assertFalse(normalized.responseIntent.attachToFocus)
        self.assertEqual(normalized.confidence, 0.99)

    def test_focus_activity_recap_preserves_timeframe(self) -> None:
        normalized = _normalize_focus_read_plan(
            TurnPlan(route=TurnRoute.RESPOND, confidence=0.4),
            source="command-interpret-shadow",
            message="Could you recap what I worked on today?",
        )

        self.assertEqual(normalized.toolCalls[0].tool, ToolName.FOCUS_READ)
        self.assertEqual(
            [argument.model_dump() for argument in normalized.toolCalls[0].arguments],
            [
                {"key": "mode", "value": "recap"},
                {"key": "timeframe", "value": "today"},
            ],
        )

    def test_focus_resume_is_not_misclassified_as_read(self) -> None:
        plan = TurnPlan(route=TurnRoute.RESPOND, confidence=0.8)
        normalized = _normalize_focus_read_plan(
            plan,
            source="command-interpret-shadow",
            message="Could you resume my last focus session?",
        )
        self.assertEqual(normalized, plan)

if __name__ == "__main__":
    unittest.main()
