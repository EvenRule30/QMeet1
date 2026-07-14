import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauthlib.oauth2 import OAuth2Error


SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


class CalendarIntegrationError(Exception):
    """Safe calendar integration error that can be shown in the UI."""


@dataclass
class CalendarConfig:
    enabled: bool
    credentials_file: Path
    token_file: Path
    auth_state_file: Path
    redirect_uri: str
    calendar_id: str
    timezone_name: str
    write_enabled: bool


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_calendar_config() -> CalendarConfig:
    backend_root = Path(__file__).resolve().parents[1]

    credentials_file = Path(
        os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", "google_credentials.json")
    )
    token_file = Path(
        os.getenv("GOOGLE_CALENDAR_TOKEN_FILE", "token_calendar_events.json")
    )
    auth_state_file = Path(
        os.getenv("GOOGLE_CALENDAR_AUTH_STATE_FILE", "calendar_auth_state.json")
    )

    if not credentials_file.is_absolute():
        credentials_file = backend_root / credentials_file

    if not token_file.is_absolute():
        token_file = backend_root / token_file

    if not auth_state_file.is_absolute():
        auth_state_file = backend_root / auth_state_file

    return CalendarConfig(
        enabled=_truthy(os.getenv("GOOGLE_CALENDAR_ENABLED", "false")),
        credentials_file=credentials_file,
        token_file=token_file,
        auth_state_file=auth_state_file,
        redirect_uri=os.getenv(
            "GOOGLE_CALENDAR_REDIRECT_URI",
            "http://localhost:8000/api/calendar/auth/callback",
        ).strip(),
        calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary",
        timezone_name=os.getenv("GOOGLE_CALENDAR_TIMEZONE", "local").strip()
        or "local",
        write_enabled=_truthy(
            os.getenv("GOOGLE_CALENDAR_WRITE_ENABLED", "false")
        ),
    )


def _get_timezone(config: CalendarConfig):
    if config.timezone_name.lower() == "local":
        return datetime.now().astimezone().tzinfo

    try:
        return ZoneInfo(config.timezone_name)
    except Exception as exc:
        raise CalendarIntegrationError(
            f'Invalid GOOGLE_CALENDAR_TIMEZONE="{config.timezone_name}". '
            'Use "local" or an IANA timezone like "America/Los_Angeles".'
        ) from exc


def _credentials_configured(config: CalendarConfig) -> bool:
    return config.enabled and config.credentials_file.exists()


def _save_credentials(config: CalendarConfig, creds: Credentials) -> None:
    config.token_file.parent.mkdir(parents=True, exist_ok=True)
    config.token_file.write_text(creds.to_json(), encoding="utf-8")


def _load_credentials(config: CalendarConfig) -> Credentials | None:
    if not _credentials_configured(config) or not config.token_file.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(
            str(config.token_file),
            SCOPES,
        )
    except Exception:
        return None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(config, creds)
        except Exception:
            return None

    return creds if creds and creds.valid else None


