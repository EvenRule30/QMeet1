"""Phase 21E2 deterministic ownership floor for direct Device/UI controls.

The unified agent remains the primary semantic decision-maker. This module only
prevents an unmistakable, reversible QMeet control request from being narrated
as ordinary conversation when the model/fallback misses Device/UI ownership.
It never executes a control and never handles destructive/session-wide actions.
"""

from __future__ import annotations

import re

from app.qmeet_agent_shadow import AgentShadowDecision
from app.qmeet_capabilities import PROMOTED_DEVICE_UI_ACTIONS

_DEVICE_UI_FLOOR_CONFIDENCE = 0.98


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _direct_request_body(message: str) -> str:
    text = _normalize(message)
    text = re.sub(r"[?!.,;:]+$", "", text).strip()
    text = re.sub(
        r"^(?:hey\s+)?(?:q\s*meet|qmeet|orb|assistant)\s*[,;:]?\s*",
        "",
        text,
    ).strip()
    text = re.sub(r"^please\s+", "", text).strip()
    text = re.sub(
        r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?",
        "",
        text,
    ).strip()
    text = re.sub(
        r"^(?:i\s+(?:want|need)\s+you\s+to|i(?:'d|\s+would)\s+like\s+you\s+to)\s+",
        "",
        text,
    ).strip()
    return text


def _looks_like_guidance_or_hypothetical(text: str) -> bool:
    if not text:
        return True
    return bool(
        re.match(
            r"^(?:why|what|when|where|who|how|is|are|do|does|did|should|can\s+i|could\s+i|"
            r"tell\s+me|show\s+me\s+how|explain|describe|teach\s+me|help\s+me\s+(?:understand|learn))\b",
            text,
        )
        or re.search(r"\b(?:how\s+to|what\s+happens\s+if|what\s+would\s+happen\s+if)\b", text)
    )


