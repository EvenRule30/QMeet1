from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from time import monotonic
from typing import Any

from app.focus.models import FocusField, FocusOperationKind, TurnPlan
from app.focus.planner import planner_enabled, preview_turn_plan
from app.focus.store import list_events
from app.focus.semantic_update_intent import (
    BRIDGE_VERSION,
    SemanticUpdateIntent,
    get_semantic_focus_update_decision,
)

_SUPPORTED_MODES = {
    "general",
    "coding",
    "meeting",
    "planning",
    "research",
    "personal",
}

_ALLOWED_COMPANION_OPERATIONS = {
    FocusOperationKind.SET_PENDING_QUESTION,
    FocusOperationKind.CLEAR_PENDING_QUESTION,
    FocusOperationKind.SET_PENDING_ACTION,
    FocusOperationKind.CLEAR_PENDING_ACTION,
    FocusOperationKind.SET_NEXT_ACTION,
}

_BLOCKING_OPERATIONS = {
    FocusOperationKind.START_FOCUS,
    FocusOperationKind.END_FOCUS,
    FocusOperationKind.MARK_FOCUS_COMPLETE,
    FocusOperationKind.RECORD_PROGRESS,
    FocusOperationKind.COMPLETE_MILESTONE,
}


@dataclass(frozen=True)
class SemanticFocusUpdate:
    title: str | None = None
    objective: str | None = None
    objective_specified: bool = False
    mode: str | None = None
    confidence: float = 0.0
    reason: str = ""

    def has_changes(self) -> bool:
        return (
            self.title is not None
            or self.objective_specified
            or self.mode is not None
        )

    def command_payload(self, source_turn_id: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "semanticBridge": True,
            "sourceTurnId": source_turn_id,
        }
        if self.title is not None:
            payload["title"] = self.title
        if self.objective_specified:
            payload["goal"] = self.objective or ""
        if self.mode is not None:
            payload["mode"] = self.mode
        return payload


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return _clean_text(raw).casefold()


def _mode_from_values(*values: Any) -> str | None:
    candidates: list[str] = []
    for raw in values:
        if isinstance(raw, (list, tuple, set)):
            candidates.extend(_clean_text(item) for item in raw)
        else:
            candidates.append(_clean_text(raw))

    for candidate in candidates:
        normalized = candidate.casefold()
        if normalized.startswith("mode:"):
            normalized = normalized.split(":", 1)[1].strip()
        if normalized in _SUPPORTED_MODES:
            return normalized
    return None


def _single_consistent(values: list[str]) -> str | None:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean_text(raw)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    if len(normalized) != 1:
        return None
    return normalized[0]



def plan_requests_semantic_focus_update(plan: TurnPlan) -> bool:
    """Return whether a plan intends to change title, objective, or mode.

    This deliberately answers a broader question than extraction. Ambiguous or
    low-confidence update plans are still deferred from planner-side mutation so
    they can fail safely instead of changing state and then falling through to
    chat.
    """

    for operation in list(getattr(plan, "focusOperations", []) or []):
        kind_value = _enum_value(getattr(operation, "kind", ""))
        try:
            kind = FocusOperationKind(kind_value)
        except ValueError:
            continue

        if kind == FocusOperationKind.RESCOPE_FOCUS:
            return True

        field_value = _enum_value(getattr(operation, "field", ""))
        try:
            field = FocusField(field_value) if field_value else None
        except ValueError:
            field = None

        if kind == FocusOperationKind.SET_FIELD and field in {
            FocusField.TITLE,
            FocusField.OBJECTIVE,
            FocusField.TAGS,
        }:
            return True

        if kind in {
            FocusOperationKind.ADD_LIST_ITEM,
            FocusOperationKind.REMOVE_LIST_ITEM,
        } and field == FocusField.TAGS:
            if _mode_from_values(
                getattr(operation, "values", []),
                getattr(operation, "value", ""),
            ) is not None:
                return True

    return False

