from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.focus.models import (
    FocusField,
    FocusOperation,
    FocusOperationKind,
    ObserveTurnRequest,
    PlannedToolCall,
    ToolArgument,
    ToolName,
    TurnPlan,
    TurnRoute,
)
from app.focus.store import apply_turn_plan, get_state, record_tool_result, reset_store


class FocusStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.previous_file = os.environ.get("QMEET_FOCUS_FILE")
        os.environ["QMEET_FOCUS_FILE"] = str(
            Path(self.temp_directory.name) / "focus.json"
        )
        reset_store()

    def tearDown(self) -> None:
        if self.previous_file is None:
            os.environ.pop("QMEET_FOCUS_FILE", None)
        else:
            os.environ["QMEET_FOCUS_FILE"] = self.previous_file
        self.temp_directory.cleanup()

    def test_generic_focus_updates_reduce_deterministically(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.FOCUS_ACTION,
            confidence=0.96,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.START_FOCUS,
                    title="Buying a laptop",
                    objective="Buy a laptop for machine learning",
                    tags=["purchase"],
                ),
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.CONSTRAINTS,
                    value="Maximum budget: $4,000.",
                ),
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.PREFERENCES,
                    value="Operating system: Windows.",
                ),
                FocusOperation(
                    kind=FocusOperationKind.SET_PENDING_QUESTION,
                    target="brand preference",
                    question="Do you prefer a brand, or should QMeet compare reputable brands?",
                ),
            ],
        )

        state = apply_turn_plan(
            plan,
            message="I want a Windows laptop for ML under $4,000.",
            turn_id="turn-1",
            source="test",
        )

        self.assertEqual(state.title, "Buying a laptop")
        self.assertEqual(state.objective, "Buy a laptop for machine learning")
        self.assertIn("Maximum budget: $4,000.", state.constraints)
        self.assertIn("Operating system: Windows.", state.preferences)
        self.assertIsNotNone(state.pendingQuestion)

    def test_tool_request_and_result_advance_state(self) -> None:
        start_plan = TurnPlan(
            route=TurnRoute.TOOL,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.START_FOCUS,
                    title="Buying a laptop",
                    objective="Buy a laptop for machine learning",
                )
            ],
            toolCalls=[
                PlannedToolCall(
                    tool=ToolName.SEARCH,
                    arguments=[
                        ToolArgument(
                            key="query",
                            value="current Windows laptops for machine learning under $4,000",
                        )
                    ],
                    reason="The user asked for current products and prices.",
                )
            ],
        )
        state = apply_turn_plan(
            start_plan,
            message="Search current options.",
            turn_id="turn-2",
            source="test",
        )
        self.assertIsNotNone(state.pendingAction)
        self.assertEqual(state.pendingAction.kind, "search")

        state = record_tool_result(
            tool=ToolName.SEARCH,
            success=True,
            summary="Search returned four current laptop options.",
            result_ids=["result-1", "result-2"],
            source_turn_id="turn-2",
            source="test",
        )
        self.assertIsNone(state.pendingAction)
        self.assertIn(
            "Search returned four current laptop options.",
            state.completedMilestones,
        )

    def test_duplicate_turn_is_idempotent(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.FOCUS_ACTION,
            focusOperations=[
                FocusOperation(
                    kind=FocusOperationKind.START_FOCUS,
                    title="Write an essay",
                    objective="Write and submit an essay",
                ),
                FocusOperation(
                    kind=FocusOperationKind.ADD_LIST_ITEM,
                    field=FocusField.REQUIREMENTS,
                    value="Use verifiable sources.",
                ),
            ],
        )
        apply_turn_plan(
            plan,
            message="I need to write an essay.",
            turn_id="same-turn",
            source="test",
        )
        apply_turn_plan(
            plan,
            message="I need to write an essay.",
            turn_id="same-turn",
            source="test",
        )
        state = get_state()
        self.assertEqual(state.requirements, ["Use verifiable sources."])


if __name__ == "__main__":
    unittest.main()
