from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.focus.context import (
    NativeFocusContextError,
    NativeFocusContextRequest,
    add_focus_context_verified,
    get_native_focus_context_health,
)
from app.focus.models import FocusStatus


def _state(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "focusId": "focus-trip",
        "title": "plan a weekend trip",
        "objective": "Choose a destination, dates, and budget",
        "status": FocusStatus.ACTIVE,
        "requirements": [],
        "constraints": [],
        "preferences": [],
        "decisions": [],
        "knownFacts": [],
        "updatedAt": "2026-08-05T17:10:00-07:00",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _event(field: str, value: str, source_turn_id: str = "turn-context") -> SimpleNamespace:
    return SimpleNamespace(
        sourceTurnId=source_turn_id,
        focusId="focus-trip",
        payload={"field": field, "value": value},
    )


class NativeFocusContextPhase20ITests(unittest.TestCase):
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

    def test_exact_context_is_persisted_without_replacing_objective(self) -> None:
        before = _state()
        after = _state(
            preferences=["somewhere warm"],
            updatedAt="2026-08-05T17:11:00-07:00",
        )
        receipt_event = _event("preferences", "somewhere warm")
        request = NativeFocusContextRequest(
            expectedFocusId="focus-trip",
            expectedObjective="Choose a destination, dates, and budget",
            field="preferences",
            value="somewhere warm",
            sourceTurnId="turn-context",
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

        self.assertTrue(result.verified)
        self.assertEqual(result.outcome, "added")
        self.assertEqual(result.focusContext.objective, request.expectedObjective)
        self.assertEqual(result.focusContext.preferences, ["somewhere warm"])
        self.assertTrue(result.verification.objectivePreserved)
        operation = apply_plan.call_args.args[0].focusOperations[0]
        self.assertEqual(operation.field.value, "preferences")
        self.assertEqual(operation.value, "somewhere warm")

    def test_stale_objective_is_rejected_before_write(self) -> None:
        request = NativeFocusContextRequest(
            expectedFocusId="focus-trip",
            expectedObjective="Old objective",
            field="constraints",
            value="Keep the total cost under $1,000",
            sourceTurnId="turn-budget",
        )
        with (
            patch("app.focus.context.get_state", return_value=_state()),
            patch("app.focus.context.apply_turn_plan") as apply_plan,
        ):
            with self.assertRaises(NativeFocusContextError) as raised:
                add_focus_context_verified(request)
        self.assertEqual(raised.exception.code, "stale_objective")
        apply_plan.assert_not_called()

    def test_same_source_turn_reuses_matching_receipt(self) -> None:
        state = _state(knownFacts=["three days available"])
        request = NativeFocusContextRequest(
            expectedFocusId="focus-trip",
            expectedObjective=state.objective,
            field="knownFacts",
            value="three days available",
            sourceTurnId="turn-days",
        )
        with (
            patch("app.focus.context.get_state", return_value=state),
            patch(
                "app.focus.context.list_events",
                return_value=[_event("knownFacts", "three days available", "turn-days")],
            ),
            patch("app.focus.context.apply_turn_plan") as apply_plan,
        ):
            result = add_focus_context_verified(request)
        self.assertEqual(result.outcome, "reused")
        apply_plan.assert_not_called()

    def test_source_turn_conflict_is_rejected(self) -> None:
        request = NativeFocusContextRequest(
            expectedFocusId="focus-trip",
            expectedObjective="Choose a destination, dates, and budget",
            field="preferences",
            value="somewhere warm",
            sourceTurnId="turn-context",
        )
        with (
            patch("app.focus.context.get_state", return_value=_state()),
            patch(
                "app.focus.context.list_events",
                return_value=[_event("constraints", "under $1,000")],
            ),
        ):
            with self.assertRaises(NativeFocusContextError) as raised:
                add_focus_context_verified(request)
        self.assertEqual(raised.exception.code, "source_turn_conflict")

    def test_health_is_durable_and_latest_success_is_verified(self) -> None:
        state = _state(preferences=["somewhere warm"])
        request = NativeFocusContextRequest(
            expectedFocusId="focus-trip",
            expectedObjective=state.objective,
            field="preferences",
            value="somewhere warm",
            sourceTurnId="turn-health",
        )
        with (
            patch("app.focus.context.get_state", return_value=state),
            patch(
                "app.focus.context.list_events",
                return_value=[_event("preferences", "somewhere warm", "turn-health")],
            ),
        ):
            add_focus_context_verified(request)
        health = get_native_focus_context_health()["addFocusContext"]
        self.assertEqual(health["attemptCount"], 1)
        self.assertEqual(health["verifiedCount"], 1)
        self.assertEqual(health["lastOutcome"], "reused")
        self.assertEqual(health["lastFailureCode"], "")


if __name__ == "__main__":
    unittest.main()
