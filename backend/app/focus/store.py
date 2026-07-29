from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Iterable
from uuid import uuid4

from app.focus.audit import build_response_audit
from app.focus.response import (
    build_response_candidate,
    build_tool_response_candidate,
)
from app.focus.models import (
    FocusEvent,
    FocusEventLog,
    FocusEventType,
    FocusField,
    FocusOperation,
    FocusOperationKind,
    FocusState,
    FocusStatus,
    LegacyFocusSeed,
    PendingAction,
    PendingQuestion,
    PlannedToolCall,
    ToolName,
    TurnPlan,
    TurnRoute,
)


_STORE_LOCK = RLock()
_MAX_EVENTS = 4000

_STRING_FIELDS = {
    FocusField.TITLE.value,
    FocusField.OBJECTIVE.value,
    FocusField.DELIVERABLE.value,
    FocusField.SUBJECT.value,
    FocusField.NEXT_ACTION.value,
}

_LIST_FIELDS = {
    FocusField.STAKEHOLDERS.value,
    FocusField.REQUIREMENTS.value,
    FocusField.CONSTRAINTS.value,
    FocusField.PREFERENCES.value,
    FocusField.DECISIONS.value,
    FocusField.KNOWN_FACTS.value,
    FocusField.MILESTONES.value,
    FocusField.COMPLETED_MILESTONES.value,
    FocusField.TAGS.value,
}


class FocusStoreError(Exception):
    """Safe error raised by the Focus event store."""


@dataclass(frozen=True)
class GuardedResponseDecision:
    """Explain whether a canonical candidate may control the visible reply."""

    candidate: FocusEvent | None = None
    fallbackReason: str = ""
    fallbackDetails: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return self.candidate is not None and not self.fallbackReason


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _new_focus_id() -> str:
    return f"focus-{uuid4().hex}"


def _stable_focus_id_from_event(event: FocusEvent) -> str:
    """Return a deterministic fallback ID for older malformed event logs.

    New events always persist a real Focus ID. This fallback only exists so an
    already-written legacy_imported or focus_started event with a blank ID can
    still be replayed without generating a different UUID on every reduction.
    """

    payload_focus_id = str(event.payload.get("focusId", "")).strip()
    if event.focusId.strip():
        return event.focusId.strip()
    if payload_focus_id:
        return payload_focus_id

    event_suffix = event.id.removeprefix("focus-event-").strip()
    if event_suffix:
        return f"focus-{event_suffix}"
    return "focus-unknown-event"


