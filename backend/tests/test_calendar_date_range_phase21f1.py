from __future__ import annotations

from datetime import timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.calendar_range_service import (
    MAX_CALENDAR_RANGE_DAYS,
    CalendarIntegrationError,
    list_calendar_events_range,
    resolve_calendar_date_window,
)
from app.calendar_service import CalendarConfig
from app.main import app


FIXED_PACIFIC_SUMMER_TIME = timezone(timedelta(hours=-7))


class CalendarDateRangePhase21F1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = CalendarConfig(
            enabled=True,
            credentials_file=Path("google_credentials.json"),
            token_file=Path("token_calendar_events.json"),
            auth_state_file=Path("calendar_auth_state.json"),
            redirect_uri="http://localhost:8000/api/calendar/auth/callback",
            calendar_id="primary",
            timezone_name="America/Los_Angeles",
            write_enabled=True,
        )

    def _resolve_window(
        self,
        start_date: str,
        end_date: str,
    ):
        # These tests verify canonical inclusive/exclusive date-window math,
        # not the operating system's IANA timezone installation. Inject the
        # August Pacific offset so the regression is deterministic on Windows,
        # macOS, and Linux without adding a new tzdata test dependency.
        with patch(
            "app.calendar_range_service._get_timezone",
            return_value=FIXED_PACIFIC_SUMMER_TIME,
        ):
            return resolve_calendar_date_window(
                start_date,
                end_date,
                self.config,
            )

    def test_single_day_is_inclusive_with_next_midnight_api_bound(self) -> None:
        window = self._resolve_window(
            "2026-08-27",
            "2026-08-27",
        )

        self.assertEqual(window.start_date.isoformat(), "2026-08-27")
        self.assertEqual(window.end_date.isoformat(), "2026-08-27")
        self.assertEqual(window.day_count, 1)
        self.assertEqual(window.start.isoformat(), "2026-08-27T00:00:00-07:00")
        self.assertEqual(
            window.end_exclusive.isoformat(),
            "2026-08-28T00:00:00-07:00",
        )

    def test_multi_day_range_keeps_end_date_inclusive(self) -> None:
        window = self._resolve_window(
            "2026-08-27",
            "2026-08-29",
        )

        self.assertEqual(window.day_count, 3)
        self.assertEqual(window.start.date().isoformat(), "2026-08-27")
        self.assertEqual(
            window.end_exclusive.date().isoformat(),
            "2026-08-30",
        )

    def test_range_rejects_reverse_dates(self) -> None:
        with self.assertRaisesRegex(
            CalendarIntegrationError,
            "endDate cannot be before startDate",
        ):
            self._resolve_window(
                "2026-08-29",
                "2026-08-27",
            )

    def test_range_rejects_non_iso_dates(self) -> None:
        with self.assertRaisesRegex(
            CalendarIntegrationError,
            "startDate must use YYYY-MM-DD",
        ):
            self._resolve_window(
                "August 27 2026",
                "2026-08-29",
            )

    def test_range_has_bounded_read_window(self) -> None:
        with self.assertRaisesRegex(
            CalendarIntegrationError,
            f"limited to {MAX_CALENDAR_RANGE_DAYS} days",
        ):
            self._resolve_window(
                "2026-08-01",
                "2026-09-01",
            )

    @patch(
        "app.calendar_range_service._get_timezone",
        return_value=FIXED_PACIFIC_SUMMER_TIME,
    )
    @patch("app.calendar_range_service._normalize_google_event")
    @patch("app.calendar_range_service.build")
    @patch("app.calendar_range_service._load_credentials")
    @patch("app.calendar_range_service.get_calendar_status")
    @patch("app.calendar_range_service.get_calendar_config")
    def test_google_query_uses_exact_canonical_window(
        self,
        get_config,
        get_status,
        load_credentials,
        build_google,
        normalize_event,
        _get_timezone,
    ) -> None:
        get_config.return_value = self.config
        get_status.return_value = {
            "configured": True,
            "connected": True,
        }
        credentials = object()
        load_credentials.return_value = credentials

        execute = Mock(return_value={"items": [{"id": "evt-1"}]})
        list_call = Mock()
        list_call.execute = execute
        events_api = Mock()
        events_api.list.return_value = list_call
        service = Mock()
        service.events.return_value = events_api
        build_google.return_value = service
        normalize_event.return_value = {
            "id": "google-evt-1",
            "title": "Example",
            "dateKey": "2026-08-28",
            "time": "10:00 AM",
            "createdAt": "2026-08-01T00:00:00-07:00",
            "source": "google",
        }

        result = list_calendar_events_range(
            "2026-08-27",
            "2026-08-29",
        )

        build_google.assert_called_once_with(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
        events_api.list.assert_called_once_with(
            calendarId="primary",
            timeMin="2026-08-27T00:00:00-07:00",
            timeMax="2026-08-30T00:00:00-07:00",
            singleEvents=True,
            orderBy="startTime",
            maxResults=100,
        )
        self.assertEqual(result["view"], "range")
        self.assertEqual(result["startDate"], "2026-08-27")
        self.assertEqual(result["endDate"], "2026-08-29")
        self.assertEqual(len(result["events"]), 1)

    def test_real_fastapi_app_exposes_range_read_without_removing_legacy_read(self) -> None:
        paths = app.openapi().get("paths", {})
        self.assertIn("/api/calendar/events", paths)
        self.assertIn("get", paths["/api/calendar/events"])
        self.assertIn("/api/calendar/events/range", paths)
        self.assertIn("get", paths["/api/calendar/events/range"])

    @patch("app.routers.calendar.list_calendar_events_range")
    def test_range_route_preserves_absolute_date_keys(
        self,
        list_range,
    ) -> None:
        list_range.return_value = {
            "ok": True,
            "configured": True,
            "connected": True,
            "source": "google",
            "view": "range",
            "startDate": "2026-08-27",
            "endDate": "2026-08-29",
            "events": [],
            "message": "Loaded 0 Google Calendar events.",
        }
        client = TestClient(app)

        response = client.get(
            "/api/calendar/events/range",
            params={
                "startDate": "2026-08-27",
                "endDate": "2026-08-29",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["startDate"], "2026-08-27")
        self.assertEqual(response.json()["endDate"], "2026-08-29")
        list_range.assert_called_once_with(
            start_date="2026-08-27",
            end_date="2026-08-29",
        )


if __name__ == "__main__":
    unittest.main()
