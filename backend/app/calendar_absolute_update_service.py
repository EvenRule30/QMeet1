from __future__ import annotations

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.calendar_absolute_create_service import (
    _event_body_for_absolute_date,
    parse_calendar_absolute_date,
)
from app.calendar_service import (
    CalendarIntegrationError,
    _load_credentials,
    _normalize_google_event,
    get_calendar_config,
    get_calendar_status,
)


def update_calendar_event_on_absolute_date(
    event_id: str,
    *,
    date_key: str,
    title: str = "",
    time: str = "",
) -> dict:
    """Update one already-resolved Google event using one canonical date key.

    Canonical event identity comes from deterministic frontend resolution and is
    never inferred here. The absolute date is validated independently so a
    confirmed farther-date move cannot fall back to today/tomorrow semantics.
    """

    config = get_calendar_config()
    status = get_calendar_status()
    if not status["configured"] or not status["connected"]:
        raise CalendarIntegrationError(status["message"])
    if not config.write_enabled:
        raise CalendarIntegrationError(
            "Google Calendar event editing is disabled. "
            "Set GOOGLE_CALENDAR_WRITE_ENABLED=true in backend/.env."
        )

    clean_event_id = (event_id or "").strip()
    if clean_event_id.startswith("google-"):
        clean_event_id = clean_event_id.removeprefix("google-")
    if not clean_event_id:
        raise CalendarIntegrationError("Google Calendar event id cannot be empty.")

    target_date = parse_calendar_absolute_date(date_key).isoformat()
    clean_title = (title or "").strip()
    clean_time = (time or "").strip()

    creds = _load_credentials(config)
    if not creds:
        raise CalendarIntegrationError(
            "Google Calendar needs authorization with event write access."
        )

    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        existing = (
            service.events()
            .get(calendarId=config.calendar_id, eventId=clean_event_id)
            .execute()
        )
        normalized_existing = _normalize_google_event(existing, config)
        preserved_time = clean_time or str(normalized_existing.get("time") or "Later")

        start_body, end_body = _event_body_for_absolute_date(
            target_date,
            preserved_time,
        )
        body: dict = {
            "start": start_body,
            "end": end_body,
        }
        if clean_title:
            body["summary"] = clean_title

        updated = (
            service.events()
            .patch(
                calendarId=config.calendar_id,
                eventId=clean_event_id,
                body=body,
            )
            .execute()
        )
    except HttpError as exc:
        status_code = getattr(getattr(exc, "resp", None), "status", None)
        if status_code == 404:
            raise CalendarIntegrationError(
                "Google Calendar event was not found. Refresh the calendar and try again."
            ) from exc
        raise CalendarIntegrationError(
            "Google Calendar event update failed. Refresh or reconnect Calendar and try again."
        ) from exc
    except CalendarIntegrationError:
        raise
    except Exception as exc:
        raise CalendarIntegrationError(
            "Could not update Google Calendar event."
        ) from exc

    return {
        "ok": True,
        "configured": True,
        "connected": True,
        "source": "google",
        "event": _normalize_google_event(updated, config),
        "message": "Updated Google Calendar event.",
    }
