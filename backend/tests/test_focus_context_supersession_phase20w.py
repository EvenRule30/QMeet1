from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.focus.context import NativeFocusContextRequest, add_focus_context_verified
from app.focus.context_hygiene import (
    duplicate_values_to_remove,
    superseded_values_to_remove,
)
from app.focus.models import FocusOperationKind, FocusStatus


def _state(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "focusId": "focus-trip",
        "title": "plan a trip",
        "objective": "",
        "status": FocusStatus.ACTIVE,
        "requirements": [],
        "constraints": [],
        "preferences": [],
        "decisions": [],
        "knownFacts": [],
        "updatedAt": "2026-08-07T20:44:00-07:00",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _event(field: str, value: str, source_turn_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        sourceTurnId=source_turn_id,
        focusId="focus-trip",
        payload={"field": field, "value": value},
    )


class FocusContextSupersessionPhase20WTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.health_patch = patch.dict(
            os.environ,
            {
                "QMEET_FOCUS_CONTEXT_HEALTH_FILE": os.path.join(
                    self.temp_dir.name,
                    "context-health.json",
                )
            },
        )
        self.health_patch.start()
        self.addCleanup(self.health_patch.stop)

    def test_explicit_budget_correction_supersedes_one_prior_budget(self) -> None:
        self.assertEqual(
            superseded_values_to_remove(
                ["keep the budget under $500"],
                "actually I can spend up to $800",
            ),
            ["keep the budget under $500"],
        )

    def test_different_budget_without_correction_remains_distinct(self) -> None:
        self.assertEqual(
            superseded_values_to_remove(
                ["keep the hotel budget under $500"],
                "keep the flight budget under $800",
            ),
            [],
        )

    def test_ambiguous_correction_does_not_delete_multiple_budget_constraints(self) -> None:
        self.assertEqual(
            superseded_values_to_remove(
                [
                    "keep the hotel budget under $500",
                    "keep the flight budget under $300",
                ],
                "actually the budget can be $800",
            ),
            [],
        )

    def test_make_that_correction_targets_most_recent_value(self) -> None:
        self.assertEqual(
            superseded_values_to_remove(
                ["I need it ready Friday"],
                "actually make that Thursday",
            ),
            ["I need it ready Friday"],
        )

    def test_duplicate_cleanup_includes_superseded_budget_value(self) -> None:
        self.assertEqual(
            duplicate_values_to_remove(
                ["keep the budget under $500"],
                preferred="actually I can spend up to $800",
            ),
            ["keep the budget under $500"],
        )

    def test_verified_context_write_removes_old_constraint_before_add(self) -> None:
        old_value = "keep the budget under $500"
        new_value = "actually I can spend up to $800"
        before = _state(constraints=[old_value])
        after = _state(
            constraints=[new_value],
            updatedAt="2026-08-07T20:44:30-07:00",
        )
        request = NativeFocusContextRequest(
            expectedFocusId="focus-trip",
            expectedObjective="",
            field="constraints",
            value=new_value,
            sourceTurnId="turn-budget-correction",
        )
        receipt_event = _event(
            "constraints",
            new_value,
            "turn-budget-correction",
        )

        with (
            patch("app.focus.context.get_state", return_value=before),
            patch("app.focus.context.apply_turn_plan", return_value=after) as apply_plan,
            patch(
                "app.focus.context.list_events",
                side_effect=[[], [receipt_event]],
            ),
        ):
            result = add_focus_context_verified(request)

        operations = apply_plan.call_args.args[0].focusOperations
        self.assertGreaterEqual(len(operations), 2)
        self.assertEqual(operations[0].kind, FocusOperationKind.REMOVE_LIST_ITEM)
        self.assertEqual(operations[0].field.value, "constraints")
        self.assertEqual(operations[0].value, old_value)
        self.assertEqual(operations[1].kind, FocusOperationKind.ADD_LIST_ITEM)
        self.assertEqual(operations[1].field.value, "constraints")
        self.assertEqual(operations[1].value, new_value)
        self.assertEqual(result.focusContext.constraints, [new_value])
        self.assertNotIn(old_value, result.focusContext.constraints)


if __name__ == "__main__":
    unittest.main()
