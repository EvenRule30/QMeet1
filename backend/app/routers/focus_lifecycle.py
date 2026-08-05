from typing import NoReturn

from fastapi import APIRouter, HTTPException

from app.focus.lifecycle import (
    NativeFocusLifecycleError,
    NativeFocusStartRequest,
    NativeFocusStartResult,
    NativeFocusUpdateRequest,
    NativeFocusUpdateResult,
    get_native_focus_lifecycle_health,
    start_focus_verified,
    update_focus_verified,
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
            "semantic_update_interpret",
            "semantic_lifecycle_interpret",
        ],
        "health": get_native_focus_lifecycle_health(),
    }
