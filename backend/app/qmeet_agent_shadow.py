from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment]

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.qmeet_capabilities import capability_digest
from app.tool_continuation import active_focus_snapshot


TurnOwner = Literal[
    "general_chat",
    "calendar",
    "search",
    "memory",
    "tasks",
    "notes",
    "focus",
    "device_ui",
    "visual",
    "other",
]

Disposition = Literal["conversation", "tool", "clarify"]

DEFAULT_MODEL = (
    os.getenv("OPENAI_AGENT_MODEL")
    or os.getenv("OPENAI_COMMAND_MODEL")
    or os.getenv("OPENAI_MODEL")
    or "gpt-4.1-mini"
)

AGENT_SHADOW_SCHEMA_VERSION = "phase21b-v1"

AGENT_SHADOW_SYSTEM_PROMPT = """
You are the Phase 21B shadow decision layer for QMeet, an AI-first tablet assistant.

You are OBSERVATIONAL ONLY. You never execute tools, mutate state, or generate the visible user reply. Your job is to predict how a future unified QMeet agent should own the current user turn before any state-changing action occurs.

Core rule: decide TURN OWNERSHIP before deciding whether Active Focus matters.

Turn owners:
- general_chat: greetings, general knowledge, ordinary conversation, or unrelated questions that need no QMeet capability.
- calendar: schedule/event/calendar reads or writes.
- search: web/search/review/look-up requests.
- memory: memory panel/history/general memory operations that are not specifically task or note operations.
- tasks: task creation, completion, task reads, or task organization.
- notes: note creation, note reads, note editing, or notes panel work.
- focus: Focus lifecycle, Focus goal/context/task linkage, Focus reads, or substantive work that clearly continues the active Focus.
- device_ui: navigation, voice, panel, launcher, or other direct UI/device controls.
- visual: camera/upload/visual-context requests.
- other: a capability not represented above.

Focus rules:
- An active Focus is context, not universal ownership.
- Set focusRelevant=false for unrelated Calendar, Search, Memory, greeting, general-knowledge, or device turns.
- Cross-capability turns may have turnOwner != focus while focusRelevant=true. Example: "add practice time for my presentation tomorrow at 2" can be calendar-owned while the presentation Focus is relevant context.
- A pending Focus coaching question is advisory context, not a conversational lock.
- If the user asks for substantive help and enough Focus context already exists, prefer disposition=conversation rather than inventing a Focus mutation.

Disposition:
- conversation: the assistant should answer/help without a state-changing tool.
- tool: a deterministic capability should execute or read authoritative state.
- clarify: one clarification is genuinely required before safe/useful execution.

Proposed action is semantic shadow metadata only. It is NOT executable and must never be treated as proof that anything changed.

Current prototype constraint: Calendar event creation currently understands today/tomorrow reliably; do not treat unsupported farther-day wording as a Focus-routing issue.

Return one compact JSON object with exactly these fields:
{
  "turnOwner": one owner string,
  "focusRelevant": boolean,
  "disposition": "conversation" | "tool" | "clarify",
  "proposedCapability": short capability string or "none",
  "proposedAction": short semantic action id or "none",
  "proposedArguments": object,
  "responsePlan": one short sentence describing what the visible assistant should do after any verified tool result,
  "confidence": number from 0 to 1,
  "reason": one short routing reason
}
""".strip()


