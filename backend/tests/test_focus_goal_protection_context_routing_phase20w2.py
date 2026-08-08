from __future__ import annotations

import unittest

from app.focus.context_boundary import classify_focus_context


class FocusGoalProtectionContextRoutingPhase20W2Tests(unittest.TestCase):
    def test_interview_date_is_durable_fact(self) -> None:
        signal = classify_focus_context("the interview is Tuesday")

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "knownFacts")
        self.assertEqual(signal.value, "the interview is Tuesday")

    def test_short_with_answer_is_durable_fact(self) -> None:
        signal = classify_focus_context("it's with three people")

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "knownFacts")
        self.assertEqual(signal.value, "it's with three people")

    def test_short_for_answer_is_durable_fact(self) -> None:
        signal = classify_focus_context("it's for a product role")

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "knownFacts")
        self.assertEqual(signal.value, "it's for a product role")

    def test_need_to_practice_is_requirement_not_lifecycle(self) -> None:
        signal = classify_focus_context("I need to practice behavioral questions")

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.field, "requirements")
        self.assertEqual(signal.value, "practice behavioral questions")

    def test_explicit_goal_update_still_stays_out_of_context(self) -> None:
        self.assertIsNone(
            classify_focus_context("make the goal feel confident and prepare strong examples")
        )

    def test_explicit_focus_transition_still_stays_out_of_context(self) -> None:
        self.assertIsNone(classify_focus_context("I need to start a new focus"))
        self.assertIsNone(classify_focus_context("I need to focus on the launch plan"))

    def test_unrelated_bare_statement_is_not_promoted_to_context(self) -> None:
        self.assertIsNone(classify_focus_context("octopuses have three hearts"))


if __name__ == "__main__":
    unittest.main()
