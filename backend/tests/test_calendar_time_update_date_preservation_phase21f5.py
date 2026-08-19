from __future__ import annotations

from datetime import timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import calendar_service


class _Executable:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _FakeEvents:
    def __init__(self, existing):
        self.existing = existing
        self.patch_body = None

    def get(self, **_kwargs):
        return _Executable(self.existing)

    def patch(self, **kwargs):
        self.patch_body = kwargs["body"]
        updated = {
            **self.existing,
            "start": self.patch_body.get("start", self.existing["start"]),
            "end": self.patch_body.get("end", self.existing["end"]),
            "summary": self.patch_body.get(
                "summary",
                self.existing.get("summary", "Meeting"),
            ),
        }
        return _Executable(updated)


class _FakeService:
    def __init__(self, existing):
        self.events_api = _FakeEvents(existing)

    def events(self):
        return self.events_api


class CalendarTimeUpdateDatePreservationPhase21F5Tests(unittest.TestCase):
    def test_time_only_update_preserves_farther_existing_date(self) -> None:
        existing = {
            "id": "evt-1",
            "summary": "Meeting",
            "created": "2026-08-01T12:00:00Z",
            "start": {"dateTime": "2026-08-29T15:00:00-07:00"},
            "end": {"dateTime": "2026-08-29T16:00:00-07:00"},
        }
        service = _FakeService(existing)
        config = SimpleNamespace(
            calendar_id="primary",
            timezone_name="America/Los_Angeles",
            write_enabled=True,
        )
        fixed_tz = timezone(timedelta(hours=-7))

        with (
            patch.object(calendar_service, "get_calendar_config", return_value=config),
            patch.object(
                calendar_service,
                "get_calendar_status",
                return_value={
                    "configured": True,
                    "connected": True,
                },
            ),
            patch.object(calendar_service, "_load_credentials", return_value=object()),
            patch.object(calendar_service, "_get_timezone", return_value=fixed_tz),
            patch.object(calendar_service, "build", return_value=service),
        ):
            result = calendar_service.update_calendar_event(
                "evt-1",
                time="4 PM",
            )

        self.assertIsNotNone(service.events_api.patch_body)
        start = service.events_api.patch_body["start"]["dateTime"]
        end = service.events_api.patch_body["end"]["dateTime"]
        self.assertTrue(start.startswith("2026-08-29T16:00:00"))
        self.assertTrue(end.startswith("2026-08-29T17:00:00"))
        self.assertEqual(result["event"]["dateKey"], "2026-08-29")
        self.assertEqual(result["event"]["time"], "4:00 PM")

    def test_internal_target_date_helper_accepts_canonical_date_key(self) -> None:
        config = SimpleNamespace(timezone_name="America/Los_Angeles")
        fixed_tz = timezone(timedelta(hours=-7))

        with patch.object(
            calendar_service,
            "_get_timezone",
            return_value=fixed_tz,
        ):
            target = calendar_service._target_date_for_day(
                "2026-08-29",
                config,
            )

        self.assertEqual(target.date().isoformat(), "2026-08-29")
        self.assertEqual((target.hour, target.minute), (0, 0))

    def test_relative_tomorrow_behavior_remains_supported(self) -> None:
        config = SimpleNamespace(timezone_name="America/Los_Angeles")
        fixed_tz = timezone(timedelta(hours=-7))

        with patch.object(
            calendar_service,
            "_get_timezone",
            return_value=fixed_tz,
        ):
            today = calendar_service._target_date_for_day("today", config)
            tomorrow = calendar_service._target_date_for_day("tomorrow", config)

        self.assertEqual(tomorrow.date(), today.date() + timedelta(days=1))


if __name__ == "__main__":
    unittest.main()
