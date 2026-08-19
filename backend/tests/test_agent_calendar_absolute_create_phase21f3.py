from __future__ import annotations

from datetime import date, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app import qmeet_agent_shadow as shadow
from app.calendar_absolute_create_service import (
    CalendarIntegrationError,
    create_calendar_event_on_date,
    parse_calendar_absolute_date,
)
from app.calendar_read_date_interpreter import (
    apply_calendar_absolute_create_ownership_floor,
)
from app.calendar_service import CalendarConfig
from app.main import app


ROOT = Path(__file__).resolve().parents[2]
FIXED_PACIFIC_SUMMER_TIME = timezone(timedelta(hours=-7))


class AgentCalendarAbsoluteCreatePhase21F3Tests(unittest.TestCase):
    def _decision(
        self,
        *,
        title: str = "Meeting",
        time_value: str | None = None,
    ) -> shadow.AgentShadowDecision:
        return shadow.AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="add-calendar-event",
            proposedArguments={
                "day": "tomorrow",
                "title": title,
                "time": time_value,
            },
            responsePlan="Create the event.",
            confidence=0.93,
            reason="Legacy today/tomorrow create proposal.",
        )

    def test_next_friday_create_becomes_one_absolute_date(self) -> None:
        result = apply_calendar_absolute_create_ownership_floor(
            "schedule a meeting next Friday at 2 PM",
            self._decision(time_value=None),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.turnOwner, "calendar")
        self.assertEqual(result.proposedAction, "add-calendar-event")
        self.assertEqual(
            result.proposedArguments,
            {
                "date": "2026-08-28",
                "title": "Meeting",
                "time": "2 PM",
            },
        )
        self.assertIn("absolute date", result.reason)

    def test_farther_date_create_without_time_stays_all_day_proposal(self) -> None:
        result = apply_calendar_absolute_create_ownership_floor(
            "schedule a meeting next Friday",
            self._decision(time_value=None),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.proposedArguments["date"], "2026-08-28")
        self.assertEqual(result.proposedArguments["title"], "Meeting")
        self.assertIsNone(result.proposedArguments["time"])

    def test_create_floor_can_repair_old_metadata_and_extract_basic_title(self) -> None:
        decision = shadow.AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Reply conversationally.",
            confidence=0.65,
            reason="Old model did not promote farther-date create.",
        )
        result = apply_calendar_absolute_create_ownership_floor(
            "schedule a dentist appointment August 27 at 10 AM",
            decision,
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.turnOwner, "calendar")
        self.assertEqual(result.disposition, "tool")
        self.assertEqual(result.proposedAction, "add-calendar-event")
        self.assertEqual(result.proposedArguments["date"], "2026-08-27")
        self.assertEqual(result.proposedArguments["title"], "dentist appointment")
        self.assertEqual(result.proposedArguments["time"], "10 AM")

    def test_date_range_cannot_preserve_poisoned_single_day_model_proposal(self) -> None:
        poisoned = self._decision(time_value="2 PM")
        self.assertEqual(poisoned.proposedArguments["day"], "tomorrow")

        result = apply_calendar_absolute_create_ownership_floor(
            "schedule a meeting next week",
            poisoned,
            reference_date=date(2026, 8, 19),
        )

        self.assertIsNot(result, poisoned)
        self.assertEqual(result.turnOwner, "calendar")
        self.assertEqual(result.disposition, "tool")
        self.assertEqual(result.proposedAction, "add-calendar-event")
        self.assertEqual(
            result.proposedArguments,
            {
                "startDate": "2026-08-24",
                "endDate": "2026-08-30",
            },
        )
        self.assertNotIn("day", result.proposedArguments)
        self.assertNotIn("time", result.proposedArguments)
        self.assertIn("multi-day", result.reason)
        self.assertIn("one specific date", result.responsePlan)

    def test_range_guard_stays_non_executable_in_frontend_create_schema(self) -> None:
        promotion = (
            ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "const legacyShape = hasExactlyKeys(argumentsValue, ['day', 'title', 'time'])",
            promotion,
        )
        self.assertIn(
            "const absoluteShape = hasExactlyKeys(argumentsValue, ['date', 'title', 'time'])",
            promotion,
        )
        self.assertNotIn(
            "hasExactlyKeys(argumentsValue, ['startDate', 'endDate'])",
            promotion,
        )

    def test_absolute_date_parser_rejects_invalid_calendar_dates(self) -> None:
        self.assertEqual(
            parse_calendar_absolute_date("2026-08-28").isoformat(),
            "2026-08-28",
        )
        with self.assertRaises(CalendarIntegrationError):
            parse_calendar_absolute_date("2026-02-30")
        with self.assertRaises(CalendarIntegrationError):
            parse_calendar_absolute_date("August 28 2026")

    @patch("app.calendar_absolute_create_service._normalize_google_event")
    @patch("app.calendar_absolute_create_service.build")
    @patch("app.calendar_absolute_create_service._load_credentials")
    @patch("app.calendar_absolute_create_service.get_calendar_status")
    @patch("app.calendar_absolute_create_service.get_calendar_config")
    @patch(
        "app.calendar_absolute_create_service._get_timezone",
        return_value=FIXED_PACIFIC_SUMMER_TIME,
    )
    @patch(
        "app.calendar_service._get_timezone",
        return_value=FIXED_PACIFIC_SUMMER_TIME,
    )
    def test_backend_create_uses_exact_absolute_date_and_existing_time_semantics(
        self,
        _calendar_timezone,
        _absolute_timezone,
        get_config,
        get_status,
        load_credentials,
        build_google,
        normalize_event,
    ) -> None:
        config = CalendarConfig(
            enabled=True,
            credentials_file=Path("google_credentials.json"),
            token_file=Path("token_calendar_events.json"),
            auth_state_file=Path("calendar_auth_state.json"),
            redirect_uri="http://localhost:8000/api/calendar/auth/callback",
            calendar_id="primary",
            timezone_name="America/Los_Angeles",
            write_enabled=True,
        )
        get_config.return_value = config
        get_status.return_value = {
            "configured": True,
            "connected": True,
        }
        credentials = object()
        load_credentials.return_value = credentials

        created_payload = {
            "id": "evt-1",
            "summary": "Meeting",
            "start": {"dateTime": "2026-08-28T14:00:00-07:00"},
            "end": {"dateTime": "2026-08-28T15:00:00-07:00"},
        }
        execute = Mock(return_value=created_payload)
        insert_call = Mock()
        insert_call.execute = execute
        events_api = Mock()
        events_api.insert.return_value = insert_call
        service = Mock()
        service.events.return_value = events_api
        build_google.return_value = service
        normalize_event.return_value = {
            "id": "google-evt-1",
            "title": "Meeting",
            "dateKey": "2026-08-28",
            "time": "2:00 PM",
            "createdAt": "2026-08-19T14:00:00-07:00",
            "source": "google",
        }

        result = create_calendar_event_on_date(
            title="Meeting",
            date_key="2026-08-28",
            time="2 PM",
        )

        build_google.assert_called_once_with(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
        events_api.insert.assert_called_once_with(
            calendarId="primary",
            body={
                "summary": "Meeting",
                "start": {
                    "dateTime": "2026-08-28T14:00:00-07:00",
                    "timeZone": "America/Los_Angeles",
                },
                "end": {
                    "dateTime": "2026-08-28T15:00:00-07:00",
                    "timeZone": "America/Los_Angeles",
                },
            },
        )
        self.assertEqual(result["event"]["dateKey"], "2026-08-28")

    def test_real_fastapi_app_exposes_absolute_create_and_legacy_create(self) -> None:
        paths = app.openapi().get("paths", {})
        self.assertIn("/api/calendar/events", paths)
        self.assertIn("post", paths["/api/calendar/events"])
        self.assertIn("/api/calendar/events/absolute", paths)
        self.assertIn("post", paths["/api/calendar/events/absolute"])

    def test_frontend_promotion_and_confirmation_round_trip_are_absolute_date_aware(self) -> None:
        promotion = (
            ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
        ).read_text(encoding="utf-8")
        commands = (ROOT / "src" / "app" / "commands.ts").read_text(
            encoding="utf-8"
        )
        handler = (
            ROOT / "src" / "app" / "commandHandlers" / "calendar.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("hasExactlyKeys(argumentsValue, ['date', 'title', 'time'])", promotion)
        self.assertIn("isCanonicalCalendarDateKey(rawDate)", promotion)
        self.assertIn("day: CalendarCommandDay", promotion)
        self.assertIn("export type CalendarCommandDay", commands)
        self.assertIn("isAbsoluteCalendarCommandDay", commands)
        self.assertIn("Phase 21F3 confirmation round-trip", commands)
        self.assertIn("createCalendarEventOnDate", handler)
        self.assertIn("isCanonicalCalendarDateKey(targetDay)", handler)
        self.assertIn("Do not open the today/tomorrow Calendar panel", handler)

    def test_router_applies_create_floor_before_range_read_floor(self) -> None:
        source = (
            ROOT / "backend" / "app" / "routers" / "agent_shadow.py"
        ).read_text(encoding="utf-8")
        create_index = source.index("apply_calendar_absolute_create_ownership_floor(")
        read_index = source.index("apply_calendar_range_read_ownership_floor(")
        self.assertLess(create_index, read_index)


if __name__ == "__main__":
    unittest.main()
