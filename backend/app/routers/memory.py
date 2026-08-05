from fastapi import APIRouter, HTTPException

from app.focus.tasks import get_active_focus_linked_task_ids
from app.memory_store import (
    MemoryStoreError,
    clear_memory_notes,
    clear_recent_actions,
    clear_visual_context,
    create_memory_note,
    create_memory_task,
    create_recent_action,
    create_visual_observation,
    delete_memory_note,
    delete_memory_task,
    delete_recent_action,
    delete_visual_observation,
    export_memory_context,
    get_active_session,
    get_memory_context,
    get_memory_status,
    get_visual_context,
    import_memory_context,
    list_memory_notes,
    list_memory_tasks,
    list_recent_actions,
    list_recent_focus_sessions,
    replace_memory_context,
    replace_memory_notes,
    replace_memory_tasks,
    replace_recent_actions,
    replace_visual_context,
    update_memory_task,
    update_visual_context,
)
from app.schemas import (
    ActiveSessionClearResponse,
    ActiveSessionReplaceRequest,
    ActiveSessionResponse,
    ActiveSessionUpdateRequest,
    MemoryClearCompletedResponse,
    MemoryContextClearResponse,
    MemoryContextExportResponse,
    MemoryContextImportRequest,
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
    RecentFocusSessionDeleteResponse,
    RecentFocusSessionsClearResponse,
    RecentFocusSessionsReplaceRequest,
    RecentFocusSessionsResponse,
    VisualContextClearResponse,
    VisualContextReplaceRequest,
    VisualContextResponse,
    VisualContextUpdateRequest,
    VisualObservationCreateRequest,
    VisualObservationCreateResponse,
    VisualObservationDeleteResponse,
)

router = APIRouter(prefix="/api/memory", tags=["memory"])

# Phase 20G contract: the broad compatibility memory API may carry a Focus
# projection for reads, but it can no longer authorize or mutate that projection.
FOCUS_PROJECTION_READ_ONLY = True
_RETIRED_FOCUS_WRITE_DETAIL = (
    "This compatibility Focus projection write route is retired. "
    "Use /api/focus/lifecycle verified native operations instead."
)


def _model_to_dict(model) -> dict:
    if model is None:
        return None
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)


def _model_fields_set(model) -> set[str]:
    """Return fields explicitly sent by the client for Pydantic v1 or v2."""
    if hasattr(model, "model_fields_set"):
        return set(model.model_fields_set)
    return set(getattr(model, "__fields_set__", set()))


def _preserve_focus_projection() -> tuple[dict | None, list[dict]]:
    """Read the current compatibility projection for pass-through preservation.

    Generic memory writes are still allowed to replace Tasks, Notes, Actions, and
    visual context. Their browser payload is never trusted for activeSession or
    recentFocusSessions; those fields are copied from the backend's current state.
    """

    current = get_memory_context()
    active_session = current.get("activeSession")
    recent_focus_sessions = current.get("recentFocusSessions")
    return (
        active_session if isinstance(active_session, dict) else None,
        recent_focus_sessions if isinstance(recent_focus_sessions, list) else [],
    )


def _task_id(task: object) -> str:
    if not isinstance(task, dict):
        return ""
    return str(task.get("id", "")).strip()


def _preserve_active_focus_linked_tasks(requested_tasks: list[dict]) -> list[dict]:
    """Protect the canonical identity of tasks owned by the open Focus.

    Browser compatibility writes may complete or reopen a linked task, but they
    cannot delete it or rewrite the id/title/createdAt tuple verified by the Focus
    relationship receipt. Ordinary unlinked tasks remain browser-managed.
    """

    protected_ids = get_active_focus_linked_task_ids()
    if not protected_ids:
        return requested_tasks

    current_tasks = list_memory_tasks().get("tasks", [])
    canonical_by_id = {
        _task_id(task): task
        for task in current_tasks
        if _task_id(task) in protected_ids
    }
    next_tasks: list[dict] = []
    seen: set[str] = set()
    for task in requested_tasks:
        task_id = _task_id(task)
        canonical = canonical_by_id.get(task_id)
        if canonical is None:
            next_tasks.append(task)
            if task_id:
                seen.add(task_id)
            continue

        protected_task = dict(canonical)
        completed_at = task.get("completedAt") if isinstance(task, dict) else None
        if isinstance(completed_at, str) and completed_at.strip():
            protected_task["completedAt"] = completed_at.strip()
        else:
            protected_task.pop("completedAt", None)
        next_tasks.append(protected_task)
        seen.add(task_id)

    for task_id, canonical in canonical_by_id.items():
        if task_id not in seen:
            next_tasks.append(dict(canonical))
    return next_tasks


def _protected_focus_task(task_id: str) -> bool:
    return task_id.strip() in get_active_focus_linked_task_ids()


def _retired_focus_task_delete() -> None:
    raise HTTPException(
        status_code=409,
        detail=(
            "This task is linked to the active verified Focus and cannot be deleted "
            "through compatibility memory controls. End the Focus first, or keep "
            "the task and mark it complete."
        ),
    )


