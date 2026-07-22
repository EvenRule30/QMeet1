from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.focus.models import (
    ObserveTurnRequest,
    PlanPreviewRequest,
    ToolResultRequest,
)
from app.focus.planner import (
    DEFAULT_MODEL,
    focus_mode,
    observe_turn,
    planner_enabled,
    preview_turn_plan,
)
from app.focus.store import (
    FocusStoreError,
    event_count,
    event_file,
    get_state,
    list_events,
    record_tool_result,
    reset_store,
)

router = APIRouter(prefix="/api/focus", tags=["focus"])


@router.get("/status")
async def focus_status():
    return {
        "ok": True,
        "mode": focus_mode(),
        "plannerEnabled": planner_enabled(),
        "model": DEFAULT_MODEL,
        "eventCount": event_count(),
        "path": str(event_file()),
        "message": "Focus is running beside the legacy focus system.",
    }


@router.get("/state")
async def focus_state():
    try:
        state = get_state()
        return {
            "ok": True,
            "state": state.model_dump(mode="json"),
            "eventCount": event_count(),
        }
    except FocusStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/events")
async def focus_events(limit: int = Query(default=200, ge=1, le=1000)):
    try:
        events = list_events(limit=limit)
        return {
            "ok": True,
            "events": [event.model_dump(mode="json") for event in events],
            "eventCount": event_count(),
        }
    except FocusStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/preview")
async def focus_preview(req: PlanPreviewRequest):
    plan = await preview_turn_plan(req.message, source=req.source)
    return {
        "ok": True,
        "plan": plan.model_dump(mode="json"),
        "state": get_state().model_dump(mode="json"),
    }


@router.post("/observe")
async def focus_observe(req: ObserveTurnRequest):
    plan, state = await observe_turn(req)
    return {
        "ok": True,
        "plan": plan.model_dump(mode="json"),
        "state": state.model_dump(mode="json"),
    }


@router.post("/tool-result")
async def focus_tool_result(req: ToolResultRequest):
    try:
        state = record_tool_result(
            tool=req.tool,
            success=req.success,
            summary=req.summary,
            result_ids=req.resultIds,
            source_turn_id=req.sourceTurnId,
            source="manual-tool-result",
        )
        return {"ok": True, "state": state.model_dump(mode="json")}
    except FocusStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/reset")
async def focus_reset():
    try:
        state = reset_store()
        return {
            "ok": True,
            "state": state.model_dump(mode="json"),
            "message": "Focus event log cleared. Legacy focus data was not changed.",
        }
    except FocusStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
