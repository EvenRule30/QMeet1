from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.calendar_service import (
    CalendarIntegrationError,
    _get_timezone,
    _load_credentials,
    _normalize_google_event,
    _parse_time_for_event,
    get_calendar_config,
    get_calendar_status,
)


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_calendar_absolute_date(value: str) -> date:
    cleaned = (value or "").strip()
    if not ISO_DATE_RE.fullmatch(cleaned):
        raise CalendarIntegrationError(
            "Calendar date must use YYYY-MM-DD."
        )
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise CalendarIntegrationError(
            "Calendar date is not a valid date."
        ) from exc


def _event_body_for_absolute_date(
    date_key: str,
    time_text: str | None,
) -> tuple[dict, dict]:
    """Reuse existing time semantics while replacing only the canonical day.

    The existing Calendar service owns interpretation of `Later`, all-day,
    noon/midnight, AM/PM, and the prototype's bare-hour convention. This helper
    deliberately reuses that behavior and substitutes an already-validated
    absolute date afterward.
    """

    target_date = parse_calendar_absolute_date(date_key)
    config = get_calendar_config()
    parsed_start, _parsed_end, all_day = _parse_time_for_event(
        "today",
        time_text,
        config,
    )

    if all_day:
        return (
            {"date": target_date.isoformat()},
            {"date": (target_date + timedelta(days=1)).isoformat()},
        )

    tz = _get_timezone(config)
    start = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        parsed_start.hour,
        parsed_start.minute,
        tzinfo=tz,
    )
    end = start + timedelta(hours=1)
    start_body: dict[str, str] = {"dateTime": start.isoformat()}
    end_body: dict[str, str] = {"dateTime": end.isoformat()}
    if config.timezone_name.lower() != "local":
        start_body["timeZone"] = config.timezone_name
        end_body["timeZone"] = config.timezone_name
    return start_body, end_body


def create_calendar_event_on_date(
    *,
    title: str,
    date_key: str,
    time: str = "Later",
    description: str = "",
    location: str = "",
) -> dict:
    """Create exactly one Google Calendar event on one canonical date.

    Natural-language date interpretation is intentionally upstream. This
    mutation boundary accepts only one absolute YYYY-MM-DD date key and keeps
    the existing Google write authorization/receipt semantics.
    """

    config = get_calendar_config()
    status = get_calendar_status()
    if not status["configured"] or not status["connected"]:
        raise CalendarIntegrationError(status["message"])
    if not config.write_enabled:
        raise CalendarIntegrationError(
            "Google Calendar event writing is disabled. "
            "Set GOOGLE_CALENDAR_WRITE_ENABLED=true in backend/.env."
        )

    clean_title = (title or "").strip()
    if not clean_title:
        raise CalendarIntegrationError(
            "Calendar event title cannot be empty."
        )
    clean_date = parse_calendar_absolute_date(date_key).isoformat()
    creds = _load_credentials(config)
    if not creds:
        raise CalendarIntegrationError(
            "Google Calendar needs authorization with event write access."
        )

    start_body, end_body = _event_body_for_absolute_date(
        clean_date,
        time,
    )
    event_body: dict = {
        "summary": clean_title,
        "start": start_body,
        "end": end_body,
    }
    if description.strip():
        event_body["description"] = description.strip()
    if location.strip():
        event_body["location"] = location.strip()

    try:
        service = build(
            "calendar",
            "v3",
            credentials=creds,
            cache_discovery=False,
        )
        created = (
            service.events()
            .insert(
                calendarId=config.calendar_id,
                body=event_body,
            )
            .execute()
        )
    except HttpError as exc:
        raise CalendarIntegrationError(
            "Google Calendar event creation failed. Reconnect Calendar "
            "and make sure the token has event write access."
        ) from exc
    except Exception as exc:
        raise CalendarIntegrationError(
            "Could not create Google Calendar event."
        ) from exc

    normalized_event = _normalize_google_event(created, config)
    return {
        "ok": True,
        "configured": True,
        "connected": True,
        "source": "google",
        "event": normalized_event,
        "message": (
            "Created Google Calendar event: "
            f"{normalized_event['time']}: "
            f"{normalized_event['title']}."
        ),
    }
