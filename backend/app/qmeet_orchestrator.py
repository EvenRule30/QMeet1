"""Phase 17C QMeet intent orchestrator.

The orchestrator is a thin model-backed router. It receives the user's message plus
lightweight browser context and returns a normal CommandInterpretResponse-compatible
payload. Existing deterministic frontend commands still execute the final action.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment]

from app.qmeet_capabilities import QMEET_SYSTEM_PROMPT, capability_digest

DEFAULT_MODEL = os.getenv("OPENAI_COMMAND_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
MIN_ORCHESTRATOR_CONFIDENCE = float(os.getenv("QMEET_ORCHESTRATOR_MIN_CONFIDENCE", "0.72"))


def _is_openai_enabled() -> bool:
    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    return provider in {"openai", "openai-compatible", "openai_compatible"}


def _command_response(
    *,
    action: str,
    frontend_command: str,
    confidence: float,
    reason: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "intent": "command",
        "action": action,
        "confidence": confidence,
        "frontendCommand": frontend_command,
        "payload": payload or {},
        "reason": reason,
    }


def _chat_response(reason: str, confidence: float = 0.35) -> dict[str, Any]:
    return {
        "intent": "chat",
        "action": "none",
        "confidence": confidence,
        "frontendCommand": "",
        "payload": {},
        "reason": reason,
    }


def _normalize(value: str) -> str:
    text = re.sub(r"[“”]", '"', value.strip())
    text = re.sub(r"[‘’]", "'", text)
    text = re.sub(r"[?!.,;:]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(?:hey\s+)?(?:q\s*meet|qmeet|orb|assistant)\s+", "", text, flags=re.I)
    return text


def _memory_state(client_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(client_context, dict):
        return {}
    memory_state = client_context.get("memoryState")
    return memory_state if isinstance(memory_state, dict) else {}


def _active_session_title(memory_state: dict[str, Any]) -> str:
    active = memory_state.get("activeSession")
    if isinstance(active, dict) and isinstance(active.get("title"), str):
        return active["title"].strip()
    return ""



def _is_active_focus_work_help(lowered: str) -> bool:
    """True when the user wants substantive help with the active focus, not QMeet feature help."""
    patterns = [
        r"\bwhat\s+(?:do|should|can)\s+i\s+do\s+(?:now|next)\b",
        r"\bwhat\s+can\s+i\s+do\s+(?:with\s+(?:it|this|that)|now|next)\b",
        r"\bnow\s+what\b",
        r"\bwhat\s+more\s+do\s+you\s+need\s+to\s+know\b",
        r"\bwhat\s+do\s+you\s+need\s+(?:to\s+know|from\s+me)\b",
        r"\b(?:can|could|will|would)\s+you\s+help\s+me\s+(?:with|do|write|fix|debug|finish|complete|get|getting|build|make)",
        r"\b(?:i\s+)?(?:just\s+)?(?:want|need)\s+help\s+(?:with|doing|writing|fixing|debugging|finishing|getting|building|making)",
        r"\bi\s+(?:do\s+not|don'?t)\s+like\s+those\s+tasks\b",
        r"\bhelp\s+me\s+(?:do|write|fix|debug|finish|complete|build|make|understand)\b",
    ]
    return any(re.search(pattern, lowered, flags=re.I) for pattern in patterns)

def _active_panel(ui_state: dict[str, Any] | None) -> str:
    if not isinstance(ui_state, dict):
        return ""
    panel = ui_state.get("activePanel")
    return panel if isinstance(panel, str) else ""


def _extract_after(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.I)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip(" .,:;?!\"'")


def _fallback_orchestrator(
    message: str,
    *,
    ui_state: dict[str, Any] | None = None,
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fast deterministic coverage for common ambiguous QMeet/UI/help cases.

    This is intentionally small. It keeps the feature useful in mock mode and gives the
    model a fallback if OpenAI is unavailable.
    """
    text = _normalize(message)
    lowered = text.lower()
    panel = _active_panel(ui_state)
    memory_state = _memory_state(client_context)
    active_title = _active_session_title(memory_state)

    if not text:
        return None

    if active_title and _is_active_focus_work_help(lowered):
        return _chat_response(
            "User is asking for substantive help with the active focus, so normal chat should answer using focus context instead of routing to a QMeet guide/tool.",
            0.92,
        )

    if re.search(r"\b(?:what\s+are\s+you|who\s+are\s+you|what\s+is\s+q\s*meet)\b", lowered):
        return _command_response(
            action="guide_overview",
            frontend_command="what can you do",
            confidence=0.9,
            reason="Orchestrator fallback routed identity/onboarding to the QMeet guide.",
        )

    if re.search(r"\b(?:what\s+can\s+(?:you|q\s*meet)|what\s+are\s+you\s+able|how\s+do\s+i\s+use|what\s+can\s+i\s+say|commands?)\b", lowered):
        topic_commands = [
            (r"\b(?:camera|webcam|visual|vision|image|snapshot|upload)\b", "help with camera", "guide_visual"),
            (r"\b(?:calendar|schedule|agenda|event|meeting|appointment)\b", "help with calendar", "guide_calendar"),
            (r"\b(?:focus|session|goal)\b", "help with focus", "guide_focus"),
            (r"\b(?:memory|remember|tasks?|notes?)\b", "help with memory", "guide_memory"),
            (r"\b(?:search|web|look\s+up)\b", "help with search", "guide_search"),
        ]
        for topic_pattern, frontend_command, action in topic_commands:
            if re.search(topic_pattern, lowered):
                return _command_response(
                    action=action,
                    frontend_command=frontend_command,
                    confidence=0.9,
                    reason="Orchestrator fallback routed topic-specific capability help to the QMeet guide.",
                )
        return _command_response(
            action="guide_overview",
            frontend_command="what can you do",
            confidence=0.88,
            reason="Orchestrator fallback routed broad capability help to the QMeet guide.",
        )

    if re.search(r"\b(?:what\s+is|how\s+do\s+i\s+use|help\s+(?:with|on))\s+(?:focus|a\s+focus|focus\s+session)\b", lowered):
        return _command_response(
            action="guide_focus",
            frontend_command="help with focus",
            confidence=0.92,
            reason="Orchestrator fallback routed focus education to the focus guide.",
        )

    if re.search(r"\b(?:what\s+can\s+i\s+do\s+(?:now|next|with\s+it|with\s+this)|now\s+what|what\s+are\s+my\s+options|can\s+i\s+(?:click|tap|press)|what\s+can\s+i\s+(?:click|tap|press))\b", lowered):
        return _command_response(
            action="guide_screen",
            frontend_command="what can I do now",
            confidence=0.9,
            reason=f"Orchestrator fallback routed contextual UI guidance. activePanel={panel or 'none'}.",
            payload={"activePanel": panel, "activeSessionTitle": active_title},
        )

    if re.search(r"\b(?:what\s+(?:was|is)\s+that\s+(?:menu|panel|screen|thing)|how\s+(?:do|to)\s+i\s+(?:open|get\s+back\s+to|reopen)\s+(?:it|that|this))\b", lowered):
        if active_title or panel == "memory":
            return _command_response(
                action="open_memory",
                frontend_command="open memory",
                confidence=0.86,
                reason="Orchestrator fallback treated the referenced panel as the focus/memory controls.",
                payload={"activePanel": panel, "activeSessionTitle": active_title},
            )
        return _command_response(
            action="open_menu",
            frontend_command="open menu",
            confidence=0.78,
            reason="Orchestrator fallback opened the launcher because no specific referenced panel was known.",
            payload={"activePanel": panel},
        )

    if re.search(r"\b(?:focus\s+menu|focus\s+controls|focus\s+panel|that\s+focus\s+thing|focus\s+stuff)\b", lowered):
        return _command_response(
            action="open_memory",
            frontend_command="open memory",
            confidence=0.93,
            reason="Orchestrator fallback routed focus UI wording to the Memory panel.",
        )

    if re.search(r"\b(?:camera|webcam|snapshot|upload\s+(?:an\s+)?image|visual\s+analysis)\b", lowered) and re.search(r"\b(?:open|show|use|where|how)\b", lowered):
        return _command_response(
            action="open_camera",
            frontend_command="open camera",
            confidence=0.86,
            reason="Orchestrator fallback routed camera/visual tool request to the Camera overlay.",
        )

    if re.search(r"\b(?:schedule|calendar|agenda|appointments?)\b", lowered) and re.search(r"\b(?:show|open|see|view)\b", lowered):
        return _command_response(
            action="open_calendar",
            frontend_command="open calendar",
            confidence=0.83,
            reason="Orchestrator fallback routed schedule viewing to Calendar.",
        )

    if re.search(r"\b(?:next|upcoming)\s+(?:meeting|event|appointment|call)\b", lowered) and re.search(r"\b(?:prepare|prep|focus|tasks?|checklist)\b", lowered):
        if re.search(r"\b(?:tasks?|checklist|steps)\b", lowered):
            return _command_response(
                action="meeting_prep_tasks",
                frontend_command="make prep tasks for my next meeting",
                confidence=0.9,
                reason="Orchestrator fallback routed next-event task request to meeting prep tasks.",
            )
        return _command_response(
            action="prepare_next_meeting",
            frontend_command="prepare me for my next meeting",
            confidence=0.9,
            reason="Orchestrator fallback routed next-event prep to calendar focus prep.",
        )

    appointment_payload = _extract_after(
        r"\b(?:i\s+have|i've\s+got|there\s+is|there's)\s+(?:an?\s+)?(.+?\b(?:today|tomorrow|tonight|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{1,2}:\d{2}\s*(?:am|pm)?).*)",
        text,
    )
    if appointment_payload and re.search(r"\b(?:prepare|prep|focus|get\s+ready)\b", lowered):
        return _command_response(
            action="start_focus_session",
            frontend_command=f"start a meeting focus session for {appointment_payload}",
            confidence=0.82,
            reason="Orchestrator fallback routed ad-hoc appointment prep to a meeting focus.",
            payload={"title": appointment_payload, "mode": "meeting"},
        )

    working_payload = _extract_after(r"\b(?:i(?:'m|\s+am)|we(?:'re|\s+are))\s+(?:working|focusing)\s+on\s+(.+)$", text)
    if working_payload:
        return _command_response(
            action="start_focus_session",
            frontend_command=f"start a focus session for {working_payload}",
            confidence=0.86,
            reason="Orchestrator fallback routed current-work statement to a focus session.",
            payload={"title": working_payload},
        )

    goal_payload = _extract_after(r"\b(?:my\s+goal\s+is|set\s+(?:my\s+)?goal\s+to|the\s+goal\s+is)\s+(.+)$", text)
    if goal_payload:
        return _command_response(
            action="set_focus_goal",
            frontend_command=f"set my goal to {goal_payload}",
            confidence=0.88,
            reason="Orchestrator fallback routed goal wording to focus goal update.",
            payload={"goal": goal_payload},
        )

    if active_title and re.search(r"\b(?:what\s+should\s+i\s+do\s+next|help\s+me\s+(?:plan|finish|complete)|recommend|next\s+step)\b", lowered):
        return _command_response(
            action="enhanced_recap",
            frontend_command="what should I focus on next",
            confidence=0.78,
            reason="Orchestrator fallback routed active-focus next-step request to enhanced recap/recommendations.",
        )

    return None


