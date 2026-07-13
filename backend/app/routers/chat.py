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
from app.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/status")
async def status():
    return get_public_status()


@router.post("/chat", response_model=ChatResponse)
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


@router.post("/chat/stream")
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


@router.post("/reset")
async def reset():
    reset_conversation()
    return {"ok": True}