def _save_auth_state(
    config: CalendarConfig,
    state: str | None,
    code_verifier: str | None,
) -> None:
    config.auth_state_file.parent.mkdir(parents=True, exist_ok=True)
    config.auth_state_file.write_text(
        json.dumps(
            {
                "state": state or "",
                "codeVerifier": code_verifier or "",
                "createdAt": datetime.now().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_auth_state(config: CalendarConfig) -> dict:
    if not config.auth_state_file.exists():
        return {}

    try:
        parsed = json.loads(
            config.auth_state_file.read_text(encoding="utf-8")
        )
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _clear_auth_state(config: CalendarConfig) -> None:
    try:
        if config.auth_state_file.exists():
            config.auth_state_file.unlink()
    except Exception:
        pass


def get_calendar_status() -> dict:
    config = get_calendar_config()
    configured = _credentials_configured(config)
    connected = _load_credentials(config) is not None

    if not config.enabled:
        message = (
            "Google Calendar integration is disabled. "
            "Set GOOGLE_CALENDAR_ENABLED=true in backend/.env."
        )
    elif not config.credentials_file.exists():
        message = (
            "Google Calendar credentials file was not found: "
            f"{config.credentials_file}"
        )
    elif not connected:
        message = "Google Calendar is configured but not authorized yet."
    else:
        message = (
            "Google Calendar is connected with event write access."
            if config.write_enabled
            else "Google Calendar is connected, but event writing is disabled."
        )

    return {
        "ok": True,
        "provider": "google",
        "configured": configured,
        "connected": connected,
        "calendarId": config.calendar_id,
        "writeEnabled": config.write_enabled,
        "scopes": SCOPES,
        "message": message,
    }


def _allow_local_http_oauth(config: CalendarConfig) -> None:
    """Allow OAuth redirects to localhost during prototype development."""
    redirect_uri = config.redirect_uri.lower()

    if redirect_uri.startswith(
        "http://localhost"
    ) or redirect_uri.startswith("http://127.0.0.1"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def _make_calendar_flow(config: CalendarConfig) -> Flow:
    _allow_local_http_oauth(config)
    return Flow.from_client_secrets_file(
        str(config.credentials_file),
        scopes=SCOPES,
        redirect_uri=config.redirect_uri,
    )


def start_calendar_auth() -> dict:
    config = get_calendar_config()

    if not config.enabled:
        raise CalendarIntegrationError(
            "Google Calendar integration is disabled. "
            "Set GOOGLE_CALENDAR_ENABLED=true in backend/.env."
        )

    if not config.credentials_file.exists():
        raise CalendarIntegrationError(
            "Google Calendar credentials file was not found: "
            f"{config.credentials_file}"
        )

    flow = _make_calendar_flow(config)

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    _save_auth_state(
        config,
        state=state,
        code_verifier=getattr(flow, "code_verifier", None),
    )

    return {
        "ok": True,
        "authUrl": auth_url,
        "message": (
            "Open this URL, sign into Google, and approve "
            "Calendar read/write access."
        ),
    }


def complete_calendar_auth(
    code: str | None = None,
    authorization_response: str | None = None,
) -> dict:
    config = get_calendar_config()

    if not config.enabled:
        raise CalendarIntegrationError(
            "Google Calendar integration is disabled. "
            "Set GOOGLE_CALENDAR_ENABLED=true in backend/.env."
        )

    if not config.credentials_file.exists():
        raise CalendarIntegrationError(
            "Google Calendar credentials file was not found: "
            f"{config.credentials_file}"
        )

    if not code and not authorization_response:
        raise CalendarIntegrationError(
            "Google OAuth callback did not include an authorization code."
        )

    flow = _make_calendar_flow(config)
    saved_auth_state = _load_auth_state(config)
    saved_state = saved_auth_state.get("state")
    saved_code_verifier = saved_auth_state.get("codeVerifier")

    if saved_state:
        try:
            flow.oauth2session.state = saved_state
        except Exception:
            pass

    if saved_code_verifier:
        try:
            flow.code_verifier = saved_code_verifier
        except Exception:
            pass

    try:
        if authorization_response:
            flow.fetch_token(
                authorization_response=authorization_response
            )
        else:
            flow.fetch_token(code=code)
    except OAuth2Error as exc:
        raise CalendarIntegrationError(
            f"Google OAuth token exchange failed: {exc}"
        ) from exc
    except Exception as exc:
        raise CalendarIntegrationError(
            f"Google OAuth callback failed: {exc}"
        ) from exc

    creds = flow.credentials

    if not creds or not creds.valid:
        raise CalendarIntegrationError(
            "Google OAuth finished, but no valid Calendar token was returned."
        )

    _save_credentials(config, creds)
    _clear_auth_state(config)

    return {
        "ok": True,
        "connected": True,
        "message": "Google Calendar connected.",
    }


def reset_calendar_auth() -> dict:
    config = get_calendar_config()

    if config.token_file.exists():
        config.token_file.unlink()

    _clear_auth_state(config)

    return {
        "ok": True,
        "message": "Google Calendar token removed.",
    }


def _date_range_for_view(
    view: str,
    config: CalendarConfig,
) -> tuple[datetime, datetime]:
    tz = _get_timezone(config)
    now = datetime.now(tz)
    today_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    if view == "tomorrow":
        start = today_start + timedelta(days=1)
        end = start + timedelta(days=1)
    elif view == "week":
        start = today_start
        end = start + timedelta(days=7)
    else:
        start = today_start
        end = start + timedelta(days=1)

    return start, end


def _format_time(
    value: str | None,
    all_day: bool,
    config: CalendarConfig,
) -> str:
    if all_day or not value:
        return "All day"

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        dt = dt.astimezone(_get_timezone(config))
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return "Later"


def _date_key_from_start(
    start_data: dict,
    config: CalendarConfig,
) -> str:
    if start_data.get("date"):
        return start_data["date"]

    date_time = start_data.get("dateTime")
    if not date_time:
        return datetime.now(_get_timezone(config)).strftime("%Y-%m-%d")

    try:
        dt = datetime.fromisoformat(
            date_time.replace("Z", "+00:00")
        )
        dt = dt.astimezone(_get_timezone(config))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(_get_timezone(config)).strftime("%Y-%m-%d")


def _normalize_google_event(
    item: dict,
    config: CalendarConfig,
) -> dict:
    start_data = item.get("start", {})
    end_data = item.get("end", {})
    all_day = bool(
        start_data.get("date") and not start_data.get("dateTime")
    )

    start_value = start_data.get("dateTime") or start_data.get("date")
    end_value = end_data.get("dateTime") or end_data.get("date")

    return {
        "id": f"google-{item.get('id', '')}",
        "googleEventId": item.get("id", ""),
        "title": item.get("summary") or "(No title)",
        "dateKey": _date_key_from_start(start_data, config),
        "time": _format_time(start_value, all_day, config),
        "createdAt": item.get("created")
        or datetime.now(_get_timezone(config)).isoformat(),
        "source": "google",
        "start": start_value,
        "end": end_value,
        "location": item.get("location") or "",
        "description": item.get("description") or "",
        "allDay": all_day,
        "calendarId": config.calendar_id,
    }


def _target_date_for_day(
    day: str,
    config: CalendarConfig,
) -> datetime:
    tz = _get_timezone(config)
    now = datetime.now(tz)
    start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    if (day or "").strip().lower() == "tomorrow":
        start += timedelta(days=1)

    return start


def _parse_time_for_event(
    day: str,
    time_text: str | None,
    config: CalendarConfig,
) -> tuple[datetime, datetime, bool]:
    start_of_day = _target_date_for_day(day, config)
    raw = (time_text or "").strip().lower()

    if not raw or raw in {
        "later",
        "all day",
        "all-day",
        "sometime",
        "anytime",
    }:
        return (
            start_of_day,
            start_of_day + timedelta(days=1),
            True,
        )

    normalized = (
        raw.replace(".", "")
        .replace("a m", "am")
        .replace("p m", "pm")
        .replace("a.m", "am")
        .replace("p.m", "pm")
        .replace("o'clock", "")
        .replace("oclock", "")
        .strip()
    )

    if normalized == "noon":
        hour = 12
        minute = 0
    elif normalized == "midnight":
        hour = 0
        minute = 0
    else:
        match = re.match(
            r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$",
            normalized,
        )
        if not match:
            return (
                start_of_day,
                start_of_day + timedelta(days=1),
                True,
            )

        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        suffix = match.group(3)

        if minute > 59 or hour > 23:
            return (
                start_of_day,
                start_of_day + timedelta(days=1),
                True,
            )

        if suffix == "pm" and hour < 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        elif suffix is None and 1 <= hour <= 7:
            # In this prototype, "at 3" usually means 3 PM.
            hour += 12

    start = start_of_day.replace(hour=hour, minute=minute)
    end = start + timedelta(hours=1)
    return start, end, False


def _event_body_for_time(
    day: str,
    time_text: str,
    config: CalendarConfig,
) -> tuple[dict, dict]:
    start, end, all_day = _parse_time_for_event(
        day,
        time_text,
        config,
    )

    if all_day:
        return (
            {"date": start.date().isoformat()},
            {"date": end.date().isoformat()},
        )

    start_body = {"dateTime": start.isoformat()}
    end_body = {"dateTime": end.isoformat()}

    if config.timezone_name.lower() != "local":
        start_body["timeZone"] = config.timezone_name
        end_body["timeZone"] = config.timezone_name

    return start_body, end_body


def create_calendar_event(
    title: str,
    day: str = "today",
    time: str = "Later",
    description: str = "",
    location: str = "",
) -> dict:
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

    creds = _load_credentials(config)
    if not creds:
        raise CalendarIntegrationError(
            "Google Calendar needs authorization with event write access."
        )

    start_body, end_body = _event_body_for_time(
        day,
        time,
        config,
    )
    event_body = {
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


def update_calendar_event(
    event_id: str,
    title: str = "",
    day: str | None = None,
    time: str = "",
    description: str = "",
    location: str = "",
) -> dict:
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
        raise CalendarIntegrationError(
            "Google Calendar event id cannot be empty."
        )

    clean_title = (title or "").strip()
    clean_time = (time or "").strip()
    clean_day = (day or "").strip().lower()

    if clean_day not in {"today", "tomorrow", ""}:
        clean_day = ""

    if (
        not clean_title
        and not clean_time
        and not clean_day
        and not description
        and not location
    ):
        raise CalendarIntegrationError(
            "No calendar event changes were provided."
        )

    creds = _load_credentials(config)
    if not creds:
        raise CalendarIntegrationError(
            "Google Calendar needs authorization with event write access."
        )

    try:
        service = build(
            "calendar",
            "v3",
            credentials=creds,
            cache_discovery=False,
        )
        existing = (
            service.events()
            .get(
                calendarId=config.calendar_id,
                eventId=clean_event_id,
            )
            .execute()
        )

        body: dict = {}

        if clean_title:
            body["summary"] = clean_title

        if description:
            body["description"] = description

        if location:
            body["location"] = location

        if clean_day or clean_time:
            target_day = clean_day

            if not target_day:
                existing_start = existing.get("start", {})
                existing_start_text = (
                    existing_start.get("dateTime")
                    or existing_start.get("date")
                )

                if existing_start_text:
                    try:
                        existing_start_dt = datetime.fromisoformat(
                            existing_start_text.replace("Z", "+00:00")
                        ).astimezone(_get_timezone(config))
                        today_key = _target_date_for_day(
                            "today",
                            config,
                        ).date().isoformat()
                        target_day = (
                            "today"
                            if existing_start_dt.date().isoformat()
                            == today_key
                            else "tomorrow"
                        )
                    except Exception:
                        target_day = "today"
                else:
                    target_day = "today"

            start_body, end_body = _event_body_for_time(
                target_day or "today",
                clean_time or "Later",
                config,
            )
            body["start"] = start_body
            body["end"] = end_body

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
        status_code = getattr(
            getattr(exc, "resp", None),
            "status",
            None,
        )

        if status_code == 404:
            raise CalendarIntegrationError(
                "Google Calendar event was not found. "
                "Refresh the calendar and try again."
            ) from exc

        raise CalendarIntegrationError(
            "Google Calendar event update failed. "
            "Refresh or reconnect Calendar and try again."
        ) from exc
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


def delete_calendar_event(event_id: str) -> dict:
    config = get_calendar_config()
    status = get_calendar_status()

    if not status["configured"] or not status["connected"]:
        raise CalendarIntegrationError(status["message"])

    if not config.write_enabled:
        raise CalendarIntegrationError(
            "Google Calendar event deletion is disabled. "
            "Set GOOGLE_CALENDAR_WRITE_ENABLED=true in backend/.env."
        )

    clean_event_id = (event_id or "").strip()
    if clean_event_id.startswith("google-"):
        clean_event_id = clean_event_id.removeprefix("google-")

    if not clean_event_id:
        raise CalendarIntegrationError(
            "Google Calendar event id cannot be empty."
        )

    creds = _load_credentials(config)
    if not creds:
        raise CalendarIntegrationError(
            "Google Calendar needs authorization with event write access."
        )

    try:
        service = build(
            "calendar",
            "v3",
            credentials=creds,
            cache_discovery=False,
        )
        (
            service.events()
            .delete(
                calendarId=config.calendar_id,
                eventId=clean_event_id,
            )
            .execute()
        )
    except HttpError as exc:
        status_code = getattr(
            getattr(exc, "resp", None),
            "status",
            None,
        )

        if status_code == 404:
            raise CalendarIntegrationError(
                "Google Calendar event was not found. "
                "Refresh the calendar and try again."
            ) from exc

        raise CalendarIntegrationError(
            "Google Calendar event deletion failed. "
            "Refresh or reconnect Calendar and try again."
        ) from exc
    except Exception as exc:
        raise CalendarIntegrationError(
            "Could not delete Google Calendar event."
        ) from exc

    return {
        "ok": True,
        "configured": True,
        "connected": True,
        "source": "google",
        "deletedEventId": clean_event_id,
        "message": "Deleted Google Calendar event.",
    }


def list_calendar_events(
    view: str = "today",
    include_past: bool = False,
) -> dict:
    """Read events for a calendar view.

    The Calendar panel passes include_past=True so the user can review the
    complete day. QMeet's agent uses the default False value, which makes its
    planning context start at the current moment and prevents completed events
    from being labeled as the next commitment.
    """

    requested_view = (
        view if view in {"today", "tomorrow", "week"} else "today"
    )
    config = get_calendar_config()
    status = get_calendar_status()

    if not status["configured"] or not status["connected"]:
        return {
            "ok": True,
            "configured": status["configured"],
            "connected": status["connected"],
            "source": "google",
            "view": requested_view,
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
            "view": requested_view,
            "events": [],
            "message": "Google Calendar needs authorization.",
        }

    start, end = _date_range_for_view(requested_view, config)

    if requested_view in {"today", "week"} and not include_past:
        now = datetime.now(_get_timezone(config))
        if now < end:
            start = max(start, now)

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
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=40,
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
        "view": requested_view,
        "events": events,
        "message": (
            f"Loaded {len(events)} Google Calendar "
            f"event{'s' if len(events) != 1 else ''}."
        ),
    }
