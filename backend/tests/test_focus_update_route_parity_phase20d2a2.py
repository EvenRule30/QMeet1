import unittest

from app.routers.command import _focus_command_intent


class FocusUpdateRouteParityPhase20D2A1Tests(unittest.TestCase):
    def assert_title_update(self, phrase: str, expected_title: str) -> None:
        result = _focus_command_intent(phrase)

        self.assertIsNotNone(result, phrase)
        assert result is not None
        self.assertEqual(result["action"], "update_focus_session")
        self.assertEqual(result["frontendCommand"], f"set current focus on {expected_title}")
        self.assertEqual(result["payload"]["title"], expected_title)

    def test_rename_my_focus_routes_to_verified_update_command(self) -> None:
        self.assert_title_update(
            "rename my focus to character design practice",
            "character design practice",
        )

    def test_rename_determiner_variants_have_route_parity(self) -> None:
        variants = (
            "rename focus to character design practice",
            "rename the focus to character design practice",
            "rename my focus to character design practice",
            "rename our focus to character design practice",
            "rename current focus to character design practice",
            "rename active focus to character design practice",
            "retitle my active session as character design practice",
        )

        for phrase in variants:
            with self.subTest(phrase=phrase):
                self.assert_title_update(phrase, "character design practice")

    def test_explicit_focus_title_variants_have_route_parity(self) -> None:
        variants = (
            "set my focus title to character design practice",
            "change our focus title to character design practice",
            "update the session title as character design practice",
            "set current focus title to character design practice",
            "change active session title to character design practice",
        )

        for phrase in variants:
            with self.subTest(phrase=phrase):
                self.assert_title_update(phrase, "character design practice")

    def test_mode_determiner_variants_still_route_as_mode_updates(self) -> None:
        for phrase in (
            "set my focus mode to planning",
            "change our focus mode to planning",
            "update current session mode to planning",
            "set active focus mode as planning",
        ):
            with self.subTest(phrase=phrase):
                result = _focus_command_intent(phrase)
                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(result["action"], "update_focus_session")
                self.assertEqual(result["frontendCommand"], "set focus mode to planning")
                self.assertEqual(result["payload"], {"mode": "planning"})

    def test_existing_goal_update_behavior_is_unchanged(self) -> None:
        result = _focus_command_intent(
            "set my focus goal to draw three anime character poses"
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["action"], "update_focus_session")
        self.assertEqual(
            result["frontendCommand"],
            "set my focus goal to draw three anime character poses",
        )
        self.assertEqual(
            result["payload"],
            {"goal": "draw three anime character poses"},
        )

    def test_planning_question_does_not_become_a_mutation(self) -> None:
        self.assertIsNone(_focus_command_intent("how should I rename my focus"))


if __name__ == "__main__":
    unittest.main()
