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
    search_web,
)

from app.calendar_service import (
    CalendarIntegrationError,
    complete_calendar_auth,
    get_calendar_status,
    list_calendar_events,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    reset_calendar_auth,
    start_calendar_auth,
)


from app.memory_store import (
    MemoryStoreError,
    clear_completed_memory_tasks,
    clear_memory_notes,
    clear_recent_actions,
    create_memory_note,
    create_memory_task,
    create_recent_action,
    delete_memory_note,
    delete_memory_task,
    delete_recent_action,
    get_memory_context,
    get_memory_status,
    list_memory_notes,
    list_memory_tasks,
    list_recent_actions,
    replace_memory_context,
    replace_memory_notes,
    replace_memory_tasks,
    replace_recent_actions,
    update_memory_task,
)

from app.schemas import (
    CalendarAuthResetResponse,
    CalendarAuthStartResponse,
    CalendarCreateEventRequest,
    CalendarCreateEventResponse,
    CalendarUpdateEventRequest,
    CalendarUpdateEventResponse,
    CalendarDeleteEventResponse,
    CalendarEventsResponse,
    CalendarStatusResponse,
    ChatRequest,
    ChatResponse,
    CommandInterpretRequest,
    CommandInterpretResponse,
    MemoryClearCompletedResponse,
    MemoryContextReplaceRequest,
    MemoryContextResponse,
    MemoryNoteCreateRequest,
    MemoryNoteDeleteResponse,
    MemoryNotesClearResponse,
    MemoryNotesReplaceRequest,
    MemoryNotesResponse,
    MemoryStatusResponse,
    MemoryTaskCreateRequest,
    MemoryTaskDeleteResponse,
    MemoryTasksReplaceRequest,
    MemoryTasksResponse,
    MemoryTaskUpdateRequest,
    RecentActionCreateRequest,
    RecentActionDeleteResponse,
    RecentActionsClearResponse,
    RecentActionsReplaceRequest,
    RecentActionsResponse,
    SearchRequest,
    SearchResponse,
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


@app.post("/api/search", response_model=SearchResponse)
async def web_search(req: SearchRequest):
    query = req.query.strip()

    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    try:
        return SearchResponse(**await search_web(query))
    except AgentUserFacingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet web search hit an unexpected error.",
        )


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


@app.post("/api/calendar/events", response_model=CalendarCreateEventResponse)
async def calendar_create_event(req: CalendarCreateEventRequest):
    try:
        return CalendarCreateEventResponse(**create_calendar_event(
            title=req.title,
            day=req.day,
            time=req.time,
            description=req.description,
            location=req.location,
        ))
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not create the Google Calendar event.",
        )


@app.patch("/api/calendar/events/{event_id}", response_model=CalendarUpdateEventResponse)
async def calendar_update_event(event_id: str, req: CalendarUpdateEventRequest):
    try:
        return CalendarUpdateEventResponse(**update_calendar_event(
            event_id=event_id,
            title=req.title,
            day=req.day,
            time=req.time,
            description=req.description,
            location=req.location,
        ))
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not update the Google Calendar event.",
        )


@app.delete("/api/calendar/events/{event_id}", response_model=CalendarDeleteEventResponse)
async def calendar_delete_event(event_id: str):
    try:
        return CalendarDeleteEventResponse(**delete_calendar_event(event_id))
    except CalendarIntegrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not delete the Google Calendar event.",
        )


@app.get("/api/memory/status", response_model=MemoryStatusResponse)
async def memory_status():
    try:
        return MemoryStatusResponse(**get_memory_status())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read memory status.",
        )


@app.get("/api/memory/context", response_model=MemoryContextResponse)
async def memory_context():
    try:
        return MemoryContextResponse(**get_memory_context())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read memory context.",
        )


@app.put("/api/memory/context", response_model=MemoryContextResponse)
async def memory_replace_context(req: MemoryContextReplaceRequest):
    try:
        return MemoryContextResponse(**replace_memory_context(
            tasks=[task.dict(exclude_none=True) for task in req.tasks],
            recent_actions=[action.dict(exclude_none=True) for action in req.recentActions],
            notes=[note.dict(exclude_none=True) for note in req.notes],
        ))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save memory context.",
        )


