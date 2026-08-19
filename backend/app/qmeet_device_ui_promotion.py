"""Phase 21E Device/UI promotion adapter.

The unified agent may select one narrow, non-destructive Device/UI action. This
module validates that semantic proposal and translates it into an existing
frontend command string. It never mutates UI/device state itself; the existing
frontend parser and deterministic handlers remain authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.qmeet_agent_shadow import (
    AgentShadowDecision,
    AgentShadowRequest,
    decide_agent_shadow,
)
from app.qmeet_capabilities import PROMOTED_DEVICE_UI_ACTIONS
from app.qmeet_device_ui_ownership import apply_device_ui_ownership_floor

MIN_DEVICE_UI_PROMOTION_CONFIDENCE = 0.90

_DEVICE_UI_FRONTEND_COMMAND_BY_ACTION: dict[str, str] = {
    "open-menu": "open menu",
    "close-menu": "close menu",
    "open-settings": "open settings",
    "close-settings": "close settings",
    "go-home": "go home",
    "show-status": "show status",
    "close-status": "close status",
    "hide-status": "hide status",
    "voice-output-on": "voice on",
    "voice-output-off": "voice off",
    "voice-output-toggle": "toggle voice",
    "voice-slower": "speak slower",
    "voice-faster": "speak faster",
    "voice-normal": "normal voice",
    "stop-speaking": "stop speaking",
    "what-did-you-hear": "what did you hear",
    "close-generic": "close current panel",
}

if set(_DEVICE_UI_FRONTEND_COMMAND_BY_ACTION) != set(PROMOTED_DEVICE_UI_ACTIONS):
    raise RuntimeError(
        "Phase 21E Device/UI frontend command mapping must exactly match the promoted action contract."
    )


@dataclass(frozen=True)
class DeviceUiPromotionResult:
    status: Literal["not-owned", "execute", "blocked"]
    action: str = ""
    frontend_command: str = ""
    confidence: float = 0.0
    reason: str = ""

    @property
    def claimed(self) -> bool:
        return self.status != "not-owned"

    @property
    def executable(self) -> bool:
        return self.status == "execute"


def frontend_command_for_promoted_device_ui_action(action: str) -> str | None:
    return _DEVICE_UI_FRONTEND_COMMAND_BY_ACTION.get(action)


def evaluate_device_ui_promotion(
    decision: AgentShadowDecision,
) -> DeviceUiPromotionResult:
    """Strictly validate one unified-agent Device/UI proposal.

    Device/UI ownership is treated as a claim even when the proposal is invalid.
    A claimed-but-invalid result is blocked so the legacy orchestrator cannot
    silently choose a different Device/UI action after the unified agent has
    already claimed the capability.
    """

    if decision.turnOwner != "device_ui":
        return DeviceUiPromotionResult(status="not-owned")

    action = decision.proposedAction.strip()
    confidence = float(decision.confidence)

    if decision.disposition != "tool":
        return DeviceUiPromotionResult(
            status="blocked",
            action=action,
            confidence=confidence,
            reason="Device/UI ownership did not include one executable tool disposition.",
        )
    if decision.proposedCapability != "device_ui":
        return DeviceUiPromotionResult(
            status="blocked",
            action=action,
            confidence=confidence,
            reason="Device/UI ownership proposed a different capability.",
        )
    if action not in PROMOTED_DEVICE_UI_ACTIONS:
        return DeviceUiPromotionResult(
            status="blocked",
            action=action,
            confidence=confidence,
            reason="The proposed Device/UI action is outside the Phase 21E promoted allowlist.",
        )
    if decision.proposedArguments != {}:
        return DeviceUiPromotionResult(
            status="blocked",
            action=action,
            confidence=confidence,
            reason="Phase 21E Device/UI promotion accepts no model-supplied arguments.",
        )
    if confidence < MIN_DEVICE_UI_PROMOTION_CONFIDENCE:
        return DeviceUiPromotionResult(
            status="blocked",
            action=action,
            confidence=confidence,
            reason="The Device/UI proposal was below the promotion confidence threshold.",
        )

    frontend_command = frontend_command_for_promoted_device_ui_action(action)
    if not frontend_command:
        return DeviceUiPromotionResult(
            status="blocked",
            action=action,
            confidence=confidence,
            reason="The canonical Device/UI action has no deterministic frontend command mapping.",
        )

    return DeviceUiPromotionResult(
        status="execute",
        action=action,
        frontend_command=frontend_command,
        confidence=confidence,
        reason=(
            "The unified agent selected one strictly validated Phase 21E Device/UI action; "
            "execution remains with the existing deterministic frontend/device handler."
        ),
    )


async def resolve_promoted_device_ui_turn(
    message: str,
    *,
    ui_state: dict[str, Any] | None = None,
    client_context: dict[str, Any] | None = None,
) -> DeviceUiPromotionResult:
    """Ask the unified agent for semantics, repair obvious ownership misses, then validate."""

    response = await decide_agent_shadow(
        AgentShadowRequest(
            userMessage=message,
            uiState=ui_state or {},
            clientContext=client_context or {},
        )
    )
    decision = apply_device_ui_ownership_floor(message, response.decision)
    return evaluate_device_ui_promotion(decision)
