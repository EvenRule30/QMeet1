import os
import json
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


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


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


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_calendar_config() -> CalendarConfig:
    backend_root = Path(__file__).resolve().parents[1]

    credentials_file = Path(
        os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", "google_credentials.json")
    )
    token_file = Path(
        os.getenv("GOOGLE_CALENDAR_TOKEN_FILE", "token_calendar_readonly.json")
    )

    if not credentials_file.is_absolute():
        credentials_file = backend_root / credentials_file

    auth_state_file = Path(
        os.getenv("GOOGLE_CALENDAR_AUTH_STATE_FILE", "calendar_auth_state.json")
    )

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
        timezone_name=os.getenv("GOOGLE_CALENDAR_TIMEZONE", "local").strip() or "local",
    )


def _get_timezone(config: CalendarConfig):
    if config.timezone_name.lower() == "local":
        return datetime.now().astimezone().tzinfo

    try:
        return ZoneInfo(config.timezone_name)
    except Exception as exc:
        raise CalendarIntegrationError(
            f'Invalid GOOGLE_CALENDAR_TIMEZONE="{config.timezone_name}". Use "local" or an IANA timezone like "America/Los_Angeles".'
        ) from exc


def _credentials_configured(config: CalendarConfig) -> bool:
    return config.enabled and config.credentials_file.exists()


def _load_credentials(config: CalendarConfig) -> Credentials | None:
    if not _credentials_configured(config) or not config.token_file.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(config.token_file), SCOPES)
    except Exception:
        return None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(config, creds)
        except Exception:
            return None

    return creds if creds and creds.valid else None


def _save_credentials(config: CalendarConfig, creds: Credentials) -> None:
    config.token_file.parent.mkdir(parents=True, exist_ok=True)
    config.token_file.write_text(creds.to_json(), encoding="utf-8")


def _save_auth_state(config: CalendarConfig, state: str | None, code_verifier: str | None) -> None:
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
        parsed = json.loads(config.auth_state_file.read_text(encoding="utf-8"))
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
        message = "Google Calendar integration is disabled. Set GOOGLE_CALENDAR_ENABLED=true in backend/.env."
    elif not config.credentials_file.exists():
        message = f"Google Calendar credentials file was not found: {config.credentials_file}"
    elif not connected:
        message = "Google Calendar is configured but not authorized yet."
    else:
        message = "Google Calendar is connected in read-only mode."

    return {
        "ok": True,
        "provider": "google",
        "configured": configured,
        "connected": connected,
        "calendarId": config.calendar_id,
        "message": message,
    }



def _allow_local_http_oauth(config: CalendarConfig) -> None:
    """Allow OAuth redirects to localhost during local prototype development."""
    redirect_uri = config.redirect_uri.lower()

    if redirect_uri.startswith("http://localhost") or redirect_uri.startswith("http://127.0.0.1"):
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
            "Google Calendar integration is disabled. Set GOOGLE_CALENDAR_ENABLED=true in backend/.env."
        )

    if not config.credentials_file.exists():
        raise CalendarIntegrationError(
            f"Google Calendar credentials file was not found: {config.credentials_file}"
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
        "message": "Open this URL, sign into Google, and approve read-only Calendar access.",
    }


def complete_calendar_auth(code: str | None = None, authorization_response: str | None = None) -> dict:
    config = get_calendar_config()

    if not config.enabled:
        raise CalendarIntegrationError(
            "Google Calendar integration is disabled. Set GOOGLE_CALENDAR_ENABLED=true in backend/.env."
        )

    if not config.credentials_file.exists():
        raise CalendarIntegrationError(
            f"Google Calendar credentials file was not found: {config.credentials_file}"
        )

    if not code and not authorization_response:
        raise CalendarIntegrationError("Google OAuth callback did not include an authorization code.")

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
            flow.fetch_token(authorization_response=authorization_response)
        else:
            flow.fetch_token(code=code)
    except OAuth2Error as exc:
        raise CalendarIntegrationError(f"Google OAuth token exchange failed: {exc}") from exc
    except Exception as exc:
        raise CalendarIntegrationError(f"Google OAuth callback failed: {exc}") from exc

    creds = flow.credentials

    if not creds or not creds.valid:
        raise CalendarIntegrationError("Google OAuth finished, but no valid Calendar token was returned.")

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


def _date_range_for_view(view: str, config: CalendarConfig) -> tuple[datetime, datetime]:
    tz = _get_timezone(config)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

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


def _format_time(value: str | None, all_day: bool, config: CalendarConfig) -> str:
    if all_day or not value:
        return "All day"

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        tz = _get_timezone(config)
        dt = dt.astimezone(tz)
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return "Later"


def _date_key_from_start(start_data: dict, config: CalendarConfig) -> str:
    if start_data.get("date"):
        return start_data["date"]

    date_time = start_data.get("dateTime")
    if not date_time:
        return datetime.now(_get_timezone(config)).strftime("%Y-%m-%d")

    try:
        dt = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
        dt = dt.astimezone(_get_timezone(config))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(_get_timezone(config)).strftime("%Y-%m-%d")


def _normalize_google_event(item: dict, config: CalendarConfig) -> dict:
    start_data = item.get("start", {})
    end_data = item.get("end", {})
    all_day = bool(start_data.get("date") and not start_data.get("dateTime"))

    start_value = start_data.get("dateTime") or start_data.get("date")
    end_value = end_data.get("dateTime") or end_data.get("date")

    return {
        "id": f"google-{item.get('id', '')}",
        "googleEventId": item.get("id", ""),
        "title": item.get("summary") or "(No title)",
        "dateKey": _date_key_from_start(start_data, config),
        "time": _format_time(start_value, all_day, config),
        "createdAt": item.get("created") or datetime.now(_get_timezone(config)).isoformat(),
        "source": "google",
        "start": start_value,
        "end": end_value,
        "location": item.get("location") or "",
        "description": item.get("description") or "",
        "allDay": all_day,
        "calendarId": config.calendar_id,
    }


def list_calendar_events(view: str = "today") -> dict:
    requested_view = view if view in {"today", "tomorrow", "week"} else "today"
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

    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
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
            "Google Calendar API request failed. Reconnect Calendar or check backend credentials."
        ) from exc
    except Exception as exc:
        raise CalendarIntegrationError(
            "Could not read Google Calendar events."
        ) from exc

    events = [_normalize_google_event(item, config) for item in response.get("items", [])]

    return {
        "ok": True,
        "configured": True,
        "connected": True,
        "source": "google",
        "view": requested_view,
        "events": events,
        "message": f"Loaded {len(events)} Google Calendar event{'s' if len(events) != 1 else ''}.",
    }
