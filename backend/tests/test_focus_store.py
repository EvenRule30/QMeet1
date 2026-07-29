from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus.models import (
    FocusEventType,
    FocusField,
    FocusOperation,
    FocusOperationKind,
    FocusStatus,
    LegacyFocusSeed,
    PendingQuestion,
    PlannedToolCall,
    ResponseIntent,
    ToolName,
    TurnPlan,
    TurnRoute,
)
from app.focus.legacy import load_legacy_focus_seed
from app.focus.store import (
    _atomic_write_unlocked,
    _read_log_unlocked,
    apply_turn_plan,
    event_count,
    get_state,
    list_events,
    guarded_route_decision_for_turn,
    guarded_tool_response_decision_for_turn,
    record_assistant_reply,
    record_response_selection,
    record_route_selection,
    record_tool_response_candidate,
    record_tool_result,
    response_selection_summary,
    route_selection_summary,
    reduce_events,
    reset_store,
    seed_from_legacy,
)


class FocusStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._event_file = Path(self._temporary_directory.name) / "qmeet_focus_test.json"
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

    def test_start_focus_and_apply_structured_updates(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.FOCUS_ACTION,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.START_FOCUS,
                    title="Choose a machine-learning laptop",
                    objective="Select a Windows laptop for machine-learning work.",
                    tags=["purchase", "technology"],
                    confidence=0.98,
                ),
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.CONSTRAINTS,
                    value="Maximum budget is $4,000",
                    confidence=0.96,
                ),
                FocusOperation(
                    kind=FocusOperationKind.SET_PENDING_QUESTION,
                    target="brandPreference",
                    question="Do you have a preferred laptop brand?",
                    confidence=0.94,
                ),
            ],
            confidence=0.97,
            reason="The user started a concrete purchasing focus.",
        )

        state = apply_turn_plan(
            plan,
            message="Help me buy a machine-learning laptop under $4,000.",
            turn_id="turn-start-focus",
            source="unit-test",
        )

        self.assertTrue(state.focusId.startswith("focus-"))
        self.assertEqual(state.title, "Choose a machine-learning laptop")
        self.assertEqual(
            state.objective,
            "Select a Windows laptop for machine-learning work.",
        )
        self.assertIn("Maximum budget is $4,000", state.constraints)
        self.assertIn("purchase", state.tags)
        self.assertEqual(state.status, FocusStatus.CLARIFYING)
        self.assertIsNotNone(state.pendingQuestion)
        self.assertEqual(state.pendingQuestion.target, "brandPreference")
        self.assertEqual(state.lastTurnId, "turn-start-focus")

    def test_duplicate_turn_id_is_idempotent(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.FOCUS_ACTION,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.START_FOCUS,
                    title="Prepare a listing",
                    objective="Create and publish a motorcycle listing.",
                ),
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.MILESTONES,
                    value="Draft the listing",
                ),
            ],
            confidence=0.9,
        )

        first_state = apply_turn_plan(
            plan,
            message="Help me sell my motorcycle.",
            turn_id="turn-idempotent",
            source="unit-test",
        )
        count_after_first_apply = event_count()

        second_state = apply_turn_plan(
            plan,
            message="Help me sell my motorcycle.",
            turn_id="turn-idempotent",
            source="unit-test",
        )

        self.assertEqual(event_count(), count_after_first_apply)
        self.assertEqual(first_state.model_dump(), second_state.model_dump())
        self.assertEqual(second_state.milestones.count("Draft the listing"), 1)

    def test_tool_result_records_knowledge_and_restores_prior_status(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.TOOL,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.START_FOCUS,
                    title="Compare laptop options",
                    objective="Find suitable machine-learning laptops.",
                )
            ],
            toolCalls=[
                PlannedToolCall(
                    tool=ToolName.SEARCH,
                    reason="Search for suitable current laptop options.",
                )
            ],
            confidence=0.95,
        )

        waiting_state = apply_turn_plan(
            plan,
            message="Compare reputable machine-learning laptops.",
            turn_id="turn-search",
            source="unit-test",
        )

        self.assertEqual(waiting_state.status, FocusStatus.WAITING)
        self.assertIsNotNone(waiting_state.pendingAction)
        self.assertEqual(waiting_state.pendingAction.kind, ToolName.SEARCH.value)

        completed_state = record_tool_result(
            tool=ToolName.SEARCH,
            success=True,
            summary="Laptop comparison search completed.",
            result_ids=["result-1", "result-2"],
            source_turn_id="turn-search",
            source="unit-test",
        )

        self.assertEqual(completed_state.status, FocusStatus.CLARIFYING)
        self.assertIsNone(completed_state.pendingAction)
        self.assertIn(
            "Laptop comparison search completed.",
            completed_state.knownFacts,
        )
        self.assertNotIn(
            "Laptop comparison search completed.",
            completed_state.completedMilestones,
        )
        self.assertEqual(get_state().model_dump(), completed_state.model_dump())

    def test_legacy_import_persists_generated_focus_id(self) -> None:
        state = seed_from_legacy(
            LegacyFocusSeed(
                title="My car trouble",
                objective="Restore reliable starting and operation for the car.",
                status=FocusStatus.CLARIFYING,
            )
        )

        events = list_events()
        self.assertEqual(len(events), 1)
        imported = events[0]

        self.assertEqual(imported.type, FocusEventType.LEGACY_IMPORTED)
        self.assertTrue(imported.focusId.startswith("focus-"))
        self.assertEqual(imported.payload["focusId"], imported.focusId)
        self.assertEqual(state.focusId, imported.focusId)

        replay_one = reduce_events(events)
        replay_two = reduce_events(events)
        self.assertEqual(replay_one.model_dump(), replay_two.model_dump())
        self.assertEqual(replay_one.focusId, imported.focusId)

    def test_end_then_start_uses_distinct_focus_ids(self) -> None:
        old_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose car trouble",
                        objective="Restore reliable starting and operation.",
                    )
                ],
            ),
            message="Help with my car trouble.",
            turn_id="turn-old-focus",
            source="unit-test",
        )
        old_focus_id = old_state.focusId

        new_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(kind=FocusOperationKind.END_FOCUS),
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Next phase of QMeet",
                        objective="Plan the next implementation phase.",
                    ),
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        reason="Research current implementation options.",
                    )
                ],
            ),
            message="Help me plan the next phase of QMeet.",
            turn_id="turn-switch-focus",
            source="unit-test",
        )

        switch_events = [
            event
            for event in list_events()
            if event.sourceTurnId == "turn-switch-focus"
        ]
        by_type = {event.type: event for event in switch_events}
        ended_events = [
            event
            for event in switch_events
            if event.type == FocusEventType.FOCUS_ENDED
        ]

        self.assertEqual(len(ended_events), 1)
        self.assertNotEqual(new_state.focusId, old_focus_id)
        self.assertEqual(
            by_type[FocusEventType.TURN_PLANNED].focusId,
            old_focus_id,
        )
        self.assertEqual(
            by_type[FocusEventType.FOCUS_ENDED].focusId,
            old_focus_id,
        )
        self.assertEqual(
            by_type[FocusEventType.FOCUS_STARTED].focusId,
            new_state.focusId,
        )
        self.assertEqual(
            by_type[FocusEventType.TOOL_REQUESTED].focusId,
            new_state.focusId,
        )

    def test_starting_new_focus_implicitly_ends_open_focus(self) -> None:
        old_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose car trouble",
                        objective="Restore reliable starting and operation.",
                    )
                ],
            ),
            message="Help with my car trouble.",
            turn_id="turn-car-focus",
            source="unit-test",
        )
        old_focus_id = old_state.focusId

        new_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Plan next phase of QMeet",
                        objective="Develop a concrete roadmap for the next phase.",
                    )
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=False,
                    askQuestion="What are the main goals for this next phase?",
                ),
            ),
            message="Help me plan the next phase of QMeet.",
            turn_id="turn-new-focus-without-explicit-end",
            source="unit-test",
        )

        switch_events = [
            event
            for event in list_events()
            if event.sourceTurnId == "turn-new-focus-without-explicit-end"
        ]
        event_types = [event.type for event in switch_events]
        ended_event = next(
            event
            for event in switch_events
            if event.type == FocusEventType.FOCUS_ENDED
        )
        started_event = next(
            event
            for event in switch_events
            if event.type == FocusEventType.FOCUS_STARTED
        )

        self.assertNotEqual(new_state.focusId, old_focus_id)
        self.assertEqual(ended_event.focusId, old_focus_id)
        self.assertEqual(ended_event.payload["newFocusId"], new_state.focusId)
        self.assertEqual(started_event.focusId, new_state.focusId)
        self.assertLess(
            event_types.index(FocusEventType.FOCUS_ENDED),
            event_types.index(FocusEventType.FOCUS_STARTED),
        )
        self.assertIsNotNone(new_state.pendingQuestion)

    def test_response_question_is_persisted_when_operation_is_missing(self) -> None:
        state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Next phase of QMeet",
                        objective="Plan the next implementation phase.",
                    )
                ],
                responseIntent=ResponseIntent(
                    acknowledge="Starting a new QMeet planning focus.",
                    answerDirectly=False,
                    askQuestion="What are the main goals for this next phase?",
                ),
                confidence=0.96,
            ),
            message="Help me plan the next phase of QMeet.",
            turn_id="turn-follow-up-question",
            source="unit-test",
        )

        question_events = [
            event
            for event in list_events()
            if event.type == FocusEventType.QUESTION_SET
        ]

        self.assertEqual(len(question_events), 1)
        self.assertEqual(question_events[0].focusId, state.focusId)
        self.assertEqual(question_events[0].payload["target"], "follow_up")
        self.assertIsNotNone(state.pendingQuestion)
        self.assertEqual(
            state.pendingQuestion.question,
            "What are the main goals for this next phase?",
        )
        self.assertEqual(state.status, FocusStatus.CLARIFYING)

    def test_explicit_pending_question_is_not_duplicated(self) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Plan QMeet",
                        objective="Choose the next implementation goal.",
                    ),
                    FocusOperation(
                        kind=FocusOperationKind.SET_PENDING_QUESTION,
                        target="priority",
                        question="Which capability should be built first?",
                    ),
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=False,
                    askQuestion="Which capability should be built first?",
                ),
            ),
            message="Help me plan QMeet.",
            turn_id="turn-explicit-question",
            source="unit-test",
        )

        question_events = [
            event
            for event in list_events()
            if event.type == FocusEventType.QUESTION_SET
        ]
        self.assertEqual(len(question_events), 1)
        self.assertEqual(question_events[0].payload["target"], "priority")


    def test_one_off_tool_result_is_logged_without_active_focus(self) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        reason="Look up current information.",
                    )
                ],
                confidence=0.94,
            ),
            message="Raspberry Pi 5 touchscreen performance",
            turn_id="turn-one-off-search",
            source="unit-test",
        )

        state = record_tool_result(
            tool=ToolName.SEARCH,
            success=True,
            summary="Search completed.",
            result_ids=["https://example.com/result"],
            source_turn_id="turn-one-off-search",
            source="unit-test",
        )

        turn_events = [
            event
            for event in list_events()
            if event.sourceTurnId == "turn-one-off-search"
        ]

        self.assertEqual(
            [event.type for event in turn_events],
            [
                FocusEventType.TURN_PLANNED,
                FocusEventType.TOOL_REQUESTED,
                FocusEventType.TOOL_COMPLETED,
            ],
        )
        self.assertEqual(turn_events[-1].focusId, "")
        self.assertEqual(state.status, FocusStatus.INACTIVE)




    def test_transient_search_policy_suppresses_erroneous_focus_start(self) -> None:
        original_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose car trouble",
                        objective="Restore reliable starting and operation.",
                    )
                ],
            ),
            message="Help with my car trouble.",
            turn_id="turn-car-before-bad-search-plan",
            source="unit-test",
        )

        state_after_bad_plan = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Why did my dog leave me?",
                        objective="Explain why the dog left.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        reason="Answer the direct Search query.",
                        attachToFocus=False,
                    )
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=False,
                    askQuestion="When did the dog leave?",
                ),
            ),
            message="why my dog left me",
            turn_id="turn-bad-search-plan",
            source="search-request-shadow",
        )

        turn_events = [
            event
            for event in list_events()
            if event.sourceTurnId == "turn-bad-search-plan"
        ]

        self.assertEqual(
            [event.type for event in turn_events],
            [
                FocusEventType.TURN_PLANNED,
                FocusEventType.TOOL_REQUESTED,
            ],
        )
        self.assertTrue(all(event.focusId == "" for event in turn_events))
        self.assertTrue(
            turn_events[0].payload["executionPolicy"]["transientSearch"]
        )
        self.assertEqual(
            turn_events[0].payload["executionPolicy"][
                "suppressedFocusOperationCount"
            ],
            1,
        )
        self.assertEqual(state_after_bad_plan.model_dump(), original_state.model_dump())


    def test_transient_search_does_not_mutate_unrelated_active_focus(self) -> None:
        original_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose car trouble",
                        objective="Restore reliable starting and operation.",
                    )
                ],
            ),
            message="Help with my car trouble.",
            turn_id="turn-car-before-transient-search",
            source="unit-test",
        )

        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        reason="Answer a one-off unrelated question.",
                        attachToFocus=False,
                    )
                ],
            ),
            message="why my dog left me",
            turn_id="turn-transient-dog-search",
            source="search-request-shadow",
        )

        completed_state = record_tool_result(
            tool=ToolName.SEARCH,
            success=True,
            summary="Search completed for the unrelated dog question.",
            source_turn_id="turn-transient-dog-search",
            source="unit-test",
        )

        turn_events = [
            event
            for event in list_events()
            if event.sourceTurnId == "turn-transient-dog-search"
        ]

        self.assertEqual(
            [event.type for event in turn_events],
            [
                FocusEventType.TURN_PLANNED,
                FocusEventType.TOOL_REQUESTED,
                FocusEventType.TOOL_COMPLETED,
            ],
        )
        self.assertTrue(all(event.focusId == "" for event in turn_events))
        self.assertFalse(turn_events[1].payload["attachToFocus"])
        self.assertEqual(completed_state.model_dump(), original_state.model_dump())

    def test_attached_search_updates_current_focus(self) -> None:
        focus_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Choose a machine-learning laptop",
                        objective="Find a suitable laptop under $4,000.",
                    )
                ],
            ),
            message="Help me choose a machine-learning laptop.",
            turn_id="turn-laptop-focus",
            source="unit-test",
        )

        waiting_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        reason="Find current RTX laptop options under $4,000.",
                        attachToFocus=True,
                    )
                ],
            ),
            message="current RTX laptops under $4,000",
            turn_id="turn-attached-laptop-search",
            source="search-request-shadow",
        )

        self.assertEqual(waiting_state.focusId, focus_state.focusId)
        self.assertEqual(waiting_state.status, FocusStatus.WAITING)
        self.assertIsNotNone(waiting_state.pendingAction)

        completed_state = record_tool_result(
            tool=ToolName.SEARCH,
            success=True,
            summary="Current RTX laptop search completed.",
            source_turn_id="turn-attached-laptop-search",
            source="unit-test",
        )

        turn_events = [
            event
            for event in list_events()
            if event.sourceTurnId == "turn-attached-laptop-search"
        ]
        self.assertTrue(
            all(event.focusId == focus_state.focusId for event in turn_events)
        )
        self.assertTrue(turn_events[1].payload["attachToFocus"])
        self.assertEqual(
            turn_events[1].payload["resumeStatus"],
            FocusStatus.CLARIFYING.value,
        )
        self.assertEqual(completed_state.status, FocusStatus.CLARIFYING)
        self.assertIn(
            "Current RTX laptop search completed.",
            completed_state.knownFacts,
        )
        self.assertNotIn(
            "Current RTX laptop search completed.",
            completed_state.completedMilestones,
        )

    def test_late_tool_result_cannot_mutate_replacement_focus(self) -> None:
        first_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Choose a laptop",
                        objective="Find a suitable laptop.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        reason="Find laptop options.",
                        attachToFocus=True,
                    )
                ],
            ),
            message="Help me find a laptop.",
            turn_id="turn-old-focus-search",
            source="unit-test",
        )
        old_focus_id = first_state.focusId

        replacement_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Plan QMeet",
                        objective="Plan the next QMeet phase.",
                    )
                ],
            ),
            message="Help me plan QMeet instead.",
            turn_id="turn-replacement-focus",
            source="unit-test",
        )

        completed_state = record_tool_result(
            tool=ToolName.SEARCH,
            success=True,
            summary="The old laptop search completed late.",
            source_turn_id="turn-old-focus-search",
            source="unit-test",
        )

        late_event = next(
            event
            for event in reversed(list_events())
            if event.type == FocusEventType.TOOL_COMPLETED
            and event.sourceTurnId == "turn-old-focus-search"
        )

        self.assertEqual(late_event.focusId, old_focus_id)
        self.assertEqual(completed_state.focusId, replacement_state.focusId)
        self.assertEqual(completed_state.title, "Plan QMeet")
        self.assertNotIn(
            "The old laptop search completed late.",
            completed_state.completedMilestones,
        )
        self.assertNotIn(
            "The old laptop search completed late.",
            completed_state.knownFacts,
        )


    def test_command_side_transient_tool_does_not_touch_focus_metadata(self) -> None:
        active_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose car trouble",
                        objective="Restore reliable starting and operation.",
                    )
                ],
            ),
            message="Help with my car trouble.",
            turn_id="turn-active-car",
            source="unit-test",
        )
        before = active_state.model_dump()

        after = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        reason="Answer an unrelated one-off question.",
                        attachToFocus=False,
                    )
                ],
                confidence=0.99,
            ),
            message="why my dog left me",
            turn_id="turn-command-transient",
            source="command-interpret-shadow",
        )

        self.assertEqual(after.model_dump(), before)

        turn_events = [
            event
            for event in list_events()
            if event.sourceTurnId == "turn-command-transient"
        ]
        self.assertEqual(
            [event.type for event in turn_events],
            [
                FocusEventType.TURN_PLANNED,
                FocusEventType.TOOL_REQUESTED,
            ],
        )
        self.assertTrue(all(event.focusId == "" for event in turn_events))
        policy = turn_events[0].payload["executionPolicy"]
        self.assertTrue(policy["transientTool"])
        self.assertTrue(policy["transientSearch"])


    def test_attached_search_restores_legacy_clarifying_status(self) -> None:
        legacy_state = seed_from_legacy(
            LegacyFocusSeed(
                title="My car trouble",
                objective="Restore reliable starting and operation.",
                nextAction="Describe exactly what happens when starting.",
                status=FocusStatus.CLARIFYING,
            )
        )

        waiting_state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        reason="Research common causes of clicking.",
                        attachToFocus=True,
                    )
                ],
            ),
            message="common causes of a car clicking but not starting",
            turn_id="turn-car-search-status",
            source="search-request-shadow",
        )

        self.assertEqual(waiting_state.status, FocusStatus.WAITING)

        completed_state = record_tool_result(
            tool=ToolName.SEARCH,
            success=True,
            summary=(
                "Clicking may indicate a weak battery, poor connection, "
                "or starter problem."
            ),
            source_turn_id="turn-car-search-status",
            source="unit-test",
        )

        self.assertEqual(completed_state.focusId, legacy_state.focusId)
        self.assertEqual(completed_state.status, FocusStatus.CLARIFYING)
        self.assertEqual(
            completed_state.nextAction,
            "Describe exactly what happens when starting.",
        )
        self.assertIn(
            "Clicking may indicate a weak battery, poor connection, or starter problem.",
            completed_state.knownFacts,
        )
        self.assertEqual(completed_state.completedMilestones, [])



    def test_legacy_pending_question_is_not_imported_as_milestone(self) -> None:
        state = seed_from_legacy(
            LegacyFocusSeed(
                title="My car trouble",
                objective="Restore reliable starting and operation.",
                pendingQuestion=PendingQuestion(
                    target="starting_symptom",
                    question=(
                        "What happens when you try to start the car—"
                        "no lights, clicking, cranking, or something else?"
                    ),
                    askedAt="2026-07-23T11:27:44-07:00",
                ),
                status=FocusStatus.CLARIFYING,
            )
        )

        self.assertIsNotNone(state.pendingQuestion)
        self.assertEqual(
            state.pendingQuestion.target,
            "starting_symptom",
        )
        self.assertEqual(state.milestones, [])

    def test_old_legacy_question_milestone_is_repaired_on_replay(self) -> None:
        state = seed_from_legacy(
            LegacyFocusSeed(
                title="My car trouble",
                objective="Restore reliable starting and operation.",
                milestones=[
                    "What happens when you try to start the car—clicking or cranking?"
                ],
                status=FocusStatus.CLARIFYING,
                updatedAt="2026-07-23T11:27:44-07:00",
            )
        )

        self.assertIsNotNone(state.pendingQuestion)
        self.assertEqual(
            state.pendingQuestion.target,
            "legacy_open_question",
        )
        self.assertEqual(
            state.pendingQuestion.question,
            "What happens when you try to start the car—clicking or cranking?",
        )
        self.assertEqual(state.milestones, [])

    def test_legacy_loader_maps_open_question_to_pending_question(self) -> None:
        session = {
            "id": "legacy-car-focus",
            "title": "my car trouble",
            "goal": "Restore reliable starting and operation for the car",
            "mode": "planning",
            "startedAt": "2026-07-23T11:20:00-07:00",
        }
        context_payload = {
            "activeContext": {
                "title": "my car trouble",
                "objective": (
                    "Restore reliable starting and operation for the car"
                ),
                "openQuestions": [
                    "What happens when you try to start the car?"
                ],
                "stage": "clarifying",
                "updatedAt": "2026-07-23T11:27:44-07:00",
            }
        }

        with patch(
            "app.focus.legacy._call_optional",
            side_effect=[session, context_payload],
        ):
            seed = load_legacy_focus_seed()

        self.assertIsNotNone(seed)
        self.assertIsNotNone(seed.pendingQuestion)
        self.assertEqual(
            seed.pendingQuestion.question,
            "What happens when you try to start the car?",
        )
        self.assertEqual(seed.milestones, [])



    def test_pending_question_becomes_canonical_next_action(self) -> None:
        state = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose car trouble",
                        objective="Restore reliable starting and operation.",
                    ),
                    FocusOperation(
                        kind=FocusOperationKind.SET_PENDING_QUESTION,
                        target="light_dimming",
                        question=(
                            "Do the dashboard lights dim when you try to "
                            "start the car?"
                        ),
                    ),
                ],
            ),
            message="Help diagnose my car.",
            turn_id="turn-question-next-action",
            source="unit-test",
        )

        self.assertIsNotNone(state.pendingQuestion)
        self.assertEqual(
            state.nextAction,
            "Do the dashboard lights dim when you try to start the car?",
        )
        self.assertEqual(state.status, FocusStatus.CLARIFYING)

    def test_answered_question_is_replaced_as_next_action(self) -> None:
        initial = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Diagnose car trouble",
                        objective="Restore reliable starting and operation.",
                    ),
                    FocusOperation(
                        kind=FocusOperationKind.SET_PENDING_QUESTION,
                        target="starting_symptom",
                        question="What happens when you try to start the car?",
                    ),
                ],
            ),
            message="Help diagnose my car.",
            turn_id="turn-initial-diagnostic-question",
            source="unit-test",
        )
        self.assertEqual(
            initial.nextAction,
            "What happens when you try to start the car?",
        )

        updated = apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.ADD_LIST_ITEM,
                        field=FocusField.KNOWN_FACTS,
                        value=(
                            "The car clicks once and the dashboard lights "
                            "stay on."
                        ),
                    ),
                    FocusOperation(
                        kind=FocusOperationKind.CLEAR_PENDING_QUESTION,
                        target="starting_symptom",
                    ),
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    askQuestion=(
                        "Do the dashboard lights dim when you try to "
                        "start the car?"
                    ),
                ),
            ),
            message="It clicks once, but the dashboard lights stay on.",
            turn_id="turn-answer-and-next-question",
            source="unit-test",
        )

        self.assertIsNotNone(updated.pendingQuestion)
        self.assertEqual(
            updated.pendingQuestion.question,
            "Do the dashboard lights dim when you try to start the car?",
        )
        self.assertEqual(
            updated.nextAction,
            "Do the dashboard lights dim when you try to start the car?",
        )
        self.assertNotEqual(
            updated.nextAction,
            "What happens when you try to start the car?",
        )


    def test_calendar_selector_rejects_clear_claim_with_event_evidence(
        self,
    ) -> None:
        turn_id = "turn-calendar-evidence-guard"
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
                }
            ],
            source_turn_id=turn_id,
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None

        document = _read_log_unlocked()
        stored = next(
            event
            for event in document.events
            if event.id == candidate.id
        )
        stored.payload["text"] = "The calendar is clear today."
        _atomic_write_unlocked(document)

        decision = guarded_tool_response_decision_for_turn(
            turn_id,
            tool=ToolName.CALENDAR_READ,
        )
        self.assertFalse(decision.eligible)
        self.assertEqual(
            decision.fallbackReason,
            "calendar_availability_without_empty_view_evidence",
        )

    def test_response_selection_summary_starts_empty(self) -> None:
        summary = response_selection_summary()

        self.assertEqual(summary["decisionCount"], 0)
        self.assertEqual(summary["takeoverCount"], 0)
        self.assertEqual(summary["fallbackCount"], 0)
        self.assertEqual(summary["successRate"], 0.0)
        self.assertEqual(summary["takeoverRate"], 0.0)
        self.assertEqual(summary["guardedAttemptCount"], 0)
        self.assertEqual(summary["guardedTakeoverRate"], 0.0)
        self.assertEqual(summary["healthyDecisionCount"], 0)
        self.assertEqual(summary["healthyDecisionRate"], 0.0)
        self.assertEqual(summary["expectedFallbackCount"], 0)
        self.assertEqual(summary["safetyFallbackCount"], 0)
        self.assertEqual(summary["systemFailureCount"], 0)
        self.assertEqual(summary["unknownFallbackCount"], 0)
        self.assertEqual(summary["fallbackReasons"], {})
        self.assertEqual(
            summary["fallbackCategoryCounts"],
            {
                "expected": 0,
                "safety": 0,
                "systemFailure": 0,
                "unknown": 0,
            },
        )
        self.assertIsNone(summary["latestDecision"])

    def test_response_selection_summary_counts_guarded_decisions(self) -> None:
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
            ),
            message="Help diagnose my car.",
            turn_id="turn-summary-start",
            source="unit-test",
        )

        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=True,
                    guidance="Check the battery terminals first.",
                ),
                confidence=1.0,
            ),
            message="What should I check next?",
            turn_id="turn-summary-takeover",
            source="unit-test",
        )
        record_assistant_reply(
            text="Check the battery terminals first.",
            source_turn_id="turn-summary-takeover",
            source="focus-visible-response",
            transport="sse",
        )

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
            turn_id="turn-summary-fallback",
            source="unit-test",
        )
        record_assistant_reply(
            text="I am QMeet and do not have a dog.",
            source_turn_id="turn-summary-fallback",
            source="chat-visible-response",
            transport="sse",
            fallback_reason="not_attached_to_focus",
        )

        summary = response_selection_summary()

        self.assertEqual(summary["decisionCount"], 2)
        self.assertEqual(summary["takeoverCount"], 1)
        self.assertEqual(summary["fallbackCount"], 1)
        self.assertEqual(summary["successRate"], 0.5)
        self.assertEqual(summary["takeoverRate"], 0.5)
        self.assertEqual(summary["guardedAttemptCount"], 1)
        self.assertEqual(summary["guardedTakeoverRate"], 1.0)
        self.assertEqual(summary["healthyDecisionCount"], 2)
        self.assertEqual(summary["healthyDecisionRate"], 1.0)
        self.assertEqual(summary["expectedFallbackCount"], 1)
        self.assertEqual(summary["safetyFallbackCount"], 0)
        self.assertEqual(summary["systemFailureCount"], 0)
        self.assertEqual(summary["unknownFallbackCount"], 0)
        self.assertEqual(
            summary["fallbackReasons"],
            {"not_attached_to_focus": 1},
        )
        self.assertEqual(
            summary["fallbackCategoryCounts"],
            {
                "expected": 1,
                "safety": 0,
                "systemFailure": 0,
                "unknown": 0,
            },
        )
        self.assertEqual(
            summary["fallbackReasonsByCategory"]["expected"],
            {"not_attached_to_focus": 1},
        )
        self.assertEqual(
            summary["latestDecision"]["sourceTurnId"],
            "turn-summary-fallback",
        )
        self.assertEqual(
            summary["latestDecision"]["outcome"],
            "fallback",
        )
        self.assertEqual(
            summary["latestDecision"]["reason"],
            "not_attached_to_focus",
        )
        self.assertEqual(
            summary["latestDecision"]["category"],
            "expected",
        )
        self.assertTrue(summary["latestDecision"]["healthy"])

    def test_response_selection_summary_counts_tool_takeover(self) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Research starter symptoms",
                        objective="Find evidence for the diagnosis.",
                    )
                ],
            ),
            message="Start research.",
            turn_id="turn-tool-summary-start",
            source="unit-test",
        )
        record_assistant_reply(
            text="Search result with citations.",
            source_turn_id="turn-tool-summary-visible",
            source="focus-tool-visible-response",
            transport="search-json",
        )

        summary = response_selection_summary()

        self.assertEqual(summary["decisionCount"], 1)
        self.assertEqual(summary["takeoverCount"], 1)
        self.assertEqual(summary["fallbackCount"], 0)
        self.assertEqual(summary["guardedTakeoverRate"], 1.0)
        self.assertEqual(
            summary["latestDecision"]["responseSource"],
            "focus-tool-visible-response",
        )

    def test_response_selection_summary_separates_safety_and_failures(
        self,
    ) -> None:
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
            ),
            message="Help diagnose my car.",
            turn_id="turn-category-start",
            source="unit-test",
        )

        record_assistant_reply(
            text="Safe legacy fallback.",
            source_turn_id="turn-category-safety",
            source="chat-visible-response",
            fallback_reason="candidate_ineligible",
            fallback_details=["unterminated_procedure"],
        )
        record_assistant_reply(
            text="Legacy response after synchronization failure.",
            source_turn_id="turn-category-system",
            source="chat-visible-response",
            fallback_reason="work_context_sync_failed",
        )
        record_assistant_reply(
            text="Legacy response for an unrecognized reason.",
            source_turn_id="turn-category-unknown",
            source="chat-visible-response",
            fallback_reason="unexpected_guard",
        )

        summary = response_selection_summary()

        self.assertEqual(summary["decisionCount"], 3)
        self.assertEqual(summary["takeoverCount"], 0)
        self.assertEqual(summary["guardedAttemptCount"], 3)
        self.assertEqual(summary["guardedTakeoverRate"], 0.0)
        self.assertEqual(summary["healthyDecisionCount"], 1)
        self.assertEqual(summary["healthyDecisionRate"], 0.3333)
        self.assertEqual(summary["expectedFallbackCount"], 0)
        self.assertEqual(summary["safetyFallbackCount"], 1)
        self.assertEqual(summary["systemFailureCount"], 1)
        self.assertEqual(summary["unknownFallbackCount"], 1)
        self.assertEqual(
            summary["fallbackCategoryCounts"],
            {
                "expected": 0,
                "safety": 1,
                "systemFailure": 1,
                "unknown": 1,
            },
        )
        self.assertEqual(
            summary["fallbackReasonsByCategory"]["safety"],
            {"candidate_ineligible": 1},
        )
        self.assertEqual(
            summary["fallbackReasonsByCategory"]["systemFailure"],
            {"work_context_sync_failed": 1},
        )
        self.assertEqual(
            summary["fallbackReasonsByCategory"]["unknown"],
            {"unexpected_guard": 1},
        )
        self.assertEqual(
            summary["latestDecision"]["category"],
            "unknown",
        )
        self.assertFalse(summary["latestDecision"]["healthy"])

    def test_response_selection_summary_counts_tool_fallback_without_reply(
        self,
    ) -> None:
        record_response_selection(
            source_turn_id="turn-calendar-fallback",
            outcome="fallback",
            reason="tool_not_attached_to_focus",
            response_source="calendar-legacy-readout",
            tool=ToolName.CALENDAR_READ,
        )

        summary = response_selection_summary()

        self.assertEqual(summary["decisionCount"], 1)
        self.assertEqual(summary["expectedFallbackCount"], 1)
        self.assertEqual(
            summary["fallbackReasons"],
            {"tool_not_attached_to_focus": 1},
        )
        self.assertEqual(
            summary["latestDecision"]["responseSource"],
            "calendar-legacy-readout",
        )

    def test_response_selection_summary_uses_latest_decision_per_turn(
        self,
    ) -> None:
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
            ),
            message="Help diagnose my car.",
            turn_id="turn-dedupe-start",
            source="unit-test",
        )
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=True,
                    guidance="Inspect the battery terminals.",
                ),
                confidence=1.0,
            ),
            message="What should I inspect?",
            turn_id="turn-dedupe-decision",
            source="unit-test",
        )
        record_assistant_reply(
            text="Legacy fallback.",
            source_turn_id="turn-dedupe-decision",
            source="chat-visible-response",
            fallback_reason="work_context_sync_failed",
        )
        record_assistant_reply(
            text="Inspect the battery terminals.",
            source_turn_id="turn-dedupe-decision",
            source="focus-visible-response",
        )

        summary = response_selection_summary()

        self.assertEqual(summary["decisionCount"], 1)
        self.assertEqual(summary["takeoverCount"], 1)
        self.assertEqual(summary["fallbackCount"], 0)
        self.assertEqual(summary["fallbackReasons"], {})
        self.assertEqual(
            summary["latestDecision"]["outcome"],
            "takeover",
        )



    def test_guarded_route_selector_accepts_safe_search_agreement(self) -> None:
        turn_id = "turn-route-search"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.SEARCH,
                        arguments=[],
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                confidence=0.98,
            ),
            message="Search for electric vehicle tax credits.",
            turn_id=turn_id,
            source="unit-test",
        )

        decision = guarded_route_decision_for_turn(
            turn_id,
            {
                "intent": "command",
                "action": "prepare_search",
                "confidence": 0.95,
                "frontendCommand": "search for electric vehicle tax credits",
                "payload": {},
            },
            minimum_confidence=0.9,
        )

        self.assertTrue(decision.eligible)
        self.assertEqual(decision.routeClass, "search")
        self.assertEqual(decision.focusRouteClass, "search")
        self.assertEqual(decision.legacyRouteClass, "search")

    def test_guarded_route_selector_accepts_notes_and_tasks_reads(self) -> None:
        cases = [
            (
                "turn-route-notes-read",
                ToolName.NOTES_READ,
                "read_notes",
                "notes_read",
            ),
            (
                "turn-route-tasks-read",
                ToolName.TASKS_READ,
                "read_memory",
                "tasks_read",
            ),
        ]

        for turn_id, tool, action, route_class in cases:
            with self.subTest(route_class=route_class):
                apply_turn_plan(
                    TurnPlan(
                        route=TurnRoute.TOOL,
                        toolCalls=[
                            PlannedToolCall(
                                tool=tool,
                                requiresConfirmation=False,
                                attachToFocus=False,
                            )
                        ],
                        confidence=0.99,
                    ),
                    message=f"Read {route_class}.",
                    turn_id=turn_id,
                    source="command-interpret-shadow",
                )

                decision = guarded_route_decision_for_turn(
                    turn_id,
                    {
                        "intent": "command",
                        "action": action,
                        "confidence": 0.99,
                        "frontendCommand": "read memory",
                        "payload": {},
                    },
                )
                self.assertTrue(decision.eligible)
                self.assertEqual(decision.routeClass, route_class)
                self.assertEqual(decision.focusRouteClass, route_class)
                self.assertEqual(decision.legacyRouteClass, route_class)

                turn_events = [
                    event for event in list_events()
                    if event.sourceTurnId == turn_id
                ]
                self.assertEqual(
                    [event.type for event in turn_events],
                    [FocusEventType.TURN_PLANNED],
                )
                self.assertTrue(
                    turn_events[0].payload["executionPolicy"]["routeOnlyTool"]
                )

    def test_memory_write_marker_is_route_only_and_non_mutating(self) -> None:
        turn_id = "turn-route-task-complete"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.ADD_LIST_ITEM,
                        field=FocusField.KNOWN_FACTS,
                        value="Must be suppressed.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.MEMORY_WRITE,
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=True,
                    guidance="I completed it.",
                ),
                confidence=0.99,
            ),
            message="Mark the budget task done.",
            turn_id=turn_id,
            source="command-interpret-shadow",
        )

        turn_events = [
            event for event in list_events()
            if event.sourceTurnId == turn_id
        ]
        self.assertEqual(
            [event.type for event in turn_events],
            [FocusEventType.TURN_PLANNED],
        )
        policy = turn_events[0].payload["executionPolicy"]
        self.assertTrue(policy["transientTool"])
        self.assertTrue(policy["routeOnlyTool"])
        self.assertEqual(policy["suppressedFocusOperationCount"], 1)

    def test_guarded_route_selector_accepts_visual_read_agreement(self) -> None:
        turn_id = "turn-route-visual-history"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.VISUAL_READ,
                        arguments=[],
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                confidence=0.99,
            ),
            message="Show my recent visual observations.",
            turn_id=turn_id,
            source="command-interpret-shadow",
        )

        decision = guarded_route_decision_for_turn(
            turn_id,
            {
                "intent": "command",
                "action": "read_visual_history",
                "confidence": 0.98,
                "frontendCommand": "show visual observations",
                "payload": {"mode": "history"},
            },
            minimum_confidence=0.9,
        )

        self.assertTrue(decision.eligible)
        self.assertEqual(decision.routeClass, "visual_read")
        self.assertEqual(decision.focusRouteClass, "visual_read")
        self.assertEqual(decision.legacyRouteClass, "visual_read")

        turn_events = [
            event
            for event in list_events()
            if event.sourceTurnId == turn_id
        ]
        self.assertEqual(
            [event.type for event in turn_events],
            [FocusEventType.TURN_PLANNED],
        )
        self.assertTrue(
            turn_events[0].payload["executionPolicy"]["routeOnlyTool"]
        )

    def test_visual_write_marker_is_route_only_and_non_mutating(self) -> None:
        turn_id = "turn-route-visual-delete"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.TOOL,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.ADD_LIST_ITEM,
                        field=FocusField.KNOWN_FACTS,
                        value="This must be suppressed.",
                    )
                ],
                toolCalls=[
                    PlannedToolCall(
                        tool=ToolName.VISUAL_WRITE,
                        arguments=[],
                        requiresConfirmation=False,
                        attachToFocus=False,
                    )
                ],
                responseIntent=ResponseIntent(
                    answerDirectly=True,
                    attachToFocus=True,
                    guidance="I cannot delete it.",
                ),
                confidence=0.99,
            ),
            message="Could you delete my last visual observation?",
            turn_id=turn_id,
            source="command-interpret-shadow",
        )

        turn_events = [
            event
            for event in list_events()
            if event.sourceTurnId == turn_id
        ]
        self.assertEqual(
            [event.type for event in turn_events],
            [FocusEventType.TURN_PLANNED],
        )
        policy = turn_events[0].payload["executionPolicy"]
        self.assertTrue(policy["transientTool"])
        self.assertTrue(policy["routeOnlyTool"])
        self.assertEqual(policy["suppressedFocusOperationCount"], 1)

    def test_guarded_route_selector_rejects_disagreement_and_writes(self) -> None:
        turn_id = "turn-route-disagreement"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                confidence=1.0,
            ),
            message="Explain the next step.",
            turn_id=turn_id,
            source="unit-test",
        )

        disagreement = guarded_route_decision_for_turn(
            turn_id,
            {
                "intent": "command",
                "action": "prepare_search",
                "frontendCommand": "search for the next step",
            },
        )
        self.assertFalse(disagreement.eligible)
        self.assertEqual(disagreement.fallbackReason, "route_disagreement")

        write_block = guarded_route_decision_for_turn(
            turn_id,
            {
                "intent": "command",
                "action": "add_calendar_event",
                "frontendCommand": "add event today at 6 PM called work meeting",
            },
        )
        self.assertFalse(write_block.eligible)
        self.assertEqual(
            write_block.fallbackReason,
            "confirmation_gated_legacy_route",
        )

        protected_visual_mutation = guarded_route_decision_for_turn(
            turn_id,
            {
                "intent": "command",
                "action": "delete_last_visual_observation",
                "frontendCommand": "delete last visual observation",
            },
        )
        self.assertFalse(protected_visual_mutation.eligible)
        self.assertEqual(
            protected_visual_mutation.fallbackReason,
            "protected_legacy_route",
        )

        protected_task_mutation = guarded_route_decision_for_turn(
            turn_id,
            {
                "intent": "command",
                "action": "mark_task_done",
                "frontendCommand": "mark task budget done",
            },
        )
        self.assertFalse(protected_task_mutation.eligible)
        self.assertEqual(
            protected_task_mutation.fallbackReason,
            "protected_legacy_route",
        )

    def test_guarded_route_selector_enforces_confidence(self) -> None:
        turn_id = "turn-route-low-confidence"
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.RESPOND,
                confidence=0.72,
            ),
            message="Explain this.",
            turn_id=turn_id,
            source="unit-test",
        )

        decision = guarded_route_decision_for_turn(
            turn_id,
            {
                "intent": "chat",
                "action": "none",
                "frontendCommand": "",
            },
            minimum_confidence=0.9,
        )

        self.assertFalse(decision.eligible)
        self.assertEqual(
            decision.fallbackReason,
            "planner_below_confidence_threshold",
        )

    def test_route_selection_summary_separates_expected_and_safety(self) -> None:
        record_route_selection(
            source_turn_id="turn-route-takeover",
            outcome="takeover",
            route_class="chat",
            focus_route_class="chat",
            legacy_route_class="chat",
            focus_confidence=1.0,
            minimum_confidence=0.9,
            legacy_intent="chat",
            legacy_action="none",
            response_source="focus-route-guarded",
        )
        record_route_selection(
            source_turn_id="turn-route-expected",
            outcome="fallback",
            reason="legacy_route_out_of_scope",
            details=["open_panel"],
            focus_route_class="chat",
            focus_confidence=1.0,
            minimum_confidence=0.9,
            legacy_intent="command",
            legacy_action="open_panel",
        )
        record_route_selection(
            source_turn_id="turn-route-safety",
            outcome="fallback",
            reason="route_disagreement",
            details=["focus=chat", "legacy=search"],
            focus_route_class="chat",
            legacy_route_class="search",
            focus_confidence=1.0,
            minimum_confidence=0.9,
            legacy_intent="command",
            legacy_action="prepare_search",
        )

        summary = route_selection_summary()

        self.assertEqual(summary["decisionCount"], 3)
        self.assertEqual(summary["takeoverCount"], 1)
        self.assertEqual(summary["fallbackCount"], 2)
        self.assertEqual(summary["expectedFallbackCount"], 1)
        self.assertEqual(summary["safetyFallbackCount"], 1)
        self.assertEqual(summary["systemFailureCount"], 0)
        self.assertEqual(summary["healthyDecisionRate"], 1.0)
        self.assertEqual(summary["guardedAttemptCount"], 2)
        self.assertEqual(summary["guardedTakeoverRate"], 0.5)
        self.assertEqual(
            summary["latestDecision"]["reason"],
            "route_disagreement",
        )

    def test_route_selection_telemetry_does_not_mutate_focus(self) -> None:
        apply_turn_plan(
            TurnPlan(
                route=TurnRoute.FOCUS_ACTION,
                focusOperations=[
                    FocusOperation(
                        kind=FocusOperationKind.START_FOCUS,
                        title="Route telemetry test",
                        objective="Keep routing metrics observational.",
                    )
                ],
                confidence=1.0,
            ),
            message="Start a routing test.",
            turn_id="turn-route-state",
            source="unit-test",
        )
        before = get_state()

        after = record_route_selection(
            source_turn_id="turn-route-state",
            outcome="fallback",
            reason="route_disagreement",
            focus_route_class="chat",
            legacy_route_class="search",
            focus_confidence=1.0,
        )

        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
