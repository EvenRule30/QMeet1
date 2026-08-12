from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app import conversation_lane
from app import tool_continuation


FOCUS_WITH_OBJECTIVE = {
    "focusId": "focus-test",
    "title": "client problem presentation",
    "objective": "move to gathering sources and evidence",
    "deliverable": "",
    "subject": "",
    "requirements": [],
    "constraints": [],
    "preferences": [],
    "decisions": [],
    "knownFacts": ["customer wants to get healthier"],
    "milestones": [],
    "completedMilestones": [],
    "nextAction": "",
    "pendingQuestion": {
        "target": "decision",
        "question": "Should the problem statement include the customer's motivation to get healthier?",
    },
    "status": "clarifying",
}


class FocusResponseContextPriorityPhase21BTests(unittest.TestCase):
    def _focus_hint(self) -> conversation_lane.ConversationOwnershipHint:
        return conversation_lane.ConversationOwnershipHint(
            source="agent-shadow",
            turnOwner="focus",
            focusRelevant=True,
            confidence=0.95,
            turnId="shadow-test",
        )

    def test_promoted_focus_conversation_excludes_generic_planner_contexts(self) -> None:
        request = conversation_lane.ConversationLaneRequest(
            userMessage="let's continue with the focus",
            recentConversation=[],
            ownershipHint=self._focus_hint(),
        )
        fake_developer_contexts = [
            {"role": "developer", "content": "SYSTEM"},
            {"role": "developer", "content": "CALENDAR CONTEXT: calendar looks open"},
            {"role": "developer", "content": "PLANNER CONTEXT: start with best next move"},
        ]

        with patch.object(
            conversation_lane,
            "_build_chat_input_messages",
            return_value=fake_developer_contexts,
        ), patch.object(
            conversation_lane,
            "active_focus_snapshot",
            return_value=FOCUS_WITH_OBJECTIVE,
        ):
            messages = conversation_lane.build_conversation_lane_input(request)

        serialized = json.dumps(messages)
        self.assertNotIn("CALENDAR CONTEXT", serialized)
        self.assertNotIn("PLANNER CONTEXT", serialized)
        self.assertIn("SYSTEM", serialized)

    def test_promoted_focus_conversation_uses_objective_as_primary_direction(self) -> None:
        request = conversation_lane.ConversationLaneRequest(
            userMessage="let's continue with the focus",
            recentConversation=[],
            ownershipHint=self._focus_hint(),
        )

        with patch.object(
            conversation_lane,
            "_build_chat_input_messages",
            return_value=[{"role": "developer", "content": "SYSTEM"}],
        ), patch.object(
            conversation_lane,
            "active_focus_snapshot",
            return_value=FOCUS_WITH_OBJECTIVE,
        ):
            messages = conversation_lane.build_conversation_lane_input(request)

        focus_context_message = next(
            item["content"]
            for item in messages
            if item["role"] == "developer"
            and "Canonical Active Focus context" in item["content"]
        )
        payload = json.loads(focus_context_message.split("\n\n", 1)[1])
        self.assertEqual(
            payload["primaryDirection"],
            "move to gathering sources and evidence",
        )
        self.assertIsNone(payload["pendingQuestion"])
        self.assertNotIn("Should the problem statement include", focus_context_message)

    def test_focus_without_objective_can_still_expose_onboarding_question(self) -> None:
        focus = dict(FOCUS_WITH_OBJECTIVE)
        focus["objective"] = ""
        request = conversation_lane.ConversationLaneRequest(
            userMessage="let's continue with the focus",
            recentConversation=[],
            ownershipHint=self._focus_hint(),
        )

        with patch.object(
            conversation_lane,
            "_build_chat_input_messages",
            return_value=[{"role": "developer", "content": "SYSTEM"}],
        ), patch.object(conversation_lane, "active_focus_snapshot", return_value=focus):
            messages = conversation_lane.build_conversation_lane_input(request)

        serialized = json.dumps(messages)
        self.assertIn("Should the problem statement include", serialized)

    def test_focus_tool_continuation_suppresses_old_pending_question_when_objective_exists(self) -> None:
        request = tool_continuation.ToolContinuationRequest(
            userMessage="goal: move to gathering sources and evidence",
            capability="focus",
            action="update-focus-session",
            toolResult="Focus goal already matches: move to gathering sources and evidence.",
            verified=True,
            success=True,
            verificationSource="phase21b-test",
        )

        with patch.object(
            tool_continuation,
            "active_focus_snapshot",
            return_value=FOCUS_WITH_OBJECTIVE,
        ):
            messages = tool_continuation.build_tool_continuation_input(request)

        payload_text = messages[-1]["content"].split("\n\n", 1)[1]
        payload = json.loads(payload_text)
        focus = payload["activeFocusAdvisoryContext"]
        self.assertEqual(
            focus["primaryDirection"],
            "move to gathering sources and evidence",
        )
        self.assertIsNone(focus["pendingQuestion"])

    def test_focus_tool_continuation_preserves_pending_question_before_goal_exists(self) -> None:
        focus_without_objective = dict(FOCUS_WITH_OBJECTIVE)
        focus_without_objective["objective"] = ""
        request = tool_continuation.ToolContinuationRequest(
            userMessage="Start a Focus: client problem presentation",
            capability="focus",
            action="start-focus-session",
            toolResult="Started Focus: client problem presentation.",
            verified=True,
            success=True,
            verificationSource="phase21b-test",
        )

        with patch.object(
            tool_continuation,
            "active_focus_snapshot",
            return_value=focus_without_objective,
        ):
            messages = tool_continuation.build_tool_continuation_input(request)

        payload_text = messages[-1]["content"].split("\n\n", 1)[1]
        payload = json.loads(payload_text)
        self.assertIsNotNone(payload["activeFocusAdvisoryContext"]["pendingQuestion"])


if __name__ == "__main__":
    unittest.main()
