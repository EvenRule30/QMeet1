import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.qmeet_agent_shadow import (
    AgentShadowCompareRequest,
    AgentShadowRequest,
    LegacyRouteObservation,
    ShadowConversationMessage,
    compare_agent_shadow_turn,
    decide_agent_shadow,
    normalize_legacy_observation,
    shadow_status,
)


ACTIVE_FOCUS = {
    "focusId": "focus-phase21b-compare",
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


class AgentShadowComparisonPhase21BTests(unittest.IsolatedAsyncioTestCase):
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

    async def _decide(self, message: str, *, recent=None, focus=ACTIVE_FOCUS):
        request = AgentShadowRequest(
            userMessage=message,
            recentConversation=recent or [],
            uiState={"activePanel": "none"},
            clientContext={},
        )
        with patch("app.qmeet_agent_shadow.active_focus_snapshot", return_value=focus), patch(
            "app.qmeet_agent_shadow._generate_model_decision",
            new=AsyncMock(return_value=None),
        ):
            return await decide_agent_shadow(request)

    async def test_problem_statement_reply_is_focus_conversation_in_fallback(self):
        recent = [
            ShadowConversationMessage(
                role="assistant",
                content=(
                    "Which section would you like to start with for the client presentation on your app's progress? "
                    "For example, key features, milestones, challenges, or next steps?"
                ),
            )
        ]
        result = await self._decide("I'd like to start with a problem statement", recent=recent)
        self.assertEqual(result.decision.turnOwner, "focus")
        self.assertTrue(result.decision.focusRelevant)
        self.assertEqual(result.decision.disposition, "conversation")
        self.assertEqual(result.decision.proposedAction, "focus.help")

    async def test_short_focus_followup_recovers_past_legacy_warning(self):
        recent = [
            ShadowConversationMessage(
                role="assistant",
                content="Which section should we start with for the client presentation on your app progress? For example, key features or milestones?",
            ),
            ShadowConversationMessage(
                role="assistant",
                content="I understood this as a possible Focus change, but I could not identify one safe lifecycle operation. The Focus was not changed.",
            ),
        ]
        result = await self._decide("key features", recent=recent)
        self.assertEqual(result.decision.turnOwner, "focus")
        self.assertTrue(result.decision.focusRelevant)
        self.assertEqual(result.decision.disposition, "conversation")

    def test_blocked_focus_route_infers_focus_clarification(self):
        observation = normalize_legacy_observation(
            LegacyRouteObservation(
                route="Semantic Focus lifecycle change blocked safely",
                action="focus_lifecycle_change",
                sequence=2,
            )
        )
        self.assertEqual(observation.owner, "focus")
        self.assertEqual(observation.disposition, "clarify")
        self.assertEqual(observation.sequence, 2)

    async def test_late_comparison_does_not_inflate_decision_event_count(self):
        result = await self._decide("why is the sky blue?")
        before = shadow_status()
        self.assertEqual(before["eventCount"], 1)
        self.assertEqual(before["comparedCount"], 0)

        comparison = compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=result.turnId,
                legacyObservation=LegacyRouteObservation(
                    route="Normal chat",
                    sequence=1,
                ),
            )
        )
        self.assertTrue(comparison.foundDecision)
        self.assertTrue(comparison.comparison.compared)

        after = shadow_status()
        self.assertEqual(after["eventCount"], 1)
        self.assertEqual(after["comparedCount"], 1)
        self.assertEqual(after["comparisonEventCount"], 1)
        self.assertEqual(after["uncomparedCount"], 0)

    async def test_highest_route_sequence_wins_if_network_order_is_reversed(self):
        recent = [
            ShadowConversationMessage(
                role="assistant",
                content="Which section should we start with for the client presentation on your app progress?",
            )
        ]
        result = await self._decide("I'd like to start with a problem statement", recent=recent)
        compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=result.turnId,
                legacyObservation=LegacyRouteObservation(
                    route="Semantic Focus lifecycle change blocked safely",
                    action="focus_lifecycle_change",
                    sequence=2,
                ),
            )
        )
        compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=result.turnId,
                legacyObservation=LegacyRouteObservation(
                    route="Exact local command",
                    sequence=1,
                ),
            )
        )
        status = shadow_status()
        self.assertEqual(status["eventCount"], 1)
        self.assertEqual(status["comparedCount"], 1)
        self.assertEqual(status["disagreementCount"], 1)
        self.assertEqual(status["ownerDisagreementCount"], 0)
        self.assertEqual(status["dispositionDisagreementCount"], 1)

    def test_unknown_turn_id_is_non_mutating_uncompared_result(self):
        result = compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId="shadow-missing",
                legacyObservation=LegacyRouteObservation(route="Normal chat", sequence=1),
            )
        )
        self.assertFalse(result.foundDecision)
        self.assertFalse(result.comparison.compared)
        self.assertFalse(self.log_path.exists())

    async def test_telemetry_is_append_only_with_distinct_record_types(self):
        result = await self._decide("hello there")
        compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=result.turnId,
                legacyObservation=LegacyRouteObservation(route="Normal chat", sequence=1),
            )
        )
        records = [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual([record.get("recordType") for record in records], ["decision", "comparison"])
        self.assertEqual(records[0]["turnId"], records[1]["turnId"])


if __name__ == "__main__":
    unittest.main()
