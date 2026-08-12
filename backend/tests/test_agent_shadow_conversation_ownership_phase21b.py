from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from app import conversation_lane


ROOT = Path(__file__).resolve().parents[2]
APP_SOURCE = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
OBSERVER_SOURCE = (
    ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts"
).read_text(encoding="utf-8")
CONVERSATION_CLIENT_SOURCE = (
    ROOT / "src" / "app" / "lib" / "conversationLane.ts"
).read_text(encoding="utf-8")


FOCUS = {
    "focusId": "focus-presentation",
    "title": "prepare for a client presentation",
    "objective": "clearly explain the customer problem",
    "deliverable": "",
    "subject": "",
    "requirements": [],
    "constraints": [],
    "preferences": ["concise answers"],
    "decisions": [],
    "knownFacts": [],
    "milestones": [],
    "completedMilestones": [],
    "nextAction": "draft the opening",
    "pendingQuestion": None,
    "status": "active",
}


class Phase21BConversationOwnershipTests(unittest.TestCase):
    def _build_input(self, request: conversation_lane.ConversationLaneRequest):
        with patch.object(
            conversation_lane,
            "active_focus_snapshot",
            return_value=FOCUS,
        ), patch.object(
            conversation_lane,
            "_developer_contexts_for_message",
            return_value=[{"role": "developer", "content": "SYSTEM"}],
        ):
            return conversation_lane.build_conversation_lane_input(request)

    def test_promoted_general_chat_suppresses_focus_context(self):
        request = conversation_lane.ConversationLaneRequest(
            userMessage="hello there",
            recentConversation=[
                {
                    "role": "assistant",
                    "content": "We were drafting your client presentation.",
                }
            ],
            ownershipHint={
                "source": "agent-shadow",
                "turnOwner": "general_chat",
                "focusRelevant": False,
                "confidence": 0.95,
                "turnId": "shadow-general",
            },
        )
        serialized = json.dumps(self._build_input(request))
        self.assertIn("Promoted read-only turn ownership from QMeet agent shadow: general_chat", serialized)
        self.assertNotIn("Canonical Active Focus context is relevant", serialized)

    def test_promoted_focus_conversation_attaches_canonical_focus(self):
        request = conversation_lane.ConversationLaneRequest(
            userMessage="main points would be good",
            recentConversation=[
                {
                    "role": "assistant",
                    "content": "I can help outline the presentation.",
                }
            ],
            ownershipHint={
                "source": "agent-shadow",
                "turnOwner": "focus",
                "focusRelevant": True,
                "confidence": 0.96,
                "turnId": "shadow-focus",
            },
        )
        serialized = json.dumps(self._build_input(request))
        self.assertIn("Promoted read-only turn ownership from QMeet agent shadow: focus", serialized)
        self.assertIn("Canonical Active Focus context is relevant", serialized)
        self.assertIn("prepare for a client presentation", serialized)
        self.assertIn("clearly explain the customer problem", serialized)

    def test_without_promoted_hint_existing_focus_heuristic_remains_available(self):
        request = conversation_lane.ConversationLaneRequest(
            userMessage="let's continue with our focus",
        )
        serialized = json.dumps(self._build_input(request))
        self.assertIn("Canonical Active Focus context is relevant", serialized)
        self.assertNotIn("Promoted read-only turn ownership", serialized)

    def test_without_promoted_hint_general_greeting_still_excludes_focus(self):
        request = conversation_lane.ConversationLaneRequest(userMessage="hello there")
        serialized = json.dumps(self._build_input(request))
        self.assertNotIn("Canonical Active Focus context is relevant", serialized)

    def test_low_confidence_hint_is_rejected_by_backend_contract(self):
        with self.assertRaises(ValidationError):
            conversation_lane.ConversationLaneRequest(
                userMessage="hello there",
                ownershipHint={
                    "source": "agent-shadow",
                    "turnOwner": "general_chat",
                    "focusRelevant": False,
                    "confidence": 0.89,
                    "turnId": "shadow-low",
                },
            )

    def test_contradictory_owner_and_focus_relevance_is_rejected(self):
        with self.assertRaises(ValidationError):
            conversation_lane.ConversationLaneRequest(
                userMessage="hello there",
                ownershipHint={
                    "source": "agent-shadow",
                    "turnOwner": "general_chat",
                    "focusRelevant": True,
                    "confidence": 0.95,
                    "turnId": "shadow-bad",
                },
            )

    def test_frontend_only_promotes_conversation_disposition(self):
        self.assertIn(
            "if (decision.disposition !== 'conversation') return null;",
            OBSERVER_SOURCE,
        )
        self.assertIn(
            "if (decision.confidence < CONVERSATION_OWNERSHIP_MIN_CONFIDENCE) return null;",
            OBSERVER_SOURCE,
        )
        self.assertIn("decision.turnOwner === 'general_chat'", OBSERVER_SOURCE)
        self.assertIn("decision.turnOwner === 'focus'", OBSERVER_SOURCE)

    def test_frontend_reuses_pre_route_shadow_turn_for_conversation(self):
        self.assertIn("resolvePromotedConversationOwnership", APP_SOURCE)
        self.assertIn("shadowTurn,\n      activeFocusId,", APP_SOURCE)
        self.assertIn("ownershipHint,\n      voiceOutputEnabled,", APP_SOURCE)
        self.assertIn("ownershipHint: options.ownershipHint ?? null", CONVERSATION_CLIENT_SOURCE)

    def test_promotion_wait_is_bounded_and_falls_back(self):
        self.assertIn("CONVERSATION_OWNERSHIP_WAIT_MS = 900", OBSERVER_SOURCE)
        self.assertIn("Promise.race", OBSERVER_SOURCE)
        self.assertIn(
            "Conversation heuristics remain authoritative.",
            OBSERVER_SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
