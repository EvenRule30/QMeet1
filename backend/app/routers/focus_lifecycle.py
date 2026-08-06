from typing import NoReturn

from app.focus.context_boundary import (
    classify_focus_context,
    encode_focus_context_reason,
)
from app.focus.context import (
    NativeFocusContextError,
    NativeFocusContextRequest,
    NativeFocusContextResult,
    add_focus_context_verified,
    get_native_focus_context_health,
)

from fastapi import APIRouter, HTTPException
from app.focus.calendar_prep import (
    NativeCalendarFocusPrepError,
    NativeCalendarFocusPrepRequest,
    NativeCalendarFocusPrepResult,
    get_native_calendar_focus_prep_health,
    prepare_calendar_focus_verified,
)
from app.focus.lifecycle import (
    NativeFocusEndRequest,
    NativeFocusEndResult,
    NativeFocusLifecycleError,
    NativeFocusResumeRequest,
    NativeFocusResumeResult,
    NativeFocusStartRequest,
    NativeFocusStartResult,
    NativeFocusUpdateRequest,
    NativeFocusUpdateResult,
    end_focus_verified,
    get_native_focus_lifecycle_health,
    resume_focus_verified,
    start_focus_verified,
    update_focus_verified,
)
from app.focus.summary import (
    NativeFocusSummaryError,
    NativeFocusSummaryRequest,
    NativeFocusSummaryResult,
    get_native_focus_summary_health,
    save_focus_summary_verified,
)
from app.focus.tasks import (
    NativeFocusTasksError,
    NativeFocusTasksRequest,
    NativeFocusTasksResult,
    get_native_focus_task_health,
    link_focus_tasks_verified,
)
from app.focus.ownership import (
    NativeFocusOwnershipReadiness,
    get_native_focus_ownership_readiness,
)
from app.focus.semantic_update_preflight import (
    SemanticFocusUpdatePreflightRequest,
    SemanticFocusUpdatePreflightResult,
    semantic_focus_update_preflight,
)
from app.focus.semantic_lifecycle_preflight import (
    SemanticFocusLifecyclePreflightRequest,
    SemanticFocusLifecyclePreflightResult,
    semantic_focus_lifecycle_preflight,
)

router = APIRouter(prefix="/api/focus/lifecycle", tags=["focus-lifecycle"])


def _raise_lifecycle_error(exc: NativeFocusLifecycleError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "verified": False,
            "successClaimAllowed": False,
        },
    ) from exc


def _raise_summary_error(exc: NativeFocusSummaryError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "verified": False,
            "successClaimAllowed": False,
        },
    ) from exc


def _raise_tasks_error(exc: NativeFocusTasksError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "verified": False,
            "successClaimAllowed": False,
        },
    ) from exc


def _raise_calendar_prep_error(exc: NativeCalendarFocusPrepError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "verified": False,
            "successClaimAllowed": False,
        },
    ) from exc


def _raise_context_error(exc: NativeFocusContextError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "verified": False,
            "successClaimAllowed": False,
        },
    ) from exc


@router.post("/start", response_model=NativeFocusStartResult)
async def start_native_focus(
    request: NativeFocusStartRequest,
) -> NativeFocusStartResult:
    try:
        result = start_focus_verified(request)
    except NativeFocusLifecycleError as exc:
        _raise_lifecycle_error(exc)
    if not result.verified:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "verification_failed",
                "message": "Canonical Focus state did not verify the transition.",
                "verified": False,
                "successClaimAllowed": False,
            },
        )
    return result


@router.post("/update", response_model=NativeFocusUpdateResult)
async def update_native_focus(
    request: NativeFocusUpdateRequest,
) -> NativeFocusUpdateResult:
    try:
        result = update_focus_verified(request)
    except NativeFocusLifecycleError as exc:
        _raise_lifecycle_error(exc)
    if not result.verified:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "verification_failed",
                "message": "Canonical Focus state did not verify the update.",
                "verified": False,
                "successClaimAllowed": False,
            },
        )
    return result


@router.post("/end", response_model=NativeFocusEndResult)
async def end_native_focus(
    request: NativeFocusEndRequest,
) -> NativeFocusEndResult:
    try:
        result = end_focus_verified(request)
    except NativeFocusLifecycleError as exc:
        _raise_lifecycle_error(exc)
    if not result.verified:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "verification_failed",
                "message": "Canonical Focus state did not verify the terminal transition.",
                "verified": False,
                "successClaimAllowed": False,
            },
        )
    return result


