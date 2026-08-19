from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse

from app.calendar_absolute_create_service import create_calendar_event_on_date
from app.calendar_range_service import list_calendar_events_range
from app.calendar_service import (
    CalendarIntegrationError,
    complete_calendar_auth,
    create_calendar_event,
    delete_calendar_event,
    get_calendar_status,
    list_calendar_events,
    reset_calendar_auth,
    start_calendar_auth,
    update_calendar_event,
)
from app.schemas import (
    CalendarAuthResetResponse,
    CalendarAuthStartResponse,
    CalendarCreateEventRequest,
    CalendarCreateEventResponse,
    CalendarDeleteEventResponse,
    CalendarEventsResponse,
    CalendarStatusResponse,
    CalendarUpdateEventRequest,
    CalendarUpdateEventResponse,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class CalendarAbsoluteCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(default="Later", max_length=32)
    description: str = ""
    location: str = ""


@router.get("/status", response_model=CalendarStatusResponse)
async def calendar_status():
    return CalendarStatusResponse(**get_calendar_status())


@router.post("/auth/start", response_model=CalendarAuthStartResponse)
async def calendar_auth_start():
    try:
        return CalendarAuthStartResponse(**start_calendar_auth())
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not start Google Calendar authorization.",
        )


@router.get("/auth/callback")
async def calendar_auth_callback(
    request: Request,
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    if error:
        return HTMLResponse(
            f"""
            <html>
              <body style="font-family: system-ui; background: #080a18; color: white; padding: 32px;">
                <h1>Google Calendar was not connected</h1>
                <p>{error}</p>
                <p>You can close this tab and try again from QMeet.</p>
              </body>
            </html>
            """,
            status_code=400,
        )

    if not code:
        return HTMLResponse(
            """
            <html>
              <body style="font-family: system-ui; background: #080a18; color: white; padding: 32px;">
                <h1>Missing authorization code</h1>
                <p>QMeet did not receive a Google authorization code.</p>
              </body>
            </html>
            """,
            status_code=400,
        )

    try:
        complete_calendar_auth(
            code=code,
            authorization_response=str(request.url),
        )
        return HTMLResponse(
            """
            <html>
              <body style="font-family: system-ui; background: #080a18; color: white; padding: 32px;">
                <h1>QMeet Calendar connected</h1>
                <p>Google Calendar is now connected to QMeet.</p>
                <p>You can close this tab and return to QMeet.</p>
              </body>
            </html>
            """
        )
    except CalendarIntegrationError as exc:
        return HTMLResponse(
            f"""
            <html>
              <body style="font-family: system-ui; background: #080a18; color: white; padding: 32px;">
                <h1>Google Calendar connection failed</h1>
                <p>{str(exc)}</p>
                <p>You can close this tab and try again from QMeet.</p>
              </body>
            </html>
            """,
            status_code=400,
        )
    except Exception as exc:
        print(f"Unexpected Google OAuth callback error: {exc}")
        return HTMLResponse(
            f"""
            <html>
              <body style="font-family: system-ui; background: #080a18; color: white; padding: 32px;">
                <h1>Google Calendar connection failed</h1>
                <p>QMeet hit an unexpected OAuth callback error.</p>
                <pre style="white-space: pre-wrap; color: #ffb4c2;">{str(exc)}</pre>
              </body>
            </html>
            """,
            status_code=500,
        )


@router.post("/auth/reset", response_model=CalendarAuthResetResponse)
async def calendar_auth_reset():
    try:
        return CalendarAuthResetResponse(**reset_calendar_auth())
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not reset Google Calendar authorization.",
        )


@router.get("/events", response_model=CalendarEventsResponse)
async def calendar_events(
    view: str = Query(
        default="today",
        pattern="^(today|tomorrow|week)$",
    ),
):
    try:
        # The Calendar panel should retain completed events so the user can
        # review the whole day. AI planning calls the service directly and
        # leaves include_past at its False default.
        return CalendarEventsResponse(
            **list_calendar_events(
                view,
                include_past=True,
            )
        )
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read Google Calendar events.",
        )


@router.get("/events/range")
async def calendar_event_range(
    start_date: str = Query(
        alias="startDate",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    end_date: str = Query(
        alias="endDate",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
):
    """Read one exact inclusive Calendar date window.

    Natural-language interpretation does not happen here. Agent/frontend
    callers must resolve user language to canonical absolute date keys first.
    """
    try:
        return list_calendar_events_range(
            start_date=start_date,
            end_date=end_date,
        )
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read that Google Calendar date range.",
        )


@router.post(
    "/events/absolute",
    response_model=CalendarCreateEventResponse,
)
async def calendar_create_event_absolute(req: CalendarAbsoluteCreateRequest):
    """Create one event on an already-resolved canonical absolute date."""

    try:
        return CalendarCreateEventResponse(
            **create_calendar_event_on_date(
                title=req.title,
                date_key=req.date,
                time=req.time,
                description=req.description,
                location=req.location,
            )
        )
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not create that Google Calendar event.",
        )


@router.post("/events", response_model=CalendarCreateEventResponse)
async def calendar_create_event(req: CalendarCreateEventRequest):
    try:
        return CalendarCreateEventResponse(
            **create_calendar_event(
                title=req.title,
                day=req.day,
                time=req.time,
                description=req.description,
                location=req.location,
            )
        )
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not create the Google Calendar event.",
        )


@router.patch(
    "/events/{event_id}",
    response_model=CalendarUpdateEventResponse,
)
async def calendar_update_event(
    event_id: str,
    req: CalendarUpdateEventRequest,
):
    try:
        return CalendarUpdateEventResponse(
            **update_calendar_event(
                event_id=event_id,
                title=req.title,
                day=req.day,
                time=req.time,
                description=req.description,
                location=req.location,
            )
        )
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not update the Google Calendar event.",
        )


@router.delete(
    "/events/{event_id}",
    response_model=CalendarDeleteEventResponse,
)
async def calendar_delete_event(event_id: str):
    try:
        return CalendarDeleteEventResponse(
            **delete_calendar_event(event_id)
        )
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not delete the Google Calendar event.",
        )
