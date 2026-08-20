from __future__ import annotations

import unittest
from unittest.mock import patch

from app import tool_continuation as continuation


class ToolContinuationIsolatedCapabilityHistoryPhase21G3B2Tests(unittest.TestCase):
    def _request(
        self,
        *,
        capability: str,
        user_message: str,
        tool_result: str,
    ) -> continuation.ToolContinuationRequest:
        return continuation.ToolContinuationRequest(
            userMessage=user_message,
            capability=capability,
            action="edit-last-event" if capability == "calendar" else "run-search",
            toolResult=tool_result,
            toolContext="qmeetCalendarWriteVerified=true"
            if capability == "calendar"
            else "qmeetSearchResultVerified=true",
            verified=True,
            success=True,
            verificationSource="frontend-deterministic-command",
            recentConversation=[
                continuation.ContinuationMessage(
                    role="tool",
                    content="Saved task: Prepare for meeting.",
                ),
                continuation.ContinuationMessage(
                    role="assistant",
                    content='The task "Prepare for meeting" has been saved globally.',
                ),
            ],
        )

    def test_calendar_continuation_excludes_stale_task_tool_card(self) -> None:
        request = self._request(
            capability="calendar",
            user_message=(
                "move my Project Meeting to August 23 and add a task "
                "called Prepare for meeting"
            ),
            tool_result=(
                "Updated Google Calendar event Sunday, August 23, 2026 "
                "at 3:00 PM: Project Meeting."
            ),
        )

        with patch.object(
            continuation,
            "active_focus_snapshot",
            return_value=None,
        ):
            messages = continuation.build_tool_continuation_input(request)

        combined = "\n".join(message["content"] for message in messages)
        self.assertNotIn("Previously displayed QMeet tool update", combined)
        self.assertNotIn("Saved task: Prepare for meeting.", combined)
        self.assertNotIn(
            'The task "Prepare for meeting" has been saved globally.',
            combined,
        )
        self.assertIn(request.userMessage, combined)
        self.assertIn(request.toolResult, combined)

    def test_search_continuation_excludes_stale_cross_capability_tool_cards(self) -> None:
        request = self._request(
            capability="search",
            user_message="search Framework Laptop reviews",
            tool_result="Search complete.",
        )

        with patch.object(
            continuation,
            "active_focus_snapshot",
            return_value=None,
        ):
            messages = continuation.build_tool_continuation_input(request)

        combined = "\n".join(message["content"] for message in messages)
        self.assertNotIn("Previously displayed QMeet tool update", combined)
        self.assertNotIn("Saved task: Prepare for meeting.", combined)

    def test_general_nonisolated_continuation_keeps_recent_history_behavior(self) -> None:
        request = continuation.ToolContinuationRequest(
            userMessage="read my notes",
            capability="notes",
            action="read-notes",
            toolResult="Saved notes: 1.",
            toolContext="qmeetScope=notes",
            verified=True,
            success=True,
            verificationSource="frontend-deterministic-command",
            recentConversation=[
                continuation.ContinuationMessage(
                    role="assistant",
                    content="Earlier relevant note discussion.",
                ),
            ],
        )

        with patch.object(
            continuation,
            "active_focus_snapshot",
            return_value=None,
        ):
            messages = continuation.build_tool_continuation_input(request)

        combined = "\n".join(message["content"] for message in messages)
        self.assertIn("Earlier relevant note discussion.", combined)

    def test_prompt_forbids_current_state_claims_from_older_history(self) -> None:
        self.assertIn(
            "do not claim that a task, note, Calendar event, or other state "
            "is currently present",
            continuation.TOOL_CONTINUATION_PROMPT,
        )
        self.assertIn(
            "Only the current verifiedToolReceipt/current verifiedToolContext "
            "may establish state",
            continuation.TOOL_CONTINUATION_PROMPT,
        )


if __name__ == "__main__":
    unittest.main()