def _retired_focus_projection_write() -> None:
    raise HTTPException(status_code=409, detail=_RETIRED_FOCUS_WRITE_DETAIL)


@router.get("/status", response_model=MemoryStatusResponse)
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


@router.get("/context", response_model=MemoryContextResponse)
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


@router.put("/context", response_model=MemoryContextResponse)
async def memory_replace_context(req: MemoryContextReplaceRequest):
    try:
        sent_fields = _model_fields_set(req)
        active_session, recent_focus_sessions = _preserve_focus_projection()
        visual_context = (
            _model_to_dict(req.visualContext)
            if "visualContext" in sent_fields
            else None
        )
        return MemoryContextResponse(
            **replace_memory_context(
                tasks=_preserve_active_focus_linked_tasks(
                    [_model_to_dict(task) for task in req.tasks]
                ),
                recent_actions=[_model_to_dict(action) for action in req.recentActions],
                notes=[_model_to_dict(note) for note in req.notes],
                active_session=active_session,
                recent_focus_sessions=recent_focus_sessions,
                visual_context=visual_context,
            )
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save memory context.",
        )


@router.get("/export", response_model=MemoryContextExportResponse)
async def memory_export_context():
    try:
        return MemoryContextExportResponse(**export_memory_context())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not export memory context.",
        )


@router.post("/import", response_model=MemoryContextResponse)
async def memory_import_context(req: MemoryContextImportRequest):
    try:
        active_session, recent_focus_sessions = _preserve_focus_projection()
        return MemoryContextResponse(
            **import_memory_context(
                tasks=_preserve_active_focus_linked_tasks(
                    [_model_to_dict(task) for task in req.tasks]
                ),
                recent_actions=[_model_to_dict(action) for action in req.recentActions],
                notes=[_model_to_dict(note) for note in req.notes],
                active_session=active_session,
                recent_focus_sessions=recent_focus_sessions,
                visual_context=_model_to_dict(req.visualContext),
            )
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not import memory context.",
        )


@router.post("/clear", response_model=MemoryContextClearResponse)
async def memory_clear_context():
    # A broad clear previously erased the compatibility Focus projection as a
    # side effect. Phase 20G retires that ambiguous write; callers must clear
    # Notes, Tasks, Actions, or visual context through their scoped endpoints.
    _retired_focus_projection_write()


@router.get("/session", response_model=ActiveSessionResponse)
async def memory_active_session():
    try:
        return ActiveSessionResponse(**get_active_session())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read the active session.",
        )


@router.put("/session", response_model=ActiveSessionResponse)
async def memory_replace_active_session(_req: ActiveSessionReplaceRequest):
    _retired_focus_projection_write()


@router.patch("/session", response_model=ActiveSessionResponse)
async def memory_update_active_session(_req: ActiveSessionUpdateRequest):
    _retired_focus_projection_write()


@router.delete("/session", response_model=ActiveSessionClearResponse)
async def memory_clear_active_session():
    _retired_focus_projection_write()


@router.get("/sessions/recent", response_model=RecentFocusSessionsResponse)
async def memory_recent_focus_sessions():
    try:
        return RecentFocusSessionsResponse(**list_recent_focus_sessions())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read recent focus sessions.",
        )


@router.put("/sessions/recent", response_model=RecentFocusSessionsResponse)
async def memory_replace_recent_focus_sessions(
    _req: RecentFocusSessionsReplaceRequest,
):
    _retired_focus_projection_write()


@router.post("/sessions/recent/clear", response_model=RecentFocusSessionsClearResponse)
async def memory_clear_recent_focus_sessions():
    _retired_focus_projection_write()


@router.delete(
    "/sessions/recent/{session_id}",
    response_model=RecentFocusSessionDeleteResponse,
)
async def memory_delete_recent_focus_session(_session_id: str):
    _retired_focus_projection_write()


@router.get("/visual", response_model=VisualContextResponse)
async def memory_visual_context():
    try:
        return VisualContextResponse(**get_visual_context())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not read visual context.",
        )


@router.put("/visual", response_model=VisualContextResponse)
async def memory_replace_visual_context(req: VisualContextReplaceRequest):
    try:
        return VisualContextResponse(
            **replace_visual_context(_model_to_dict(req.visualContext))
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save visual context.",
        )


@router.patch("/visual", response_model=VisualContextResponse)
async def memory_update_visual_context(req: VisualContextUpdateRequest):
    try:
        sent_fields = _model_fields_set(req)
        return VisualContextResponse(
            **update_visual_context(
                enabled=req.enabled if "enabled" in sent_fields else None,
                last_observation=(
                    _model_to_dict(req.lastObservation)
                    if "lastObservation" in sent_fields
                    else None
                ),
                recent_observations=(
                    [_model_to_dict(item) for item in (req.recentObservations or [])]
                    if "recentObservations" in sent_fields
                    else None
                ),
                update_last_observation="lastObservation" in sent_fields,
                update_recent_observations="recentObservations" in sent_fields,
            )
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not update visual context.",
        )


