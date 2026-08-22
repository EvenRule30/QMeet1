from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.agent import (
    AgentUserFacingError,
    generate_reply,
    get_public_status,
    reset_conversation,
    sse_event,
    stream_reply,
)
from app.conversation_lane import ConversationLaneRequest, stream_conversation_lane
from app.daily_brief import generate_daily_brief, is_daily_brief_request, stream_daily_brief
from app.schemas import ChatRequest, ChatResponse
from app.work_context import (
    WorkContextError,
    clear_background_work_context,
    get_background_work_context,
    prepare_background_chat_message,
    record_background_assistant_reply,
)

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/status")
async def status():
    return get_public_status()


@router.get("/work-context")
async def work_context():
    try:
        return get_background_work_context()
    except WorkContextError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/work-context")
async def clear_work_context():
    try:
        return clear_background_work_context()
    except WorkContextError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    try:
        if is_daily_brief_request(message):
            reply = await generate_daily_brief(
                ConversationLaneRequest(userMessage=message)
            )
            return ChatResponse(reply=reply, state="speaking")

        contextual_message, _visible_user_message = prepare_background_chat_message(
            message
        )
        reply = await generate_reply(contextual_message)
        record_background_assistant_reply(reply)
        return ChatResponse(reply=reply, state="speaking")
    except (AgentUserFacingError, WorkContextError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="QMeet backend hit an unexpected error.",
        ) from exc


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    async def event_generator():
        assistant_reply_parts: list[str] = []
        try:
            if is_daily_brief_request(message):
                yield sse_event("start", {"ok": True})
                async for chunk in stream_daily_brief(
                    ConversationLaneRequest(userMessage=message)
                ):
                    yield sse_event("chunk", {"text": chunk})
                yield sse_event("done", {"ok": True})
                return

            contextual_message, _visible_user_message = prepare_background_chat_message(
                message
            )
            yield sse_event("start", {"ok": True})
            async for chunk in stream_reply(contextual_message):
                assistant_reply_parts.append(chunk)
                yield sse_event("chunk", {"text": chunk})
            record_background_assistant_reply("".join(assistant_reply_parts))
            yield sse_event("done", {"ok": True})
        except (AgentUserFacingError, WorkContextError) as exc:
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


@router.post("/chat/conversation/stream")
async def conversation_stream(req: ConversationLaneRequest):
    """Read-only visible conversation lane after deterministic routing.
    This route intentionally does not call the legacy background Focus wrapper.
    Its path also remains outside the Focus/background middleware observation
    allowlists, so a turn already classified as conversation cannot gain a
    second visible Focus owner here.
    """

    async def event_generator():
        try:
            yield sse_event("start", {"ok": True})
            streamer = (
                stream_daily_brief
                if is_daily_brief_request(req.userMessage)
                else stream_conversation_lane
            )
            async for chunk in streamer(req):
                yield sse_event("chunk", {"text": chunk})
            yield sse_event("done", {"ok": True})
        except AgentUserFacingError as exc:
            yield sse_event("error", {"message": str(exc)})
        except Exception:
            yield sse_event(
                "error",
                {"message": "QMeet backend hit an unexpected conversation streaming error."},
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


@router.post("/reset")
async def reset():
    reset_conversation()
    return {"ok": True}
