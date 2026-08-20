from __future__ import annotations

from pathlib import Path
import unittest

from app.qmeet_agent_composite import (
    COMPOSITE_ATOMIC_ACTIONS_BY_OWNER,
    COMPOSITE_PLAN_SYSTEM_PROMPT,
    sanitize_composite_plan,
)
from app.qmeet_agent_shadow import AgentShadowDecision
from app.routers.agent_shadow import router


ROOT = Path(__file__).resolve().parents[2]


class AgentCompositePlanPhase21G1Tests(unittest.TestCase):
    def test_calendar_then_explicit_task_plan_is_atomic_and_dependency_free(self) -> None:
        plan = sanitize_composite_plan(
            {
                "isComposite": True,
                "steps": [
                    {
                        "turnOwner": "calendar",
                        "focusRelevant": False,
                        "proposedCapability": "calendar",
                        "proposedAction": "edit-last-event",
                        "proposedArguments": {
                            "targetDate": "2026-08-28",
                            "query": "meeting",
                            "currentTime": "3 PM",
                            "changeField": "date",
                            "changeValue": "2026-08-29",
                        },
                        "dependsOn": [],
                        "reason": "Move the requested meeting.",
                    },
                    {
                        "turnOwner": "tasks",
                        "focusRelevant": False,
                        "proposedCapability": "tasks",
                        "proposedAction": "remember-task",
                        "proposedArguments": {
                            "title": "Prepare for the meeting",
                        },
                        "dependsOn": [],
                        "inputBindings": [],
                        "reason": "Create the explicitly named preparation task.",
                    },
                ],
                "responsePlan": "Execute each validated step and then summarize verified results.",
                "confidence": 0.98,
                "reason": "The user explicitly requested two capability actions.",
            }
        )

        self.assertTrue(plan.isComposite)
        self.assertEqual(
            [step.stepId for step in plan.steps],
            ["step-1", "step-2"],
        )
        self.assertEqual(plan.steps[0].turnOwner, "calendar")
        self.assertEqual(
            plan.steps[0].proposedAction,
            "edit-last-event",
        )
        self.assertEqual(plan.steps[1].turnOwner, "tasks")
        self.assertEqual(
            plan.steps[1].proposedAction,
            "remember-task",
        )
        self.assertEqual(plan.steps[1].dependsOn, [])
        self.assertEqual(plan.steps[1].inputBindings, [])
        self.assertEqual(plan.executionPolicy, "sequential-verified")
        self.assertEqual(
            plan.confirmationPolicy,
            "preserve-existing-capability-gates",
        )
        self.assertEqual(
            plan.failurePolicy,
            "stop-before-dependent-step",
        )

    def test_plan_rejects_canonical_event_identity_from_model(self) -> None:
        plan = sanitize_composite_plan(
            {
                "isComposite": True,
                "steps": [
                    {
                        "turnOwner": "calendar",
                        "focusRelevant": False,
                        "proposedCapability": "calendar",
                        "proposedAction": "edit-last-event",
                        "proposedArguments": {
                            "eventId": "google-secret-id",
                            "query": "meeting",
                        },
                        "dependsOn": [],
                        "reason": "Unsafe identity proposal.",
                    },
                    {
                        "turnOwner": "tasks",
                        "focusRelevant": False,
                        "proposedCapability": "tasks",
                        "proposedAction": "remember-task",
                        "proposedArguments": {"title": "Prepare"},
                        "dependsOn": [1],
                        "reason": "Second step.",
                    },
                ],
                "confidence": 0.99,
                "reason": "Unsafe plan.",
            }
        )

        self.assertFalse(plan.isComposite)
        self.assertEqual(plan.steps, [])
        self.assertIn("identity", plan.reason)

    def test_dependency_must_reference_an_earlier_step(self) -> None:
        plan = sanitize_composite_plan(
            {
                "isComposite": True,
                "steps": [
                    {
                        "turnOwner": "calendar",
                        "focusRelevant": False,
                        "proposedCapability": "calendar",
                        "proposedAction": "read-calendar",
                        "proposedArguments": {"view": "tomorrow"},
                        "dependsOn": [2],
                        "reason": "Invalid forward dependency.",
                    },
                    {
                        "turnOwner": "notes",
                        "focusRelevant": False,
                        "proposedCapability": "notes",
                        "proposedAction": "save-note",
                        "proposedArguments": {"content": "Schedule"},
                        "dependsOn": [],
                        "reason": "Save note.",
                    },
                ],
                "confidence": 0.9,
                "reason": "Invalid dependency.",
            }
        )

        self.assertFalse(plan.isComposite)
        self.assertIn("earlier step", plan.reason)

    def test_focus_is_not_in_first_composite_execution_allowlist(self) -> None:
        self.assertNotIn("focus", COMPOSITE_ATOMIC_ACTIONS_BY_OWNER)

        plan = sanitize_composite_plan(
            {
                "isComposite": True,
                "steps": [
                    {
                        "turnOwner": "focus",
                        "focusRelevant": True,
                        "proposedCapability": "focus",
                        "proposedAction": "update-focus-session",
                        "proposedArguments": {"goal": "Finish slides"},
                        "dependsOn": [],
                        "reason": "Not yet allowed in G1.",
                    },
                    {
                        "turnOwner": "tasks",
                        "focusRelevant": False,
                        "proposedCapability": "tasks",
                        "proposedAction": "remember-task",
                        "proposedArguments": {"title": "Finish slides"},
                        "dependsOn": [],
                        "reason": "Create task.",
                    },
                ],
                "confidence": 0.99,
                "reason": "Mixed focus plan.",
            }
        )

        self.assertFalse(plan.isComposite)

    def test_single_intent_schema_remains_single_owner_single_action(self) -> None:
        fields = set(AgentShadowDecision.model_fields)
        self.assertIn("turnOwner", fields)
        self.assertIn("proposedAction", fields)
        self.assertNotIn("steps", fields)
        self.assertNotIn("plan", fields)

    def test_composite_prompt_is_observational_and_preserves_existing_gates(self) -> None:
        self.assertIn("OBSERVATIONAL ONLY", COMPOSITE_PLAN_SYSTEM_PROMPT)
        self.assertIn("never execute tools", COMPOSITE_PLAN_SYSTEM_PROMPT)
        self.assertIn(
            "existing confirmation policy",
            COMPOSITE_PLAN_SYSTEM_PROMPT,
        )
        self.assertIn("verified receipt", COMPOSITE_PLAN_SYSTEM_PROMPT)
        self.assertIn(
            "Do not invent helpful follow-up actions",
            COMPOSITE_PLAN_SYSTEM_PROMPT,
        )

    def test_shadow_router_exposes_additive_plan_endpoint(self) -> None:
        route_paths = {route.path for route in router.routes}
        self.assertIn("/api/agent/shadow/decide", route_paths)
        self.assertIn("/api/agent/shadow/plan", route_paths)

    def test_no_frontend_composite_execution_is_added_in_g1(self) -> None:
        app_source = (
            ROOT / "src/app/App.tsx"
        ).read_text(encoding="utf-8")
        self.assertNotIn("executeCompositePlan", app_source)
        self.assertNotIn("pendingCompositePlan", app_source)


if __name__ == "__main__":
    unittest.main()
