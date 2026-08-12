import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.qmeet_agent_shadow import (
    AgentShadowRequest,
    LegacyRouteObservation,
    ShadowConversationMessage,
    compare_shadow_to_legacy,
    decide_agent_shadow,
    shadow_status,
)


ACTIVE_FOCUS = {
    "focusId": "focus-phase21b",
    "title": "prepare for a client presentation",
    "objective": "clearly show the progress of my app",
    "deliverable": "",
    "subject": "",
    "requirements": [],
    "constraints": [],
    "preferences": ["concise answers"],
    "decisions": [],
    "knownFacts": [],
    "milestones": [],
    "completedMilestones": [],
    "nextAction": "",
    "pendingQuestion": None,
    "status": "clarifying",
}


class AgentShadowPhase21BTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.log_path = Path(self.temp_dir.name) / "agent-shadow.jsonl"
        self.env_patch = patch.dict(
            os.environ,
            {
                "QMEET_AGENT_SHADOW_LOG": str(self.log_path),
                "LLM_PROVIDER": "mock",
            },
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    async def _decide(self, message: str, *, recent=None, legacy=None, focus=ACTIVE_FOCUS):
        request = AgentShadowRequest(
            userMessage=message,
            recentConversation=recent or [],
            uiState={"activePanel": "none"},
            clientContext={},
            legacyObservation=legacy,
        )
        with patch("app.qmeet_agent_shadow.active_focus_snapshot", return_value=focus), patch(
            "app.qmeet_agent_shadow._generate_model_decision",
            new=AsyncMock(return_value=None),
        ):
            return await decide_agent_shadow(request)

    async def test_active_focus_does_not_own_unrelated_calendar_turn(self):
        result = await self._decide("add a dentist appointment tomorrow at 2")
        self.assertEqual(result.decision.turnOwner, "calendar")
        self.assertFalse(result.decision.focusRelevant)
        self.assertEqual(result.decision.disposition, "tool")
        self.assertEqual(result.decision.proposedAction, "calendar.create_event")

    async def test_active_focus_does_not_own_general_knowledge_turn(self):
        result = await self._decide("why is the sky blue?")
        self.assertEqual(result.decision.turnOwner, "general_chat")
        self.assertFalse(result.decision.focusRelevant)
        self.assertEqual(result.decision.disposition, "conversation")

    async def test_active_focus_does_not_own_greeting(self):
        result = await self._decide("hello there")
        self.assertEqual(result.decision.turnOwner, "general_chat")
        self.assertFalse(result.decision.focusRelevant)

    async def test_active_focus_does_not_own_search_turn(self):
        result = await self._decide("search for reviews of the Framework Laptop")
        self.assertEqual(result.decision.turnOwner, "search")
        self.assertFalse(result.decision.focusRelevant)
        self.assertEqual(result.decision.proposedAction, "search.run")

    async def test_explicit_focus_goal_update_is_focus_owned_tool_work(self):
        result = await self._decide("goal: I want to clearly show the progress of my app")
        self.assertEqual(result.decision.turnOwner, "focus")
        self.assertTrue(result.decision.focusRelevant)
        self.assertEqual(result.decision.disposition, "tool")
        self.assertEqual(result.decision.proposedAction, "focus.update_goal")

    async def test_substantive_help_continuation_is_focus_conversation_not_mutation(self):
        recent = [
            ShadowConversationMessage(
                role="assistant",
                content="I can help outline the client presentation and highlight your app progress.",
            ),
            ShadowConversationMessage(role="user", content="I want concise answers"),
            ShadowConversationMessage(
                role="assistant",
                content="Keep the presentation centered on milestones, current functionality, and next steps.",
            ),
        ]
        result = await self._decide("so can you help me?", recent=recent)
        self.assertEqual(result.decision.turnOwner, "focus")
        self.assertTrue(result.decision.focusRelevant)
        self.assertEqual(result.decision.disposition, "conversation")
        self.assertEqual(result.decision.proposedAction, "focus.help")

    async def test_short_referential_followup_can_continue_focus_work(self):
        recent = [
            ShadowConversationMessage(
                role="assistant",
                content="Would you like an outline or the main points for your client presentation?",
            )
        ]
        result = await self._decide("main points would be good", recent=recent)
        self.assertEqual(result.decision.turnOwner, "focus")
        self.assertTrue(result.decision.focusRelevant)
        self.assertEqual(result.decision.disposition, "conversation")

    async def test_cross_capability_calendar_turn_can_use_focus_without_focus_ownership(self):
        result = await self._decide("add practice time for my presentation tomorrow at 2")
        self.assertEqual(result.decision.turnOwner, "calendar")
        self.assertTrue(result.decision.focusRelevant)
        self.assertEqual(result.decision.disposition, "tool")

    async def test_shadow_comparison_records_owner_disagreement(self):
        legacy = LegacyRouteObservation(
            route="Normal chat",
            owner="focus",
            action="none",
            disposition="conversation",
        )
        result = await self._decide("why is the sky blue?", legacy=legacy)
        self.assertTrue(result.comparison.compared)
        self.assertFalse(result.comparison.ownerAgreement)
        self.assertIn("owner shadow=general_chat legacy=focus", result.comparison.disagreementSummary)

    async def test_shadow_telemetry_is_append_only_observation(self):
        before = dict(ACTIVE_FOCUS)
        result = await self._decide("what is my focus")
        self.assertEqual(result.mode, "shadow")
        self.assertEqual(ACTIVE_FOCUS, before)
        self.assertTrue(self.log_path.exists())
        records = [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["mode"], "shadow")
        self.assertEqual(records[0]["activeFocusId"], "focus-phase21b")
        self.assertEqual(records[0]["decision"]["turnOwner"], "focus")
        self.assertNotIn("verified", records[0]["decision"])

    async def test_status_counts_compared_disagreements(self):
        legacy = LegacyRouteObservation(
            route="Legacy Focus chat",
            owner="focus",
            disposition="conversation",
        )
        await self._decide("hello there", legacy=legacy)
        await self._decide("search for Framework Laptop reviews")
        status = shadow_status()
        self.assertEqual(status["eventCount"], 2)
        self.assertEqual(status["comparedCount"], 1)
        self.assertEqual(status["ownerDisagreementCount"], 1)
        self.assertEqual(status["disagreementCount"], 1)

    def test_compare_without_legacy_observation_is_explicitly_uncompared(self):
        from app.qmeet_agent_shadow import AgentShadowDecision

        decision = AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Answer directly.",
            confidence=0.9,
            reason="General chat.",
        )
        comparison = compare_shadow_to_legacy(decision, None)
        self.assertFalse(comparison.compared)
        self.assertIsNone(comparison.ownerAgreement)


if __name__ == "__main__":
    unittest.main()
