from __future__ import annotations

import unittest
from pathlib import Path

from app.qmeet_agent_shadow import (
    AGENT_SHADOW_SYSTEM_PROMPT,
    GLOBAL_CAPABILITY_CONTRACT,
    AgentShadowDecision,
    AgentShadowRequest,
    _fallback_shadow_decision,
    apply_task_create_ownership_floor,
    normalize_shadow_decision,
)


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"
PROMOTION = ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"


class AgentTaskCreatePromotionPhase21C1Tests(unittest.TestCase):
    def test_agent_prompt_has_strict_task_create_contract(self) -> None:
        self.assertIn("Tasks ownership rule:", AGENT_SHADOW_SYSTEM_PROMPT)
        self.assertIn("proposedAction=remember-task", AGENT_SHADOW_SYSTEM_PROMPT)
        self.assertIn('{"title": "<concise task title>"}', AGENT_SHADOW_SYSTEM_PROMPT)
        self.assertIn("Task completion remains", AGENT_SHADOW_SYSTEM_PROMPT)
        self.assertIn("put X on my to-do list", AGENT_SHADOW_SYSTEM_PROMPT)
        self.assertIn("do not use disposition=conversation", AGENT_SHADOW_SYSTEM_PROMPT)

    def test_shared_contract_exposes_title_only_schema(self) -> None:
        tasks = next(item for item in GLOBAL_CAPABILITY_CONTRACT if item.get("owner") == "tasks")
        schema = tasks["createArgumentSchema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["required"], ["title"])
        self.assertEqual(schema["properties"]["title"]["maxLength"], 240)

    def test_frontend_validator_is_title_only_and_fail_closed(self) -> None:
        source = PROMOTION.read_text(encoding="utf-8")
        self.assertIn("export function isPromotedTaskCreateToolDecision", source)
        self.assertIn("export function resolvePromotedTaskCreateToolCommand", source)
        self.assertIn("keys.length !== 1 || keys[0] !== 'title'", source)
        self.assertIn("command: 'remember-task'", source)
        self.assertIn("payload: title", source)

    def test_app_promotes_task_create_before_calendar_without_bypassing_handler(self) -> None:
        source = APP.read_text(encoding="utf-8")
        task_index = source.index("const promotedTaskCreateCandidate")
        calendar_index = source.index("const promotedCalendarCreateCandidate")
        self.assertLess(task_index, calendar_index)
        self.assertIn("'Agent-promoted task create rejected'", source)
        self.assertIn("'I understood this as creating a task, but I could not safely validate one task title. No task was added.'", source)
        self.assertIn("promotedTaskCreateTool.commandMatch", source)
        self.assertIn("'agent'", source[task_index:calendar_index])

    def test_existing_task_completion_identity_seam_is_unchanged(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("const confirmedTaskCommandMatch: CommandMatch | undefined =", source)
        self.assertIn("resolvedTaskTargets", source)
        self.assertIn("completeConfirmedTaskTargets", source)

    def test_explicit_task_container_fallback_covers_live_phrasings(self) -> None:
        cases = {
            "put finishing the executive slides on my to-do list": "finishing the executive slides",
            "make sending the invoice a task": "sending the invoice",
            "add review the presentation outline to my tasks": "review the presentation outline",
        }
        for user_message, expected_title in cases.items():
            with self.subTest(user_message=user_message):
                decision = normalize_shadow_decision(
                    _fallback_shadow_decision(
                        AgentShadowRequest(userMessage=user_message),
                        None,
                    )
                )
                self.assertEqual(decision.turnOwner, "tasks")
                self.assertEqual(decision.disposition, "tool")
                self.assertEqual(decision.proposedCapability, "tasks")
                self.assertEqual(decision.proposedAction, "remember-task")
                self.assertEqual(decision.proposedArguments, {"title": expected_title})
                self.assertGreaterEqual(decision.confidence, 0.95)

    def test_task_floor_repairs_false_conversation_and_uses_literal_fallback_title(self) -> None:
        request = AgentShadowRequest(
            userMessage="add review the presentation outline to my tasks"
        )
        wrong = AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Acknowledge conversationally.",
            confidence=0.92,
            reason="Model misclassified an explicit task mutation.",
        )
        repaired = apply_task_create_ownership_floor(request, None, wrong)
        self.assertEqual(repaired.turnOwner, "tasks")
        self.assertEqual(repaired.disposition, "tool")
        self.assertEqual(repaired.proposedAction, "remember-task")
        self.assertEqual(
            repaired.proposedArguments,
            {"title": "review the presentation outline"},
        )

    def test_task_floor_preserves_valid_model_title_when_only_ownership_is_wrong(self) -> None:
        request = AgentShadowRequest(
            userMessage="put finishing the executive slides on my to-do list"
        )
        wrong = AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={"title": "Finish Executive Slides"},
            responsePlan="Acknowledge conversationally.",
            confidence=0.92,
            reason="Model chose the wrong disposition but supplied a safe title.",
        )
        repaired = apply_task_create_ownership_floor(request, None, wrong)
        self.assertEqual(repaired.turnOwner, "tasks")
        self.assertEqual(repaired.disposition, "tool")
        self.assertEqual(repaired.proposedAction, "remember-task")
        self.assertEqual(
            repaired.proposedArguments,
            {"title": "Finish Executive Slides"},
        )

    def test_task_floor_does_not_convert_non_mutating_task_question(self) -> None:
        request = AgentShadowRequest(userMessage="what tasks do I have?")
        conversation = AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Answer conversationally.",
            confidence=0.92,
            reason="Synthetic conversation decision.",
        )
        unchanged = apply_task_create_ownership_floor(request, None, conversation)
        self.assertIs(unchanged, conversation)


if __name__ == "__main__":
    unittest.main()