@router.post("/resume", response_model=NativeFocusResumeResult)
async def resume_native_focus(
    request: NativeFocusResumeRequest,
) -> NativeFocusResumeResult:
    try:
        result = resume_focus_verified(request)
    except NativeFocusLifecycleError as exc:
        _raise_lifecycle_error(exc)
    if not result.verified:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "verification_failed",
                "message": "Canonical Focus state did not verify the resume transition.",
                "verified": False,
                "successClaimAllowed": False,
            },
        )
    return result


@router.post("/summary", response_model=NativeFocusSummaryResult)
async def save_native_focus_summary(
    request: NativeFocusSummaryRequest,
) -> NativeFocusSummaryResult:
    try:
        result = save_focus_summary_verified(request)
    except NativeFocusSummaryError as exc:
        _raise_summary_error(exc)
    if not result.verified:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "verification_failed",
                "message": "Canonical state did not verify the Focus summary receipt.",
                "verified": False,
                "successClaimAllowed": False,
            },
        )
    return result


@router.post("/tasks", response_model=NativeFocusTasksResult)
async def link_native_focus_tasks(
    request: NativeFocusTasksRequest,
) -> NativeFocusTasksResult:
    try:
        result = link_focus_tasks_verified(request)
    except NativeFocusTasksError as exc:
        _raise_tasks_error(exc)
    if not result.verified:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "verification_failed",
                "message": "Canonical state did not verify the Focus task receipt.",
                "verified": False,
                "successClaimAllowed": False,
            },
        )
    return result


@router.post("/calendar-prep", response_model=NativeCalendarFocusPrepResult)
async def prepare_native_calendar_focus(
    request: NativeCalendarFocusPrepRequest,
) -> NativeCalendarFocusPrepResult:
    try:
        result = prepare_calendar_focus_verified(request)
    except NativeCalendarFocusPrepError as exc:
        _raise_calendar_prep_error(exc)
    if not result.verified:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "verification_failed",
                "message": "Canonical state did not verify the combined calendar Focus receipt.",
                "verified": False,
                "successClaimAllowed": False,
            },
        )
    return result


@router.post("/context", response_model=NativeFocusContextResult)
async def add_native_focus_context(
    request: NativeFocusContextRequest,
) -> NativeFocusContextResult:
    try:
        result = add_focus_context_verified(request)
    except NativeFocusContextError as exc:
        _raise_context_error(exc)
    if not result.verified:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "verification_failed",
                "message": "Canonical state did not verify the Focus context receipt.",
                "verified": False,
                "successClaimAllowed": False,
            },
        )
    return result


@router.post(
    "/semantic-update/interpret",
    response_model=SemanticFocusUpdatePreflightResult,
)
async def interpret_semantic_focus_update(
    request: SemanticFocusUpdatePreflightRequest,
) -> SemanticFocusUpdatePreflightResult:
    return await semantic_focus_update_preflight(request)


@router.post(
    "/semantic/interpret",
    response_model=SemanticFocusLifecyclePreflightResult,
)
async def interpret_semantic_focus_lifecycle(
    request: SemanticFocusLifecyclePreflightRequest,
) -> SemanticFocusLifecyclePreflightResult:
    context_signal = classify_focus_context(request.message)
    if context_signal is not None:
        return SemanticFocusLifecyclePreflightResult(
            intent="update",
            possibleMutation=True,
            confidence=1.0,
            reason=encode_focus_context_reason(context_signal),
            sourceTurnId=request.sourceTurnId,
        )
    return await semantic_focus_lifecycle_preflight(request)


@router.get(
    "/ownership-readiness",
    response_model=NativeFocusOwnershipReadiness,
)
async def native_focus_ownership_readiness() -> NativeFocusOwnershipReadiness:
    return get_native_focus_ownership_readiness()


@router.get("/health")
async def native_focus_lifecycle_health() -> dict[str, object]:
    ownership_readiness = get_native_focus_ownership_readiness()
    return {
        "ok": True,
        "ownership": "native",
        "scope": [
            "start_focus",
            "replace_focus",
            "update_focus",
            "end_focus",
            "complete_focus",
            "resume_focus",
            "save_focus_summary",
            "link_focus_tasks",
            "prepare_calendar_focus",
            "semantic_update_interpret",
            "semantic_lifecycle_interpret",
            "add_focus_context",
        ],
        "health": get_native_focus_lifecycle_health(),
        "summaryHealth": get_native_focus_summary_health(),
        "taskHealth": get_native_focus_task_health(),
        "calendarPrepHealth": get_native_calendar_focus_prep_health(),
        "contextHealth": get_native_focus_context_health(),
        "ownershipReadiness": ownership_readiness.model_dump(),
    }