GLOBAL_CAPABILITY_CONTRACT = [
    {
        "owner": "general_chat",
        "authority": "read-only conversation",
        "actions": ["conversation.respond"],
    },
    {
        "owner": "focus",
        "authority": "canonical verified Focus backend",
        "actions": [
            "focus.start",
            "focus.read",
            "focus.update_goal",
            "focus.update_context",
            "focus.end",
            "focus.resume",
            "focus.help",
        ],
        "rule": "Active Focus is context, not universal ownership.",
    },
    {
        "owner": "calendar",
        "authority": "deterministic Calendar handlers / verified Google Calendar writes",
        "actions": ["calendar.read", "calendar.create_event", "calendar.update_event", "calendar.delete_event"],
        "constraint": "Current natural event-date support is primarily today/tomorrow.",
    },
    {
        "owner": "search",
        "authority": "deterministic search capability",
        "actions": ["search.run", "search.open"],
    },
    {
        "owner": "memory",
        "authority": "deterministic Memory state",
        "actions": ["memory.open", "memory.read"],
    },
    {
        "owner": "tasks",
        "authority": "deterministic task handlers plus canonical Focus lineage when linked",
        "actions": ["tasks.read", "tasks.create", "tasks.complete", "tasks.clear_completed"],
    },
    {
        "owner": "notes",
        "authority": "deterministic note handlers",
        "actions": ["notes.open", "notes.read", "notes.save", "notes.delete"],
    },
    {
        "owner": "device_ui",
        "authority": "deterministic frontend/device handlers",
        "actions": ["ui.navigate", "voice.control"],
    },
    {
        "owner": "visual",
        "authority": "deterministic camera/visual-context handlers",
        "actions": ["visual.open_camera", "visual.read_context", "visual.link_to_focus"],
    },
]


class ShadowConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=6000)

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        return value.strip()


class LegacyRouteObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str = Field(min_length=1, max_length=160)
    owner: TurnOwner | None = None
    action: str = Field(default="", max_length=160)
    frontendCommand: str = Field(default="", max_length=600)
    disposition: Disposition | None = None


class AgentShadowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userMessage: str = Field(min_length=1, max_length=6000)
    recentConversation: list[ShadowConversationMessage] = Field(default_factory=list, max_length=16)
    uiState: dict[str, Any] = Field(default_factory=dict)
    clientContext: dict[str, Any] = Field(default_factory=dict)
    legacyObservation: LegacyRouteObservation | None = None

    @field_validator("userMessage")
    @classmethod
    def clean_user_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("userMessage cannot be blank")
        return cleaned


class AgentShadowDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turnOwner: TurnOwner
    focusRelevant: bool
    disposition: Disposition
    proposedCapability: str
    proposedAction: str
    proposedArguments: dict[str, Any] = Field(default_factory=dict)
    responsePlan: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class AgentShadowComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compared: bool
    ownerAgreement: bool | None = None
    dispositionAgreement: bool | None = None
    actionAgreement: bool | None = None
    legacyRoute: str = ""
    disagreementSummary: str = ""


class AgentShadowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    mode: Literal["shadow"] = "shadow"
    schemaVersion: str = AGENT_SHADOW_SCHEMA_VERSION
    turnId: str
    decision: AgentShadowDecision
    comparison: AgentShadowComparison


def _is_openai_enabled() -> bool:
    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    return provider in {"openai", "openai-compatible", "openai_compatible"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _tokens(text: str) -> set[str]:
    stop = {
        "about",
        "after",
        "again",
        "before",
        "could",
        "focus",
        "from",
        "have",
        "help",
        "into",
        "make",
        "need",
        "prepare",
        "should",
        "that",
        "their",
        "there",
        "these",
        "this",
        "those",
        "want",
        "with",
        "would",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) >= 4 and token not in stop
    }


def _focus_overlap(message: str, focus: dict[str, Any] | None) -> bool:
    if not focus:
        return False
    focus_text = " ".join(
        str(focus.get(key) or "")
        for key in ("title", "objective", "deliverable", "subject")
    )
    return bool(_tokens(message) & _tokens(focus_text))


def _recent_focus_continuation(request: AgentShadowRequest, focus: dict[str, Any] | None) -> bool:
    if not focus:
        return False
    message = _normalize(request.userMessage)
    if len(message.split()) > 7:
        return False
    if re.fullmatch(r"(?:hi|hello|hey|hello there|hey there|good morning|good afternoon|good evening)[.!?]*", message):
        return False
    continuation_markers = (
        "help me",
        "can you help",
        "so can you help",
        "main points",
        "key points",
        "outline",
        "do that",
        "continue",
        "go ahead",
        "what next",
    )
    if not any(marker in message for marker in continuation_markers):
        return False

    recent_text = " ".join(item.content for item in request.recentConversation[-4:])
    focus_text = " ".join(
        str(focus.get(key) or "")
        for key in ("title", "objective", "deliverable", "subject")
    )
    return bool(_tokens(recent_text) & _tokens(focus_text))