def _matches(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def resolve_obvious_device_ui_action(message: str) -> str | None:
    """Resolve only unmistakable direct controls in the promoted safe subset.

    This is intentionally an ownership floor, not a general natural-language
    parser. Fuzzy or ambiguous wording remains with the unified agent/legacy
    fallback. The returned value is always a canonical promoted action id.
    """

    text = _direct_request_body(message)
    if _looks_like_guidance_or_hypothetical(text):
        return None

    # Existing Focus-panel semantics have their own deterministic route. A
    # generic UI floor must not reinterpret "open the Focus menu/panel" as the
    # launcher/menu action merely because the word "menu" appears.
    if _matches(r"\bfocus\b", text) and _matches(r"\b(?:menu|panel|controls?|screen)\b", text):
        return None

    # Navigation / panels.
    if _matches(
        r"^(?:go|return|take|bring|get|send)\b.*\b(?:home|main\s+screen|home\s+screen|start\s+screen)\b",
        text,
    ) or _matches(r"^(?:back|home)\s+(?:to\s+)?(?:the\s+)?(?:main|home)?\s*screen?$", text):
        return "go-home"

    if _matches(r"^(?:open|show|display|bring\s+up|pull\s+up)\b.*\bsettings\b", text):
        return "open-settings"
    if _matches(r"^(?:close|hide|dismiss)\b.*\bsettings\b", text):
        return "close-settings"

    if _matches(r"^(?:open|show|display|bring\s+up|pull\s+up)\b.*\b(?:menu|launcher)\b", text):
        return "open-menu"
    if _matches(r"^(?:close|hide|dismiss)\b.*\b(?:menu|launcher)\b", text):
        return "close-menu"

    if _matches(r"^(?:show|open|display|bring\s+up|pull\s+up)\b.*\bstatus\b", text):
        return "show-status"
    if _matches(r"^hide\b.*\bstatus\b", text):
        return "hide-status"
    if _matches(r"^(?:close|dismiss)\b.*\bstatus\b", text):
        return "close-status"

    # Voice speed is more specific than general voice-output toggles.
    if _matches(
        r"^(?:(?:speak|talk|read)\b.*\bslower\b|slow\s+down\b.*\b(?:voice|speech|speaking|talking|reading|responses?|answers?|replies)\b)",
        text,
    ):
        return "voice-slower"
    if _matches(
        r"^(?:(?:speak|talk|read)\b.*\bfaster\b|speed\s+up\b.*\b(?:voice|speech|speaking|talking|reading|responses?|answers?|replies)\b)",
        text,
    ):
        return "voice-faster"
    if _matches(
        r"^(?:(?:speak|talk|read)\b.*\b(?:normally|normal\s+speed)\b|(?:reset|restore|set)\b.*\b(?:voice|speech|speaking)\b.*\b(?:normal|default)\b)",
        text,
    ):
        return "voice-normal"

    # Persistent voice-output state. Mentioning answers/responses/replies or
    # "out loud" distinguishes this from stopping only the current utterance.
    spoken_output_subject = r"(?:voice(?:\s+output)?|speech|spoken\s+(?:responses?|answers?|replies)|reading|speaking)"
    if _matches(
        rf"^(?:(?:turn|switch|set)\b.*\b{spoken_output_subject}\b.*\bon\b|"
        rf"(?:enable|start|resume|unmute)\b.*\b{spoken_output_subject}\b|"
        r"(?:start|resume)\s+(?:reading|speaking)\b.*\b(?:answers?|responses?|replies)\b(?:.*\b(?:out\s+loud|aloud)\b)?)",
        text,
    ):
        return "voice-output-on"

    if _matches(
        rf"^(?:(?:turn|switch|set)\b.*\b{spoken_output_subject}\b.*\boff\b|"
        rf"(?:disable|mute)\b.*\b{spoken_output_subject}\b|"
        r"stop\s+(?:reading|speaking)\b.*\b(?:answers?|responses?|replies)\b(?:.*\b(?:out\s+loud|aloud)\b)?)",
        text,
    ):
        return "voice-output-off"

    if _matches(r"^(?:toggle|switch)\b.*\b(?:voice|voice\s+output|spoken\s+responses?)\b", text):
        return "voice-output-toggle"

    # Current-utterance stop remains separate from disabling future output.
    if _matches(r"^(?:stop|quit|cease)\s+(?:speaking|talking|reading)(?:\s+(?:now|please))?$", text):
        return "stop-speaking"

    if _matches(
        r"^(?:what\s+did\s+you\s+hear|repeat\s+what\s+you\s+heard|show\s+(?:me\s+)?(?:the\s+)?(?:last\s+)?transcript|read\s+(?:back\s+)?what\s+you\s+heard)$",
        text,
    ):
        return "what-did-you-hear"

    if _matches(
        r"^(?:close|hide|dismiss)\s+(?:(?:this|the|current|active)\s+)?(?:panel|overlay|screen|window)$",
        text,
    ):
        return "close-generic"

    return None


def _is_valid_existing_device_ui_proposal(decision: AgentShadowDecision) -> bool:
    return (
        decision.turnOwner == "device_ui"
        and decision.disposition == "tool"
        and decision.proposedCapability == "device_ui"
        and decision.proposedAction in PROMOTED_DEVICE_UI_ACTIONS
        and decision.proposedArguments == {}
    )


def apply_device_ui_ownership_floor(
    user_message: str,
    decision: AgentShadowDecision,
) -> AgentShadowDecision:
    """Repair only obvious direct-control misses before routing can become chat."""

    if _is_valid_existing_device_ui_proposal(decision):
        # Device/UI owns its own control turn. Active Focus may remain available
        # as ambient context elsewhere, but it is not relevant to execution or
        # continuation for this independent capability action.
        if decision.focusRelevant:
            return decision.model_copy(update={"focusRelevant": False})
        return decision

    action = resolve_obvious_device_ui_action(user_message)
    if action is None or action not in PROMOTED_DEVICE_UI_ACTIONS:
        return decision

    # Never steal an already-specific non-UI capability claim. The floor exists
    # to repair general/focus/device ambiguity, not to override Calendar, Tasks,
    # Notes, Search, Memory, or Visual ownership.
    if decision.turnOwner not in {"general_chat", "device_ui", "focus", "other"}:
        return decision

    return AgentShadowDecision(
        turnOwner="device_ui",
        focusRelevant=False,
        disposition="tool",
        proposedCapability="device_ui",
        proposedAction=action,
        proposedArguments={},
        responsePlan=(
            "Execute the existing deterministic QMeet Device/UI control and keep "
            "the visible acknowledgement brief."
        ),
        confidence=max(_DEVICE_UI_FLOOR_CONFIDENCE, float(decision.confidence)),
        reason=(
            "Deterministic Device/UI ownership floor repaired an unmistakable "
            "direct reversible QMeet control request; execution remains with the "
            "existing deterministic frontend/device handler."
        ),
    )
