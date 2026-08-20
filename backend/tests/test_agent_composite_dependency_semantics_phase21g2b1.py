from __future__ import annotations

import unittest

from app.qmeet_agent_composite import COMPOSITE_PLAN_SYSTEM_PROMPT


class AgentCompositeDependencySemanticsPhase21G2B1Tests(unittest.TestCase):
    def test_dependency_requires_verified_output_not_topical_relationship(self) -> None:
        prompt = COMPOSITE_PLAN_SYSTEM_PROMPT

        self.assertIn(
            "dependsOn is ONLY for a real verified-output/data dependency",
            prompt,
        )
        self.assertIn(
            "Do NOT add dependsOn merely because two actions discuss the same subject",
            prompt,
        )
        self.assertIn(
            'user says "and" or "then"',
            prompt,
        )
        self.assertIn(
            "or it would be preferable for one action to happen",
            prompt,
        )

    def test_explicit_search_and_task_example_is_dependency_free(self) -> None:
        prompt = COMPOSITE_PLAN_SYSTEM_PROMPT

        self.assertIn(
            "search for Framework Laptop reviews and add a task called Compare",
            prompt,
        )
        self.assertIn(
            "Framework options",
            prompt,
        )
        self.assertIn(
            "has two dependency-free steps",
            prompt,
        )
        self.assertIn(
            "already explicit in the original turn",
            prompt,
        )

    def test_search_result_to_note_remains_real_dependency(self) -> None:
        prompt = COMPOSITE_PLAN_SYSTEM_PROMPT

        self.assertIn(
            "search Framework reviews and save a note with the result",
            prompt,
        )
        self.assertIn(
            "note content requires the verified Search output",
            prompt,
        )


if __name__ == "__main__":
    unittest.main()
