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

ACTION_VOCABULARY_VERSION = "canonical-local-command-v1"
CANONICAL_TOOL_ACTIONS_BY_OWNER: dict[str, tuple[str, ...]] = {
    "focus": (
        "start-focus-session",
        "update-focus-session",
        "read-focus-session",
        "end-focus-session",
        "focus-to-tasks",
        "summarize-focus-session",
        "save-focus-summary",
        "end-focus-with-summary",
        "read-last-focus-session",
        "read-focus-history",
        "resume-last-focus-session",
        "recap-focus-activity",
        "enhanced-focus-recap",
        "prepare-calendar-focus",
        "create-meeting-follow-up-tasks",
        "wrap-up-meeting-focus",
        "link-visual-to-focus",
        "read-focus-visuals",
    ),
    "calendar": (
        "open-calendar",
        "add-calendar-event",
        "read-calendar",
        "refresh-calendar",
        "edit-last-event",
        "delete-calendar-event",
        "delete-last-event",
        "clear-calendar",
        "show-today",
        "show-tomorrow",
        "close-calendar",
    ),
    "search": ("open-search", "run-search", "clear-search", "close-search"),
    "memory": ("open-memory", "close-memory", "read-memory"),
    "tasks": ("remember-task", "mark-task-done", "delete-last-task", "clear-done-tasks", "read-memory"),
    "notes": ("open-notes", "new-note", "save-note", "read-notes", "delete-last-note", "close-notes", "clear-notes"),
    "device_ui": (
        "help",
        "identity",
        "open-menu",
        "close-menu",
        "open-settings",
        "close-settings",
        "go-home",
        "show-status",
        "close-status",
        "hide-status",
        "voice-output-on",
        "voice-output-off",
        "voice-output-toggle",
        "voice-slower",
        "voice-faster",
        "voice-normal",
        "stop-speaking",
        "what-did-you-hear",
        "cancel-action",
        "clear-chat",
        "end-chat",
        "close-generic",
    ),
    "visual": (
        "create-visual-observation",
        "read-visual-context",
        "read-last-visual-observation",
        "read-visual-history",
        "summarize-visual-context",
        "link-visual-to-focus",
        "read-focus-visuals",
        "clear-visual-context",
        "delete-last-visual-observation",
    ),
}
CANONICAL_TOOL_ACTIONS = {
    action
    for actions in CANONICAL_TOOL_ACTIONS_BY_OWNER.values()
    for action in actions
}
ACTION_ALIASES = {
    "focus.start": "start-focus-session",
    "start-focus": "start-focus-session",
    "focus.read": "read-focus-session",
    "read-focus": "read-focus-session",
    "read-current-focus": "read-focus-session",
    "focus.update-goal": "update-focus-session",
    "focus.update-context": "update-focus-session",
    "set-focus-goal": "update-focus-session",
    "focus.end": "end-focus-session",
    "focus.complete": "end-focus-session",
    "focus.resume": "resume-last-focus-session",
    "search.run": "run-search",
    "search.open": "open-search",
    "calendar.read": "read-calendar",
    "calendar.create-event": "add-calendar-event",
    "calendar.update-event": "edit-last-event",
    "calendar.delete-event": "delete-calendar-event",
    "memory.open": "open-memory",
    "memory.read": "read-memory",
    "tasks.read": "read-memory",
    "tasks.create": "remember-task",
    "tasks.complete": "mark-task-done",
    "tasks.clear-completed": "clear-done-tasks",
    "notes.open": "open-notes",
    "notes.read": "read-notes",
    "notes.save": "save-note",
    "notes.delete": "delete-last-note",
}
AGENT_SHADOW_SYSTEM_PROMPT = """
You are the Phase 21B shadow decision layer for QMeet, an AI-first tablet assistant.

You are OBSERVATIONAL ONLY. You never execute tools, mutate state, or generate the visible user reply. Your job is to predict how a future unified QMeet agent should own the current user turn before any state-changing action occurs.

Core rule: decide TURN OWNERSHIP before deciding whether Active Focus matters.
Turn owners:
- general_chat: greetings, general knowledge, ordinary conversation, or unrelated questions that need no QMeet capability.
- calendar: schedule/event/calendar reads or writes.
- search: requests whose answer should come from external/web evidence rather than model memory. This includes explicit search/look-up/research requests, requests to check what reviewers/users/critics/people are saying, requests for current/recent/latest information, or requests to find/verify sources, reviews, ratings, evidence, or web opinions.
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
Search ownership rule:
- If the user's request asks QMeet to discover, verify, inspect, compare, or report external opinions/evidence that should come from the web, choose turnOwner=search and disposition=tool. Do not answer those requests from model memory merely because you could produce a plausible answer.
- Natural research wording still counts as Search even when the user does not say the word "search". Examples of the semantic class include asking what reviewers think, what people are saying about a product, whether recent sources support a claim, or asking QMeet to see/check/find out what the web says.
- For executable Search, use proposedCapability=search, proposedAction=run-search, and proposedArguments with exactly one field: {"query": "<the concise web query to run>"}. Do not use request/topic/text/url or extra argument keys.
Calendar ownership rule:
- Natural single-intent schedule and availability questions are Calendar-owned reads even when the user does not literally say "calendar". This includes asking what is scheduled today or tomorrow, whether anything is scheduled, what the schedule looks like, or whether the user is free, available, busy, or booked.
- For executable Calendar READS, use proposedCapability=calendar, proposedAction=read-calendar, and proposedArguments with exactly one field: {"view": "today" | "tomorrow" | "all"}. Use today or tomorrow when the user names that day. Use all only for a general schedule/calendar read with no specific day.
- Calendar CREATE is the first promoted write proposal. For one event on today or tomorrow, use proposedCapability=calendar, proposedAction=add-calendar-event, and proposedArguments with exactly these fields: {"day": "today" | "tomorrow", "title": "<one event title>", "time": "<specific time>" | null}. Use time=null when the user gives no specific time; the deterministic Calendar path will preview and confirm that as an all-day event. Never invent a time.
- Do not collapse a broad plan such as "schedule my day" or a multi-event request into one add-calendar-event proposal. Those are outside this single-intent slice.
- Calendar edits, moves, deletes, cancellations, and clears are NOT agent-executable yet. Still classify one of those single-intent writes as turnOwner=calendar, disposition=tool, proposedCapability=calendar, and the exact canonical Calendar write action, but treat its proposed arguments only as routing/consistency metadata for the existing guarded path.
- A Calendar create proposal is still only a proposal. It is not proof that an event was written; deterministic validation, confirmation, execution, and verified receipts remain authoritative.
Proposed action never proves that anything changed.
Canonical action vocabulary:
- If disposition=tool, proposedAction MUST be one exact action id from capabilityContract. Do not invent aliases such as focus.read, read_current_focus, calendar.create_event, or custom compound action names.
- If disposition=conversation, proposedAction MUST be focus.help for Focus-owned work or conversation.respond otherwise.
- If disposition=clarify, proposedAction MUST be none.
- proposedCapability identifies the owning capability; proposedAction identifies the exact canonical action contract.
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
        "conversationActions": ["conversation.respond"],
    },
    {
        "owner": "focus",
        "authority": "canonical verified Focus backend",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["focus"]),
        "conversationActions": ["focus.help"],
        "rule": "Active Focus is context, not universal ownership.",
    },
    {
        "owner": "calendar",
        "authority": "deterministic Calendar handlers / verified Google Calendar writes",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["calendar"]),
        "constraint": "Current natural event-date support is primarily today/tomorrow.",
        "promotedReadAction": "read-calendar",
        "readArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["view"],
            "properties": {
                "view": {"type": "string", "enum": ["today", "tomorrow", "all"]},
            },
        },
        "promotedCreateAction": "add-calendar-event",
        "createArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["day", "title", "time"],
            "properties": {
                "day": {"type": "string", "enum": ["today", "tomorrow"]},
                "title": {"type": "string", "minLength": 1, "maxLength": 240},
                "time": {"type": ["string", "null"]},
            },
        },
        "promotionConstraint": (
            "read-calendar and add-calendar-event proposals are agent-promotable. Calendar create "
            "still requires deterministic argument validation plus the existing confirmation/write path; "
            "edits and deletes remain deferred."
        ),
    },
    {
        "owner": "search",
        "authority": "deterministic search capability",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["search"]),
        "ownershipRule": (
            "Use Search when the user asks QMeet to discover, verify, inspect, compare, or report "
            "external web evidence/opinions/current information rather than answer from model memory."
        ),
        "executableAction": "run-search",
        "argumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 500},
            },
        },
    },
    {
        "owner": "memory",
        "authority": "deterministic Memory state",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["memory"]),
    },
    {
        "owner": "tasks",
        "authority": "deterministic task handlers plus canonical Focus lineage when linked",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["tasks"]),
    },
    {
        "owner": "notes",
        "authority": "deterministic note handlers",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["notes"]),
    },
    {
        "owner": "device_ui",
        "authority": "deterministic frontend/device handlers",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["device_ui"]),
    },
    {
        "owner": "visual",
        "authority": "deterministic camera/visual-context handlers",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["visual"]),
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
    sequence: int = Field(default=0, ge=0, le=1000)


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


class AgentShadowCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turnId: str = Field(min_length=1, max_length=200)
    legacyObservation: LegacyRouteObservation


class AgentShadowCompareResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    mode: Literal["shadow"] = "shadow"
    schemaVersion: str = AGENT_SHADOW_SCHEMA_VERSION
    turnId: str
    foundDecision: bool
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


def _recent_focus_work_reply(request: AgentShadowRequest, focus: dict[str, Any] | None) -> bool:
    if not focus:
        return False
    message = _normalize(request.userMessage)
    if not message or len(message.split()) > 10:
        return False
    if re.fullmatch(r"(?:hi|hello|hey|hello there|hey there|good morning|good afternoon|good evening)[.!?]*", message):
        return False
    if re.search(
        r"\b(?:calendar|appointment|schedule|search|look up|memory|task|tasks|note|notes|unmute|mute|voice|camera)\b",
        message,
    ):
        return False
    recent_assistant_messages = [
        item.content
        for item in request.recentConversation[-8:]
        if item.role == "assistant"
    ][-3:]
    recent_assistant = " ".join(recent_assistant_messages)
    if not recent_assistant:
        return False
    focus_text = " ".join(
        str(focus.get(key) or "")
        for key in ("title", "objective", "deliverable", "subject")
    )
    if not (_tokens(recent_assistant) & _tokens(focus_text)):
        return False
    prompt_like = bool(
        "?" in recent_assistant
        or re.search(
            r"\b(?:would you like|which|what|where|start with|for example|choose|section|points|outline|features|milestones|challenges|next steps)\b",
            recent_assistant.casefold(),
        )
    )
    return prompt_like


def _focus_is_relevant(request: AgentShadowRequest, focus: dict[str, Any] | None) -> bool:
    message = request.userMessage
    normalized = _normalize(message)
    if not focus:
        return False
    if re.search(r"\b(?:my|our|this|that|current|active)\s+(?:focus|goal)\b|\bfocus session\b", normalized):
        return True
    return (
        _focus_overlap(message, focus)
        or _recent_focus_continuation(request, focus)
        or _recent_focus_work_reply(request, focus)
    )


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


def _calendar_read_view(text: str) -> Literal["today", "tomorrow", "all"]:
    if re.search(r"\btomorrow\b", text):
        return "tomorrow"
    if re.search(r"\btoday\b", text):
        return "today"
    return "all"


def _calendar_write_action(text: str) -> str | None:
    match = re.match(
        r"^(?:(?:please\s+)?|(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+(?:want|need)\s+you\s+to\s+|i(?:'d| would)\s+like\s+you\s+to\s+)(add|schedule|create|book|move|reschedule|change|edit|delete|remove|cancel)\b",
        text,
    )
    if not match:
        return None

    verb = match.group(1)
    if verb in {"add", "schedule", "create", "book"}:
        return "add-calendar-event"
    if verb in {"move", "reschedule", "change", "edit"}:
        return "edit-last-event"
    if verb in {"delete", "remove", "cancel"}:
        return "delete-calendar-event"
    return None


def _looks_like_calendar_write_request(text: str) -> bool:
    return _calendar_write_action(text) is not None


def _has_explicit_calendar_time_slot(text: str) -> bool:
    """Recognize a concrete near-term time slot without requiring a Calendar noun.

    This preserves cross-capability ownership for requests such as adding Focus-related
    practice time tomorrow at 2: Calendar owns the mutation while Focus may still be
    relevant context. The prototype's existing natural-date contract remains limited
    to today/tomorrow.
    """
    if not re.search(r"\b(?:today|tomorrow)\b", text):
        return False
    return bool(
        re.search(
            r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?\b"
            r"|\b(?:morning|afternoon|evening|night)\b",
            text,
        )
    )


def _calendar_create_arguments(text: str) -> dict[str, Any] | None:
    """Extract a narrow fallback create proposal for one today/tomorrow event.

    This is a capability ownership floor, not an executor. The frontend performs
    the same strict schema validation again before constructing a CommandMatch,
    and the existing Calendar confirmation gate remains authoritative.
    """
    normalized = re.sub(r"\s+", " ", text.strip())
    normalized = re.sub(
        r"^(?:(?:please\s+)?|(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+(?:want|need)\s+you\s+to\s+|i(?:'d| would)\s+like\s+you\s+to\s+)",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    match = re.match(
        r"^(?:add|schedule|create|book)\s+(.+?)\s+(today|tomorrow)(?:\s+at\s+(.+?))?$",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    title = match.group(1).strip().strip(" ,.;:")
    day = match.group(2).casefold()
    raw_time = (match.group(3) or "").strip().strip(" ,.;:")
    if not title or len(title) > 240 or re.search(r"[\x00-\x1f\x7f]", title):
        return None
    if re.fullmatch(r"(?:(?:my|our|the)\s+)?(?:day|schedule|agenda|plans?)", title, re.IGNORECASE):
        return None

    time_value: str | None = None
    if raw_time:
        if len(raw_time) > 32 or re.search(r"[\x00-\x1f\x7f]", raw_time):
            return None
        normalized_time = re.sub(r"\s+", " ", raw_time.casefold().replace(".", "")).strip()
        if normalized_time not in {"noon", "midnight"}:
            time_match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", normalized_time)
            if not time_match:
                return None
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or "0")
            meridiem = time_match.group(3)
            if minute > 59:
                return None
            if meridiem and not 1 <= hour <= 12:
                return None
            if not meridiem and not 0 <= hour <= 23:
                return None
        time_value = raw_time

    return {"day": day, "title": title, "time": time_value}


def _looks_like_broad_calendar_planning_request(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip())
    normalized = re.sub(
        r"^(?:(?:please\s+)?|(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+(?:want|need)\s+you\s+to\s+|i(?:'d| would)\s+like\s+you\s+to\s+)",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    return bool(
        re.fullmatch(
            r"schedule\s+(?:(?:my|our|the)\s+)?(?:day|schedule|agenda|plans?)(?:\s+(?:today|tomorrow))?",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _looks_like_calendar_read_request(text: str) -> bool:
    # Read ownership must never reinterpret a Calendar write as a read. Exact
    # deterministic writes still win before the agent, and ambiguous writes
    # remain on the existing guarded write/confirmation path.
    if _looks_like_calendar_write_request(text):
        return False

    calendar_or_schedule_term = bool(
        re.search(r"\b(?:calendar|agenda|appointments?|schedule|meetings?|events?)\b", text)
    )
    availability_question = bool(
        re.search(
            r"\b(?:am i|are we|do i look|will i be)\s+(?:free|available|busy|booked)\b",
            text,
        )
    )
    have_anything_question = bool(
        re.search(r"\b(?:do i|do we)\s+have\s+(?:anything|something|plans?|meetings?|events?)\b", text)
        and re.search(r"\b(?:today|tomorrow)\b", text)
    )
    return calendar_or_schedule_term or availability_question or have_anything_question


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
    explicit_search_request = bool(
        re.search(
            r"\b(?:search|look up|lookup|research|check online|check the web|web search|find out|find reviews?|reviews? of)\b",
            text,
        )
    )
    external_opinion_request = bool(
        re.search(
            r"\b(?:reviewers?|users?|critics?|people|customers?)\b",
            text,
        )
        and re.search(
            r"\b(?:think|thinking|say|saying|said|feel|reviews?|ratings?|opinions?|feedback|experience|experiences)\b",
            text,
        )
    )
    external_evidence_request = bool(
        re.search(r"\b(?:sources?|evidence|reviews?|ratings?|news)\b", text)
        and re.search(r"\b(?:find|check|see|show|give|get|gather|verify|compare|what)\b", text)
    )
    recency_requires_search = bool(
        re.search(r"\b(?:latest|recent|current|currently|today|this week|this month)\b", text)
        and re.search(r"\b(?:reviews?|news|prices?|opinions?|feedback|information|info|saying|think)\b", text)
    )
    if (
        explicit_search_request
        or external_opinion_request
        or external_evidence_request
        or recency_requires_search
    ):
        return _decision(
            owner="search",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="search",
            action="search.run",
            response_plan="Run Search, then summarize or offer the most useful consequence of the verified result.",
            confidence=0.94,
            reason="The request depends on external web evidence/opinions rather than model memory.",
            arguments={"query": request.userMessage},
        )

    calendar_terms = bool(
        re.search(r"\b(?:calendar|agenda|appointments?|schedule|events?|meetings?)\b", text)
    )
    calendar_write_action = _calendar_write_action(text)
    if calendar_write_action == "add-calendar-event" and _looks_like_broad_calendar_planning_request(request.userMessage):
        calendar_write_action = None
    calendar_create_arguments = (
        _calendar_create_arguments(request.userMessage)
        if calendar_write_action == "add-calendar-event"
        else None
    )
    calendar_write_target = (
        calendar_terms
        or _has_explicit_calendar_time_slot(text)
        or calendar_create_arguments is not None
    )
    if calendar_write_action and calendar_write_target:
        create_is_typed = (
            calendar_write_action == "add-calendar-event"
            and calendar_create_arguments is not None
        )
        return _decision(
            owner="calendar",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="calendar",
            action=calendar_write_action,
            response_plan=(
                "Validate the typed Calendar create proposal, require the existing confirmation, then continue only from the verified write receipt."
                if create_is_typed
                else "Keep Calendar ownership, then defer this unpromoted mutation to the existing guarded Calendar write path."
            ),
            confidence=0.95,
            reason=(
                "The request is one Calendar event creation with a narrow today/tomorrow argument contract."
                if create_is_typed
                else "Calendar/event write language owns this turn, but this mutation is not agent-executable in this slice."
            ),
            arguments=(
                calendar_create_arguments
                if create_is_typed
                else {"request": request.userMessage}
            ),
        )
    if _looks_like_calendar_read_request(text):
        return _decision(
            owner="calendar",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="calendar",
            action="read-calendar",
            response_plan="Read authoritative Calendar state, then summarize only the verified schedule result.",
            confidence=0.95,
            reason="The turn is a single-intent Calendar schedule or availability read.",
            arguments={"view": _calendar_read_view(text)},
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
    if _recent_focus_continuation(request, focus) or _recent_focus_work_reply(request, focus) or (
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


def _is_executable_search_tool_decision(decision: AgentShadowDecision) -> bool:
    if decision.turnOwner != "search" or decision.disposition != "tool":
        return False
    if decision.proposedCapability != "search" or canonical_action_id(decision.proposedAction) != "run-search":
        return False
    arguments = decision.proposedArguments
    if set(arguments) != {"query"}:
        return False
    query = arguments.get("query")
    return isinstance(query, str) and bool(query.strip()) and len(query.strip()) <= 500


def _is_valid_calendar_create_arguments(arguments: dict[str, Any]) -> bool:
    if set(arguments) != {"day", "title", "time"}:
        return False
    day = arguments.get("day")
    title = arguments.get("title")
    time_value = arguments.get("time")
    if day not in {"today", "tomorrow"}:
        return False
    if not isinstance(title, str):
        return False
    title = title.strip()
    if (
        not title
        or len(title) > 240
        or re.search(r"[\x00-\x1f\x7f]", title)
        or re.fullmatch(r"(?:(?:my|our|the)\s+)?(?:day|schedule|agenda|plans?)", title, re.IGNORECASE)
    ):
        return False
    if time_value is None:
        return True
    if not isinstance(time_value, str):
        return False
    time_value = time_value.strip()
    if not time_value or len(time_value) > 32 or re.search(r"[\x00-\x1f\x7f]", time_value):
        return False
    normalized_time = re.sub(r"\s+", " ", time_value.casefold().replace(".", "")).strip()
    if normalized_time in {"noon", "midnight"}:
        return True
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", normalized_time)
    if not match:
        return False
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3)
    if minute > 59:
        return False
    if meridiem:
        return 1 <= hour <= 12
    return 0 <= hour <= 23


def _is_executable_calendar_create_tool_decision(decision: AgentShadowDecision) -> bool:
    return (
        decision.turnOwner == "calendar"
        and decision.disposition == "tool"
        and decision.proposedCapability == "calendar"
        and canonical_action_id(decision.proposedAction) == "add-calendar-event"
        and _is_valid_calendar_create_arguments(decision.proposedArguments)
    )


def apply_calendar_write_ownership_floor(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
    decision: AgentShadowDecision,
) -> AgentShadowDecision:
    """Keep clear single-intent Calendar mutations out of chat/Focus ownership.

    Calendar create may carry the narrow typed proposal that the frontend will
    validate again. Other writes remain routing metadata only and continue into
    their existing guarded interpreter/confirmation paths. Nothing executes here.
    """
    fallback = normalize_shadow_decision(_fallback_shadow_decision(request, focus))
    fallback_action = canonical_action_id(fallback.proposedAction)
    if not (
        fallback.turnOwner == "calendar"
        and fallback.disposition == "tool"
        and fallback_action in {
            "add-calendar-event",
            "edit-last-event",
            "delete-calendar-event",
            "delete-last-event",
            "clear-calendar",
        }
        and fallback.confidence >= 0.95
    ):
        return decision

    if fallback_action == "add-calendar-event" and _is_executable_calendar_create_tool_decision(decision):
        return decision

    if (
        fallback_action != "add-calendar-event"
        and decision.turnOwner == "calendar"
        and decision.disposition == "tool"
        and decision.proposedCapability == "calendar"
        and canonical_action_id(decision.proposedAction) == fallback_action
    ):
        return decision

    return fallback.model_copy(
        update={
            "reason": (
                "Deterministic Calendar write ownership floor: an explicit single-intent Calendar mutation cannot be swallowed by Focus or ordinary conversation. Execution still requires the capability-specific validator and guarded Calendar path."
            )
        }
    )


def apply_search_ownership_floor(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
    decision: AgentShadowDecision,
) -> AgentShadowDecision:
    """Keep external-evidence requests on the Search capability.
    The model remains the primary owner classifier, but a confident deterministic
    external-evidence classification is a capability safety floor: QMeet must not
    answer requests for reviewers/users/current web evidence from model memory.
    This is intentionally Search-only in Phase 21B and does not execute anything;
    it only normalizes the proposed owner/action/arguments before the existing
    frontend Search validator and deterministic Search handler run.
    """
    fallback = normalize_shadow_decision(_fallback_shadow_decision(request, focus))
    if not (
        fallback.turnOwner == "search"
        and fallback.disposition == "tool"
        and fallback.proposedAction == "run-search"
        and fallback.confidence >= 0.94
    ):
        return decision

    if _is_executable_search_tool_decision(decision):
        return decision
    return fallback.model_copy(
        update={
            "reason": (
                "Deterministic Search ownership floor: the request requires external "
                "web evidence/opinions, so model-memory conversation cannot own it."
            )
        }
    )


def _action_token(value: str) -> str:
    return re.sub(r"-+", "-", value.strip().casefold().replace("_", "-"))


def canonical_action_id(value: str) -> str | None:
    token = _action_token(value)
    if not token or token == "none":
        return None
    if token in CANONICAL_TOOL_ACTIONS:
        return token
    return ACTION_ALIASES.get(token)


def normalize_shadow_decision(decision: AgentShadowDecision) -> AgentShadowDecision:
    if decision.disposition == "conversation":
        expected_action = "focus.help" if decision.turnOwner == "focus" else "conversation.respond"
        expected_capability = "focus" if decision.turnOwner == "focus" else "none"
        return decision.model_copy(
            update={
                "proposedCapability": expected_capability,
                "proposedAction": expected_action,
            }
        )
    if decision.disposition == "clarify":
        return decision.model_copy(update={"proposedAction": "none"})

    canonical = canonical_action_id(decision.proposedAction)
    if canonical is not None:
        return decision.model_copy(update={"proposedAction": canonical})
    arguments = dict(decision.proposedArguments)
    raw_action = decision.proposedAction.strip()
    if raw_action and raw_action.casefold() != "none":
        arguments.setdefault("shadowRawProposedAction", raw_action)
    return decision.model_copy(
        update={
            "proposedAction": "none",
            "proposedArguments": arguments,
        }
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
        return normalize_shadow_decision(AgentShadowDecision.model_validate(value))
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


def _infer_legacy_owner(observation: LegacyRouteObservation) -> TurnOwner | None:
    if observation.owner is not None:
        return observation.owner
    joined = " ".join(
        part for part in (observation.route, observation.action, observation.frontendCommand) if part
    ).casefold()
    if "normal chat" in joined or "conversation" in joined:
        return "general_chat"
    if "calendar" in joined or "event" in joined or "appointment" in joined:
        return "calendar"
    if "search" in joined or "review" in joined or "look-up" in joined or "lookup" in joined:
        return "search"
    if "task" in joined or "todo" in joined or "to-do" in joined:
        return "tasks"
    if "note" in joined:
        return "notes"
    if "memory" in joined:
        return "memory"
    if "focus" in joined or "goal" in joined:
        return "focus"
    if "camera" in joined or "visual" in joined:
        return "visual"
    if any(token in joined for token in ("voice", "mute", "unmute", "panel", "menu", "launcher", "go home", "status")):
        return "device_ui"
    return None


def _infer_legacy_disposition(observation: LegacyRouteObservation) -> Disposition | None:
    if observation.disposition is not None:
        return observation.disposition
    route = observation.route.casefold()
    joined = " ".join((observation.route, observation.action, observation.frontendCommand)).casefold()
    if "normal chat" in route or "conversation" in route:
        return "conversation"
    if any(token in route for token in ("needs confirmation", "blocked", "no target", "clarification", "cancellation", "failed to execute")):
        return "clarify"
    owner = _infer_legacy_owner(observation)
    if owner is not None and owner != "general_chat":
        return "tool"
    if joined:
        return "conversation"
    return None


def normalize_legacy_observation(observation: LegacyRouteObservation) -> LegacyRouteObservation:
    return observation.model_copy(
        update={
            "owner": _infer_legacy_owner(observation),
            "disposition": _infer_legacy_disposition(observation),
        }
    )


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
    if (
        decision.disposition == "tool"
        and observation.disposition == "tool"
        and observation.action.strip()
    ):
        shadow_action = canonical_action_id(decision.proposedAction)
        legacy_action = canonical_action_id(observation.action)
        if shadow_action is None:
            action_agreement = False
        elif legacy_action is None:
            action_agreement = _action_token(decision.proposedAction) == _action_token(observation.action)
        else:
            action_agreement = shadow_action == legacy_action
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
        "recordType": "decision",
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


def _read_decision_record(turn_id: str) -> dict[str, Any] | None:
    path = _telemetry_path()
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            record_type = record.get("recordType") or "decision"
            if record_type == "decision" and record.get("turnId") == turn_id:
                return record
    return None


def _append_late_comparison(
    *,
    turn_id: str,
    decision: AgentShadowDecision,
    observation: LegacyRouteObservation,
    comparison: AgentShadowComparison,
) -> None:
    path = _telemetry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recordType": "comparison",
        "schemaVersion": AGENT_SHADOW_SCHEMA_VERSION,
        "mode": "shadow",
        "turnId": turn_id,
        "sequence": observation.sequence,
        "decision": decision.model_dump(),
        "legacyObservation": observation.model_dump(),
        "comparison": comparison.model_dump(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def compare_agent_shadow_turn(request: AgentShadowCompareRequest) -> AgentShadowCompareResponse:
    record = _read_decision_record(request.turnId)
    if record is None:
        return AgentShadowCompareResponse(
            turnId=request.turnId,
            foundDecision=False,
            comparison=AgentShadowComparison(compared=False),
        )
    try:
        decision = AgentShadowDecision.model_validate(record.get("decision") or {})
    except Exception:
        return AgentShadowCompareResponse(
            turnId=request.turnId,
            foundDecision=False,
            comparison=AgentShadowComparison(compared=False),
        )
    observation = normalize_legacy_observation(request.legacyObservation)
    comparison = compare_shadow_to_legacy(decision, observation)
    _append_late_comparison(
        turn_id=request.turnId,
        decision=decision,
        observation=observation,
        comparison=comparison,
    )
    return AgentShadowCompareResponse(
        turnId=request.turnId,
        foundDecision=True,
        comparison=comparison,
    )


def _load_shadow_telemetry() -> tuple[
    list[str],
    dict[str, dict[str, Any]],
    dict[str, tuple[int, LegacyRouteObservation, AgentShadowComparison]],
    int,
]:
    path = _telemetry_path()
    decision_order: list[str] = []
    decisions: dict[str, dict[str, Any]] = {}
    comparison_by_turn: dict[str, tuple[int, LegacyRouteObservation, AgentShadowComparison]] = {}
    comparison_event_count = 0
    if not path.exists():
        return decision_order, decisions, comparison_by_turn, comparison_event_count
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            record_type = record.get("recordType") or "decision"
            turn_id = str(record.get("turnId") or "")
            if not turn_id:
                continue
            if record_type == "decision":
                if turn_id not in decisions:
                    decision_order.append(turn_id)
                decisions[turn_id] = record
                comparison_raw = record.get("comparison") or {}
                observation_raw = record.get("legacyObservation") or {}
                if comparison_raw.get("compared") and observation_raw:
                    try:
                        observation = LegacyRouteObservation.model_validate(observation_raw)
                        comparison = AgentShadowComparison.model_validate(comparison_raw)
                    except Exception:
                        continue
                    comparison_by_turn[turn_id] = (0, observation, comparison)
                continue
            if record_type != "comparison":
                continue
            comparison_event_count += 1
            try:
                observation = LegacyRouteObservation.model_validate(record.get("legacyObservation") or {})
                comparison = AgentShadowComparison.model_validate(record.get("comparison") or {})
            except Exception:
                continue
            sequence = int(record.get("sequence") or observation.sequence or 0)
            existing = comparison_by_turn.get(turn_id)
            if existing is None or sequence >= existing[0]:
                comparison_by_turn[turn_id] = (sequence, observation, comparison)
    for turn_id, comparison_record in list(comparison_by_turn.items()):
        decision_record = decisions.get(turn_id) or {}
        try:
            decision = normalize_shadow_decision(
                AgentShadowDecision.model_validate(decision_record.get("decision") or {})
            )
        except Exception:
            continue
        sequence, observation, _stored_comparison = comparison_record
        normalized_observation = normalize_legacy_observation(observation)
        comparison_by_turn[turn_id] = (
            sequence,
            normalized_observation,
            compare_shadow_to_legacy(decision, normalized_observation),
        )
    return decision_order, decisions, comparison_by_turn, comparison_event_count


def _is_focus_replacement_risk(
    decision_record: dict[str, Any],
    comparison_record: tuple[int, LegacyRouteObservation, AgentShadowComparison] | None,
) -> bool:
    if comparison_record is None:
        return False
    if not str(decision_record.get("activeFocusId") or "").strip():
        return False
    _, observation, _ = comparison_record
    joined = " ".join(
        part
        for part in (observation.route, observation.action, observation.frontendCommand)
        if part
    ).casefold()
    legacy_started_focus = (
        "focus start" in joined
        or "start_focus" in joined
        or "start-focus" in joined
        or "start focus" in joined
    )
    if not legacy_started_focus:
        return False
    try:
        decision = normalize_shadow_decision(
            AgentShadowDecision.model_validate(decision_record.get("decision") or {})
        )
    except Exception:
        return False
    return not (
        decision.turnOwner == "focus"
        and decision.disposition == "tool"
        and decision.proposedAction == "start-focus-session"
    )


def shadow_recent(*, limit: int = 20, disagreements_only: bool = False) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 50))
    decision_order, decisions, comparison_by_turn, _ = _load_shadow_telemetry()
    items: list[dict[str, Any]] = []
    for turn_id in reversed(decision_order):
        decision_record = decisions.get(turn_id) or {}
        comparison_record = comparison_by_turn.get(turn_id)
        comparison = comparison_record[2] if comparison_record is not None else None
        if disagreements_only and not (comparison and comparison.disagreementSummary):
            continue
        legacy_observation = comparison_record[1] if comparison_record is not None else None
        normalized_decision_payload = decision_record.get("decision") or {}
        try:
            normalized_decision_payload = normalize_shadow_decision(
                AgentShadowDecision.model_validate(normalized_decision_payload)
            ).model_dump()
        except Exception:
            pass
        items.append(
            {
                "timestamp": str(decision_record.get("timestamp") or ""),
                "turnId": turn_id,
                "userMessage": str(decision_record.get("userMessage") or ""),
                "activeFocusId": decision_record.get("activeFocusId"),
                "activeFocusTitle": decision_record.get("activeFocusTitle"),
                "decision": normalized_decision_payload,
                "compared": bool(comparison and comparison.compared),
                "comparisonSequence": comparison_record[0] if comparison_record is not None else None,
                "legacyObservation": legacy_observation.model_dump() if legacy_observation else None,
                "comparison": comparison.model_dump() if comparison else None,
                "focusReplacementRisk": _is_focus_replacement_risk(
                    decision_record,
                    comparison_record,
                ),
            }
        )
        if len(items) >= bounded_limit:
            break
    return {
        "ok": True,
        "mode": "shadow",
        "schemaVersion": AGENT_SHADOW_SCHEMA_VERSION,
        "actionVocabularyVersion": ACTION_VOCABULARY_VERSION,
        "count": len(items),
        "limit": bounded_limit,
        "disagreementsOnly": disagreements_only,
        "items": items,
    }


def shadow_status() -> dict[str, Any]:
    path = _telemetry_path()
    decision_order, decisions, comparison_by_turn, comparison_event_count = _load_shadow_telemetry()
    comparisons = [comparison for _, _, comparison in comparison_by_turn.values()]
    compared = sum(1 for comparison in comparisons if comparison.compared)
    disagreements = sum(1 for comparison in comparisons if comparison.disagreementSummary)
    owner_disagreements = sum(1 for comparison in comparisons if comparison.ownerAgreement is False)
    disposition_disagreements = sum(1 for comparison in comparisons if comparison.dispositionAgreement is False)
    action_disagreements = sum(1 for comparison in comparisons if comparison.actionAgreement is False)
    focus_replacement_risks = sum(
        1
        for turn_id, decision_record in decisions.items()
        if _is_focus_replacement_risk(decision_record, comparison_by_turn.get(turn_id))
    )
    return {
        "ok": True,
        "mode": "shadow",
        "schemaVersion": AGENT_SHADOW_SCHEMA_VERSION,
        "actionVocabularyVersion": ACTION_VOCABULARY_VERSION,
        "model": DEFAULT_MODEL,
        "eventCount": len(decision_order),
        "comparedCount": compared,
        "uncomparedCount": max(0, len(decision_order) - compared),
        "comparisonEventCount": comparison_event_count,
        "disagreementCount": disagreements,
        "ownerDisagreementCount": owner_disagreements,
        "dispositionDisagreementCount": disposition_disagreements,
        "actionDisagreementCount": action_disagreements,
        "focusReplacementRiskCount": focus_replacement_risks,
        "path": str(path),
    }


async def decide_agent_shadow(request: AgentShadowRequest) -> AgentShadowResponse:
    focus = active_focus_snapshot()
    model_decision = await _generate_model_decision(request, focus)
    decision = normalize_shadow_decision(
        model_decision or _fallback_shadow_decision(request, focus)
    )
    decision = apply_search_ownership_floor(request, focus, decision)
    decision = apply_calendar_write_ownership_floor(request, focus, decision)
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
