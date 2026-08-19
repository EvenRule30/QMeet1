from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.calendar_service import (
    CalendarConfig,
    CalendarIntegrationError,
    _get_timezone,
    _load_credentials,
    _normalize_google_event,
    get_calendar_config,
    get_calendar_status,
)


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_CALENDAR_RANGE_DAYS = 31


@dataclass(frozen=True)
class CalendarDateWindow:
    """Canonical inclusive date window with an exclusive API end bound."""

    start_date: date
    end_date: date
    start: datetime
    end_exclusive: datetime

    @property
    def day_count(self) -> int:
        return (self.end_date - self.start_date).days + 1


def _parse_iso_date(value: str, field_name: str) -> date:
    cleaned = (value or "").strip()
    if not ISO_DATE_RE.fullmatch(cleaned):
        raise CalendarIntegrationError(
            f"Calendar {field_name} must use YYYY-MM-DD."
        )
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise CalendarIntegrationError(
            f"Calendar {field_name} is not a valid date."
        ) from exc


def resolve_calendar_date_window(
    start_date: str,
    end_date: str,
    config: CalendarConfig | None = None,
) -> CalendarDateWindow:
    """Resolve an inclusive date range into timezone-aware API boundaries.

    The user-facing contract is inclusive on both ends:
      startDate=2026-08-27, endDate=2026-08-29

    Google Calendar uses an exclusive timeMax, so the canonical backend
    converts endDate to midnight immediately after the requested final day.
    """

    resolved_config = config or get_calendar_config()
    start_key = _parse_iso_date(start_date, "startDate")
    end_key = _parse_iso_date(end_date, "endDate")

    if end_key < start_key:
        raise CalendarIntegrationError(
            "Calendar endDate cannot be before startDate."
        )

    day_count = (end_key - start_key).days + 1
    if day_count > MAX_CALENDAR_RANGE_DAYS:
        raise CalendarIntegrationError(
            f"Calendar date ranges are limited to {MAX_CALENDAR_RANGE_DAYS} days."
        )

    tz = _get_timezone(resolved_config)
    start = datetime(
        start_key.year,
        start_key.month,
        start_key.day,
        tzinfo=tz,
    )
    end_exclusive_key = end_key + timedelta(days=1)
    end_exclusive = datetime(
        end_exclusive_key.year,
        end_exclusive_key.month,
        end_exclusive_key.day,
        tzinfo=tz,
    )

    return CalendarDateWindow(
        start_date=start_key,
        end_date=end_key,
        start=start,
        end_exclusive=end_exclusive,
    )


def list_calendar_events_range(
    start_date: str,
    end_date: str,
) -> dict:
    """Read the exact canonical Calendar window requested by the caller.

    This path deliberately does not interpret natural-language dates. The
    caller must supply validated absolute date keys. That keeps date-language
    interpretation separate from canonical Calendar state access.
    """

    config = get_calendar_config()
    window = resolve_calendar_date_window(
        start_date,
        end_date,
        config,
    )
    start_key = window.start_date.isoformat()
    end_key = window.end_date.isoformat()

    status = get_calendar_status()
    if not status["configured"] or not status["connected"]:
        return {
            "ok": True,
            "configured": status["configured"],
            "connected": status["connected"],
            "source": "google",
            "view": "range",
            "startDate": start_key,
            "endDate": end_key,
            "events": [],
            "message": status["message"],
        }

    creds = _load_credentials(config)
    if not creds:
        return {
            "ok": True,
            "configured": True,
            "connected": False,
            "source": "google",
            "view": "range",
            "startDate": start_key,
            "endDate": end_key,
            "events": [],
            "message": "Google Calendar needs authorization.",
        }

    try:
        service = build(
            "calendar",
            "v3",
            credentials=creds,
            cache_discovery=False,
        )
        response = (
            service.events()
            .list(
                calendarId=config.calendar_id,
                timeMin=window.start.isoformat(),
                timeMax=window.end_exclusive.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=100,
            )
            .execute()
        )
    except HttpError as exc:
        raise CalendarIntegrationError(
            "Google Calendar API request failed. "
            "Reconnect Calendar or check backend credentials."
        ) from exc
    except Exception as exc:
        raise CalendarIntegrationError(
            "Could not read Google Calendar events."
        ) from exc

    events = [
        _normalize_google_event(item, config)
        for item in response.get("items", [])
    ]

    return {
        "ok": True,
        "configured": True,
        "connected": True,
        "source": "google",
        "view": "range",
        "startDate": start_key,
        "endDate": end_key,
        "events": events,
        "message": (
            f"Loaded {len(events)} Google Calendar "
            f"event{'s' if len(events) != 1 else ''}."
        ),
    }