def _focus_is_relevant(request: AgentShadowRequest, focus: dict[str, Any] | None) -> bool:
    message = request.userMessage
    normalized = _normalize(message)
    if not focus:
        return False
    if re.search(r"\b(?:my|our|this|that|current|active)\s+(?:focus|goal)\b|\bfocus session\b", normalized):
        return True
    return _focus_overlap(message, focus) or _recent_focus_continuation(request, focus)


def _decision(
    *,
    owner: TurnOwner,
    focus_relevant: bool,
    disposition: Disposition,
    capability: str,
    action: str,
    response_plan: str,
    confidence: float,
    reason: str,
    arguments: dict[str, Any] | None = None,
) -> AgentShadowDecision:
    return AgentShadowDecision(
        turnOwner=owner,
        focusRelevant=focus_relevant,
        disposition=disposition,
        proposedCapability=capability,
        proposedAction=action,
        proposedArguments=arguments or {},
        responsePlan=response_plan,
        confidence=confidence,
        reason=reason,
    )


def _fallback_shadow_decision(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
) -> AgentShadowDecision:
    text = _normalize(request.userMessage)
    focus_relevant = _focus_is_relevant(request, focus)

    if re.fullmatch(r"(?:hi|hello|hey|hello there|hey there|good morning|good afternoon|good evening)[.!?]*", text):
        return _decision(
            owner="general_chat",
            focus_relevant=False,
            disposition="conversation",
            capability="none",
            action="conversation.respond",
            response_plan="Reply naturally to the greeting without steering back to Active Focus.",
            confidence=0.99,
            reason="Self-contained greeting should remain general conversation.",
        )

    if re.search(r"\b(?:search|look up|find reviews?|reviews? of|web search)\b", text):
        return _decision(
            owner="search",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="search",
            action="search.run",
            response_plan="Run Search, then summarize or offer the most useful consequence of the verified result.",
            confidence=0.94,
            reason="The user explicitly requested web/search work.",
            arguments={"query": request.userMessage},
        )

    calendar_terms = re.search(r"\b(?:calendar|appointment|schedule|event|meeting at|tomorrow at|today at)\b", text)
    calendar_write = re.search(r"\b(?:add|schedule|create|move|change|delete|remove|cancel)\b", text)
    if calendar_terms:
        return _decision(
            owner="calendar",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="calendar",
            action="calendar.create_event" if calendar_write else "calendar.read",
            response_plan="Use Calendar as the authoritative capability and keep unrelated Focus state unchanged.",
            confidence=0.95,
            reason="Calendar/event language owns this turn.",
            arguments={"request": request.userMessage},
        )

    if re.search(r"\b(?:note|notes)\b", text):
        return _decision(
            owner="notes",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="notes",
            action="notes.open" if re.search(r"\b(?:open|show|view)\b", text) else "notes.save",
            response_plan="Use the Notes capability and continue conversationally after the verified note result.",
            confidence=0.91,
            reason="The user explicitly referenced notes.",
            arguments={"request": request.userMessage},
        )

    if re.search(r"\b(?:task|tasks|checklist|to do|todo)\b", text):
        action = "tasks.complete" if re.search(r"\b(?:done|complete|completed|finish|finished)\b", text) else "tasks.read"
        if re.search(r"\b(?:make|create|turn .* into|add)\b", text):
            action = "tasks.create"
        return _decision(
            owner="tasks",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="tasks",
            action=action,
            response_plan="Use deterministic task handling and preserve canonical Focus lineage when the task is Focus-linked.",
            confidence=0.91,
            reason="The user explicitly referenced task work.",
            arguments={"request": request.userMessage},
        )

    if re.search(r"\bmemory\b", text):
        return _decision(
            owner="memory",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="memory",
            action="memory.open" if re.search(r"\b(?:open|show|view)\b", text) else "memory.read",
            response_plan="Use Memory without letting an active Focus claim unrelated memory work.",
            confidence=0.91,
            reason="The user explicitly referenced Memory.",
            arguments={"request": request.userMessage},
        )

    if re.search(r"\b(?:unmute|mute|voice|open menu|open launcher|go home|open camera|camera)\b", text):
        visual = bool(re.search(r"\bcamera\b", text))
        return _decision(
            owner="visual" if visual else "device_ui",
            focus_relevant=focus_relevant if visual else False,
            disposition="tool",
            capability="visual" if visual else "device_ui",
            action="visual.open_camera" if visual else ("voice.control" if re.search(r"\b(?:voice|mute|unmute)\b", text) else "ui.navigate"),
            response_plan="Execute the deterministic UI/device action; avoid redundant narration for simple controls.",
            confidence=0.95,
            reason="The turn directly controls QMeet UI/device behavior.",
            arguments={"request": request.userMessage},
        )

    explicit_focus = bool(
        re.search(
            r"\b(?:start|end|resume|update|change|set|what is|what's|show)\b.*\bfocus\b|\bgoal\s*:|\bset (?:my )?goal\b",
            text,
        )
    )
    if explicit_focus:
        action = "focus.read"
        if re.search(r"\bstart\b", text):
            action = "focus.start"
        elif re.search(r"\b(?:end|complete|finish)\b", text):
            action = "focus.end"
        elif re.search(r"\bresume\b", text):
            action = "focus.resume"
        elif re.search(r"\bgoal\b", text):
            action = "focus.update_goal"
        return _decision(
            owner="focus",
            focus_relevant=True,
            disposition="tool",
            capability="focus",
            action=action,
            response_plan="Use the verified canonical Focus operation, then continue with useful help rather than another intake loop.",
            confidence=0.96,
            reason="The user explicitly requested a Focus operation.",
            arguments={"request": request.userMessage},
        )

    if _recent_focus_continuation(request, focus) or (
        focus_relevant and re.search(r"\b(?:help|outline|points|draft|write|ideas|structure|practice|improve)\b", text)
    ):
        return _decision(
            owner="focus",
            focus_relevant=True,
            disposition="conversation",
            capability="focus",
            action="focus.help",
            response_plan="Use the relevant Focus context to help immediately; do not create a mutation merely to keep the conversation moving.",
            confidence=0.88,
            reason="The turn clearly continues substantive work inside the active Focus.",
        )

    general_question = bool(re.match(r"^(?:why|what|who|where|when|how|is|are|can|could|do|does)\b", text))
    if general_question and not focus_relevant:
        return _decision(
            owner="general_chat",
            focus_relevant=False,
            disposition="conversation",
            capability="none",
            action="conversation.respond",
            response_plan="Answer the question directly without mentioning Active Focus unless the user connects it.",
            confidence=0.86,
            reason="The turn reads as a self-contained general question with no Focus connection.",
        )

    return _decision(
        owner="focus" if focus_relevant else "general_chat",
        focus_relevant=focus_relevant,
        disposition="conversation",
        capability="focus" if focus_relevant else "none",
        action="focus.help" if focus_relevant else "conversation.respond",
        response_plan=(
            "Continue the relevant Focus work conversationally without inventing a state change."
            if focus_relevant
            else "Respond normally to the user's current request without pulling in unrelated Focus state."
        ),
        confidence=0.62 if focus_relevant else 0.58,
        reason=(
            "Conservative fallback found a topical connection to Active Focus."
            if focus_relevant
            else "No deterministic capability ownership signal was found."
        ),
    )


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