def extract_semantic_focus_update(
    plan: TurnPlan,
    *,
    minimum_confidence: float | None = None,
) -> SemanticFocusUpdate | None:
    """Convert semantic Focus planner output into one verified update request.

    The bridge accepts only title, objective, and mode changes. It never uses
    planner-authored success wording and it rejects plans that also start, end,
    complete, or record progress on a Focus.
    """

    threshold = (
        minimum_confidence
        if minimum_confidence is not None
        else float(os.getenv("QMEET_SEMANTIC_FOCUS_UPDATE_MIN_CONFIDENCE", "0.78"))
    )
    plan_confidence = float(getattr(plan, "confidence", 0.0) or 0.0)
    if plan_confidence < threshold:
        return None

    operations = list(getattr(plan, "focusOperations", []) or [])
    if not operations:
        return None

    titles: list[str] = []
    objectives: list[str] = []
    objective_specified = False
    modes: list[str] = []
    relevant_confidences: list[float] = []

    for operation in operations:
        kind_value = _enum_value(getattr(operation, "kind", ""))
        try:
            kind = FocusOperationKind(kind_value)
        except ValueError:
            return None

        if kind in _BLOCKING_OPERATIONS:
            return None
        if kind in _ALLOWED_COMPANION_OPERATIONS:
            continue

        operation_confidence = float(
            getattr(operation, "confidence", plan_confidence) or plan_confidence
        )

        if kind == FocusOperationKind.RESCOPE_FOCUS:
            title = _clean_text(getattr(operation, "title", ""))
            objective = _clean_text(getattr(operation, "objective", ""))
            if title:
                titles.append(title)
                relevant_confidences.append(operation_confidence)
            if objective:
                objectives.append(objective)
                objective_specified = True
                relevant_confidences.append(operation_confidence)
            mode = _mode_from_values(getattr(operation, "tags", []))
            if mode:
                modes.append(mode)
                relevant_confidences.append(operation_confidence)
            continue

        field_value = _enum_value(getattr(operation, "field", ""))
        field = None
        if field_value:
            try:
                field = FocusField(field_value)
            except ValueError:
                return None

        if kind == FocusOperationKind.SET_FIELD:
            if field == FocusField.TITLE:
                title = _clean_text(getattr(operation, "value", ""))
                if not title:
                    return None
                titles.append(title)
                relevant_confidences.append(operation_confidence)
                continue
            if field == FocusField.OBJECTIVE:
                objectives.append(_clean_text(getattr(operation, "value", "")))
                objective_specified = True
                relevant_confidences.append(operation_confidence)
                continue
            if field == FocusField.TAGS:
                mode = _mode_from_values(
                    getattr(operation, "values", []),
                    getattr(operation, "value", ""),
                )
                if mode:
                    modes.append(mode)
                    relevant_confidences.append(operation_confidence)
                    continue
            return None

        if kind == FocusOperationKind.ADD_LIST_ITEM and field == FocusField.TAGS:
            mode = _mode_from_values(
                getattr(operation, "values", []),
                getattr(operation, "value", ""),
            )
            if mode:
                modes.append(mode)
                relevant_confidences.append(operation_confidence)
                continue
            return None

        if kind == FocusOperationKind.REMOVE_LIST_ITEM and field == FocusField.TAGS:
            # Removing an obsolete mode tag commonly accompanies adding the new
            # mode. The lifecycle executor receives only the final requested mode.
            continue

        return None

    title = _single_consistent(titles) if titles else None
    if titles and title is None:
        return None

    objective: str | None = None
    if objective_specified:
        unique_objectives = []
        seen_objectives: set[str] = set()
        for raw in objectives:
            key = raw.casefold()
            if key in seen_objectives:
                continue
            seen_objectives.add(key)
            unique_objectives.append(raw)
        if len(unique_objectives) != 1:
            return None
        objective = unique_objectives[0]

    mode = _single_consistent(modes) if modes else None
    if modes and mode is None:
        return None
    if mode is not None:
        mode = mode.casefold()
        if mode not in _SUPPORTED_MODES:
            return None

    effective_confidence = min([plan_confidence, *relevant_confidences])
    if effective_confidence < threshold:
        return None

    result = SemanticFocusUpdate(
        title=title,
        objective=objective,
        objective_specified=objective_specified,
        mode=mode,
        confidence=effective_confidence,
        reason=(
            "Semantic Focus planner output was converted into a typed, "
            "verified native Focus update."
        ),
    )
    return result if result.has_changes() else None


