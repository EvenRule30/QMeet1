from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.conversation_lane import (
    CONVERSATION_LANE_PROMPT,
    ConversationLaneRequest,
    build_conversation_lane_input,
)
from app.tool_continuation import TOOL_CONTINUATION_PROMPT


REPO_ROOT = Path(__file__).resolve().parents[2]


class Phase21AConversationQualityTests(unittest.TestCase):
    def _read(self, relative_path: str) -> str:
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    @staticmethod
    def _focus_snapshot() -> dict:
        return {
            "focusId": "focus-presentation",
            "title": "prepare for a client presentation",
            "objective": "clearly show the progress of my app",
            "deliverable": "",
            "subject": "",
            "requirements": [],
            "constraints": [],
            "preferences": ["concise answers"],
            "decisions": [],
            "knownFacts": ["the presentation is for a contractor"],
            "milestones": [],
            "completedMilestones": [],
            "nextAction": "",
            "pendingQuestion": {
                "target": "audience",
                "question": "Who is the presentation for?",
            },
            "status": "clarifying",
        }

    def test_unrelated_general_question_does_not_receive_canonical_focus(self):
        request = ConversationLaneRequest(
            userMessage="why is the sky blue?",
            recentConversation=[
                {
                    "role": "assistant",
                    "content": "We were working on your presentation.",
                }
            ],
            uiContext={"activePanel": "none"},
        )
        with (
            patch("app.conversation_lane.active_focus_snapshot", return_value=self._focus_snapshot()),
            patch(
                "app.conversation_lane._developer_contexts_for_message",
                return_value=[{"role": "developer", "content": "base-system"}],
            ),
        ):
            messages = build_conversation_lane_input(request)

        serialized = "\n".join(message["content"] for message in messages)
        self.assertNotIn("Canonical Active Focus context is relevant", serialized)
        self.assertIn("why is the sky blue?", serialized)

    def test_explicit_focus_turn_can_receive_canonical_focus_advisory_context(self):
        request = ConversationLaneRequest(
            userMessage="give me key points for my client presentation focus",
            recentConversation=[],
            uiContext={"activePanel": "none"},
        )
        with (
            patch("app.conversation_lane.active_focus_snapshot", return_value=self._focus_snapshot()),
            patch(
                "app.conversation_lane._developer_contexts_for_message",
                return_value=[{"role": "developer", "content": "base-system"}],
            ),
        ):
            messages = build_conversation_lane_input(request)

        serialized = "\n".join(message["content"] for message in messages)
        self.assertIn("Canonical Active Focus context is relevant", serialized)
        self.assertIn("clearly show the progress of my app", serialized)

    def test_conversation_policy_is_help_first_and_focus_is_not_universal_owner(self):
        lowered = CONVERSATION_LANE_PROMPT.casefold()
        self.assertIn("turn ownership comes first", lowered)
        self.assertIn("active focus is optional context", lowered)
        self.assertIn("help first", lowered)
        self.assertIn("do not repeat", lowered)
        self.assertIn("ask at most one follow-up question", lowered)
        self.assertIn("self-contained greeting", lowered)

    def test_tool_continuation_policy_does_not_replay_pending_question(self):
        lowered = TOOL_CONTINUATION_PROMPT.casefold()
        self.assertIn("help first", lowered)
        self.assertIn("do not repeat", lowered)
        self.assertIn("pending focus coaching question is advisory context only", lowered)
        self.assertIn("after a read-only request", lowered)

    def test_visible_automatic_focus_onboarding_bridge_is_no_longer_mounted(self):
        source = self._read("src/main.tsx")
        self.assertNotIn("FocusConversationBridge", source)
        self.assertIn("WorkContextMemoryBridge", source)
        self.assertIn("installQMeetFocusTurnHeaders", source)

    def test_conversation_route_preserves_work_context_routes_but_bypasses_legacy_wrapper(self):
        source = self._read("backend/app/routers/chat.py")
        self.assertIn('@router.get("/work-context")', source)
        self.assertIn('@router.delete("/work-context")', source)
        self.assertIn('@router.post("/chat/conversation/stream")', source)
        conversation_section = source.split('@router.post("/chat/conversation/stream")', 1)[1]
        conversation_section = conversation_section.split('@router.post("/reset")', 1)[0]
        self.assertIn("stream_conversation_lane", conversation_section)
        self.assertNotIn("prepare_background_chat_message", conversation_section)
        self.assertNotIn("record_background_assistant_reply", conversation_section)

    def test_conversation_route_is_outside_legacy_focus_observation_paths(self):
        background_source = self._read("backend/app/background_context_middleware.py")
        focus_source = self._read("backend/app/focus/middleware.py")
        self.assertNotIn('"/api/chat/conversation/stream"', background_source)
        self.assertNotIn('"/api/chat/conversation/stream"', focus_source)

    def test_frontend_fallback_chat_uses_conversation_lane(self):
        app_source = self._read("src/app/App.tsx")
        lane_source = self._read("src/app/lib/conversationLane.ts")
        self.assertIn("sendConversationLaneMessage", app_source)
        self.assertIn("cancelActiveConversationLane", app_source)
        self.assertIn("continueAfterVerifiedToolUpdate", app_source)
        self.assertNotIn("await sendStreamingChat(messageText, visibleUserText);", app_source)
        self.assertIn("/api/chat/conversation/stream", lane_source)
        self.assertIn("recentConversation", lane_source)

    def test_current_focus_read_is_tool_card_complete(self):
        source = self._read("src/app/lib/toolContinuation.ts")
        self.assertIn("TOOL_CARD_COMPLETE_COMMANDS", source)
        self.assertIn("'read-focus-session'", source)
        self.assertIn("TOOL_CARD_COMPLETE_COMMANDS.has(command)", source)


if __name__ == "__main__":
    unittest.main()
