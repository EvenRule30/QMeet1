from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent import AgentUserFacingError, sse_event
from app.tool_continuation import (
    ToolContinuationRequest,
    continuation_allowed_for_capability,
    stream_tool_continuation,
)


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/tool-continuation/stream")
async def tool_continuation_stream(req: ToolContinuationRequest):
    if not req.verified:
        raise HTTPException(
            status_code=409,
            detail="Tool continuation requires a verified deterministic result.",
        )
    if not req.success:
        raise HTTPException(
            status_code=409,
            detail="Phase 21A continuation currently accepts successful tool results only.",
        )

    async def event_generator():
        if not continuation_allowed_for_capability(req.capability):
            yield sse_event(
                "start",
                {"ok": True, "continuation": False, "reason": "silent_capability"},
            )
            yield sse_event(
                "done",
                {"ok": True, "continuation": False, "reason": "silent_capability"},
            )
            return

        try:
            yield sse_event("start", {"ok": True, "continuation": True})
            async for chunk in stream_tool_continuation(req):
                yield sse_event("chunk", {"text": chunk})
            yield sse_event("done", {"ok": True, "continuation": True})
        except AgentUserFacingError as exc:
            yield sse_event("error", {"message": str(exc)})
        except Exception:
            yield sse_event(
                "error",
                {
                    "message": (
                        "QMeet backend hit an unexpected post-tool continuation error."
                    )
                },
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
