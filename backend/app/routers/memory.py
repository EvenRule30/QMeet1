from fastapi import APIRouter, HTTPException

from app.memory_store import (
    MemoryStoreError,
    clear_active_session,
    clear_completed_memory_tasks,
    clear_memory_context,
    clear_memory_notes,
    clear_recent_actions,
    clear_recent_focus_sessions,
    create_memory_note,
    create_memory_task,
    create_recent_action,
    delete_memory_note,
    delete_memory_task,
    delete_recent_action,
    delete_recent_focus_session,
    export_memory_context,
    get_active_session,
    get_memory_context,
    get_memory_status,
    import_memory_context,
    list_memory_notes,
    list_memory_tasks,
    list_recent_actions,
    list_recent_focus_sessions,
    replace_active_session,
    replace_memory_context,
    replace_memory_notes,
    replace_memory_tasks,
    replace_recent_actions,
    replace_recent_focus_sessions,
    update_active_session,
    update_memory_task,
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
)


router = APIRouter(prefix="/api/memory", tags=["memory"])


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
        recent_focus_sessions = (
            [_model_to_dict(session) for session in req.recentFocusSessions]
            if "recentFocusSessions" in sent_fields
            else None
        )

        return MemoryContextResponse(
            **replace_memory_context(
                tasks=[_model_to_dict(task) for task in req.tasks],
                recent_actions=[_model_to_dict(action) for action in req.recentActions],
                notes=[_model_to_dict(note) for note in req.notes],
                active_session=_model_to_dict(req.activeSession),
                recent_focus_sessions=recent_focus_sessions,
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
        return MemoryContextResponse(
            **import_memory_context(
                tasks=[_model_to_dict(task) for task in req.tasks],
                recent_actions=[_model_to_dict(action) for action in req.recentActions],
                notes=[_model_to_dict(note) for note in req.notes],
                active_session=_model_to_dict(req.activeSession),
                recent_focus_sessions=[
                    _model_to_dict(session) for session in req.recentFocusSessions
                ],
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
    try:
        return MemoryContextClearResponse(**clear_memory_context())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not clear memory context.",
        )


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
async def memory_replace_active_session(req: ActiveSessionReplaceRequest):
    try:
        return ActiveSessionResponse(
            **replace_active_session(_model_to_dict(req.activeSession))
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save the active session.",
        )


@router.patch("/session", response_model=ActiveSessionResponse)
async def memory_update_active_session(req: ActiveSessionUpdateRequest):
    try:
        sent_fields = _model_fields_set(req)
        return ActiveSessionResponse(
            **update_active_session(
                title=req.title if "title" in sent_fields else None,
                mode=req.mode if "mode" in sent_fields else None,
                goal=req.goal if "goal" in sent_fields else None,
                pinned_note_ids=req.pinnedNoteIds if "pinnedNoteIds" in sent_fields else None,
                linked_task_ids=req.linkedTaskIds if "linkedTaskIds" in sent_fields else None,
                summary=req.summary if "summary" in sent_fields else None,
                update_summary="summary" in sent_fields,
            )
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not update the active session.",
        )


@router.delete("/session", response_model=ActiveSessionClearResponse)
async def memory_clear_active_session():
    try:
        return ActiveSessionClearResponse(**clear_active_session())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not clear the active session.",
        )


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
async def memory_replace_recent_focus_sessions(req: RecentFocusSessionsReplaceRequest):
    try:
        return RecentFocusSessionsResponse(
            **replace_recent_focus_sessions(
                [_model_to_dict(session) for session in req.recentFocusSessions]
            )
        )
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not save recent focus sessions.",
        )


@router.post("/sessions/recent/clear", response_model=RecentFocusSessionsClearResponse)
async def memory_clear_recent_focus_sessions():
    try:
        return RecentFocusSessionsClearResponse(**clear_recent_focus_sessions())
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not clear recent focus sessions.",
        )


@router.delete(
    "/sessions/recent/{session_id}",
    response_model=RecentFocusSessionDeleteResponse,
)
async def memory_delete_recent_focus_session(session_id: str):
    try:
        return RecentFocusSessionDeleteResponse(**delete_recent_focus_session(session_id))
    except MemoryStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not delete recent focus session.",
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
        return MemoryTasksResponse(
            **replace_memory_tasks([_model_to_dict(task) for task in req.tasks])
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
        return MemoryClearCompletedResponse(**clear_completed_memory_tasks())
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
        return MemoryTasksResponse(
            **update_memory_task(
                task_id=task_id,
                title=req.title,
                completed_at=req.completedAt,
                update_completed_at="completedAt" in sent_fields,
            )
        )
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
        return MemoryTaskDeleteResponse(**delete_memory_task(task_id))
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
