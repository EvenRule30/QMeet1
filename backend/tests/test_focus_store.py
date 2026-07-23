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
    PlannedToolCall,
    ResponseIntent,
    ToolName,
    TurnPlan,
    TurnRoute,
)
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

    def test_tool_result_clears_pending_action_and_records_progress(self) -> None:
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

        self.assertEqual(completed_state.status, FocusStatus.ACTIVE)
        self.assertIsNone(completed_state.pendingAction)
        self.assertIn(
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


if __name__ == "__main__":
    unittest.main()