def _sanitize_model_decision(value: dict[str, Any]) -> AgentShadowDecision | None:
    try:
        return AgentShadowDecision.model_validate(value)
    except Exception:
        return None


def _model_payload(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "userMessage": request.userMessage,
        "recentConversation": [item.model_dump() for item in request.recentConversation[-10:]],
        "uiState": request.uiState,
        "clientContext": request.clientContext,
        "canonicalActiveFocus": focus,
        "capabilityContract": GLOBAL_CAPABILITY_CONTRACT,
        "existingFrontendCapabilityDigest": capability_digest(),
    }


async def _generate_model_decision(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
) -> AgentShadowDecision | None:
    if not _is_openai_enabled() or not os.getenv("OPENAI_API_KEY") or AsyncOpenAI is None:
        return None

    try:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            temperature=0.0,
            max_tokens=500,
            messages=[
                {"role": "system", "content": AGENT_SHADOW_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(_model_payload(request, focus), ensure_ascii=False),
                },
            ],
        )
        content = response.choices[0].message.content if response.choices else ""
        parsed = _json_object_from_text(content or "")
        return _sanitize_model_decision(parsed) if parsed else None
    except Exception:
        return None


def compare_shadow_to_legacy(
    decision: AgentShadowDecision,
    observation: LegacyRouteObservation | None,
) -> AgentShadowComparison:
    if observation is None:
        return AgentShadowComparison(compared=False)

    owner_agreement = None if observation.owner is None else observation.owner == decision.turnOwner
    disposition_agreement = (
        None if observation.disposition is None else observation.disposition == decision.disposition
    )
    action_agreement = None
    if observation.action.strip():
        shadow_leaf = decision.proposedAction.split(".")[-1].replace("_", "-")
        legacy_action = observation.action.strip().casefold().replace("_", "-")
        action_agreement = shadow_leaf in legacy_action or legacy_action in shadow_leaf

    disagreements: list[str] = []
    if owner_agreement is False:
        disagreements.append(f"owner shadow={decision.turnOwner} legacy={observation.owner}")
    if disposition_agreement is False:
        disagreements.append(
            f"disposition shadow={decision.disposition} legacy={observation.disposition}"
        )
    if action_agreement is False:
        disagreements.append(
            f"action shadow={decision.proposedAction} legacy={observation.action}"
        )

    return AgentShadowComparison(
        compared=True,
        ownerAgreement=owner_agreement,
        dispositionAgreement=disposition_agreement,
        actionAgreement=action_agreement,
        legacyRoute=observation.route,
        disagreementSummary="; ".join(disagreements),
    )


