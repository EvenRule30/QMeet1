from __future__ import annotations

import unittest

from app import qmeet_agent_composite as composite


class AgentCompositeGroundedDependencyRepairPhase21G3B1Tests(unittest.TestCase):
    def _calendar_then_task_plan(
        self,
        *,
        task_title: str = "Prepare for meeting",
        task_depends_on: list[int] | None = None,
    ) -> dict:
        return {
            "isComposite": True,
            "steps": [
                {
                    "turnOwner": "calendar",
                    "focusRelevant": False,
                    "proposedCapability": "calendar",
                    "proposedAction": "edit-last-event",
                    "proposedArguments": {
                        "targetDay": "2026-08-21",
                        "query": "Project meeting",
                        "currentTime": "3 PM",
                        "changeField": "day",
                        "changeValue": "2026-08-22",
                    },
                    "dependsOn": [],
                    "inputBindings": [],
                    "reason": "Move the requested Calendar event.",
                },
                {
                    "turnOwner": "tasks",
                    "focusRelevant": False,
                    "proposedCapability": "tasks",
                    "proposedAction": "remember-task",
                    "proposedArguments": {"title": task_title},
                    "dependsOn": task_depends_on or [],
                    "inputBindings": [],
                    "reason": "Create the explicitly requested Task.",
                },
            ],
            "responsePlan": "Move the meeting, then create the task.",
            "confidence": 0.97,
            "reason": "The turn contains two explicitly requested actions.",
        }

    def test_explicit_task_title_repairs_spurious_calendar_dependency(self) -> None:
        raw = self._calendar_then_task_plan(task_depends_on=[1])
        plan = composite.sanitize_composite_plan(
            raw,
            user_message=(
                "move my 3 PM Project meeting on August 21 to August 22 "
                "and add a task called Prepare for meeting"
            ),
        )

        self.assertTrue(plan.isComposite)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[1].proposedAction, "remember-task")
        self.assertEqual(plan.steps[1].dependsOn, [])
        self.assertEqual(plan.steps[1].inputBindings, [])
        self.assertIn("normalized away", plan.steps[1].reason)

    def test_dependency_is_not_repaired_when_task_title_is_not_grounded(self) -> None:
        raw = self._calendar_then_task_plan(
            task_title="Prepare project packet",
            task_depends_on=[1],
        )
        plan = composite.sanitize_composite_plan(
            raw,
            user_message=(
                "move my 3 PM Project meeting on August 21 to August 22 "
                "and add a task for that"
            ),
        )

        self.assertFalse(plan.isComposite)
        self.assertEqual(plan.steps, [])
        self.assertIn("unsupported or untyped", plan.reason)

    def test_dependency_is_not_repaired_for_other_target_actions(self) -> None:
        raw = self._calendar_then_task_plan(task_depends_on=[])
        raw["steps"][1] = {
            "turnOwner": "notes",
            "focusRelevant": False,
            "proposedCapability": "notes",
            "proposedAction": "save-note",
            "proposedArguments": {"content": "Prepare for meeting"},
            "dependsOn": [1],
            "inputBindings": [],
            "reason": "Save a note after the Calendar edit.",
        }
        plan = composite.sanitize_composite_plan(
            raw,
            user_message=(
                "move my 3 PM Project meeting on August 21 to August 22 "
                "and save a note saying Prepare for meeting"
            ),
        )

        self.assertFalse(plan.isComposite)
        self.assertEqual(plan.steps, [])

    def test_typed_search_to_notes_binding_remains_unchanged(self) -> None:
        raw = {
            "isComposite": True,
            "steps": [
                {
                    "turnOwner": "search",
                    "focusRelevant": False,
                    "proposedCapability": "search",
                    "proposedAction": "run-search",
                    "proposedArguments": {"query": "Framework Laptop reviews"},
                    "dependsOn": [],
                    "inputBindings": [],
                    "reason": "Run the requested Search.",
                },
                {
                    "turnOwner": "notes",
                    "focusRelevant": False,
                    "proposedCapability": "notes",
                    "proposedAction": "save-note",
                    "proposedArguments": {},
                    "dependsOn": [1],
                    "inputBindings": [
                        {
                            "targetArgument": "content",
                            "sourceStep": 1,
                            "sourceField": "search.resultText",
                        }
                    ],
                    "reason": "Save the verified Search result.",
                },
            ],
            "responsePlan": "Search, then save the verified result.",
            "confidence": 0.97,
            "reason": "The Notes content depends on verified Search output.",
        }
        plan = composite.sanitize_composite_plan(
            raw,
            user_message=(
                "search for Framework Laptop reviews and save a note with the result"
            ),
        )

        self.assertTrue(plan.isComposite)
        self.assertEqual(plan.steps[1].dependsOn, ["step-1"])
        self.assertEqual(len(plan.steps[1].inputBindings), 1)
        self.assertEqual(
            plan.steps[1].inputBindings[0].sourceField,
            "search.resultText",
        )

    def test_model_path_sanitizes_with_current_user_message(self) -> None:
        source = open(composite.__file__, encoding="utf-8").read()
        self.assertIn(
            "sanitize_composite_plan(\n            parsed,\n            user_message=request.userMessage,",
            source,
        )

    def test_prompt_explicitly_distinguishes_same_subject_from_data_dependency(self) -> None:
        prompt = composite.COMPOSITE_PLAN_SYSTEM_PROMPT
        self.assertIn(
            "A literal task title supplied by the user is self-contained.",
            prompt,
        )
        self.assertIn(
            "Prepare for meeting",
            prompt,
        )
        self.assertIn(
            "two dependency-free steps",
            prompt,
        )


if __name__ == "__main__":
    unittest.main()
