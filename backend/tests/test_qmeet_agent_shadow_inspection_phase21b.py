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
    shadow_recent,
    shadow_status,
)


ACTIVE_FOCUS = {
    "focusId": "focus-phase21b-inspection",
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


class AgentShadowInspectionPhase21BTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_recent_pairs_problem_statement_decision_with_latest_legacy_route(self):
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
        compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=result.turnId,
                legacyObservation=LegacyRouteObservation(
                    route="Semantic lifecycle Focus start",
                    action="start_focus_session",
                    frontendCommand="apply semantic focus start",
                    sequence=2,
                ),
            )
        )

        payload = shadow_recent(limit=10)
        self.assertEqual(payload["count"], 1)
        item = payload["items"][0]
        self.assertEqual(item["userMessage"], "I'd like to start with a problem statement")
        self.assertEqual(item["decision"]["turnOwner"], "focus")
        self.assertEqual(item["decision"]["disposition"], "conversation")
        self.assertEqual(item["decision"]["proposedAction"], "focus.help")
        self.assertEqual(item["legacyObservation"]["action"], "start_focus_session")
        self.assertEqual(item["comparisonSequence"], 2)
        self.assertTrue(item["focusReplacementRisk"])

    async def test_status_counts_focus_replacement_risk_separately(self):
        recent = [
            ShadowConversationMessage(
                role="assistant",
                content="Which section should we start with for the client presentation?",
            )
        ]
        result = await self._decide("I'd like to start with a problem statement", recent=recent)
        compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=result.turnId,
                legacyObservation=LegacyRouteObservation(
                    route="Semantic lifecycle Focus start",
                    action="start_focus_session",
                    frontendCommand="apply semantic focus start",
                    sequence=1,
                ),
            )
        )
        status = shadow_status()
        self.assertEqual(status["eventCount"], 1)
        self.assertEqual(status["comparedCount"], 1)
        self.assertEqual(status["disagreementCount"], 1)
        self.assertEqual(status["focusReplacementRiskCount"], 1)

    async def test_explicit_focus_start_agreement_is_not_replacement_risk(self):
        result = await self._decide("Start a Focus: prepare for a product demo")
        self.assertEqual(result.decision.proposedAction, "start-focus-session")
        self.assertEqual(result.decision.disposition, "tool")
        compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=result.turnId,
                legacyObservation=LegacyRouteObservation(
                    route="Semantic lifecycle Focus start",
                    action="start_focus_session",
                    frontendCommand="apply semantic focus start",
                    sequence=1,
                ),
            )
        )
        recent = shadow_recent(limit=5)
        self.assertFalse(recent["items"][0]["focusReplacementRisk"])
        self.assertEqual(shadow_status()["focusReplacementRiskCount"], 0)

    async def test_recent_uses_highest_comparison_sequence_even_when_appended_later_out_of_order(self):
        result = await self._decide("why is the sky blue")
        compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=result.turnId,
                legacyObservation=LegacyRouteObservation(
                    route="Normal chat",
                    sequence=4,
                ),
            )
        )
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
        item = shadow_recent(limit=5)["items"][0]
        self.assertEqual(item["comparisonSequence"], 4)
        self.assertEqual(item["legacyObservation"]["route"], "Normal chat")
        self.assertFalse(item["comparison"]["disagreementSummary"])

    async def test_recent_disagreements_only_filters_agreements_and_uncompared_turns(self):
        agreeing = await self._decide("why is the sky blue")
        compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=agreeing.turnId,
                legacyObservation=LegacyRouteObservation(route="Normal chat", sequence=1),
            )
        )
        await self._decide("hello there")
        disagreeing = await self._decide(
            "I'd like to start with a problem statement",
            recent=[
                ShadowConversationMessage(
                    role="assistant",
                    content="Which section should we start with for the client presentation?",
                )
            ],
        )
        compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=disagreeing.turnId,
                legacyObservation=LegacyRouteObservation(
                    route="Semantic lifecycle Focus start",
                    action="start_focus_session",
                    sequence=1,
                ),
            )
        )
        payload = shadow_recent(limit=20, disagreements_only=True)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["turnId"], disagreeing.turnId)

    async def test_recent_limit_returns_newest_decisions_first(self):
        first = await self._decide("hello there")
        second = await self._decide("why is the sky blue")
        third = await self._decide("search for Framework Laptop reviews")
        payload = shadow_recent(limit=2)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(
            [item["turnId"] for item in payload["items"]],
            [third.turnId, second.turnId],
        )
        self.assertNotEqual(payload["items"][0]["turnId"], first.turnId)

    async def test_recent_preserves_uncompared_decisions(self):
        result = await self._decide("hello there")
        item = shadow_recent(limit=5)["items"][0]
        self.assertEqual(item["turnId"], result.turnId)
        self.assertFalse(item["compared"])
        self.assertIsNone(item["legacyObservation"])
        self.assertIsNone(item["comparison"])
        self.assertIsNone(item["comparisonSequence"])

    async def test_malformed_telemetry_lines_are_ignored(self):
        await self._decide("hello there")
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write("not-json\n")
            handle.write(json.dumps({"recordType": "decision", "turnId": ""}) + "\n")
        payload = shadow_recent(limit=10)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(shadow_status()["eventCount"], 1)


if __name__ == "__main__":
    unittest.main()
