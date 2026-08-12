import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.qmeet_agent_shadow import (
    ACTION_VOCABULARY_VERSION,
    AgentShadowCompareRequest,
    AgentShadowDecision,
    AgentShadowRequest,
    LegacyRouteObservation,
    compare_agent_shadow_turn,
    compare_shadow_to_legacy,
    decide_agent_shadow,
    normalize_shadow_decision,
    shadow_recent,
    shadow_status,
)


ACTIVE_FOCUS = {
    "focusId": "focus-phase21b-action-vocab",
    "title": "prepare for a client presentation",
    "objective": "clearly show the progress of my app",
    "deliverable": "",
    "subject": "",
    "requirements": [],
    "constraints": [],
    "preferences": [],
    "decisions": [],
    "knownFacts": [],
    "milestones": [],
    "completedMilestones": [],
    "nextAction": "",
    "pendingQuestion": None,
    "status": "clarifying",
}


class AgentShadowActionVocabularyPhase21BTests(unittest.IsolatedAsyncioTestCase):
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

    async def _decide(self, message: str, *, focus=ACTIVE_FOCUS):
        request = AgentShadowRequest(
            userMessage=message,
            recentConversation=[],
            uiState={"activePanel": "none"},
            clientContext={},
        )
        with patch("app.qmeet_agent_shadow.active_focus_snapshot", return_value=focus), patch(
            "app.qmeet_agent_shadow._generate_model_decision",
            new=AsyncMock(return_value=None),
        ):
            return await decide_agent_shadow(request)

    async def test_focus_read_uses_canonical_local_command_action(self):
        result = await self._decide("what is my focus")
        self.assertEqual(result.decision.proposedAction, "read-focus-session")
        comparison = compare_agent_shadow_turn(
            AgentShadowCompareRequest(
                turnId=result.turnId,
                legacyObservation=LegacyRouteObservation(
                    route="Exact local command",
                    owner="focus",
                    action="read-focus-session",
                    disposition="tool",
                    sequence=1,
                ),
            )
        )
        self.assertTrue(comparison.comparison.actionAgreement)
        self.assertFalse(comparison.comparison.disagreementSummary)

    async def test_focus_goal_update_uses_canonical_update_action(self):
        result = await self._decide("goal: clearly explain the customer problem")
        self.assertEqual(result.decision.proposedAction, "update-focus-session")

    async def test_calendar_and_search_fallbacks_use_local_command_ids(self):
        calendar = await self._decide("add a dentist appointment tomorrow at 2")
        search = await self._decide("search for Framework Laptop reviews")
        self.assertEqual(calendar.decision.proposedAction, "add-calendar-event")
        self.assertEqual(search.decision.proposedAction, "run-search")

    def test_old_semantic_aliases_compare_equal_to_canonical_legacy_actions(self):
        decision = AgentShadowDecision(
            turnOwner="focus",
            focusRelevant=True,
            disposition="tool",
            proposedCapability="focus",
            proposedAction="focus.read",
            proposedArguments={},
            responsePlan="Read the current focus.",
            confidence=1.0,
            reason="Explicit Focus read.",
        )
        comparison = compare_shadow_to_legacy(
            decision,
            LegacyRouteObservation(
                route="Exact local command",
                owner="focus",
                action="read_focus_session",
                disposition="tool",
            ),
        )
        self.assertTrue(comparison.actionAgreement)
        self.assertFalse(comparison.disagreementSummary)

    def test_conversation_action_is_normalized_away_from_tool_alias(self):
        decision = normalize_shadow_decision(
            AgentShadowDecision(
                turnOwner="focus",
                focusRelevant=True,
                disposition="conversation",
                proposedCapability="focus",
                proposedAction="focus.update_context",
                proposedArguments={"contextUpdate": "problem statement"},
                responsePlan="Help with the problem statement.",
                confidence=0.95,
                reason="Substantive Focus work.",
            )
        )
        self.assertEqual(decision.proposedAction, "focus.help")
        self.assertEqual(decision.proposedCapability, "focus")

    def test_action_comparison_is_not_counted_when_disposition_is_conversation(self):
        decision = AgentShadowDecision(
            turnOwner="focus",
            focusRelevant=True,
            disposition="conversation",
            proposedCapability="focus",
            proposedAction="focus.help",
            proposedArguments={},
            responsePlan="Help directly.",
            confidence=0.95,
            reason="Focus conversation.",
        )
        comparison = compare_shadow_to_legacy(
            decision,
            LegacyRouteObservation(
                route="Agent shadow guarded inferred Focus mutation",
                owner="focus",
                action="update-focus-session",
                disposition="conversation",
            ),
        )
        self.assertIsNone(comparison.actionAgreement)
        self.assertFalse(comparison.disagreementSummary)

    def test_unknown_tool_action_is_not_promoted_into_canonical_vocabulary(self):
        decision = normalize_shadow_decision(
            AgentShadowDecision(
                turnOwner="focus",
                focusRelevant=True,
                disposition="tool",
                proposedCapability="focus",
                proposedAction="resume_previous_focus_with_problem_statement",
                proposedArguments={},
                responsePlan="Resume prior Focus.",
                confidence=0.95,
                reason="Compound lifecycle request.",
            )
        )
        self.assertEqual(decision.proposedAction, "none")
        self.assertEqual(
            decision.proposedArguments["shadowRawProposedAction"],
            "resume_previous_focus_with_problem_statement",
        )

    def test_historical_false_action_disagreement_is_recomputed_on_read(self):
        decision_record = {
            "timestamp": "2026-08-12T12:01:47-07:00",
            "recordType": "decision",
            "schemaVersion": "phase21b-v1",
            "mode": "shadow",
            "turnId": "shadow-historical-read",
            "userMessage": "what is my focus",
            "activeFocusId": ACTIVE_FOCUS["focusId"],
            "activeFocusTitle": ACTIVE_FOCUS["title"],
            "decision": {
                "turnOwner": "focus",
                "focusRelevant": True,
                "disposition": "tool",
                "proposedCapability": "focus.read",
                "proposedAction": "read_current_focus",
                "proposedArguments": {},
                "responsePlan": "Read the current Focus.",
                "confidence": 1.0,
                "reason": "Explicit Focus read.",
            },
            "legacyObservation": None,
            "comparison": {"compared": False},
        }
        comparison_record = {
            "timestamp": "2026-08-12T12:01:48-07:00",
            "recordType": "comparison",
            "schemaVersion": "phase21b-v1",
            "mode": "shadow",
            "turnId": "shadow-historical-read",
            "sequence": 1,
            "decision": decision_record["decision"],
            "legacyObservation": {
                "route": "Exact local command",
                "owner": "focus",
                "action": "read-focus-session",
                "frontendCommand": "",
                "disposition": "tool",
                "sequence": 1,
            },
            "comparison": {
                "compared": True,
                "ownerAgreement": True,
                "dispositionAgreement": True,
                "actionAgreement": False,
                "legacyRoute": "Exact local command",
                "disagreementSummary": "action shadow=read_current_focus legacy=read-focus-session",
            },
        }
        self.log_path.write_text(
            json.dumps(decision_record) + "\n" + json.dumps(comparison_record) + "\n",
            encoding="utf-8",
        )

        status = shadow_status()
        self.assertEqual(status["actionVocabularyVersion"], ACTION_VOCABULARY_VERSION)
        self.assertEqual(status["actionDisagreementCount"], 0)
        self.assertEqual(status["disagreementCount"], 0)

        recent = shadow_recent(limit=5)
        item = recent["items"][0]
        self.assertEqual(item["decision"]["proposedAction"], "read-focus-session")
        self.assertTrue(item["comparison"]["actionAgreement"])
        self.assertEqual(item["comparison"]["disagreementSummary"], "")


if __name__ == "__main__":
    unittest.main()
