from __future__ import annotations

import unittest

from app.focus.context_boundary import (
    classify_focus_context,
    decode_focus_context_reason,
    encode_focus_context_reason,
)


class FocusContextBoundaryPhase20ITests(unittest.TestCase):
    def test_preference_is_context_not_lifecycle(self) -> None:
        signal = classify_focus_context("I want somewhere warm")
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "preferences")
        self.assertEqual(signal.value, "somewhere warm")

    def test_availability_is_known_fact(self) -> None:
        signal = classify_focus_context("I have three days available")
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "knownFacts")
        self.assertEqual(signal.value, "three days available")

    def test_budget_limit_is_constraint(self) -> None:
        signal = classify_focus_context("Keep the total cost under $1,000")
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "constraints")
        self.assertEqual(signal.value, "Keep the total cost under $1,000")

    def test_explicit_goal_update_remains_lifecycle(self) -> None:
        self.assertIsNone(
            classify_focus_context("make the goal choose a destination, dates, and budget")
        )
        self.assertIsNone(
            classify_focus_context("replace the goal with book the cheapest flight")
        )

    def test_explicit_new_focus_remains_lifecycle(self) -> None:
        self.assertIsNone(classify_focus_context("start a focus to plan a weekend trip"))
        self.assertIsNone(classify_focus_context("switch my focus to the project report"))

    def test_decisions_and_requirements_have_distinct_fields(self) -> None:
        decision = classify_focus_context("We decided to leave Friday evening")
        requirement = classify_focus_context("The plan needs to include a hotel")
        self.assertEqual(decision.field if decision else None, "decisions")
        self.assertEqual(requirement.field if requirement else None, "requirements")

    def test_context_reason_round_trips(self) -> None:
        signal = classify_focus_context("I prefer a beach town")
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(decode_focus_context_reason(encode_focus_context_reason(signal)), signal)


if __name__ == "__main__":
    unittest.main()
