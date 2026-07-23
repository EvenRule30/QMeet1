from __future__ import annotations

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
    apply_turn_plan,
    event_count,
    get_state,
    list_events,
    record_tool_result,
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



if __name__ == "__main__":
    unittest.main()
