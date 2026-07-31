from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable
from uuid import uuid4

from app.focus import middleware as focus_middleware
from app.focus.models import (
    FocusEvent,
    FocusEventType,
    FocusState,
    ObserveTurnRequest,
    TurnPlan,
)
from app.focus.semantic_update_intent import (
    BRIDGE_VERSION,
    SemanticUpdateIntent,
    get_semantic_focus_update_decision,
    semantic_update_turn_plan,
)
from app.focus.store import append_events, get_state, has_turn

_ObserveTurn = Callable[
    [ObserveTurnRequest],
    Awaitable[tuple[TurnPlan, FocusState]],
]
_INSTALLED = False
_ORIGINAL_OBSERVE_TURN = focus_middleware.observe_turn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_deferred_decision(
    plan: TurnPlan,
    *,
    message: str,
    turn_id: str,
    source: str,
    semantic_intent: str,
) -> FocusState:
    current = get_state()
    append_events(
        [
            FocusEvent(
                id=f"focus-event-{uuid4().hex}",
                focusId=current.focusId,
                type=FocusEventType.TURN_PLANNED,
                payload={
                    "message": message,
                    "route": plan.route.value,
                    "reason": plan.reason,
                    "plan": plan.model_dump(mode="json"),
                    "executionPolicy": {
                        "nativeFocusUpdateDeferred": True,
                        "semanticBridgeVersion": BRIDGE_VERSION,
                        "semanticIntent": semantic_intent,
                        "suppressedFocusOperationCount": len(
                            plan.focusOperations
                        ),
                        "responseCandidateSuppressed": True,
                    },
                },
                sourceTurnId=turn_id,
                source=source,
                confidence=plan.confidence,
                createdAt=_now_iso(),
            )
        ]
    )
    return get_state()


async def _observe_turn_with_semantic_update_deferral(
    request: ObserveTurnRequest,
    *,
    turn_id: str | None = None,
) -> tuple[TurnPlan, FocusState]:
    """Give semantic current-Focus updates one non-mutating authority.

    For command interpretation turns, the dedicated semantic classifier runs
    before the broad planner. Update and clarification decisions are recorded
    for telemetry but never applied by the planner. The command router consumes
    the same cached decision and sends typed fields to the verified lifecycle
    executor. Non-update turns continue through the original observer unchanged.
    """

    if request.source != "command-interpret-shadow" or not request.apply:
        return await _ORIGINAL_OBSERVE_TURN(request, turn_id=turn_id)

    effective_turn_id = (turn_id or f"focus-turn-{uuid4().hex}").strip()
    if has_turn(effective_turn_id):
        return await _ORIGINAL_OBSERVE_TURN(
            request,
            turn_id=effective_turn_id,
        )

    decision = await get_semantic_focus_update_decision(
        request.message,
        source_turn_id=effective_turn_id,
    )
    if decision.intent == SemanticUpdateIntent.NOT_UPDATE:
        return await _ORIGINAL_OBSERVE_TURN(
            request,
            turn_id=effective_turn_id,
        )

    plan = semantic_update_turn_plan(decision)
    state = _record_deferred_decision(
        plan,
        message=request.message,
        turn_id=effective_turn_id,
        source=request.source,
        semantic_intent=decision.intent.value,
    )
    return plan, state


def install_semantic_focus_update_observation_policy() -> None:
    """Install the command-observation policy once at backend startup."""

    global _INSTALLED
    if _INSTALLED:
        return
    focus_middleware.observe_turn = _observe_turn_with_semantic_update_deferral
    _INSTALLED = True


def semantic_focus_update_observation_policy_installed() -> bool:
    return _INSTALLED and (
        focus_middleware.observe_turn
        is _observe_turn_with_semantic_update_deferral
    )