def _json_object_from_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.I).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _sanitize_model_intent(value: dict[str, Any]) -> dict[str, Any] | None:
    intent = value.get("intent")
    if intent == "chat":
        return _chat_response(str(value.get("reason") or "Orchestrator chose normal chat."), float(value.get("confidence") or 0.4))
    if intent != "command":
        return None

    frontend_command = value.get("frontendCommand")
    action = value.get("action") or "orchestrated_command"
    if not isinstance(frontend_command, str) or not frontend_command.strip():
        return None

    confidence_raw = value.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 0.74

    payload = value.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    if confidence < MIN_ORCHESTRATOR_CONFIDENCE:
        return _chat_response(
            f"Orchestrator confidence was below threshold: {confidence:.2f}.",
            confidence,
        )

    return _command_response(
        action=str(action),
        frontend_command=frontend_command.strip(),
        confidence=confidence,
        reason=str(value.get("reason") or "QMeet orchestrator selected this command."),
        payload=payload,
    )


async def interpret_qmeet_orchestrator(
    message: str,
    *,
    ui_state: dict[str, Any] | None = None,
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a CommandInterpretResponse-compatible dict, or None to keep routing."""
    fallback = _fallback_orchestrator(message, ui_state=ui_state, client_context=client_context)

    if fallback and fallback.get("intent") == "chat" and float(fallback.get("confidence") or 0) >= 0.85:
        return fallback

    if not _is_openai_enabled() or not os.getenv("OPENAI_API_KEY") or AsyncOpenAI is None:
        return fallback

    # The fallback already handles the highest-confidence common cases. The model is most
    # useful for fuzzy wording around UI/help/QMeet actions.
    try:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            temperature=0.0,
            max_tokens=350,
            messages=[
                {"role": "system", "content": QMEET_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": message,
                            "uiState": ui_state or {},
                            "clientContext": client_context or {},
                            "allowedActions": capability_digest(),
                            "requiredOutput": {
                                "intent": "command or chat",
                                "action": "one allowed action id, or none",
                                "confidence": "0 to 1",
                                "frontendCommand": "exact QMeet command to execute, or empty for chat",
                                "payload": "small object with extracted values if useful",
                                "reason": "short routing reason",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content if response.choices else ""
        parsed = _json_object_from_text(content or "")
        if parsed:
            sanitized = _sanitize_model_intent(parsed)
            if sanitized is not None:
                return sanitized
    except Exception:
        # Keep command routing usable even if the model fails.
        return fallback

    return fallback
