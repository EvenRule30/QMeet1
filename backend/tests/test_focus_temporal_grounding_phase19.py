from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.focus.models import FocusState, ResponseIntent, TurnPlan, TurnRoute
from app.focus.planner import (
    _compact_recent_event_payload,
    _current_time_context,
    _planner_input,
    _planner_system_prompt,
)
from app.focus.response import (
    _has_stale_prospective_same_day_claim,
    build_response_candidate,
    compose_response_candidate,
)


class FocusTemporalGroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(
            2026,
            7,
            29,
            17,
            31,
            tzinfo=timezone(timedelta(hours=-7), name="PDT"),
        )

    def test_current_time_context_exposes_authoritative_local_clock(self) -> None:
        context = _current_time_context(self.now)

        self.assertEqual(context["localIso"], "2026-07-29T17:31:00-07:00")
        self.assertEqual(context["localDate"], "2026-07-29")
        self.assertEqual(context["localTime"], "17:31:00")
        self.assertEqual(context["timezone"], "PDT")
        self.assertEqual(context["utcOffset"], "-07:00")

    def test_planner_input_includes_mode_and_current_time(self) -> None:
        with (
            patch.dict(os.environ, {"QMEET_FOCUS_MODE": "shadow"}, clear=False),
            patch("app.focus.planner._local_now", return_value=self.now),
            patch("app.focus.planner._recent_event_summary", return_value=[]),
        ):
            payload = json.loads(
                _planner_input(
                    source="chat-request-shadow",
                    message="What should I review first?",
                    state=FocusState(),
                )
            )

        self.assertEqual(payload["plannerMode"], "shadow")
        self.assertEqual(payload["currentTime"]["localIso"], "2026-07-29T17:31:00-07:00")
        self.assertEqual(payload["currentTime"]["utcOffset"], "-07:00")

    def test_verified_calendar_tool_evidence_survives_recent_event_compaction(self) -> None:
        payload = _compact_recent_event_payload(
            "response_candidate",
            {
                "text": "Calendar read complete for today.",
                "stage": "tool_result",
                "eligibility": {"eligible": True, "reasons": []},
                "toolEvidence": {
                    "tool": "calendar_read",
                    "success": True,
                    "calendarView": "today",
                    "eventCount": 1,
                    "events": [
                        {
                            "title": "Work meeting",
                            "time": "3:00 PM",
                            "start": "2026-07-29T15:00:00-07:00",
                        }
                    ],
                },
            },
        )

        self.assertEqual(payload["stage"], "tool_result")
        self.assertEqual(payload["toolEvidence"]["tool"], "calendar_read")
        self.assertTrue(payload["toolEvidence"]["success"])

    def test_system_prompt_describes_configured_runtime_mode(self) -> None:
        with patch.dict(os.environ, {"QMEET_FOCUS_MODE": "active"}, clear=False):
            active_prompt = _planner_system_prompt()
        with patch.dict(os.environ, {"QMEET_FOCUS_MODE": "shadow"}, clear=False):
            shadow_prompt = _planner_system_prompt()

        self.assertIn("active planner mode", active_prompt)
        self.assertNotIn("currently in shadow planner mode", active_prompt)
        self.assertIn("shadow planner mode", shadow_prompt)

    def test_stale_same_day_meeting_is_repaired_into_safe_takeover(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.RESPOND,
            responseIntent=ResponseIntent(
                answerDirectly=True,
                attachToFocus=True,
                guidance=(
                    "The first thing you should review is your scheduled calendar "
                    "event for today: your work meeting at 3:00 PM. Start by "
                    "confirming the agenda."
                ),
            ),
            confidence=0.99,
            reason="Answer the meeting-preparation question directly.",
        )

        with patch("app.focus.response._local_now", return_value=self.now):
            candidate = build_response_candidate(plan)
            visible_text = compose_response_candidate(plan)

        self.assertTrue(candidate["text"])
        self.assertEqual(candidate["text"], visible_text)
        self.assertTrue(candidate["eligibility"]["eligible"])
        self.assertEqual(candidate["eligibility"]["reasons"], [])
        self.assertNotIn("3:00 PM", visible_text)
        self.assertNotIn("work meeting", visible_text.casefold())
        self.assertIn("agenda", visible_text.casefold())
        self.assertIn(
            "replaced_stale_prospective_event_with_grounded_meeting_guidance",
            candidate["repairs"],
        )

    def test_smoke_test_wording_without_today_is_repaired(self) -> None:
        plan = TurnPlan(
            route=TurnRoute.RESPOND,
            responseIntent=ResponseIntent(
                answerDirectly=True,
                attachToFocus=True,
                guidance=(
                    "To start your meeting preparation, review your calendar "
                    "event details for the 3:00 PM work meeting—look at the "
                    "agenda, attendee list, and any materials or notes you have "
                    "from previous meetings. Reviewing these will give you a "
                    "strong foundation for focused preparation."
                ),
                askQuestion=(
                    "Is there a specific topic you want to address in your "
                    "3:00 PM work meeting?"
                ),
            ),
            confidence=0.99,
            reason="Answer the meeting-preparation question directly.",
        )
        smoke_test_now = datetime(
            2026,
            7,
            29,
            18,
            10,
            tzinfo=timezone(timedelta(hours=-7), name="PDT"),
        )

        with patch("app.focus.response._local_now", return_value=smoke_test_now):
            candidate = build_response_candidate(plan)
            visible_text = compose_response_candidate(plan)

        self.assertTrue(candidate["eligibility"]["eligible"])
        self.assertEqual(candidate["eligibility"]["reasons"], [])
        self.assertEqual(candidate["text"], visible_text)
        self.assertNotIn("3:00 PM", visible_text)
        self.assertNotIn("work meeting", visible_text.casefold())
        self.assertNotIn("specific topic", visible_text.casefold())
        self.assertIn("agenda", visible_text.casefold())

    def test_future_same_day_meeting_remains_eligible(self) -> None:
        text = (
            "Your next scheduled event today is at 6:00 PM. "
            "Start by confirming the agenda."
        )
        self.assertFalse(
            _has_stale_prospective_same_day_claim(text, now=self.now)
        )

    def test_explicit_tomorrow_meeting_remains_eligible(self) -> None:
        text = (
            "Start by reviewing the agenda for tomorrow's 3:00 PM meeting."
        )
        self.assertFalse(
            _has_stale_prospective_same_day_claim(text, now=self.now)
        )

    def test_explicit_calendar_date_meeting_remains_eligible(self) -> None:
        text = (
            "Start by reviewing the agenda for the August 3 3:00 PM meeting."
        )
        self.assertFalse(
            _has_stale_prospective_same_day_claim(text, now=self.now)
        )

    def test_explicitly_past_meeting_wording_remains_eligible(self) -> None:
        text = (
            "Review notes from today's 3:00 PM meeting, which already ended, "
            "and identify the follow-up decisions."
        )
        self.assertFalse(
            _has_stale_prospective_same_day_claim(text, now=self.now)
        )


if __name__ == "__main__":
    unittest.main()