@router.post("/visual/observations", response_model=VisualObservationCreateResponse)
async def memory_create_visual_observation(req: VisualObservationCreateRequest):
    try:
        return VisualObservationCreateResponse(
            **create_visual_observation(
                summary=req.summary,
                source=req.source,
                captured_at=req.capturedAt or "",
                confidence=req.confidence,
                related_focus_id=req.relatedFocusId,
            )
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save visual observation.",
        )


@router.post("/visual/clear", response_model=VisualContextClearResponse)
async def memory_clear_visual_context():
    try:
        return VisualContextClearResponse(**clear_visual_context())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not clear visual context.",
        )


@router.delete(
    "/visual/observations/{observation_id}",
    response_model=VisualObservationDeleteResponse,
)
async def memory_delete_visual_observation(observation_id: str):
    try:
        return VisualObservationDeleteResponse(
            **delete_visual_observation(observation_id)
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not delete visual observation.",
        )


@router.get("/tasks", response_model=MemoryTasksResponse)
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


@router.put("/tasks", response_model=MemoryTasksResponse)
async def memory_replace_tasks(req: MemoryTasksReplaceRequest):
    try:
        requested_tasks = [_model_to_dict(task) for task in req.tasks]
        return MemoryTasksResponse(
            **replace_memory_tasks(
                _preserve_active_focus_linked_tasks(requested_tasks)
            )
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save memory tasks.",
        )


@router.post("/tasks", response_model=MemoryTasksResponse)
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


@router.post("/tasks/clear-completed", response_model=MemoryClearCompletedResponse)
async def memory_clear_completed_tasks():
    try:
        current_tasks = list_memory_tasks().get("tasks", [])
        protected_ids = get_active_focus_linked_task_ids()
        next_tasks = [
            task
            for task in current_tasks
            if not task.get("completedAt") or _task_id(task) in protected_ids
        ]
        removed_count = len(current_tasks) - len(next_tasks)
        response = replace_memory_tasks(next_tasks)
        return MemoryClearCompletedResponse(
            ok=True,
            provider=response.get("provider", "local-json"),
            removedCount=removed_count,
            tasks=response.get("tasks", next_tasks),
            message=(
                f"Cleared {removed_count} completed task"
                f"{'s' if removed_count != 1 else ''}."
            ),
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not clear completed memory tasks.",
        )


@router.patch("/tasks/{task_id}", response_model=MemoryTasksResponse)
async def memory_update_task(task_id: str, req: MemoryTaskUpdateRequest):
    try:
        sent_fields = _model_fields_set(req)
        if _protected_focus_task(task_id) and "title" in sent_fields:
            current_task = next(
                (
                    task
                    for task in list_memory_tasks().get("tasks", [])
                    if _task_id(task) == task_id.strip()
                ),
                None,
            )
            current_title = (
                str(current_task.get("title", "")).strip()
                if isinstance(current_task, dict)
                else ""
            )
            if req.title.strip() and req.title.strip() != current_title:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "The title of a task linked to the active verified Focus "
                        "cannot be changed through compatibility memory controls."
                    ),
                )
        return MemoryTasksResponse(
            **update_memory_task(
                task_id=task_id,
                title=req.title,
                completed_at=req.completedAt,
                update_completed_at="completedAt" in sent_fields,
            )
        )
    except HTTPException:
        raise
    except MemoryStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not update memory task.",
        )


@router.delete("/tasks/{task_id}", response_model=MemoryTaskDeleteResponse)
async def memory_delete_task(task_id: str):
    try:
        if _protected_focus_task(task_id):
            _retired_focus_task_delete()
        return MemoryTaskDeleteResponse(**delete_memory_task(task_id))
    except HTTPException:
        raise
    except MemoryStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not delete memory task.",
        )


@router.get("/notes", response_model=MemoryNotesResponse)
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


@router.put("/notes", response_model=MemoryNotesResponse)
async def memory_replace_notes(req: MemoryNotesReplaceRequest):
    try:
        return MemoryNotesResponse(
            **replace_memory_notes([_model_to_dict(note) for note in req.notes])
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save memory notes.",
        )


@router.post("/notes", response_model=MemoryNotesResponse)
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


@router.post("/notes/clear", response_model=MemoryNotesClearResponse)
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


@router.delete("/notes/{note_id}", response_model=MemoryNoteDeleteResponse)
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


@router.get("/actions", response_model=RecentActionsResponse)
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


@router.put("/actions", response_model=RecentActionsResponse)
async def memory_replace_recent_actions(req: RecentActionsReplaceRequest):
    try:
        return RecentActionsResponse(
            **replace_recent_actions([_model_to_dict(action) for action in req.recentActions])
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save recent actions.",
        )


@router.post("/actions", response_model=RecentActionsResponse)
async def memory_create_recent_action(req: RecentActionCreateRequest):
    try:
        return RecentActionsResponse(
            **create_recent_action(
                label=req.label,
                detail=req.detail,
            )
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save recent action.",
        )


@router.post("/actions/clear", response_model=RecentActionsClearResponse)
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


@router.delete("/actions/{action_id}", response_model=RecentActionDeleteResponse)
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
