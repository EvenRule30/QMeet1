from __future__ import annotations

import asyncio
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from app.qmeet_agent_shadow import (
    AgentShadowDecision,
    AgentShadowRequest,
    AgentShadowResponse,
    AgentShadowComparison,
)
from app.qmeet_device_ui_ownership import (
    apply_device_ui_ownership_floor,
    resolve_obvious_device_ui_action,
)
from app.qmeet_device_ui_promotion import resolve_promoted_device_ui_turn


class AgentDeviceUiRuntimePhase21E2Tests(TestCase):
    def _conversation_decision(
        self,
        *,
        owner: str = "general_chat",
        confidence: float = 0.96,
        focus_relevant: bool = False,
    ) -> AgentShadowDecision:
        return AgentShadowDecision(
            turnOwner=owner,
            focusRelevant=focus_relevant,
            disposition="conversation",
            proposedCapability="none" if owner == "general_chat" else owner,
            proposedAction="conversation.respond" if owner == "general_chat" else "focus.help",
            proposedArguments={},
            responsePlan="Answer conversationally.",
            confidence=confidence,
            reason="simulated missed Device/UI ownership",
        )

    def _response(self, decision: AgentShadowDecision) -> AgentShadowResponse:
        return AgentShadowResponse(
            turnId="phase21e2-test-turn",
            decision=decision,
            comparison=AgentShadowComparison(
                compared=False,
                ownerAgreement=None,
                dispositionAgreement=None,
                actionAgreement=None,
                legacyRoute="",
                disagreementSummary="",
            ),
        )

    def test_live_voice_wording_resolves_to_persistent_voice_output_on(self) -> None:
        self.assertEqual(
            resolve_obvious_device_ui_action(
                "could you start reading your answers out loud for a bit?"
            ),
            "voice-output-on",
        )

    def test_live_main_screen_wording_resolves_to_go_home(self) -> None:
        self.assertEqual(
            resolve_obvious_device_ui_action(
                "can you get me back to the main screen?"
            ),
            "go-home",
        )

    def test_guidance_and_discussion_about_controls_do_not_execute(self) -> None:
        for message in (
            "could you tell me how to turn voice on?",
            "why do people read answers out loud?",
            "what happens if I turn voice off?",
            "explain the main screen",
            "how do I get back to the main screen?",
        ):
            with self.subTest(message=message):
                self.assertIsNone(resolve_obvious_device_ui_action(message))

    def test_floor_does_not_promote_destructive_or_session_wide_commands(self) -> None:
        for message in (
            "clear this chat",
            "end this conversation",
            "cancel the pending action",
            "delete everything",
        ):
            with self.subTest(message=message):
                self.assertIsNone(resolve_obvious_device_ui_action(message))

    def test_focus_panel_wording_stays_with_existing_focus_ui_semantics(self) -> None:
        for message in (
            "open the focus menu",
            "show my focus panel",
            "bring up the focus controls",
        ):
            with self.subTest(message=message):
                self.assertIsNone(resolve_obvious_device_ui_action(message))

    def test_floor_repairs_general_chat_capability_denial_before_visible_chat(self) -> None:
        repaired = apply_device_ui_ownership_floor(
            "could you start reading your answers out loud for a bit?",
            self._conversation_decision(),
        )

        self.assertEqual(repaired.turnOwner, "device_ui")
        self.assertFalse(repaired.focusRelevant)
        self.assertEqual(repaired.disposition, "tool")
        self.assertEqual(repaired.proposedCapability, "device_ui")
        self.assertEqual(repaired.proposedAction, "voice-output-on")
        self.assertEqual(repaired.proposedArguments, {})
        self.assertGreaterEqual(repaired.confidence, 0.98)

    def test_active_focus_cannot_steal_an_obvious_device_control(self) -> None:
        repaired = apply_device_ui_ownership_floor(
            "can you get me back to the main screen?",
            self._conversation_decision(
                owner="focus",
                focus_relevant=True,
            ),
        )

        self.assertEqual(repaired.turnOwner, "device_ui")
        self.assertFalse(repaired.focusRelevant)
        self.assertEqual(repaired.proposedAction, "go-home")

    def test_valid_device_ui_proposal_drops_stale_focus_relevance(self) -> None:
        decision = AgentShadowDecision(
            turnOwner="device_ui",
            focusRelevant=True,
            disposition="tool",
            proposedCapability="device_ui",
            proposedAction="voice-output-on",
            proposedArguments={},
            responsePlan="Enable voice output.",
            confidence=0.95,
            reason="Simulated model proposal with stale Focus relevance.",
        )

        repaired = apply_device_ui_ownership_floor(
            "could you start reading your answers out loud for a bit?",
            decision,
        )

        self.assertEqual(repaired.turnOwner, "device_ui")
        self.assertFalse(repaired.focusRelevant)
        self.assertEqual(repaired.proposedAction, "voice-output-on")
        self.assertEqual(repaired.confidence, 0.95)

    def test_orchestrator_device_ui_promotion_precedes_active_focus_chat_fallback(self) -> None:
        from app import qmeet_orchestrator
        from app.qmeet_device_ui_promotion import DeviceUiPromotionResult

        active_focus_context = {
            "memoryState": {
                "activeSession": {
                    "title": "Presentation",
                }
            }
        }
        high_confidence_focus_chat = qmeet_orchestrator._chat_response(
            "simulated active Focus conversation guard",
            0.99,
        )
        promoted = DeviceUiPromotionResult(
            status="execute",
            action="go-home",
            frontend_command="go home",
            confidence=0.98,
            reason="validated Device/UI promotion",
        )

        with patch(
            "app.qmeet_orchestrator._fallback_orchestrator",
            return_value=high_confidence_focus_chat,
        ), patch(
            "app.qmeet_orchestrator.resolve_promoted_device_ui_turn",
            new=AsyncMock(return_value=promoted),
        ):
            result = asyncio.run(
                qmeet_orchestrator.interpret_qmeet_orchestrator(
                    "can you get me back to the main screen?",
                    ui_state={"activePanel": "settings"},
                    client_context=active_focus_context,
                )
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["intent"], "command")
        self.assertEqual(result["action"], "go-home")
        self.assertEqual(result["frontendCommand"], "go home")
        self.assertEqual(result["confidence"], 0.98)

    def test_floor_does_not_override_a_specific_other_capability_owner(self) -> None:
        calendar = AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="read-calendar",
            proposedArguments={"view": "today"},
            responsePlan="Read Calendar.",
            confidence=0.97,
            reason="calendar-owned test decision",
        )
        repaired = apply_device_ui_ownership_floor(
            "open settings for my calendar",
            calendar,
        )
        self.assertIs(repaired, calendar)

    def test_interpreter_bridge_repairs_a_missed_agent_decision_then_reuses_existing_command(self) -> None:
        missed = self._response(self._conversation_decision())
        with patch(
            "app.qmeet_device_ui_promotion.decide_agent_shadow",
            new=AsyncMock(return_value=missed),
        ):
            result = asyncio.run(
                resolve_promoted_device_ui_turn(
                    "could you start reading your answers out loud for a bit?",
                    ui_state={"activePanel": "none"},
                    client_context={"memoryState": {"activeSession": {"title": "Presentation"}}},
                )
            )

        self.assertEqual(result.status, "execute")
        self.assertEqual(result.action, "voice-output-on")
        self.assertEqual(result.frontend_command, "voice on")

    def test_agent_decision_endpoint_repairs_before_frontend_single_intent_promotion(self) -> None:
        from app.routers import agent_shadow

        req = AgentShadowRequest(
            userMessage="can you get me back to the main screen?",
            uiState={"activePanel": "settings"},
            clientContext={},
        )
        missed = self._response(self._conversation_decision())

        with patch(
            "app.routers.agent_shadow.decide_agent_shadow",
            new=AsyncMock(return_value=missed),
        ):
            response = asyncio.run(agent_shadow.decide(req))

        self.assertEqual(response.decision.turnOwner, "device_ui")
        self.assertEqual(response.decision.disposition, "tool")
        self.assertEqual(response.decision.proposedAction, "go-home")

    def test_real_fastapi_app_mounts_the_frontend_agent_decision_endpoint(self) -> None:
        from app.main import app

        # FastAPI 0.137+ preserves included APIRouters as lazy wrappers instead
        # of flattening every child route into app.routes.  Verify the public
        # application contract rather than depending on that internal shape.
        openapi_schema = app.openapi()
        path_item = openapi_schema.get("paths", {}).get(
            "/api/agent/shadow/decide"
        )

        self.assertIsNotNone(path_item)
        assert path_item is not None
        self.assertIn("post", path_item)

    def test_source_contract_connects_frontend_endpoint_router_and_main(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        observer_source = (
            repo_root / "src" / "app" / "lib" / "agentShadowObserver.ts"
        ).read_text(encoding="utf-8")
        router_source = (
            repo_root / "backend" / "app" / "routers" / "agent_shadow.py"
        ).read_text(encoding="utf-8")
        main_source = (repo_root / "backend" / "app" / "main.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("/api/agent/shadow/decide", observer_source)
        self.assertIn('@router.post("/decide"', router_source)
        self.assertIn("agent_shadow,", main_source)
        self.assertIn("app.include_router(agent_shadow.router)", main_source)


if __name__ == "__main__":
    import unittest

    unittest.main()
