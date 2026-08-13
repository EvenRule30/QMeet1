from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app import conversation_lane


FOCUS = {
    "focusId": "focus-test",
    "title": "client problem presentation",
    "objective": "move to gathering sources and evidence",
    "deliverable": "",
    "subject": "",
    "requirements": [],
    "constraints": [],
    "preferences": [],
    "decisions": [],
    "knownFacts": [],
    "nextAction": "",
    "pendingQuestion": {
        "target": "decision",
        "question": "Should the problem statement include the customer's motivation?",
    },
    "status": "clarifying",
}


class ConversationLaneCompatibilitySeamPhase21BTests(unittest.TestCase):
    def test_legacy_developer_context_patch_seam_remains_available(self) -> None:
        self.assertTrue(
            hasattr(conversation_lane, "_developer_contexts_for_message")
        )

        request = conversation_lane.ConversationLaneRequest(
            userMessage="hello there"
        )
        with patch.object(
            conversation_lane,
            "_developer_contexts_for_message",
            return_value=[{"role": "developer", "content": "PATCHED SYSTEM"}],
        ), patch.object(
            conversation_lane,
            "active_focus_snapshot",
            return_value=FOCUS,
        ):
            messages = conversation_lane.build_conversation_lane_input(request)

        self.assertEqual(messages[0]["content"], "PATCHED SYSTEM")
        self.assertFalse(
            any(
                "Canonical Active Focus context" in str(message.get("content", ""))
                for message in messages
            )
        )

    def test_request_aware_focus_filtering_still_runs_through_compat_seam(self) -> None:
        request = conversation_lane.ConversationLaneRequest(
            userMessage="let's continue with the focus",
            ownershipHint={
                "source": "agent-shadow",
                "turnOwner": "focus",
                "focusRelevant": True,
                "confidence": 0.95,
                "turnId": "shadow-focus",
            },
        )
        developer_contexts = [
            {"role": "developer", "content": "SYSTEM"},
            {"role": "developer", "content": "CALENDAR CONTEXT"},
            {"role": "developer", "content": "PLANNER CONTEXT"},
        ]

        with patch.object(
            conversation_lane,
            "_developer_contexts_for_message",
            return_value=developer_contexts,
        ), patch.object(
            conversation_lane,
            "active_focus_snapshot",
            return_value=FOCUS,
        ):
            messages = conversation_lane.build_conversation_lane_input(request)

        contents = [str(message.get("content", "")) for message in messages]
        self.assertTrue(any(content == "SYSTEM" for content in contents))
        self.assertFalse(any("CALENDAR CONTEXT" in content for content in contents))
        self.assertFalse(any("PLANNER CONTEXT" in content for content in contents))

        focus_context = next(
            content
            for content in contents
            if "Canonical Active Focus context" in content
        )
        self.assertIn("move to gathering sources and evidence", focus_context)

        payload_text = focus_context.rsplit("\n\n", 1)[-1]
        payload = json.loads(payload_text)
        self.assertEqual(payload["focusId"], "focus-test")
        self.assertEqual(
            payload["objective"],
            "move to gathering sources and evidence",
        )
        self.assertEqual(
            payload["primaryDirection"],
            "move to gathering sources and evidence",
        )
        self.assertIsNone(payload["pendingQuestion"])


if __name__ == "__main__":
    unittest.main()
