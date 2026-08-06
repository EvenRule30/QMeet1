from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.focus.calendar_prep import get_native_calendar_focus_prep_health
from app.focus.context import get_native_focus_context_health
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

    retired: bool
    fallbackBlocked: bool
    ownershipVersion: str
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

_CALENDAR_LEGACY_MARKERS = {
    "replaceActiveSession": "calendar hook imports the legacy active-session writer",
    "replaceMemoryTasks": "calendar hook imports the legacy bulk-task writer",
    "qmeet-calendar-focus-prep-command": "calendar hook still listens for the legacy prep event",
    "prepareFocusFromNextCalendarEvent": "calendar hook still exposes the browser-owned prep executor",
    "createCalendarFocusSession": "calendar hook still creates browser-owned Focus identities",
    "applyCalendarFocusSession": "calendar hook still writes browser Focus storage directly",
}

_MEMORY_ROUTER_LEGACY_MARKERS = {
    "**replace_active_session(": "compatibility memory router can replace the Focus projection",
    "**update_active_session(": "compatibility memory router can patch the Focus projection",
    "**clear_active_session(": "compatibility memory router can clear the Focus projection",
    "**replace_recent_focus_sessions(": "compatibility memory router can replace Focus history",
    "**clear_recent_focus_sessions(": "compatibility memory router can clear Focus history",
    "**delete_recent_focus_session(": "compatibility memory router can delete Focus history",
}


class _ProjectionAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ownershipVersion: str
    fallbackBlocked: bool
    remainingSurfaces: list[str] = Field(default_factory=list)


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


def _repository_root() -> Path:
    configured = os.getenv("QMEET_REPO_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def _read_source(root: Path, relative_path: str) -> tuple[str, str | None]:
    path = root / relative_path
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return "", f"{relative_path}: source could not be inspected ({exc.__class__.__name__})"


def _audit_projection_retirement() -> _ProjectionAudit:
    root = _repository_root()
    remaining: list[str] = []

    calendar_path = "src/app/hooks/useCalendarController.ts"
    calendar_source, calendar_error = _read_source(root, calendar_path)
    if calendar_error:
        remaining.append(calendar_error)
    else:
        for marker, description in _CALENDAR_LEGACY_MARKERS.items():
            if marker in calendar_source:
                remaining.append(f"{calendar_path}: {description}")

    memory_router_path = "backend/app/routers/memory.py"
    memory_router_source, memory_router_error = _read_source(root, memory_router_path)
    if memory_router_error:
        remaining.append(memory_router_error)
    else:
        if "FOCUS_PROJECTION_READ_ONLY = True" not in memory_router_source:
            remaining.append(
                f"{memory_router_path}: generic memory writes do not declare the Focus projection read-only"
            )
        if "_preserve_focus_projection()" not in memory_router_source:
            remaining.append(
                f"{memory_router_path}: generic memory writes do not preserve backend Focus projection fields"
            )
        if "status_code=409" not in memory_router_source or (
            "_retired_focus_projection_write()" not in memory_router_source
        ):
            remaining.append(
                f"{memory_router_path}: direct compatibility Focus writes are not retired with HTTP 409"
            )
        for marker, description in _MEMORY_ROUTER_LEGACY_MARKERS.items():
            if marker in memory_router_source:
                remaining.append(f"{memory_router_path}: {description}")

    wrapper_path = "src/app/commandHandlers/memory.ts"
    wrapper_source, wrapper_error = _read_source(root, wrapper_path)
    ownership_version = "unknown"
    fallback_blocked = False
    if wrapper_error:
        remaining.append(wrapper_error)
    else:
        version_match = re.search(
            r"NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
            wrapper_source,
        )
        if version_match:
            ownership_version = version_match.group(1).strip()
        else:
            remaining.append(f"{wrapper_path}: ownership version declaration is missing")

        guard_index = wrapper_source.find(
            "RETIRED_LEGACY_FOCUS_OWNERSHIP_COMMANDS.has(commandMatch.command)"
        )
        fallback_index = wrapper_source.rfind(
            "return handleMemoryCommandCore(commandMatch, deps)"
        )
        commands_present = all(
            f"'{command}'" in wrapper_source or f'"{command}"' in wrapper_source
            for command in _QUARANTINED_COMMANDS
        )
        fallback_blocked = (
            guard_index >= 0
            and fallback_index >= 0
            and guard_index < fallback_index
            and commands_present
        )
        if "addNativeFocusContextVerified" not in wrapper_source:
            remaining.append(
                f"{wrapper_path}: durable Focus context does not use the verified native executor"
            )

    context_path = "backend/app/focus/context.py"
    context_source, context_error = _read_source(root, context_path)
    if context_error:
        remaining.append(context_error)
    elif "add_focus_context_verified" not in context_source or (
        "objectivePreserved" not in context_source
    ):
        remaining.append(
            f"{context_path}: verified context persistence or objective-preservation proof is missing"
        )

    semantic_path = "src/app/lib/semanticFocusLifecycle.ts"
    semantic_source, semantic_error = _read_source(root, semantic_path)
    if semantic_error:
        remaining.append(semantic_error)
    elif "phase20i-context:" not in semantic_source:
        remaining.append(
            f"{semantic_path}: natural Focus context is not routed through the native context receipt"
        )

    return _ProjectionAudit(
        ownershipVersion=ownership_version,
        fallbackBlocked=fallback_blocked,
        remainingSurfaces=remaining,
    )


def get_native_focus_ownership_readiness() -> NativeFocusOwnershipReadiness:
    lifecycle_health = get_native_focus_lifecycle_health()
    summary_health = get_native_focus_summary_health()
    task_health = get_native_focus_task_health()
    calendar_health = get_native_calendar_focus_prep_health()
    context_health = get_native_focus_context_health()

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
        _operation(
            "add_focus_context",
            _section(context_health, "addFocusContext"),
        ),
    ]

    projection_audit = _audit_projection_retirement()
    legacy_projection = NativeFocusLegacyProjectionStatus(
        retired=not projection_audit.remainingSurfaces,
        fallbackBlocked=projection_audit.fallbackBlocked,
        ownershipVersion=projection_audit.ownershipVersion,
        quarantinedCommands=list(_QUARANTINED_COMMANDS),
        remainingBrowserOwnedWriteSurfaces=list(projection_audit.remainingSurfaces),
    )

    blockers = [
        f"{item.operation} has a degraded latest ownership receipt"
        for item in operations
        if item.status == "degraded"
    ]
    if not legacy_projection.fallbackBlocked:
        blockers.append("The retired legacy Focus command fallback is not fully blocked")
    blockers.extend(
        f"Legacy Focus projection remains writable: {surface}"
        for surface in legacy_projection.remainingBrowserOwnedWriteSurfaces
    )

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

    ready = (
        readiness == "ready"
        and legacy_projection.retired
        and legacy_projection.fallbackBlocked
    )
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
