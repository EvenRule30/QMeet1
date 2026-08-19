from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from app.qmeet_agent_shadow import AgentShadowDecision
from app.qmeet_capabilities import GLOBAL_CAPABILITY_CONTRACT, PROMOTED_DEVICE_UI_ACTIONS
from app.qmeet_device_ui_promotion import (
    MIN_DEVICE_UI_PROMOTION_CONFIDENCE,
    DeviceUiPromotionResult,
    evaluate_device_ui_promotion,
    frontend_command_for_promoted_device_ui_action,
)
from app.qmeet_orchestrator import interpret_qmeet_orchestrator


class AgentDeviceUiPromotionPhase21ETests(TestCase):
    def _decision(
        self,
        *,
        action: str,
        owner: str = "device_ui",
        capability: str = "device_ui",
        disposition: str = "tool",
        arguments: dict | None = None,
        confidence: float = 0.96,
        focus_relevant: bool = False,
    ) -> AgentShadowDecision:
        return AgentShadowDecision(
            turnOwner=owner,
            focusRelevant=focus_relevant,
            disposition=disposition,
            proposedCapability=capability,
            proposedAction=action,
            proposedArguments={} if arguments is None else arguments,
            responsePlan="Execute the verified Device/UI control and continue naturally.",
            confidence=confidence,
            reason="test decision",
        )

    def test_capability_contract_exposes_narrow_argument_free_device_ui_promotion(self) -> None:
        contract = next(
            item for item in GLOBAL_CAPABILITY_CONTRACT if item.get("owner") == "device_ui"
        )

        self.assertEqual(contract.get("promotedActions"), list(PROMOTED_DEVICE_UI_ACTIONS))
        self.assertEqual(
            contract.get("argumentSchema"),
            {
                "type": "object",
                "additionalProperties": False,
                "required": [],
                "properties": {},
            },
        )
        self.assertTrue(set(PROMOTED_DEVICE_UI_ACTIONS).issubset(set(contract.get("actions") or [])))
        self.assertNotIn("clear-chat", PROMOTED_DEVICE_UI_ACTIONS)
        self.assertNotIn("end-chat", PROMOTED_DEVICE_UI_ACTIONS)
        self.assertNotIn("cancel-action", PROMOTED_DEVICE_UI_ACTIONS)

    def test_every_promoted_device_ui_action_has_one_deterministic_frontend_command(self) -> None:
        for action in PROMOTED_DEVICE_UI_ACTIONS:
            with self.subTest(action=action):
                result = evaluate_device_ui_promotion(self._decision(action=action))
                self.assertEqual(result.status, "execute")
                self.assertEqual(result.action, action)
                self.assertTrue(result.frontend_command)
                self.assertEqual(
                    result.frontend_command,
                    frontend_command_for_promoted_device_ui_action(action),
                )

    def test_device_ui_claim_is_blocked_when_action_is_not_promoted(self) -> None:
        for action in ("clear-chat", "end-chat", "cancel-action", "help", "identity", "voice.control", "ui.navigate"):
            with self.subTest(action=action):
                result = evaluate_device_ui_promotion(self._decision(action=action))
                self.assertEqual(result.status, "blocked")
                self.assertTrue(result.claimed)
                self.assertFalse(result.executable)

    def test_device_ui_claim_requires_exact_capability_empty_arguments_and_confidence(self) -> None:
        cases = (
            self._decision(action="open-settings", capability="focus"),
            self._decision(action="open-settings", arguments={"panel": "settings"}),
            self._decision(
                action="open-settings",
                confidence=MIN_DEVICE_UI_PROMOTION_CONFIDENCE - 0.01,
            ),
            self._decision(action="open-settings", disposition="conversation"),
        )
        for decision in cases:
            with self.subTest(decision=decision.model_dump()):
                result = evaluate_device_ui_promotion(decision)
                self.assertEqual(result.status, "blocked")
                self.assertTrue(result.claimed)
                self.assertFalse(result.executable)

    def test_non_device_owner_does_not_claim_device_ui_promotion(self) -> None:
        result = evaluate_device_ui_promotion(
            self._decision(
                action="read-calendar",
                owner="calendar",
                capability="calendar",
            )
        )
        self.assertEqual(result.status, "not-owned")
        self.assertFalse(result.claimed)

    def test_active_focus_relevance_does_not_turn_device_control_into_focus_mutation(self) -> None:
        result = evaluate_device_ui_promotion(
            self._decision(action="voice-output-off", focus_relevant=True)
        )
        self.assertEqual(result.status, "execute")
        self.assertEqual(result.action, "voice-output-off")
        self.assertNotIn("focus", result.action)

    def test_promoted_frontend_commands_are_covered_by_existing_frontend_parser_source(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        commands_source = (repo_root / "src" / "app" / "commands.ts").read_text(encoding="utf-8")

        for action in PROMOTED_DEVICE_UI_ACTIONS:
            with self.subTest(action=action):
                self.assertIn(f"'{action}'", commands_source)

        # No new LocalCommand executor is introduced by Phase 21E. Every promoted
        # semantic action must already exist in the deterministic frontend command
        # vocabulary; the adapter only supplies a parser-compatible command phrase.
        self.assertIn("export function parseCommand", commands_source)

    def test_orchestrator_returns_promoted_device_ui_command_before_legacy_model(self) -> None:
        promoted = DeviceUiPromotionResult(
            status="execute",
            action="voice-output-off",
            frontend_command="voice off",
            confidence=0.97,
            reason="validated unified Device/UI proposal",
        )
        with patch(
            "app.qmeet_orchestrator.resolve_promoted_device_ui_turn",
            new=AsyncMock(return_value=promoted),
        ), patch.dict(os.environ, {"LLM_PROVIDER": "mock"}, clear=False):
            result = asyncio.run(
                interpret_qmeet_orchestrator(
                    "make your spoken replies quiet for now",
                    ui_state={"activePanel": "none"},
                    client_context={"memoryState": {"activeSession": {"title": "Presentation"}}},
                )
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["intent"], "command")
        self.assertEqual(result["action"], "voice-output-off")
        self.assertEqual(result["frontendCommand"], "voice off")
        self.assertEqual(result["confidence"], 0.97)

    def test_claimed_but_invalid_device_ui_proposal_cannot_fall_through_to_legacy_action(self) -> None:
        blocked = DeviceUiPromotionResult(
            status="blocked",
            action="clear-chat",
            confidence=0.98,
            reason="action is intentionally outside the Phase 21E allowlist",
        )
        with patch(
            "app.qmeet_orchestrator.resolve_promoted_device_ui_turn",
            new=AsyncMock(return_value=blocked),
        ), patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test"}, clear=False):
            result = asyncio.run(
                interpret_qmeet_orchestrator(
                    "wipe this whole conversation away",
                    ui_state={"activePanel": "none"},
                    client_context={},
                )
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["intent"], "chat")
        self.assertEqual(result["action"], "none")
        self.assertEqual(result["frontendCommand"], "")
        self.assertIn("not eligible for Phase 21E execution", result["reason"])

    def test_non_device_agent_decision_preserves_existing_orchestrator_fallback(self) -> None:
        not_owned = DeviceUiPromotionResult(status="not-owned")
        with patch(
            "app.qmeet_orchestrator.resolve_promoted_device_ui_turn",
            new=AsyncMock(return_value=not_owned),
        ), patch.dict(os.environ, {"LLM_PROVIDER": "mock"}, clear=False):
            result = asyncio.run(
                interpret_qmeet_orchestrator(
                    "what can you do",
                    ui_state={"activePanel": "none"},
                    client_context={},
                )
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["intent"], "command")
        self.assertEqual(result["action"], "guide_overview")
        self.assertEqual(result["frontendCommand"], "what can you do")


if __name__ == "__main__":
    import unittest

    unittest.main()
