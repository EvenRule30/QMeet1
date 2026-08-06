from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app import memory_store
from app.focus.middleware import focus_response_mode, focus_route_mode
from app.focus.native_read_middleware import (
    NATIVE_WRITE_CONFIRMATION_SCOPE,
    NATIVE_WRITE_ROUTE_SCOPE,
    native_read_route_mode,
    native_read_routes_enabled,
    native_write_route_mode,
    native_write_routes_enabled,
)
from app.focus.models import (
    ExactRouteObservationRequest,
    ObserveTurnRequest,
    PlanPreviewRequest,
    ToolResultRequest,
)
from app.focus.ownership import get_native_focus_ownership_readiness
from app.focus.planner import (
    DEFAULT_MODEL,
    focus_mode,
    observe_turn,
    planner_enabled,
    preview_turn_plan,
)
from app.focus.readiness import (
    build_promotion_readiness,
    update_last_successful_validation,
)
from app.focus.store import (
    FocusStoreError,
    event_count,
    exact_route_observation_summary,
    event_file,
    get_state,
    list_events,
    record_exact_route_observation,
    record_tool_result,
    reset_store,
    response_selection_summary,
    route_selection_summary,
)
from app.focus.task_lineage import (
    get_active_focus_lineage_linked_task_ids,
)

router = APIRouter(prefix="/api/focus", tags=["focus"])
_SESSION_STARTED_AT = datetime.now().astimezone().isoformat()


def _status_message(planner_mode: str) -> str:
    normalized_mode = planner_mode.strip().casefold()
    if normalized_mode == "active":
        return "Focus planner is active with guarded legacy safeguards."
    if normalized_mode == "off":
        return "Focus planner is disabled; the legacy focus system remains available."
    return "Focus is running beside the legacy focus system."


def _ordered_active_focus_linked_task_ids() -> list[str]:
    """Return canonical linked IDs in stable Memory task order.

    The verified Focus-task receipt owns membership. Memory contributes only the
    display order used by task reads and ordinal references such as "first task".
    """

    linked_task_ids = get_active_focus_lineage_linked_task_ids()
    if not linked_task_ids:
        return []

    try:
        memory_tasks = memory_store.list_memory_tasks().get("tasks", [])
    except memory_store.MemoryStoreError:
        return sorted(linked_task_ids)

    ordered_ids: list[str] = []
    seen: set[str] = set()
    for task in memory_tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id", "")).strip()
        if task_id in linked_task_ids and task_id not in seen:
            ordered_ids.append(task_id)
            seen.add(task_id)

    ordered_ids.extend(sorted(linked_task_ids - seen))
    return ordered_ids


@router.get("/status")
async def focus_status():
    planner_mode = focus_mode()
    response_mode = focus_response_mode()
    route_mode = focus_route_mode()
    native_read_mode = native_read_route_mode()
    native_read_enabled = native_read_routes_enabled()
    native_write_mode = native_write_route_mode()
    native_write_enabled = native_write_routes_enabled()
    is_planner_enabled = planner_enabled()
    response_selection = response_selection_summary()
    route_selection = route_selection_summary()
    exact_route_observation = exact_route_observation_summary()
    session_response_selection = response_selection_summary(
        since_created_at=_SESSION_STARTED_AT,
    )
    session_route_selection = route_selection_summary(
        since_created_at=_SESSION_STARTED_AT,
    )
    session_exact_route_observation = exact_route_observation_summary(
        since_created_at=_SESSION_STARTED_AT,
    )
    ownership_readiness = (
        get_native_focus_ownership_readiness().model_dump(mode="json")
    )
    promotion_readiness = build_promotion_readiness(
        response_selection=session_response_selection,
        route_selection=session_route_selection,
        exact_route_observation=session_exact_route_observation,
        planner_mode=planner_mode,
        response_mode=response_mode,
        route_mode=route_mode,
        planner_enabled=is_planner_enabled,
        ownership_readiness=ownership_readiness,
    )
    promotion_readiness["lastSuccessfulValidation"] = (
        update_last_successful_validation(
            readiness=promotion_readiness,
            session_started_at=_SESSION_STARTED_AT,
            planner_mode=planner_mode,
            response_mode=response_mode,
            route_mode=route_mode,
            planner_enabled=is_planner_enabled,
        )
    )
    return {
        "ok": True,
        "mode": planner_mode,
        "responseMode": response_mode,
        "routeMode": route_mode,
        "nativeReadRouteMode": native_read_mode,
        "nativeReadRoutesEnabled": native_read_enabled,
        "nativeWriteRouteMode": native_write_mode,
        "nativeWriteRoutesEnabled": native_write_enabled,
        "nativeWriteRouteScope": list(NATIVE_WRITE_ROUTE_SCOPE),
        "nativeWriteConfirmationScope": list(
            NATIVE_WRITE_CONFIRMATION_SCOPE
        ),
        "plannerEnabled": is_planner_enabled,
        "model": DEFAULT_MODEL,
        "eventCount": event_count(),
        "path": str(event_file()),
        "responseSelection": response_selection,
        "routeSelection": route_selection,
        "exactRouteObservation": exact_route_observation,
        "ownershipReadiness": ownership_readiness,
        "promotionReadiness": promotion_readiness,
        "currentSession": {
            "startedAt": _SESSION_STARTED_AT,
            "responseSelection": session_response_selection,
            "routeSelection": session_route_selection,
            "exactRouteObservation": session_exact_route_observation,
        },
        "message": _status_message(planner_mode),
    }


@router.get("/state")
async def focus_state():
    try:
        state = get_state()
        return {
            "ok": True,
            "state": state.model_dump(mode="json"),
            "linkedTaskIds": _ordered_active_focus_linked_task_ids(),
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


@router.post("/route-observation")
async def focus_route_observation(req: ExactRouteObservationRequest):
    try:
        state = record_exact_route_observation(
            command=req.command,
            source_turn_id=req.sourceTurnId,
            requires_confirmation=req.requiresConfirmation,
        )
        return {
            "ok": True,
            "state": state.model_dump(mode="json"),
            "eventCount": event_count(),
        }
    except FocusStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
            "message": (
                "Focus event log cleared. Legacy focus data was not changed."
            ),
        }
    except FocusStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
