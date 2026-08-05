from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.focus.calendar_prep import get_native_calendar_focus_prep_health
from app.focus.lifecycle import get_native_focus_lifecycle_health
from app.focus.summary import get_native_focus_summary_health
from app.focus.tasks import get_native_focus_task_health

OwnershipOperationStatus = Literal["verified", "unexercised", "degraded"]
OwnershipReadiness = Literal["ready", "collecting", "blocked"]


class NativeFocusOwnershipOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str
    owner: Literal["backend-native"] = "backend-native"
    status: OwnershipOperationStatus
    attemptCount: int = 0
    verifiedCount: int = 0
    failedCount: int = 0
    lastOutcome: str = ""
    lastFailureCode: str = ""
    lastUpdatedAt: str = ""


class NativeFocusLegacyProjectionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retired: bool = True
    fallbackBlocked: bool = True
    ownershipVersion: str = "phase20f"
    quarantinedCommands: list[str] = Field(default_factory=list)
    remainingBrowserOwnedWriteSurfaces: list[str] = Field(default_factory=list)


class NativeFocusOwnershipReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    ownership: Literal["backend-native"] = "backend-native"
    readiness: OwnershipReadiness
    readyForLegacyProjectionRetirement: bool
    verifiedOperationCount: int
    requiredOperationCount: int
    operations: list[NativeFocusOwnershipOperation]
    legacyProjection: NativeFocusLegacyProjectionStatus
    blockers: list[str] = Field(default_factory=list)
    evidenceNeeded: list[str] = Field(default_factory=list)


_QUARANTINED_COMMANDS = [
    "start-focus-session",
    "update-focus-session",
    "resume-last-focus-session",
    "end-focus-session",
    "end-focus-with-summary",
    "wrap-up-meeting-focus",
    "save-focus-summary",
    "focus-to-tasks",
    "create-meeting-follow-up-tasks",
    "prepare-calendar-focus",
]


def _section(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    return value if isinstance(value, dict) else {}


def _integer(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _text(value: object) -> str:
    return str(value or "").strip()


def _operation(
    operation: str,
    section: dict[str, object],
) -> NativeFocusOwnershipOperation:
    attempts = _integer(section.get("attemptCount"))
    verified = _integer(section.get("verifiedCount"))
    failed = _integer(section.get("failedCount"))
    last_outcome = _text(section.get("lastOutcome"))
    last_failure = _text(section.get("lastFailureCode"))

    if last_outcome == "failed" or last_failure:
        status: OwnershipOperationStatus = "degraded"
    elif attempts == 0 or verified == 0:
        status = "unexercised"
    else:
        status = "verified"

    return NativeFocusOwnershipOperation(
        operation=operation,
        status=status,
        attemptCount=attempts,
        verifiedCount=verified,
        failedCount=failed,
        lastOutcome=last_outcome,
        lastFailureCode=last_failure,
        lastUpdatedAt=_text(section.get("lastUpdatedAt")),
    )


def get_native_focus_ownership_readiness() -> NativeFocusOwnershipReadiness:
    lifecycle_health = get_native_focus_lifecycle_health()
    summary_health = get_native_focus_summary_health()
    task_health = get_native_focus_task_health()
    calendar_health = get_native_calendar_focus_prep_health()

    operations = [
        _operation("start_focus", _section(lifecycle_health, "startFocus")),
        _operation("update_focus", _section(lifecycle_health, "updateFocus")),
        _operation("end_focus", _section(lifecycle_health, "endFocus")),
        _operation("resume_focus", _section(lifecycle_health, "resumeFocus")),
        _operation("save_focus_summary", _section(summary_health, "saveFocusSummary")),
        _operation("link_focus_tasks", _section(task_health, "linkFocusTasks")),
        _operation(
            "prepare_calendar_focus",
            _section(calendar_health, "prepareCalendarFocus"),
        ),
    ]

    blockers = [
        f"{item.operation} has a degraded latest ownership receipt"
        for item in operations
        if item.status == "degraded"
    ]
    evidence_needed = [
        f"Run and verify {item.operation} at least once"
        for item in operations
        if item.status == "unexercised"
    ]
    verified_count = sum(item.status == "verified" for item in operations)

    if blockers:
        readiness: OwnershipReadiness = "blocked"
    elif evidence_needed:
        readiness = "collecting"
    else:
        readiness = "ready"

    legacy_projection = NativeFocusLegacyProjectionStatus(
        quarantinedCommands=list(_QUARANTINED_COMMANDS),
        remainingBrowserOwnedWriteSurfaces=[],
    )
    ready = readiness == "ready" and legacy_projection.retired
    return NativeFocusOwnershipReadiness(
        ok=not blockers,
        readiness=readiness,
        readyForLegacyProjectionRetirement=ready,
        verifiedOperationCount=verified_count,
        requiredOperationCount=len(operations),
        operations=operations,
        legacyProjection=legacy_projection,
        blockers=blockers,
        evidenceNeeded=evidence_needed,
    )
