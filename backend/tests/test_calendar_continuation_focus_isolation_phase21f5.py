from __future__ import annotations

import unittest
from unittest.mock import patch

from app.tool_continuation import (
    ToolContinuationRequest,
    build_tool_continuation_input,
    focus_context_relevant_to_continuation,
)


def _focus() -> dict:
    return {
        "focusId": "focus-1",
        "title": "Prepare presentation",
        "objective": "Prepare the project review presentation",
        "deliverable": "",
        "subject": "",
        "requirements": [],
        "constraints": [],
        "preferences": [],
        "decisions": [],
        "knownFacts": ["Review project progress"],
        "milestones": [],
        "completedMilestones": [],
        "nextAction": "",
        "pendingQuestion": None,
        "status": "active",
    }


def _calendar_request(user_message: str) -> ToolContinuationRequest:
    return ToolContinuationRequest(
        userMessage=user_message,
        capability="calendar",
        action="edit-last-event",
        toolResult=(
            "Updated Google Calendar event Saturday, August 29, 2026 "
            "at 4:00 PM: Final Project Review."
        ),
        toolContext=(
            "qmeetScope=calendar. qmeetCalendarWriteVerified=true. "
            "verifiedEventDate=2026-08-29. "
            "verifiedEventTime=4:00 PM. "
            'verifiedEventTitle="Final Project Review".'
        ),
        verified=True,
        success=True,
        verificationSource="deterministic-tool",
        recentConversation=[],
        uiContext={},
    )


class CalendarContinuationFocusIsolationPhase21F5Tests(unittest.TestCase):
    def test_calendar_title_overlap_does_not_attach_unrelated_focus(self) -> None:
        request = _calendar_request(
            "rename my 4 PM Project Review August 29 to Final Project Review"
        )

        self.assertFalse(
            focus_context_relevant_to_continuation(request, _focus())
        )

    def test_calendar_relational_phrase_can_attach_matching_focus(self) -> None:
        request = _calendar_request(
            "add practice time for my project review presentation tomorrow at 2"
        )

        self.assertTrue(
            focus_context_relevant_to_continuation(request, _focus())
        )

    def test_calendar_explicit_focus_reference_can_attach_focus(self) -> None:
        request = _calendar_request(
            "rename the 4 PM meeting for my focus to Final Project Review"
        )

        self.assertTrue(
            focus_context_relevant_to_continuation(request, _focus())
        )

    def test_calendar_input_excludes_focus_when_only_title_tokens_overlap(self) -> None:
        request = _calendar_request(
            "rename my 4 PM Project Review August 29 to Final Project Review"
        )

        with patch(
            "app.tool_continuation.active_focus_snapshot",
            return_value=_focus(),
        ):
            messages = build_tool_continuation_input(request)

        final_payload = messages[-1]["content"]
        self.assertIn('"focusContextIncluded": false', final_payload)
        self.assertIn('"activeFocusAdvisoryContext": null', final_payload)
        self.assertIn("verifiedEventDate=2026-08-29.", final_payload)

    def test_calendar_input_can_include_focus_when_user_explicitly_connects_it(self) -> None:
        request = _calendar_request(
            "rename the 4 PM meeting for my focus to Final Project Review"
        )

        with patch(
            "app.tool_continuation.active_focus_snapshot",
            return_value=_focus(),
        ):
            messages = build_tool_continuation_input(request)

        final_payload = messages[-1]["content"]
        self.assertIn('"focusContextIncluded": true', final_payload)
        self.assertIn('"activeFocusAdvisoryContext": {', final_payload)


if __name__ == "__main__":
    unittest.main()