def _turn_plan_from_store(source_turn_id: str) -> TurnPlan | None:
    turn_id = source_turn_id.strip()
    if not turn_id:
        return None

    for event in reversed(list_events(limit=500)):
        if getattr(event, "sourceTurnId", "") != turn_id:
            continue
        if _enum_value(getattr(event, "type", "")) != "turn_planned":
            continue
        payload = getattr(event, "payload", {})
        if not isinstance(payload, dict):
            return None
        raw_plan = payload.get("plan")
        if not isinstance(raw_plan, dict):
            return None
        try:
            return TurnPlan.model_validate(raw_plan)
        except Exception:
            return None
    return None


async def _wait_for_turn_plan(source_turn_id: str) -> TurnPlan | None:
    timeout = max(
        0.1,
        float(os.getenv("QMEET_SEMANTIC_FOCUS_ROUTE_WAIT_SECONDS", "6.0")),
    )
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        plan = _turn_plan_from_store(source_turn_id)
        if plan is not None:
            return plan
        await asyncio.sleep(0.025)
    return _turn_plan_from_store(source_turn_id)


async def semantic_focus_update_command(
    message: str,
    *,
    source_turn_id: str = "",
) -> dict[str, Any] | None:
    """Return a typed native command from the dedicated semantic authority.

    The broad turn planner remains useful for durable planning, but it is no
    longer the only classifier allowed to recognize title, objective, and mode
    updates. Middleware observation and this route share the same cached
    structured decision for a turn.
    """

    if not message.strip():
        return None

    decision = await get_semantic_focus_update_decision(
        message,
        source_turn_id=source_turn_id,
    )
    turn_id = source_turn_id.strip()

    if decision.intent == SemanticUpdateIntent.NOT_UPDATE:
        return None

    if decision.intent == SemanticUpdateIntent.CLARIFY:
        return {
            "intent": "command",
            "action": "update_focus_session",
            "confidence": max(float(decision.confidence), 0.5),
            "frontendCommand": "clarify semantic focus update",
            "payload": {
                "semanticBridge": True,
                "semanticBridgeVersion": BRIDGE_VERSION,
                "semanticBridgeBlocked": True,
                "sourceTurnId": turn_id,
                "message": (
                    "I understood this as a possible Focus change, but I could "
                    "not verify one specific title, goal, or mode update. "
                    "Please state the exact change again."
                ),
            },
            "reason": decision.reason,
        }

    if not decision.has_changes():
        return {
            "intent": "command",
            "action": "update_focus_session",
            "confidence": max(float(decision.confidence), 0.5),
            "frontendCommand": "clarify semantic focus update",
            "payload": {
                "semanticBridge": True,
                "semanticBridgeVersion": BRIDGE_VERSION,
                "semanticBridgeBlocked": True,
                "sourceTurnId": turn_id,
                "message": (
                    "I understood this as a Focus update, but no concrete title, "
                    "goal, or mode value was available to execute."
                ),
            },
            "reason": decision.reason,
        }

    return {
        "intent": "command",
        "action": "update_focus_session",
        # The backend has already enforced the semantic execution threshold.
        # Keep the measured confidence for telemetry; the frontend recognizes
        # semanticBridge=true as an already-gated typed command.
        "confidence": float(decision.confidence),
        "frontendCommand": "apply semantic focus update",
        "payload": decision.command_payload(turn_id),
        "reason": decision.reason,
    }