def _telemetry_path() -> Path:
    configured = os.getenv("QMEET_AGENT_SHADOW_LOG", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "qmeet_agent_shadow.jsonl"


def _append_telemetry(
    *,
    turn_id: str,
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
    decision: AgentShadowDecision,
    comparison: AgentShadowComparison,
) -> None:
    path = _telemetry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "schemaVersion": AGENT_SHADOW_SCHEMA_VERSION,
        "mode": "shadow",
        "turnId": turn_id,
        "userMessage": request.userMessage,
        "uiState": request.uiState,
        "activeFocusId": (focus or {}).get("focusId"),
        "activeFocusTitle": (focus or {}).get("title"),
        "decision": decision.model_dump(),
        "legacyObservation": request.legacyObservation.model_dump() if request.legacyObservation else None,
        "comparison": comparison.model_dump(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def shadow_status() -> dict[str, Any]:
    path = _telemetry_path()
    count = 0
    compared = 0
    disagreements = 0
    owner_disagreements = 0
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                count += 1
                comparison = record.get("comparison") or {}
                if comparison.get("compared"):
                    compared += 1
                if comparison.get("disagreementSummary"):
                    disagreements += 1
                if comparison.get("ownerAgreement") is False:
                    owner_disagreements += 1
    return {
        "ok": True,
        "mode": "shadow",
        "schemaVersion": AGENT_SHADOW_SCHEMA_VERSION,
        "model": DEFAULT_MODEL,
        "eventCount": count,
        "comparedCount": compared,
        "disagreementCount": disagreements,
        "ownerDisagreementCount": owner_disagreements,
        "path": str(path),
    }


async def decide_agent_shadow(request: AgentShadowRequest) -> AgentShadowResponse:
    focus = active_focus_snapshot()
    model_decision = await _generate_model_decision(request, focus)
    decision = model_decision or _fallback_shadow_decision(request, focus)
    comparison = compare_shadow_to_legacy(decision, request.legacyObservation)
    turn_id = f"shadow-{uuid4().hex}"
    _append_telemetry(
        turn_id=turn_id,
        request=request,
        focus=focus,
        decision=decision,
        comparison=comparison,
    )
    return AgentShadowResponse(
        turnId=turn_id,
        decision=decision,
        comparison=comparison,
    )
