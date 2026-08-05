from typing import NoReturn

from fastapi import APIRouter, HTTPException

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
    return await semantic_focus_lifecycle_preflight(request)


@router.get("/health")
async def native_focus_lifecycle_health() -> dict[str, object]:
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
            "semantic_update_interpret",
            "semantic_lifecycle_interpret",
        ],
        "health": get_native_focus_lifecycle_health(),
        "summaryHealth": get_native_focus_summary_health(),
    }