@app.get("/api/memory/tasks", response_model=MemoryTasksResponse)
async def memory_tasks():
    try:
        return MemoryTasksResponse(**list_memory_tasks())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read memory tasks.",
        )


@app.put("/api/memory/tasks", response_model=MemoryTasksResponse)
async def memory_replace_tasks(req: MemoryTasksReplaceRequest):
    try:
        return MemoryTasksResponse(**replace_memory_tasks(
            [task.dict(exclude_none=True) for task in req.tasks]
        ))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save memory tasks.",
        )


@app.post("/api/memory/tasks", response_model=MemoryTasksResponse)
async def memory_create_task(req: MemoryTaskCreateRequest):
    try:
        return MemoryTasksResponse(**create_memory_task(req.title))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not create memory task.",
        )


@app.patch("/api/memory/tasks/{task_id}", response_model=MemoryTasksResponse)
async def memory_update_task(task_id: str, req: MemoryTaskUpdateRequest):
    try:
        return MemoryTasksResponse(**update_memory_task(
            task_id=task_id,
            title=req.title,
            completed_at=req.completedAt,
        ))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not update memory task.",
        )


@app.delete("/api/memory/tasks/{task_id}", response_model=MemoryTaskDeleteResponse)
async def memory_delete_task(task_id: str):
    try:
        return MemoryTaskDeleteResponse(**delete_memory_task(task_id))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not delete memory task.",
        )


@app.post("/api/memory/tasks/clear-completed", response_model=MemoryClearCompletedResponse)
async def memory_clear_completed_tasks():
    try:
        return MemoryClearCompletedResponse(**clear_completed_memory_tasks())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not clear completed memory tasks.",
        )


@app.get("/api/memory/notes", response_model=MemoryNotesResponse)
async def memory_notes():
    try:
        return MemoryNotesResponse(**list_memory_notes())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read memory notes.",
        )


@app.put("/api/memory/notes", response_model=MemoryNotesResponse)
async def memory_replace_notes(req: MemoryNotesReplaceRequest):
    try:
        return MemoryNotesResponse(**replace_memory_notes(
            [note.dict(exclude_none=True) for note in req.notes]
        ))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save memory notes.",
        )


@app.post("/api/memory/notes", response_model=MemoryNotesResponse)
async def memory_create_note(req: MemoryNoteCreateRequest):
    try:
        return MemoryNotesResponse(**create_memory_note(req.content))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not create memory note.",
        )


@app.delete("/api/memory/notes/{note_id}", response_model=MemoryNoteDeleteResponse)
async def memory_delete_note(note_id: str):
    try:
        return MemoryNoteDeleteResponse(**delete_memory_note(note_id))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not delete memory note.",
        )


@app.post("/api/memory/notes/clear", response_model=MemoryNotesClearResponse)
async def memory_clear_notes():
    try:
        return MemoryNotesClearResponse(**clear_memory_notes())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not clear memory notes.",
        )


@app.get("/api/memory/actions", response_model=RecentActionsResponse)
async def memory_recent_actions():
    try:
        return RecentActionsResponse(**list_recent_actions())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read recent actions.",
        )


@app.put("/api/memory/actions", response_model=RecentActionsResponse)
async def memory_replace_recent_actions(req: RecentActionsReplaceRequest):
    try:
        return RecentActionsResponse(**replace_recent_actions(
            [action.dict(exclude_none=True) for action in req.recentActions]
        ))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save recent actions.",
        )


@app.post("/api/memory/actions", response_model=RecentActionsResponse)
async def memory_create_recent_action(req: RecentActionCreateRequest):
    try:
        return RecentActionsResponse(**create_recent_action(
            label=req.label,
            detail=req.detail,
        ))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save recent action.",
        )


@app.delete("/api/memory/actions/{action_id}", response_model=RecentActionDeleteResponse)
async def memory_delete_recent_action(action_id: str):
    try:
        return RecentActionDeleteResponse(**delete_recent_action(action_id))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not delete recent action.",
        )


@app.post("/api/memory/actions/clear", response_model=RecentActionsClearResponse)
async def memory_clear_recent_actions():
    try:
        return RecentActionsClearResponse(**clear_recent_actions())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not clear recent actions.",
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