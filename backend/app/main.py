import os
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from app.agent import (
    AgentUserFacingError,
    generate_reply,
    interpret_command_intent,
    get_public_status,
    reset_conversation,
    sse_event,
    stream_reply,
)

from app.calendar_service import (
    CalendarIntegrationError,
    complete_calendar_auth,
    get_calendar_status,
    list_calendar_events,
    reset_calendar_auth,
    start_calendar_auth,
)

from app.schemas import (
    CalendarAuthResetResponse,
    CalendarAuthStartResponse,
    CalendarEventsResponse,
    CalendarStatusResponse,
    ChatRequest,
    ChatResponse,
    CommandInterpretRequest,
    CommandInterpretResponse,
)

load_dotenv()

app = FastAPI(title="QMeet Agent Backend")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

# change allow comments when loosening or tightening CORS for testing
app.add_middleware(
    CORSMiddleware,
    #allow_origins=[frontend_origin],
    allow_origins=["*"],
    #allow_credentials=True,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "qmeet-agent",
    }


@app.get("/api/status")
async def status():
    return get_public_status()


@app.get("/api/calendar/status", response_model=CalendarStatusResponse)
async def calendar_status():
    return CalendarStatusResponse(**get_calendar_status())


@app.post("/api/calendar/auth/start", response_model=CalendarAuthStartResponse)
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


@app.get("/api/calendar/auth/callback")
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
        complete_calendar_auth(code=code, authorization_response=str(request.url))
        return HTMLResponse(
            """
            <html>
              <body style="font-family: system-ui; background: #080a18; color: white; padding: 32px;">
                <h1>QMeet Calendar connected</h1>
                <p>Google Calendar is now connected in read-only mode.</p>
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


@app.post("/api/calendar/auth/reset", response_model=CalendarAuthResetResponse)
async def calendar_auth_reset():
    try:
        return CalendarAuthResetResponse(**reset_calendar_auth())
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not reset Google Calendar authorization.",
        )


@app.get("/api/calendar/events", response_model=CalendarEventsResponse)
async def calendar_events(
    view: str = Query(default="today", pattern="^(today|tomorrow|week)$"),
):
    try:
        return CalendarEventsResponse(**list_calendar_events(view))
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read Google Calendar events.",
        )


@app.post("/api/command/interpret", response_model=CommandInterpretResponse)
async def command_interpret(req: CommandInterpretRequest):
    message = req.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        intent = await interpret_command_intent(message)
        return CommandInterpretResponse(**intent)
    except AgentUserFacingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet command interpreter hit an unexpected error.",
        )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    message = req.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        reply = await generate_reply(message)
        return ChatResponse(reply=reply, state="speaking")
    except AgentUserFacingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet backend hit an unexpected error.",
        )
    

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    message = req.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    async def event_generator():
        try:
            yield sse_event("start", {"ok": True})

            async for chunk in stream_reply(message):
                yield sse_event("chunk", {"text": chunk})

            yield sse_event("done", {"ok": True})

        except AgentUserFacingError as exc:
            yield sse_event("error", {"message": str(exc)})
        except Exception:
            yield sse_event(
                "error",
                {"message": "QMeet backend hit an unexpected streaming error."},
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/reset")
async def reset():
    reset_conversation()
    return {"ok": True}