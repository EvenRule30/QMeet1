from __future__ import annotations

import unittest

from app.focus.context_boundary import classify_focus_context
from app.focus.context_hygiene import duplicate_values_to_remove


class FocusReferentialConstraintCorrectionPhase20W1Tests(unittest.TestCase):
    def test_weekday_referential_correction_routes_to_constraints(self) -> None:
        signal = classify_focus_context("actually make that Thursday")

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "constraints")
        self.assertEqual(signal.value, "actually make that Thursday")

    def test_change_that_to_weekday_routes_to_constraints(self) -> None:
        signal = classify_focus_context("actually change that to Friday")

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "constraints")

    def test_currency_referential_correction_routes_to_constraints(self) -> None:
        signal = classify_focus_context("actually make that $800")

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "constraints")

    def test_generic_referential_correction_is_not_guessed_as_constraint(self) -> None:
        self.assertIsNone(classify_focus_context("actually make that blue"))

    def test_lifecycle_goal_update_stays_out_of_context_boundary(self) -> None:
        self.assertIsNone(classify_focus_context("actually make that the goal"))
        self.assertIsNone(classify_focus_context("make the goal finish by Thursday"))

    def test_weekday_correction_reaches_phase20w_supersession_semantics(self) -> None:
        removals = duplicate_values_to_remove(
            ["I need it ready Friday"],
            preferred="actually make that Thursday",
        )

        self.assertEqual(removals, ["I need it ready Friday"])


if __name__ == "__main__":
    unittest.main()