def event_file() -> Path:
    configured = os.getenv("QMEET_FOCUS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "qmeet_focus.json"


def _empty_log() -> FocusEventLog:
    return FocusEventLog(version=1, updatedAt=_now_iso(), events=[])


def _read_log_unlocked() -> FocusEventLog:
    path = event_file()
    if not path.exists():
        return _empty_log()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return FocusEventLog.model_validate(payload)
    except Exception as exc:
        raise FocusStoreError(
            f"Focus event log could not be read: {path}"
        ) from exc


def _atomic_write_unlocked(document: FocusEventLog) -> None:
    path = event_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    document.updatedAt = _now_iso()

    if len(document.events) > _MAX_EVENTS:
        document.events = document.events[-_MAX_EVENTS:]

    handle = None
    temporary_path: Path | None = None

    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(handle.name)
        json.dump(document.model_dump(mode="json"), handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        temporary_path.replace(path)
    except Exception as exc:
        if handle is not None:
            handle.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise FocusStoreError(
            f"Focus event log could not be written: {path}"
        ) from exc


def _new_event(
    event_type: FocusEventType,
    *,
    focus_id: str = "",
    payload: dict | None = None,
    source_turn_id: str = "",
    source: str = "",
    confidence: float = 1.0,
) -> FocusEvent:
    return FocusEvent(
        id=f"focus-event-{uuid4().hex}",
        focusId=focus_id,
        type=event_type,
        payload=payload or {},
        sourceTurnId=source_turn_id,
        source=source,
        confidence=max(0.0, min(1.0, confidence)),
        createdAt=_now_iso(),
    )


def append_events(events: Iterable[FocusEvent]) -> list[FocusEvent]:
    items = list(events)
    if not items:
        return []

    with _STORE_LOCK:
        document = _read_log_unlocked()
        existing_ids = {event.id for event in document.events}

        for event in items:
            if event.id in existing_ids:
                continue
            document.events.append(event)
            existing_ids.add(event.id)

        _atomic_write_unlocked(document)

    return items


def list_events(limit: int = 200) -> list[FocusEvent]:
    safe_limit = max(1, min(limit, 1000))
    with _STORE_LOCK:
        events = _read_log_unlocked().events
    return events[-safe_limit:]


def event_count() -> int:
    with _STORE_LOCK:
        return len(_read_log_unlocked().events)


_EXPECTED_FALLBACK_REASONS = frozenset({
    "not_attached_to_focus",
    "tool_requested",
    "candidate_not_direct",
})

_SAFETY_FALLBACK_REASONS = frozenset({
    "candidate_ineligible",
    "candidate_below_confidence_threshold",
    "empty_candidate",
    "missing_eligibility",
    "candidate_missing_focus",
    "no_active_focus",
    "focus_mismatch",
})

_SYSTEM_FAILURE_FALLBACK_REASONS = frozenset({
    "observation_timeout",
    "missing_candidate",
    "work_context_sync_failed",
})


def _fallback_category(reason: str) -> str:
    normalized = reason.strip()

    if normalized in _EXPECTED_FALLBACK_REASONS:
        return "expected"
    if normalized in _SAFETY_FALLBACK_REASONS:
        return "safety"
    if normalized in _SYSTEM_FAILURE_FALLBACK_REASONS:
        return "system_failure"
    return "unknown"


def response_selection_summary() -> dict[str, object]:
    """Summarize explicit guarded visible-response decisions.

    Shadow-era assistant replies are intentionally excluded. A guarded
    decision is counted only when the canonical candidate controlled the
    visible reply or when the legacy reply contains guarded fallback
    telemetry. If a turn was recorded more than once, only its latest
    decision contributes to the aggregate.

    ``successRate`` remains the original raw takeover ratio for backward
    compatibility. ``guardedTakeoverRate`` excludes expected routing
    fallbacks, while ``healthyDecisionRate`` treats expected and safety
    fallbacks as correct guarded behavior and penalizes only system failures
    or unknown outcomes.
    """

    with _STORE_LOCK:
        events = list(_read_log_unlocked().events)

    decisions_by_turn: dict[str, dict[str, object]] = {}
    decision_order: list[str] = []

    for event in events:
        if event.type != FocusEventType.ASSISTANT_REPLIED:
            continue

        payload = event.payload
        fallback = payload.get("guardedFallback")
        outcome = ""
        reason = ""
        details: list[str] = []
        category = "takeover"

        if event.source in {
            "focus-visible-response",
            "focus-tool-visible-response",
        }:
            outcome = "takeover"
        elif isinstance(fallback, dict) and fallback.get("used") is True:
            outcome = "fallback"
            reason = str(fallback.get("reason", "")).strip()
            category = _fallback_category(reason)
            raw_details = fallback.get("details", [])
            if isinstance(raw_details, list):
                details = [
                    str(detail).strip()
                    for detail in raw_details
                    if str(detail).strip()
                ]

        if not outcome:
            continue

        audit = payload.get("audit", {})
        candidate_eligible = (
            audit.get("candidateEligible")
            if isinstance(audit, dict)
            else None
        )
        healthy = (
            outcome == "takeover"
            or category in {"expected", "safety"}
        )
        turn_key = event.sourceTurnId.strip() or event.id
        decision = {
            "sourceTurnId": event.sourceTurnId,
            "focusId": event.focusId,
            "outcome": outcome,
            "reason": reason,
            "category": category,
            "healthy": healthy,
            "details": details,
            "candidateEligible": candidate_eligible,
            "responseSource": event.source,
            "createdAt": event.createdAt,
        }

        if turn_key in decisions_by_turn:
            decision_order.remove(turn_key)
        decision_order.append(turn_key)
        decisions_by_turn[turn_key] = decision

    decisions = [decisions_by_turn[key] for key in decision_order]
    takeover_count = sum(
        1 for decision in decisions if decision["outcome"] == "takeover"
    )
    fallback_count = sum(
        1 for decision in decisions if decision["outcome"] == "fallback"
    )
    fallback_reasons: dict[str, int] = {}
    category_counts = {
        "expected": 0,
        "safety": 0,
        "systemFailure": 0,
        "unknown": 0,
    }
    reasons_by_category: dict[str, dict[str, int]] = {
        "expected": {},
        "safety": {},
        "systemFailure": {},
        "unknown": {},
    }

    category_key_by_value = {
        "expected": "expected",
        "safety": "safety",
        "system_failure": "systemFailure",
        "unknown": "unknown",
    }

    for decision in decisions:
        if decision["outcome"] != "fallback":
            continue

        reason = str(decision["reason"] or "unknown")
        fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1

        category_value = str(decision["category"])
        category_key = category_key_by_value.get(
            category_value,
            "unknown",
        )
        category_counts[category_key] += 1
        category_reasons = reasons_by_category[category_key]
        category_reasons[reason] = category_reasons.get(reason, 0) + 1

    decision_count = takeover_count + fallback_count
    expected_fallback_count = category_counts["expected"]
    safety_fallback_count = category_counts["safety"]
    system_failure_count = category_counts["systemFailure"]
    unknown_fallback_count = category_counts["unknown"]

    raw_takeover_rate = (
        round(takeover_count / decision_count, 4)
        if decision_count
        else 0.0
    )

    guarded_attempt_count = (
        takeover_count
        + safety_fallback_count
        + system_failure_count
        + unknown_fallback_count
    )
    guarded_takeover_rate = (
        round(takeover_count / guarded_attempt_count, 4)
        if guarded_attempt_count
        else 0.0
    )

    healthy_decision_count = (
        takeover_count
        + expected_fallback_count
        + safety_fallback_count
    )
    healthy_decision_rate = (
        round(healthy_decision_count / decision_count, 4)
        if decision_count
        else 0.0
    )

    return {
        "decisionCount": decision_count,
        "takeoverCount": takeover_count,
        "fallbackCount": fallback_count,
        "successRate": raw_takeover_rate,
        "takeoverRate": raw_takeover_rate,
        "guardedAttemptCount": guarded_attempt_count,
        "guardedTakeoverRate": guarded_takeover_rate,
        "healthyDecisionCount": healthy_decision_count,
        "healthyDecisionRate": healthy_decision_rate,
        "expectedFallbackCount": expected_fallback_count,
        "safetyFallbackCount": safety_fallback_count,
        "systemFailureCount": system_failure_count,
        "unknownFallbackCount": unknown_fallback_count,
        "fallbackReasons": fallback_reasons,
        "fallbackCategoryCounts": category_counts,
        "fallbackReasonsByCategory": reasons_by_category,
        "latestDecision": decisions[-1] if decisions else None,
    }



def guarded_tool_response_decision_for_turn(
    source_turn_id: str,
    *,
    tool: ToolName = ToolName.SEARCH,
) -> GuardedResponseDecision:
    """Return an eligible post-tool candidate for guarded presentation."""

    turn_id = source_turn_id.strip()
    if not turn_id:
        return GuardedResponseDecision(fallbackReason="missing_turn_id")

    with _STORE_LOCK:
        events = list(_read_log_unlocked().events)

    turn_events = [
        event for event in events if event.sourceTurnId == turn_id
    ]
    tool_request = next(
        (
            event
            for event in reversed(turn_events)
            if event.type == FocusEventType.TOOL_REQUESTED
            and str(event.payload.get("tool", "")) == tool.value
        ),
        None,
    )
    if tool_request is None:
        return GuardedResponseDecision(
            fallbackReason="missing_tool_request",
        )
    if (
        not tool_request.focusId.strip()
        or tool_request.payload.get("attachToFocus") is not True
    ):
        return GuardedResponseDecision(
            fallbackReason="tool_not_attached_to_focus",
        )

    tool_result = next(
        (
            event
            for event in reversed(turn_events)
            if event.type in {
                FocusEventType.TOOL_COMPLETED,
                FocusEventType.TOOL_FAILED,
            }
            and str(event.payload.get("tool", "")) == tool.value
        ),
        None,
    )
    if tool_result is None:
        return GuardedResponseDecision(
            fallbackReason="missing_tool_result",
        )
    if tool_result.type == FocusEventType.TOOL_FAILED:
        return GuardedResponseDecision(fallbackReason="tool_failed")

    candidate = next(
        (
            event
            for event in reversed(turn_events)
            if event.type == FocusEventType.RESPONSE_CANDIDATE
            and str(event.payload.get("stage", "")) == "tool_result"
            and isinstance(event.payload.get("toolEvidence"), dict)
            and event.payload["toolEvidence"].get("tool") == tool.value
        ),
        None,
    )
    if candidate is None:
        return GuardedResponseDecision(
            fallbackReason="missing_tool_response_candidate",
        )

    payload = candidate.payload
    text = str(payload.get("text", "")).strip()
    eligibility = payload.get("eligibility")
    evidence = payload.get("toolEvidence")

    if payload.get("attachToFocus") is not True:
        return GuardedResponseDecision(
            fallbackReason="tool_response_not_attached_to_focus",
        )
    if not text:
        return GuardedResponseDecision(fallbackReason="empty_candidate")
    if not isinstance(eligibility, dict):
        return GuardedResponseDecision(
            fallbackReason="missing_eligibility",
        )
    if not isinstance(evidence, dict):
        return GuardedResponseDecision(
            fallbackReason="missing_tool_evidence",
        )
    if evidence.get("success") is not True:
        return GuardedResponseDecision(
            fallbackReason="tool_evidence_unsuccessful",
        )

    raw_reasons = eligibility.get("reasons", [])
    eligibility_reasons = tuple(
        str(reason).strip()
        for reason in raw_reasons
        if str(reason).strip()
    ) if isinstance(raw_reasons, list) else ()
    if eligibility.get("eligible") is not True or eligibility_reasons:
        return GuardedResponseDecision(
            fallbackReason="candidate_ineligible",
            fallbackDetails=eligibility_reasons,
        )

    current = reduce_events(events)
    if not current.focusId.strip():
        return GuardedResponseDecision(fallbackReason="no_active_focus")
    if candidate.focusId.strip() != current.focusId.strip():
        return GuardedResponseDecision(
            fallbackReason="focus_mismatch",
            fallbackDetails=(
                candidate.focusId.strip() or "missing_candidate_focus",
                current.focusId.strip(),
            ),
        )

    return GuardedResponseDecision(candidate=candidate)


def record_tool_response_candidate(
    *,
    tool: ToolName,
    success: bool,
    query: str,
    summary: str,
    recommendation: str = "",
    steps: list[str] | None = None,
    sources: list[dict] | None = None,
    source_turn_id: str,
    source: str = "focus-tool-response-candidate",
) -> FocusEvent | None:
    """Persist one deterministic candidate after verified tool completion."""

    turn_id = source_turn_id.strip()
    if not turn_id:
        return None

    with _STORE_LOCK:
        document = _read_log_unlocked()
        turn_events = [
            event
            for event in document.events
            if event.sourceTurnId == turn_id
        ]
        existing = next(
            (
                event
                for event in reversed(turn_events)
                if event.type == FocusEventType.RESPONSE_CANDIDATE
                and str(event.payload.get("stage", "")) == "tool_result"
                and isinstance(event.payload.get("toolEvidence"), dict)
                and event.payload["toolEvidence"].get("tool") == tool.value
            ),
            None,
        )
        if existing is not None:
            return existing

        tool_request = next(
            (
                event
                for event in reversed(turn_events)
                if event.type == FocusEventType.TOOL_REQUESTED
                and str(event.payload.get("tool", "")) == tool.value
            ),
            None,
        )
        if tool_request is None:
            return None

        focus_id = tool_request.focusId.strip()
        attach_to_focus = bool(
            focus_id
            and tool_request.payload.get("attachToFocus") is True
        )
        candidate_payload = build_tool_response_candidate(
            tool=tool.value,
            success=success,
            query=query,
            summary=summary,
            recommendation=recommendation,
            steps=steps or [],
            sources=sources or [],
            attach_to_focus=attach_to_focus,
        )
        candidate_payload["attachToFocus"] = attach_to_focus

        event = _new_event(
            FocusEventType.RESPONSE_CANDIDATE,
            focus_id=focus_id if attach_to_focus else "",
            payload=candidate_payload,
            source_turn_id=turn_id,
            source=source,
            confidence=1.0 if success else 0.0,
        )
        document.events.append(event)
        _atomic_write_unlocked(document)
        return event


def guarded_response_decision_for_turn(
    source_turn_id: str,
) -> GuardedResponseDecision:
    """Return the candidate decision and a deterministic fallback reason.

    Reasons are intentionally stable telemetry values rather than prose. They
    explain why guarded mode used the legacy chat path for a given turn.
    """

    turn_id = source_turn_id.strip()
    if not turn_id:
        return GuardedResponseDecision(
            fallbackReason="missing_turn_id",
        )

    with _STORE_LOCK:
        events = list(_read_log_unlocked().events)

    turn_events = [
        event
        for event in events
        if event.sourceTurnId == turn_id
    ]
    if any(
        event.type == FocusEventType.TOOL_REQUESTED
        for event in turn_events
    ):
        return GuardedResponseDecision(
            fallbackReason="tool_requested",
        )

    candidate = next(
        (
            event
            for event in reversed(turn_events)
            if event.type == FocusEventType.RESPONSE_CANDIDATE
        ),
        None,
    )
    if candidate is None:
        return GuardedResponseDecision(
            fallbackReason="missing_candidate",
        )

    payload = candidate.payload
    text = str(payload.get("text", "")).strip()
    stage = str(payload.get("stage", "")).strip()
    eligibility = payload.get("eligibility")

    if payload.get("attachToFocus") is not True:
        return GuardedResponseDecision(
            fallbackReason="not_attached_to_focus",
        )
    if not text:
        return GuardedResponseDecision(
            fallbackReason="empty_candidate",
        )
    if stage != "direct":
        return GuardedResponseDecision(
            fallbackReason="candidate_not_direct",
            fallbackDetails=(stage or "missing_stage",),
        )
    if not isinstance(eligibility, dict):
        return GuardedResponseDecision(
            fallbackReason="missing_eligibility",
        )

    raw_reasons = eligibility.get("reasons", [])
    eligibility_reasons = (
        tuple(str(reason).strip() for reason in raw_reasons if str(reason).strip())
        if isinstance(raw_reasons, list)
        else ("invalid_eligibility_reasons",)
    )
    if eligibility.get("eligible") is not True or eligibility_reasons:
        return GuardedResponseDecision(
            fallbackReason="candidate_ineligible",
            fallbackDetails=eligibility_reasons,
        )

    try:
        minimum_confidence = float(
            eligibility.get("minimumConfidence", 0.9)
        )
        candidate_confidence = float(
            eligibility.get("confidence", candidate.confidence)
        )
    except (TypeError, ValueError):
        return GuardedResponseDecision(
            fallbackReason="invalid_candidate_confidence",
        )

    if candidate_confidence < minimum_confidence:
        return GuardedResponseDecision(
            fallbackReason="candidate_below_confidence_threshold",
            fallbackDetails=(
                f"confidence={candidate_confidence}",
                f"minimum={minimum_confidence}",
            ),
        )

    candidate_focus_id = candidate.focusId.strip()
    if not candidate_focus_id:
        return GuardedResponseDecision(
            fallbackReason="candidate_missing_focus",
        )

    current_focus_id = reduce_events(events).focusId.strip()
    if not current_focus_id:
        return GuardedResponseDecision(
            fallbackReason="no_active_focus",
        )
    if candidate_focus_id != current_focus_id:
        return GuardedResponseDecision(
            fallbackReason="focus_mismatch",
            fallbackDetails=(
                f"candidate={candidate_focus_id}",
                f"active={current_focus_id}",
            ),
        )

    return GuardedResponseDecision(candidate=candidate)


def eligible_response_candidate_for_turn(
    source_turn_id: str,
) -> FocusEvent | None:
    """Compatibility wrapper returning only an eligible guarded candidate."""

    return guarded_response_decision_for_turn(source_turn_id).candidate


def _append_unique(values: list[str], candidate: str, limit: int = 80) -> None:
    item = " ".join(candidate.split()).strip()
    if not item:
        return

    key = item.casefold()
    if any(existing.casefold() == key for existing in values):
        return

    values.append(item)
    if len(values) > limit:
        del values[:-limit]


def _remove_casefold(values: list[str], candidate: str) -> None:
    key = " ".join(candidate.split()).strip().casefold()
    if not key:
        return
    values[:] = [value for value in values if value.casefold() != key]


def _state_from_seed(
    seed_payload: dict,
    *,
    fallback_focus_id: str,
    fallback_timestamp: str,
) -> FocusState:
    seed = LegacyFocusSeed.model_validate(seed_payload)
    focus_id = seed.focusId.strip() or fallback_focus_id
    created_at = seed.createdAt or fallback_timestamp
    updated_at = seed.updatedAt or fallback_timestamp
    milestones = list(seed.milestones)
    pending_question = seed.pendingQuestion

    # Older Phase 18R legacy-import events stored the first open question in
    # milestones because LegacyFocusSeed did not yet expose pendingQuestion.
    # Repair that shape deterministically during replay so existing event logs
    # project correctly without requiring a reset.
    if pending_question is None and seed.status == FocusStatus.CLARIFYING:
        for index, item in enumerate(milestones):
            question = " ".join(item.split()).strip()
            if question.endswith("?"):
                pending_question = PendingQuestion(
                    target="legacy_open_question",
                    question=question,
                    askedAt=updated_at,
                )
                del milestones[index]
                break

    return FocusState(
        focusId=focus_id,
        title=seed.title,
        objective=seed.objective,
        deliverable=seed.deliverable,
        subject=seed.subject,
        stakeholders=seed.stakeholders,
        requirements=seed.requirements,
        constraints=seed.constraints,
        preferences=seed.preferences,
        decisions=seed.decisions,
        knownFacts=seed.knownFacts,
        milestones=milestones,
        completedMilestones=seed.completedMilestones,
        pendingQuestion=pending_question,
        nextAction=seed.nextAction,
        status=seed.status,
        tags=seed.tags,
        createdAt=created_at,
        updatedAt=updated_at,
    )


def reduce_events(events: Iterable[FocusEvent]) -> FocusState:
    """Project the append-only event log into the current Focus state.

    Reduction must be deterministic. No UUID or current timestamp is generated
    here; every replay of the same events returns the same state.
    """

    state = FocusState()
    tool_resume_status_by_turn: dict[str, FocusStatus] = {}
    pending_tool_count_by_turn: dict[str, int] = {}

    for event in events:
        payload = event.payload
        event_time = event.createdAt

        if event.type == FocusEventType.LEGACY_IMPORTED:
            state = _state_from_seed(
                payload,
                fallback_focus_id=_stable_focus_id_from_event(event),
                fallback_timestamp=event_time,
            )
            if event.sourceTurnId:
                state.lastTurnId = event.sourceTurnId
            continue

        if event.type == FocusEventType.FOCUS_STARTED:
            state = FocusState(
                focusId=_stable_focus_id_from_event(event),
                title=str(payload.get("title", "")).strip(),
                objective=str(payload.get("objective", "")).strip(),
                tags=list(payload.get("tags", [])),
                status=FocusStatus.CLARIFYING,
                createdAt=event_time,
                updatedAt=event_time,
                lastTurnId=event.sourceTurnId,
            )
            continue

        if event.type in {
            FocusEventType.RESPONSE_CANDIDATE,
            FocusEventType.ASSISTANT_REPLIED,
        }:
            # Candidate and visible replies are observational evidence.
            # They must never alter the canonical Focus projection.
            continue

        if event.type == FocusEventType.TURN_PLANNED:
            # A transient turn may be logged with no Focus ID. It should remain
            # traceable without becoming the active Focus's last semantic turn.
            if event.focusId and event.focusId == state.focusId:
                state.updatedAt = event_time
                if event.sourceTurnId:
                    state.lastTurnId = event.sourceTurnId
            continue

        # Every non-lifecycle state mutation is scoped to one Focus. Blank IDs
        # represent transient activity; mismatched IDs represent older Focuses.
        # Neither may alter the current projection.
        if not event.focusId or event.focusId != state.focusId:
            continue

        if state.status == FocusStatus.INACTIVE:
            continue

        if event.type == FocusEventType.FOCUS_RESCOPED:
            title = str(payload.get("title", "")).strip()
            objective = str(payload.get("objective", "")).strip()

            if title:
                state.title = title
            if objective:
                state.objective = objective
            for tag in payload.get("tags", []):
                _append_unique(state.tags, str(tag), 24)

            state.status = FocusStatus.CLARIFYING

        elif event.type == FocusEventType.FIELD_SET:
            field = str(payload.get("field", ""))
            value = " ".join(str(payload.get("value", "")).split()).strip()

            if field in _STRING_FIELDS:
                setattr(state, field, value)
            elif field == FocusField.STATUS.value:
                try:
                    state.status = FocusStatus(value)
                except ValueError:
                    pass

        elif event.type == FocusEventType.LIST_ITEM_ADDED:
            field = str(payload.get("field", ""))
            value = str(payload.get("value", ""))
            if field in _LIST_FIELDS:
                _append_unique(getattr(state, field), value)

        elif event.type == FocusEventType.LIST_ITEM_REMOVED:
            field = str(payload.get("field", ""))
            value = str(payload.get("value", ""))
            if field in _LIST_FIELDS:
                _remove_casefold(getattr(state, field), value)

        elif event.type == FocusEventType.QUESTION_SET:
            question = str(payload.get("question", "")).strip()
            state.pendingQuestion = PendingQuestion(
                target=str(payload.get("target", "")).strip(),
                question=question,
                askedAt=event_time,
            )
            # While QMeet is waiting for one answer, that question is the
            # canonical next action. This prevents a previously answered
            # nextAction from remaining visible beside a newer question.
            if question:
                state.nextAction = question
            if state.status != FocusStatus.COMPLETE:
                state.status = FocusStatus.CLARIFYING

        elif event.type == FocusEventType.QUESTION_CLEARED:
            cleared_question = (
                state.pendingQuestion.question.strip()
                if state.pendingQuestion is not None
                else ""
            )
            state.pendingQuestion = None
            if (
                cleared_question
                and state.nextAction.strip().casefold()
                == cleared_question.casefold()
            ):
                state.nextAction = ""
            if state.status == FocusStatus.CLARIFYING:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.ACTION_SET:
            state.pendingAction = PendingAction(
                kind=str(payload.get("kind", "")).strip(),
                description=str(payload.get("description", "")).strip(),
                createdAt=event_time,
            )
            if state.status != FocusStatus.COMPLETE:
                state.status = FocusStatus.WAITING

        elif event.type == FocusEventType.ACTION_CLEARED:
            state.pendingAction = None
            if state.status == FocusStatus.WAITING:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.NEXT_ACTION_SET:
            state.nextAction = str(payload.get("value", "")).strip()

        elif event.type == FocusEventType.PROGRESS_RECORDED:
            _append_unique(
                state.completedMilestones,
                str(payload.get("value", "")),
            )
            if state.status not in {FocusStatus.COMPLETE, FocusStatus.WAITING}:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.MILESTONE_COMPLETED:
            value = str(payload.get("value", "")).strip()
            _remove_casefold(state.milestones, value)
            _append_unique(state.completedMilestones, value)
            if state.status not in {FocusStatus.COMPLETE, FocusStatus.WAITING}:
                state.status = FocusStatus.ACTIVE

        elif event.type == FocusEventType.TOOL_REQUESTED:
            tool = str(payload.get("tool", "")).strip()
            turn_key = event.sourceTurnId or event.id
            pending_count = pending_tool_count_by_turn.get(turn_key, 0)

            if pending_count == 0:
                resume_value = str(payload.get("resumeStatus", "")).strip()
                try:
                    resume_status = FocusStatus(resume_value)
                except ValueError:
                    resume_status = state.status

                if resume_status in {
                    FocusStatus.INACTIVE,
                    FocusStatus.WAITING,
                    FocusStatus.COMPLETE,
                }:
                    resume_status = (
                        FocusStatus.CLARIFYING
                        if state.pendingQuestion is not None
                        else FocusStatus.ACTIVE
                    )

                tool_resume_status_by_turn[turn_key] = resume_status

            pending_tool_count_by_turn[turn_key] = pending_count + 1
            state.pendingAction = PendingAction(
                kind=tool,
                description=str(payload.get("reason", "")).strip(),
                createdAt=event_time,
            )
            state.status = FocusStatus.WAITING

        elif event.type in {
            FocusEventType.TOOL_COMPLETED,
            FocusEventType.TOOL_FAILED,
        }:
            summary = str(payload.get("summary", "")).strip()
            if summary:
                # Tool output is evidence about the Focus. It is not proof that
                # a milestone was completed. Milestones move only through an
                # explicit progress or completion operation.
                _append_unique(state.knownFacts, summary)

            turn_key = event.sourceTurnId or event.id
            remaining = max(
                0,
                pending_tool_count_by_turn.get(turn_key, 1) - 1,
            )

            if remaining:
                pending_tool_count_by_turn[turn_key] = remaining
                state.status = FocusStatus.WAITING
            else:
                pending_tool_count_by_turn.pop(turn_key, None)
                state.pendingAction = None

                if state.status != FocusStatus.COMPLETE:
                    resume_status = tool_resume_status_by_turn.pop(
                        turn_key,
                        FocusStatus.CLARIFYING
                        if state.pendingQuestion is not None
                        else FocusStatus.ACTIVE,
                    )
                    state.status = resume_status

        elif event.type == FocusEventType.FOCUS_COMPLETED:
            state.status = FocusStatus.COMPLETE
            state.pendingQuestion = None
            state.pendingAction = None
            state.nextAction = str(payload.get("nextAction", "")).strip()

        elif event.type == FocusEventType.FOCUS_ENDED:
            state.status = FocusStatus.INACTIVE
            state.pendingQuestion = None
            state.pendingAction = None
            state.nextAction = ""

        state.updatedAt = event_time
        if event.sourceTurnId:
            state.lastTurnId = event.sourceTurnId

    return state


def get_state() -> FocusState:
    with _STORE_LOCK:
        events = list(_read_log_unlocked().events)
    return reduce_events(events)


def reset_store() -> FocusState:
    with _STORE_LOCK:
        _atomic_write_unlocked(_empty_log())
    return FocusState()


def has_turn(turn_id: str) -> bool:
    if not turn_id:
        return False

    with _STORE_LOCK:
        return any(
            event.sourceTurnId == turn_id
            and event.type == FocusEventType.TURN_PLANNED
            for event in _read_log_unlocked().events
        )


def seed_from_legacy(seed: LegacyFocusSeed | None) -> FocusState:
    if seed is None:
        return get_state()

    with _STORE_LOCK:
        document = _read_log_unlocked()
        current = reduce_events(document.events)

        if current.status != FocusStatus.INACTIVE:
            return current

        focus_id = seed.focusId.strip() or _new_focus_id()
        seed_payload = seed.model_dump(mode="json")
        seed_payload["focusId"] = focus_id

        event = _new_event(
            FocusEventType.LEGACY_IMPORTED,
            focus_id=focus_id,
            payload=seed_payload,
            source="legacy-bootstrap",
        )
        document.events.append(event)
        _atomic_write_unlocked(document)
        return reduce_events(document.events)


def _events_from_operation(
    operation: FocusOperation,
    *,
    focus_id: str,
    turn_id: str,
    source: str,
) -> list[FocusEvent]:
    common = {
        "focus_id": focus_id,
        "source_turn_id": turn_id,
        "source": source,
        "confidence": operation.confidence,
    }

    kind = operation.kind

    if kind == FocusOperationKind.START_FOCUS:
        return [
            _new_event(
                FocusEventType.FOCUS_STARTED,
                payload={
                    "title": operation.title or operation.value,
                    "objective": operation.objective,
                    "tags": operation.tags,
                },
                **common,
            )
        ]

    if kind == FocusOperationKind.RESCOPE_FOCUS:
        return [
            _new_event(
                FocusEventType.FOCUS_RESCOPED,
                payload={
                    "title": operation.title or operation.value,
                    "objective": operation.objective,
                    "tags": operation.tags,
                },
                **common,
            )
        ]

    if kind == FocusOperationKind.SET_FIELD and operation.field:
        event_type = (
            FocusEventType.NEXT_ACTION_SET
            if operation.field == FocusField.NEXT_ACTION
            else FocusEventType.FIELD_SET
        )
        return [
            _new_event(
                event_type,
                payload={
                    "field": operation.field.value,
                    "value": operation.value,
                },
                **common,
            )
        ]

    if kind in {
        FocusOperationKind.ADD_LIST_ITEM,
        FocusOperationKind.REMOVE_LIST_ITEM,
    } and operation.field:
        event_type = (
            FocusEventType.LIST_ITEM_ADDED
            if kind == FocusOperationKind.ADD_LIST_ITEM
            else FocusEventType.LIST_ITEM_REMOVED
        )
        values = operation.values or ([operation.value] if operation.value else [])
        return [
            _new_event(
                event_type,
                payload={"field": operation.field.value, "value": value},
                **common,
            )
            for value in values
        ]

    if kind == FocusOperationKind.SET_PENDING_QUESTION:
        return [
            _new_event(
                FocusEventType.QUESTION_SET,
                payload={
                    "target": operation.target,
                    "question": operation.question,
                },
                **common,
            )
        ]

    if kind == FocusOperationKind.CLEAR_PENDING_QUESTION:
        return [_new_event(FocusEventType.QUESTION_CLEARED, **common)]

    if kind == FocusOperationKind.SET_PENDING_ACTION:
        return [
            _new_event(
                FocusEventType.ACTION_SET,
                payload={
                    "kind": operation.target,
                    "description": operation.value,
                },
                **common,
            )
        ]

    if kind == FocusOperationKind.CLEAR_PENDING_ACTION:
        return [_new_event(FocusEventType.ACTION_CLEARED, **common)]

    if kind == FocusOperationKind.SET_NEXT_ACTION:
        return [
            _new_event(
                FocusEventType.NEXT_ACTION_SET,
                payload={"value": operation.value},
                **common,
            )
        ]

    if kind == FocusOperationKind.RECORD_PROGRESS:
        values = operation.values or ([operation.value] if operation.value else [])
        return [
            _new_event(
                FocusEventType.PROGRESS_RECORDED,
                payload={"value": value},
                **common,
            )
            for value in values
        ]

    if kind == FocusOperationKind.COMPLETE_MILESTONE:
        values = operation.values or ([operation.value] if operation.value else [])
        return [
            _new_event(
                FocusEventType.MILESTONE_COMPLETED,
                payload={"value": value},
                **common,
            )
            for value in values
        ]

    if kind == FocusOperationKind.MARK_FOCUS_COMPLETE:
        return [
            _new_event(
                FocusEventType.FOCUS_COMPLETED,
                payload={"nextAction": operation.value},
                **common,
            )
        ]

    if kind == FocusOperationKind.END_FOCUS:
        return [_new_event(FocusEventType.FOCUS_ENDED, **common)]

    return []


def _tool_request_event(
    tool_call: PlannedToolCall,
    *,
    focus_id: str,
    turn_id: str,
    source: str,
    confidence: float,
    resume_status: FocusStatus,
) -> FocusEvent:
    return _new_event(
        FocusEventType.TOOL_REQUESTED,
        focus_id=focus_id,
        payload={
            "tool": tool_call.tool.value,
            "reason": tool_call.reason,
            "arguments": [
                argument.model_dump(mode="json")
                for argument in tool_call.arguments
            ],
            "requiresConfirmation": tool_call.requiresConfirmation,
            "attachToFocus": bool(focus_id),
            "resumeStatus": resume_status.value,
        },
        source_turn_id=turn_id,
        source=source,
        confidence=confidence,
    )


def _automatic_question_event(
    plan: TurnPlan,
    *,
    focus_id: str,
    turn_id: str,
    source: str,
) -> FocusEvent | None:
    question = " ".join(plan.responseIntent.askQuestion.split()).strip()
    if not question or not focus_id:
        return None

    explicitly_set = any(
        operation.kind == FocusOperationKind.SET_PENDING_QUESTION
        for operation in plan.focusOperations
    )
    if explicitly_set:
        return None

    return _new_event(
        FocusEventType.QUESTION_SET,
        focus_id=focus_id,
        payload={"target": "follow_up", "question": question},
        source_turn_id=turn_id,
        source=source,
        confidence=plan.confidence,
    )


def apply_turn_plan(
    plan: TurnPlan,
    *,
    message: str,
    turn_id: str,
    source: str,
) -> FocusState:
    with _STORE_LOCK:
        existing_events = list(_read_log_unlocked().events)

    if turn_id and any(
        event.sourceTurnId == turn_id
        and event.type == FocusEventType.TURN_PLANNED
        for event in existing_events
    ):
        return reduce_events(existing_events)

    current = reduce_events(existing_events)
    current_focus_id = current.focusId.strip()

    real_tool_calls = [
        tool_call
        for tool_call in plan.toolCalls
        if tool_call.tool != ToolName.NONE
    ]
    has_attached_tool = any(
        tool_call.attachToFocus
        for tool_call in real_tool_calls
    )
    shadow_tool_source = source in {
        "command-interpret-shadow",
        "search-request-shadow",
    }
    transient_tool_turn = (
        bool(real_tool_calls)
        and not has_attached_tool
        and (shadow_tool_source or not plan.focusOperations)
    )
    transient_search = transient_tool_turn and any(
        tool_call.tool == ToolName.SEARCH
        for tool_call in real_tool_calls
    )

    # attachToFocus=False is a deterministic boundary, not a suggestion. A
    # transient tool turn may be logged and completed, but it cannot mutate,
    # replace, or ask follow-ups on the current durable Focus even if the model
    # accidentally emitted Focus operations beside the tool call.
    effective_focus_operations = (
        [] if transient_tool_turn else plan.focusOperations
    )
    start_focus_ids = {
        index: _new_focus_id()
        for index, operation in enumerate(effective_focus_operations)
        if operation.kind == FocusOperationKind.START_FOCUS
    }
    first_started_focus_id = next(iter(start_focus_ids.values()), "")
    has_focus_operations = bool(effective_focus_operations)

    if first_started_focus_id:
        # A replacement plan is interpreted in the context of the old Focus,
        # while a first-ever Focus uses the new ID immediately.
        turn_focus_id = current_focus_id or first_started_focus_id
    elif has_focus_operations or has_attached_tool:
        turn_focus_id = current_focus_id
    else:
        # A transient tool turn remains traceable but is not assigned to the
        # unrelated active Focus.
        turn_focus_id = ""

    active_focus_id = current_focus_id
    active_focus_is_open = bool(active_focus_id) and current.status not in {
        FocusStatus.INACTIVE,
        FocusStatus.COMPLETE,
    }
    focus_accepts_question = active_focus_is_open and not transient_tool_turn

    execution_policy = {
        "transientTool": transient_tool_turn,
        "transientSearch": transient_search,
        "suppressedFocusOperationCount": (
            len(plan.focusOperations) if transient_tool_turn else 0
        ),
    }

    events: list[FocusEvent] = [
        _new_event(
            FocusEventType.TURN_PLANNED,
            focus_id=turn_focus_id,
            payload={
                "message": message,
                "route": plan.route.value,
                "reason": plan.reason,
                "plan": plan.model_dump(mode="json"),
                "executionPolicy": execution_policy,
            },
            source_turn_id=turn_id,
            source=source,
            confidence=plan.confidence,
        )
    ]

    for index, operation in enumerate(effective_focus_operations):
        if operation.kind == FocusOperationKind.START_FOCUS:
            operation_focus_id = start_focus_ids[index]

            # A FocusState represents one current durable objective. Starting a
            # different focus therefore closes the currently open one even when
            # the model omitted an explicit end_focus operation. This keeps the
            # event history truthful without relying on planner consistency.
            if active_focus_id and active_focus_is_open:
                events.append(
                    _new_event(
                        FocusEventType.FOCUS_ENDED,
                        focus_id=active_focus_id,
                        payload={
                            "reason": "superseded_by_new_focus",
                            "newFocusId": operation_focus_id,
                        },
                        source_turn_id=turn_id,
                        source=source,
                        confidence=operation.confidence,
                    )
                )
                active_focus_is_open = False
                focus_accepts_question = False
        else:
            operation_focus_id = active_focus_id or turn_focus_id

        operation_events = _events_from_operation(
            operation,
            focus_id=operation_focus_id,
            turn_id=turn_id,
            source=source,
        )
        events.extend(operation_events)

        if operation.kind == FocusOperationKind.START_FOCUS:
            active_focus_id = operation_focus_id
            active_focus_is_open = True
            focus_accepts_question = True
        elif operation.kind in {
            FocusOperationKind.END_FOCUS,
            FocusOperationKind.MARK_FOCUS_COMPLETE,
        }:
            active_focus_is_open = False
            focus_accepts_question = False

    if focus_accepts_question:
        question_event = _automatic_question_event(
            plan,
            focus_id=active_focus_id,
            turn_id=turn_id,
            source=source,
        )
        if question_event is not None:
            events.append(question_event)

    projected_before_tools = reduce_events([*existing_events, *events])
    tool_resume_status = projected_before_tools.status

    started_focus_this_turn = bool(first_started_focus_id)
    for tool_call in plan.toolCalls:
        if tool_call.tool == ToolName.NONE:
            continue

        attach_to_focus = tool_call.attachToFocus or started_focus_this_turn
        tool_focus_id = active_focus_id if attach_to_focus else ""
        events.append(
            _tool_request_event(
                tool_call,
                focus_id=tool_focus_id,
                turn_id=turn_id,
                source=source,
                confidence=plan.confidence,
                resume_status=tool_resume_status,
            )
        )

    response_candidate = build_response_candidate(plan)
    response_candidate_text = str(response_candidate.get("text", "")).strip()
    if response_candidate_text:
        response_attaches_to_focus = bool(
            active_focus_id
            and not transient_tool_turn
            and (
                has_focus_operations
                or plan.route == TurnRoute.FOCUS_ACTION
                or plan.responseIntent.attachToFocus
            )
        )
        candidate_focus_id = (
            active_focus_id
            if response_attaches_to_focus
            else ""
        )
        response_candidate["text"] = response_candidate_text[:12000]
        response_candidate["attachToFocus"] = response_attaches_to_focus
        events.append(
            _new_event(
                FocusEventType.RESPONSE_CANDIDATE,
                focus_id=candidate_focus_id,
                payload=response_candidate,
                source_turn_id=turn_id,
                source="focus-response-candidate",
                confidence=plan.confidence,
            )
        )

    append_events(events)
    return get_state()


def _focus_id_for_tool_result(
    events: list[FocusEvent],
    source_turn_id: str,
) -> str:
    """Resolve a tool result to the Focus that requested it.

    One-off tools may legitimately have no durable Focus, in which case the
    returned ID is blank but the event is still preserved for turn tracing.
    """

    if source_turn_id:
        for event in reversed(events):
            if event.sourceTurnId != source_turn_id:
                continue
            if event.type == FocusEventType.TOOL_REQUESTED:
                return event.focusId.strip()

        for event in reversed(events):
            if event.sourceTurnId == source_turn_id and event.focusId.strip():
                return event.focusId.strip()

    return reduce_events(events).focusId.strip()


def record_tool_result(
    *,
    tool: ToolName,
    success: bool,
    summary: str,
    result_ids: list[str] | None = None,
    source_turn_id: str = "",
    source: str = "tool-result",
) -> FocusState:
    with _STORE_LOCK:
        document = _read_log_unlocked()
        focus_id = _focus_id_for_tool_result(
            document.events,
            source_turn_id,
        )

        event = _new_event(
            FocusEventType.TOOL_COMPLETED
            if success
            else FocusEventType.TOOL_FAILED,
            focus_id=focus_id,
            payload={
                "tool": tool.value,
                "summary": summary,
                "resultIds": result_ids or [],
            },
            source_turn_id=source_turn_id,
            source=source,
        )
        document.events.append(event)
        _atomic_write_unlocked(document)
        return reduce_events(document.events)

def _focus_id_for_turn(
    events: list[FocusEvent],
    source_turn_id: str,
) -> str:
    if not source_turn_id:
        return ""

    preferred_types = {
        FocusEventType.QUESTION_SET,
        FocusEventType.TOOL_REQUESTED,
        FocusEventType.FOCUS_STARTED,
        FocusEventType.TURN_PLANNED,
    }

    for event in reversed(events):
        if event.sourceTurnId != source_turn_id:
            continue
        if event.type in preferred_types:
            return event.focusId.strip()

    for event in reversed(events):
        if event.sourceTurnId == source_turn_id:
            return event.focusId.strip()

    return ""


def record_assistant_reply(
    *,
    text: str,
    source_turn_id: str,
    source: str = "assistant-response",
    transport: str = "",
    response_status: int = 200,
    fallback_reason: str = "",
    fallback_details: Iterable[str] = (),
) -> FocusState:
    reply_text = text.strip()
    if not reply_text:
        return get_state()

    with _STORE_LOCK:
        document = _read_log_unlocked()
        focus_id = _focus_id_for_turn(
            document.events,
            source_turn_id,
        )
        audit = build_response_audit(
            reply_text,
            document.events,
            source_turn_id=source_turn_id,
        )

        clean_fallback_reason = fallback_reason.strip()[:120]
        clean_fallback_details = [
            str(detail).strip()[:500]
            for detail in fallback_details
            if str(detail).strip()
        ][:20]
        payload = {
            "text": reply_text[:12000],
            "transport": transport[:40],
            "responseStatus": response_status,
            "audit": audit,
        }
        if clean_fallback_reason:
            payload["guardedFallback"] = {
                "used": True,
                "reason": clean_fallback_reason,
                "details": clean_fallback_details,
            }
            audit["guardedFallbackReason"] = clean_fallback_reason
            audit["guardedFallbackDetails"] = clean_fallback_details

        event = _new_event(
            FocusEventType.ASSISTANT_REPLIED,
            focus_id=focus_id,
            payload=payload,
            source_turn_id=source_turn_id,
            source=source,
        )
        document.events.append(event)
        _atomic_write_unlocked(document)
        return reduce_events(document.events)

