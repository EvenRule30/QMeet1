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

from app.qmeet_capabilities import (
    ACTION_VOCABULARY_VERSION,
    CANONICAL_TOOL_ACTIONS,
    CANONICAL_TOOL_ACTIONS_BY_OWNER,
    GLOBAL_CAPABILITY_CONTRACT,
    capability_digest,
)
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
- If the user's requested outcome would add, save, change, complete, delete, move, or otherwise mutate durable QMeet state, do not use disposition=conversation merely because a conversational acknowledgement would sound natural. Route the mutation to its owning capability/tool contract.
Search ownership rule:
- If the user's request asks QMeet to discover, verify, inspect, compare, or report external opinions/evidence that should come from the web, choose turnOwner=search and disposition=tool. Do not answer those requests from model memory merely because you could produce a plausible answer.
- Natural research wording still counts as Search even when the user does not say the word "search". Examples of the semantic class include asking what reviewers think, what people are saying about a product, whether recent sources support a claim, or asking QMeet to see/check/find out what the web says.
- For executable Search, use proposedCapability=search, proposedAction=run-search, and proposedArguments with exactly one field: {"query": "<the concise web query to run>"}. Do not use request/topic/text/url or extra argument keys.
Calendar ownership rule:
- Natural single-intent schedule and availability questions are Calendar-owned reads even when the user does not literally say "calendar". This includes asking what is scheduled today or tomorrow, whether anything is scheduled, what the schedule looks like, or whether the user is free, available, busy, or booked.
- For executable Calendar READS, use proposedCapability=calendar, proposedAction=read-calendar, and proposedArguments with exactly one field: {"view": "today" | "tomorrow" | "all"}. Use today or tomorrow when the user names that day. Use all only for a general schedule/calendar read with no specific day.
- Calendar CREATE is promoted for one event on today or tomorrow. Use proposedCapability=calendar, proposedAction=add-calendar-event, and proposedArguments with exactly these fields: {"day": "today" | "tomorrow", "title": "<concise human-friendly event title>", "time": "<specific time>" | null}. The title is a proposed Calendar label, not a verbatim transcript: remove filler/articles when natural, correct obvious spelling, preserve proper names, and compress descriptive wording into a useful event name (for example "a business meeting" -> "Business Meeting", "time to practice my presentation" -> "Presentation Practice"). Do not invent people, companies, locations, goals, or other facts that are unsupported by the request or genuinely relevant Focus context. Use time=null when the user gives no specific time; the deterministic Calendar path will preview and confirm that as an all-day event. Never invent a time.
- Calendar TARGETED DELETE is also promoted, but only as criteria for deterministic lookup. Use proposedCapability=calendar, proposedAction=delete-calendar-event, and proposedArguments with exactly these fields: {"day": "today" | "tomorrow", "title": "<user-provided title or identifying descriptor>" | null, "time": "<specific time>" | null}. The day must be explicit in the user request, and at least one of title or time must be non-null. Preserve identifying words the user actually supplied (for example "meeting" or "dentist"); never invent a title, time, event id, or hidden Calendar fact.
- A delete proposal identifies search criteria only. It never identifies the canonical event itself. Deterministic Calendar state must resolve the criteria to zero, one, or multiple events; only one resolved event may proceed to the existing destructive confirmation path.
- Calendar TARGETED EDIT is promoted with the existing canonical edit-last-event action, but this single-intent slice proposes one natural event reference plus one requested change. Use proposedCapability=calendar, proposedAction=edit-last-event, and proposedArguments with exactly these fields: {"targetDay": "today" | "tomorrow", "query": "<the user's event reference or identifying descriptor>", "currentTime": "<current specific time>" | null, "changeField": "time" | "title" | "day", "changeValue": "<new time, new title, or destination day>"}. targetDay is always where the event exists now, never the destination day. The query is lookup language, not canonical identity; preserve what the user means even if it may differ slightly from the stored Calendar title. Use currentTime only when the user identifies the existing event by its current time. For "move my business meeting today to tomorrow" use targetDay="today", changeField="day", changeValue="tomorrow"; "same time" means preserve the existing time and do not invent a time change. Never put an event id in proposedArguments and never invent a target or requested change.
- An edit proposal identifies a natural target reference plus one desired change only. Deterministic Calendar state resolves the reference as exact, likely, ambiguous, or none. A likely fuzzy match must be shown to the user for confirmation against the real Calendar event before mutation; ambiguous matches must ask the user to distinguish candidates; only one resolved canonical event identity may proceed and it must remain locked across confirmation.
- Do not collapse a broad plan such as "schedule my day" or a multi-event request into one add-calendar-event proposal. Those are outside this single-intent slice.
- Calendar delete-last and clear operations are NOT agent-executable yet. Still classify those single-intent writes as turnOwner=calendar, disposition=tool, proposedCapability=calendar, and the exact canonical Calendar write action, but treat proposed arguments only as routing/consistency metadata for the existing guarded path.
- Calendar create/delete/edit proposals are still only proposals. They are not proof that anything changed; deterministic validation, target resolution, confirmation, execution, and verified receipts remain authoritative.
Tasks ownership rule:
- Natural single-intent requests to create one task are Tasks-owned tools when the user is asking QMeet to save/add something as a task or to-do. Structural forms such as "put X on my to-do list", "add X to my tasks", "make X a task", and equivalent natural wording are mutations, not conversation. Use proposedCapability=tasks, proposedAction=remember-task, and proposedArguments with exactly one field: {"title": "<concise task title>"}.
- The task title is a proposed label, not execution authority. Make it concise and action-oriented, remove conversational filler such as "remember to" when natural, and do not invent deadlines, people, project context, or other details the user did not provide.
- Natural requests for the user's GLOBAL task list are Tasks-owned reads. Examples include "what tasks do I have?", "read my tasks", "show my to-do list", and equivalent wording that does not explicitly reference the active Focus. Use proposedCapability=tasks, proposedAction=read-memory, and proposedArguments exactly {"scope": "global"}. For this global scope set focusRelevant=false even when a Focus is active.
- Questions specifically about tasks linked to the active Focus (for example "what tasks are part of this focus?" or "show my Focus tasks") are Focus-owned, not global Tasks reads. Use the Focus capability/read surface so canonical Focus linkage remains authoritative.
- Natural single-intent statements that one named/referenced task is already finished are Tasks-owned mutations. Examples include "I finished the invoice", "mark the presentation outline done", "I sent the invoice", and "I took care of the slides" when they refer to one task. Use proposedCapability=tasks, proposedAction=mark-task-done, and proposedArguments exactly {"scope": "global", "query": "<concise identifying task reference>"}. The query is lookup language only, never a task id or proof of completion. Remove conversational completion wrappers/articles when useful (for example "the invoice" -> "invoice"), but do not invent a task title or hidden task state.
- Do not collapse multi-task or ordinal completion requests into one promoted completion. Requests such as "I finished the first two tasks" or "mark all tasks done" remain on the existing deterministic parser/preview path when it can handle them.
- Task completion remains on QMeet's existing deterministic identity/confirmation execution path: the semantic query must resolve against real open task state to zero, one, or multiple candidates; zero changes nothing, multiple candidates require clarification, and exactly one resolved task identity must remain locked across confirmation. If that task is Focus-linked, canonical Focus progress verification remains authoritative before local completion.
- Do not use remember-task for statements that work was already completed. Delete-last and clear-completed also remain on their existing guarded paths in this slice.
- A promoted task create/read/complete still executes only after deterministic frontend validation; a read proposal never authorizes mutation and a completion proposal never supplies canonical task identity.
Notes ownership rule:
- Natural single-intent requests to save one note are Notes-owned mutations. Use proposedCapability=notes, proposedAction=save-note, and proposedArguments with exactly one field: {"content": "<the note content the user asked to preserve>"}.
- Preserve the user's intended note content rather than turning it into a task, Calendar event, or invented summary. Remove only the surrounding request wrapper when appropriate. Do not invent deadlines, priorities, people, decisions, or conclusions that are not supported by the request/current conversation.
- Natural requests to read/list/recall the user's saved Notes are Notes-owned reads. Use proposedCapability=notes, proposedAction=read-notes, and proposedArguments={}.
- A request to save/summarize the active Focus as a note remains Focus-owned through save-focus-summary/end-focus-with-summary; do not reclassify that workflow as an ordinary save-note.
- Notes delete/clear remain on their existing deterministic paths in this slice. A promoted note save/read still executes only through the existing Notes handler after deterministic frontend validation.
Proposed action never proves that anything changed.
Canonical action vocabulary:
- If disposition=tool, proposedAction MUST be one exact action id from capabilityContract. Do not invent aliases such as focus.read, read_current_focus, calendar.create_event, or custom compound action names.
- If disposition=conversation, proposedAction MUST be focus.help for Focus-owned work or conversation.respond otherwise.
- If disposition=clarify, proposedAction MUST be none.
- proposedCapability identifies the owning capability; proposedAction identifies the exact canonical action contract.
Current prototype constraint: promoted Calendar create, targeted-delete, and targeted-edit arguments currently understand today/tomorrow reliably; do not treat unsupported farther-day wording as a Focus-routing issue.
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


def _clean_fallback_calendar_create_title(value: str) -> str:
    """Apply conservative display cleanup when the model create proposal is unavailable.

    Semantic naming remains the agent's job. This fallback only removes an opening
    article/possessive and applies restrained title casing; it never invents facts.
    """
    cleaned = re.sub(r"\s+", " ", value.strip()).strip(" ,.;:")
    cleaned = re.sub(r"^(?:a|an|the|my|our)\s+", "", cleaned, flags=re.IGNORECASE)
    if not cleaned:
        return ""
    small_words = {"and", "or", "of", "the", "to", "for", "with", "at", "in", "on"}
    words = cleaned.split(" ")
    rendered: list[str] = []
    for index, word in enumerate(words):
        if any(char.isupper() for char in word[1:]) or "&" in word or any(char.isdigit() for char in word):
            rendered.append(word)
            continue
        lower = word.casefold()
        if index not in {0, len(words) - 1} and lower in small_words:
            rendered.append(lower)
        else:
            rendered.append(word[:1].upper() + word[1:].lower())
    return " ".join(rendered)


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

    title = _clean_fallback_calendar_create_title(match.group(1))
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


def _clean_explicit_task_create_title(value: str) -> str | None:
    title = re.sub(r"\s+", " ", value.strip())
    title = re.sub(r"^[\"'`]+|[\"'`]+$", "", title).strip()
    title = re.sub(r"^(?:to\s+)", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"[.!?]+$", "", title).strip()
    if not title or len(title) > 240 or re.search(r"[\x00-\x1f\x7f]", title):
        return None
    return title


def _explicit_task_create_title(user_message: str) -> str | None:
    """Extract one literal task body only from an unmistakable task container.

    This is a deterministic ownership/execution fallback, not the primary semantic
    parser. The unified agent still gets the first chance to produce a cleaner
    action-oriented title. These wrappers only ensure an obvious durable task
    mutation cannot fall through to read-only conversation when the model
    misclassifies the disposition.
    """
    text = re.sub(r"\s+", " ", user_message.strip())
    wrappers = (
        r"^(?:please\s+)?(?:put|add|save)\s+(.+?)\s+(?:on|to|in)\s+(?:(?:my|our|the)\s+)?(?:to[-\s]?do(?:\s+list)?|tasks?|task\s+list|checklist)\s*[.!?]*$",
        r"^(?:please\s+)?(?:make)\s+(.+?)\s+(?:a\s+)?task\s*[.!?]*$",
        r"^(?:please\s+)?(?:turn)\s+(.+?)\s+into\s+(?:a\s+)?task\s*[.!?]*$",
        r"^(?:please\s+)?(?:create|add|make)\s+(?:a\s+)?task\s+(?:to\s+)?(.+?)\s*$",
        r"^(?:please\s+)?(?:save|remember)\s+(.+?)\s+as\s+(?:a\s+)?task\s*[.!?]*$",
    )
    for pattern in wrappers:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_explicit_task_create_title(match.group(1))
    return None


def _is_explicit_global_task_read_request(user_message: str) -> bool:
    """Recognize an explicit global task-list read without claiming Focus tasks."""
    text = _normalize(user_message)
    if not re.search(r"\b(?:tasks?|task\s+list|to[- ]?do(?:\s+list)?|todo(?:\s+list)?|checklist)\b", text):
        return False
    if re.search(r"\b(?:focus|focus\s+session|linked\s+tasks?)\b", text):
        return False
    if re.search(r"\btasks?\s+(?:for|from|in|under)\s+(?:this|my|the|our)?\s*focus\b", text):
        return False
    if re.search(r"\b(?:add|create|make|put|save|remember|mark|complete|completed|finish|finished|delete|remove|clear|reopen|restore)\b", text):
        return False
    return bool(
        re.search(r"\b(?:read|list|show|display|review|recall|tell me|what|which)\b", text)
    )


def _clean_explicit_note_content(value: str) -> str | None:
    content = re.sub(r"\s+", " ", value.strip())
    content = re.sub(r"^[\"'`]+|[\"'`]+$", "", content).strip()
    if not content or len(content) > 6000 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", content):
        return None
    return content


def _explicit_note_save_content(user_message: str) -> str | None:
    """Extract literal note content only from unmistakable note containers.

    This is an ownership fallback, not the primary semantic interpreter. The
    unified agent remains free to understand broader natural note wording. The
    fallback only prevents obvious durable note mutations from being narrated by
    read-only conversation when one literal note body is present in this turn.
    """
    text = re.sub(r"\s+", " ", user_message.strip())
    wrappers = (
        r"^(?:please\s+)?(?:jot|write)\s+(?:this\s+)?down\s+(?:in|to)\s+(?:(?:my|the)\s+)?notes?\s*(?:that\s+|:)?(.+?)\s*$",
        r"^(?:please\s+)?(?:put|add|save)\s+(.+?)\s+(?:in|to)\s+(?:(?:my|the)\s+)?notes?\s*[.!?]*$",
        r"^(?:please\s+)?(?:save|keep)\s+(.+?)\s+as\s+(?:a\s+)?note\s*[.!?]*$",
        r"^(?:please\s+)?(?:make|create|take|write)\s+(?:a\s+)?note\s+(?:that\s+|saying\s+|about\s+)?(.+?)\s*$",
        r"^(?:please\s+)?note\s+that\s+(.+?)\s*$",
    )
    for pattern in wrappers:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            content = _clean_explicit_note_content(match.group(1))
            if content and not re.fullmatch(r"(?:(?:this|the|my|current|active)\s+)?focus(?:\s+session)?", content, flags=re.IGNORECASE):
                return content
    return None


def _is_explicit_note_read_request(user_message: str) -> bool:
    text = _normalize(user_message)
    if not re.search(r"\bnotes?\b", text):
        return False
    if re.search(r"\b(?:delete|remove|clear|wipe|save|add|put|write|jot|take|make|create)\b", text):
        return False
    return bool(
        re.search(r"\b(?:read|list|recall|show|tell me|what|which|review|go over|have i written|did i write)\b", text)
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
                else (
                    "Keep Calendar ownership. Targeted edit/delete still require a capability-specific typed proposal and deterministic target resolution; broad writes remain on the existing guarded path."
                    if calendar_write_action in {"edit-last-event", "delete-calendar-event"}
                    else "Keep Calendar ownership, then defer this unpromoted mutation to the existing guarded Calendar write path."
                )
            ),
            confidence=0.95,
            reason=(
                "The request is one Calendar event creation with a narrow today/tomorrow argument contract."
                if create_is_typed
                else (
                    "Calendar/event write language owns this turn; targeted mutations are executable only when the agent supplies a valid typed proposal that deterministic Calendar state resolves safely."
                    if calendar_write_action in {"edit-last-event", "delete-calendar-event"}
                    else "Calendar/event write language owns this turn, but this mutation is not agent-executable in this slice."
                )
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
    explicit_note_content = _explicit_note_save_content(request.userMessage)
    if explicit_note_content:
        return _decision(
            owner="notes",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="notes",
            action="save-note",
            response_plan="Save exactly one verified note through the deterministic Notes handler, then continue from the Tool receipt.",
            confidence=0.97,
            reason="The user placed one literal item into an explicit note container.",
            arguments={"content": explicit_note_content},
        )
    if _is_explicit_note_read_request(request.userMessage):
        return _decision(
            owner="notes",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="notes",
            action="read-notes",
            response_plan="Read authoritative saved Notes through the deterministic Notes handler and ground the reply in that Tool result.",
            confidence=0.97,
            reason="The user explicitly asked to read or recall saved Notes.",
            arguments={},
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
    explicit_task_create_title = _explicit_task_create_title(request.userMessage)
    if explicit_task_create_title:
        return _decision(
            owner="tasks",
            focus_relevant=focus_relevant,
            disposition="tool",
            capability="tasks",
            action="remember-task",
            response_plan="Save exactly one verified task through the deterministic task handler, then continue from the Tool receipt.",
            confidence=0.97,
            reason="The user placed one item into an explicit task/to-do container.",
            arguments={"title": explicit_task_create_title},
        )
    if _is_explicit_global_task_read_request(request.userMessage):
        return _decision(
            owner="tasks",
            focus_relevant=False,
            disposition="tool",
            capability="tasks",
            action="read-memory",
            response_plan="Read the authoritative global open-task list without allowing Active Focus to replace the requested scope.",
            confidence=0.97,
            reason="The user explicitly requested the global task/to-do list and did not reference Focus-linked tasks.",
            arguments={"scope": "global"},
        )
    if re.search(r"\b(?:task|tasks|checklist|to[- ]?do|todo)\b", text):
        action = "tasks.complete" if re.search(r"\b(?:done|complete|completed|finish|finished)\b", text) else "tasks.read"
        if re.search(r"\b(?:make|create|turn .* into|add|put|save)\b", text):
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


def _is_valid_calendar_delete_arguments(arguments: dict[str, Any]) -> bool:
    if set(arguments) != {"day", "title", "time"}:
        return False
    day = arguments.get("day")
    title = arguments.get("title")
    time_value = arguments.get("time")
    if day not in {"today", "tomorrow"}:
        return False
    if title is not None:
        if not isinstance(title, str):
            return False
        title = title.strip()
        if not title or len(title) > 240 or re.search(r"[\x00-\x1f\x7f]", title):
            return False
    if time_value is not None:
        if not isinstance(time_value, str):
            return False
        time_value = time_value.strip()
        if not time_value or len(time_value) > 32 or re.search(r"[\x00-\x1f\x7f]", time_value):
            return False
        normalized_time = re.sub(r"\s+", " ", time_value.casefold().replace(".", "")).strip()
        if normalized_time not in {"noon", "midnight"}:
            match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", normalized_time)
            if not match:
                return False
            hour = int(match.group(1))
            minute = int(match.group(2) or "0")
            meridiem = match.group(3)
            if minute > 59:
                return False
            if meridiem and not 1 <= hour <= 12:
                return False
            if not meridiem and not 0 <= hour <= 23:
                return False
    return bool(title or time_value)


def _is_executable_calendar_delete_tool_decision(decision: AgentShadowDecision) -> bool:
    return (
        decision.turnOwner == "calendar"
        and decision.disposition == "tool"
        and decision.proposedCapability == "calendar"
        and canonical_action_id(decision.proposedAction) == "delete-calendar-event"
        and _is_valid_calendar_delete_arguments(decision.proposedArguments)
    )


def _is_valid_calendar_edit_arguments(arguments: dict[str, Any]) -> bool:
    if set(arguments) != {"targetDay", "query", "currentTime", "changeField", "changeValue"}:
        return False

    target_day = arguments.get("targetDay")
    query = arguments.get("query")
    current_time = arguments.get("currentTime")
    change_field = arguments.get("changeField")
    change_value = arguments.get("changeValue")

    if target_day not in {"today", "tomorrow"}:
        return False
    if (
        not isinstance(query, str)
        or not query.strip()
        or len(query.strip()) > 240
        or re.search(r"[\x00-\x1f\x7f]", query.strip())
    ):
        return False

    def valid_optional_time(value: Any) -> bool:
        if value is None:
            return True
        if not isinstance(value, str):
            return False
        time_value = value.strip()
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

    if not valid_optional_time(current_time):
        return False
    if change_field not in {"time", "title", "day"}:
        return False
    if not isinstance(change_value, str):
        return False
    change_value = change_value.strip()
    if not change_value or re.search(r"[\x00-\x1f\x7f]", change_value):
        return False
    if change_field == "time":
        return len(change_value) <= 32 and valid_optional_time(change_value)
    if change_field == "day":
        return change_value in {"today", "tomorrow"} and change_value != target_day
    return len(change_value) <= 240


def _is_executable_calendar_edit_tool_decision(decision: AgentShadowDecision) -> bool:
    return (
        decision.turnOwner == "calendar"
        and decision.disposition == "tool"
        and decision.proposedCapability == "calendar"
        and canonical_action_id(decision.proposedAction) == "edit-last-event"
        and _is_valid_calendar_edit_arguments(decision.proposedArguments)
    )


def _normalize_calendar_time_reference(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.casefold().replace(".", "")).strip()
    if cleaned in {"noon", "midnight"}:
        return cleaned
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", cleaned)
    if not match:
        return cleaned.replace(" ", "")
    hour = str(int(match.group(1)))
    minute = match.group(2) or "00"
    meridiem = match.group(3) or ""
    return f"{hour}:{minute}{meridiem}"


def _calendar_edit_current_time_is_explicit(
    user_message: str,
    current_time: Any,
) -> bool:
    """Allow currentTime to narrow lookup only when this turn says that time.

    Recent conversation can be useful context, but it must not silently become a
    canonical lookup criterion for a Calendar mutation.
    """
    if current_time is None:
        return True
    if not isinstance(current_time, str) or not current_time.strip():
        return False
    target = _normalize_calendar_time_reference(current_time)
    tokens = re.findall(
        r"\b(?:\d{1,2}(?::\d{2})?\s*(?:a\.?\s*m\.?|p\.?\s*m\.?|am|pm)?|noon|midnight)\b",
        user_message,
        flags=re.IGNORECASE,
    )
    return any(_normalize_calendar_time_reference(token) == target for token in tokens)


def _has_valid_calendar_edit_proposal(decision: AgentShadowDecision) -> bool:
    """Accept typed edit semantics for ownership-floor repair only.

    This does not execute or authorize Calendar state. It lets the deterministic
    Calendar ownership floor preserve a valid target/change proposal even when
    the model mislabeled owner/capability metadata. Frontend validation, canonical
    state resolution, confirmation, and the deterministic executor still gate the write.
    """
    return (
        decision.disposition == "tool"
        and canonical_action_id(decision.proposedAction) == "edit-last-event"
        and _is_valid_calendar_edit_arguments(
            _normalize_calendar_edit_argument_shape(decision.proposedArguments)
        )
    )


def apply_calendar_write_ownership_floor(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
    decision: AgentShadowDecision,
) -> AgentShadowDecision:
    """Keep clear single-intent Calendar mutations out of chat/Focus ownership.

    Calendar create, targeted delete, and targeted edit may carry narrow typed
    proposals that the frontend validates again. Other writes remain routing
    metadata only and continue into their existing guarded interpreter/confirmation
    paths. Nothing executes here.
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
    if fallback_action == "delete-calendar-event" and _is_executable_calendar_delete_tool_decision(decision):
        return decision
    if fallback_action == "edit-last-event" and _has_valid_calendar_edit_proposal(decision):
        normalized_arguments = _normalize_calendar_edit_argument_shape(
            decision.proposedArguments
        )
        if not _calendar_edit_current_time_is_explicit(
            request.userMessage,
            normalized_arguments.get("currentTime"),
        ):
            normalized_arguments = {
                **normalized_arguments,
                "currentTime": None,
            }
        return fallback.model_copy(
            update={
                "proposedArguments": normalized_arguments,
                "reason": (
                    "Deterministic Calendar write ownership floor repaired Calendar edit ownership metadata while preserving only the model's strictly validated target/change proposal. Execution still requires deterministic event resolution and confirmation."
                ),
            }
        )

    if (
        fallback_action not in {"add-calendar-event", "delete-calendar-event", "edit-last-event"}
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


def _is_valid_task_create_arguments(arguments: dict[str, Any]) -> bool:
    if set(arguments) != {"title"}:
        return False
    title = arguments.get("title")
    if not isinstance(title, str):
        return False
    title = re.sub(r"\s+", " ", title.strip())
    return bool(title) and len(title) <= 240 and not re.search(r"[\x00-\x1f\x7f]", title)


def _is_executable_task_create_tool_decision(decision: AgentShadowDecision) -> bool:
    return (
        decision.turnOwner == "tasks"
        and decision.disposition == "tool"
        and decision.proposedCapability == "tasks"
        and canonical_action_id(decision.proposedAction) == "remember-task"
        and _is_valid_task_create_arguments(decision.proposedArguments)
    )


def _is_valid_task_read_arguments(arguments: dict[str, Any]) -> bool:
    return set(arguments) == {"scope"} and arguments.get("scope") == "global"


def _is_executable_task_read_tool_decision(decision: AgentShadowDecision) -> bool:
    return (
        decision.turnOwner == "tasks"
        and decision.disposition == "tool"
        and decision.proposedCapability == "tasks"
        and canonical_action_id(decision.proposedAction) == "read-memory"
        and _is_valid_task_read_arguments(decision.proposedArguments)
    )


def apply_task_create_ownership_floor(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
    decision: AgentShadowDecision,
) -> AgentShadowDecision:
    """Keep unmistakable single-task creation out of read-only conversation.

    The model remains primary. This floor activates only when the conservative
    fallback grammar identifies one explicit task/to-do container. It preserves a
    valid model-proposed title when available; otherwise it uses only the literal
    task body extracted from the current user request. It never executes state.
    Frontend validation and the existing remember-task handler remain authoritative.
    """
    fallback = normalize_shadow_decision(_fallback_shadow_decision(request, focus))
    if not (
        fallback.turnOwner == "tasks"
        and fallback.disposition == "tool"
        and canonical_action_id(fallback.proposedAction) == "remember-task"
        and fallback.confidence >= 0.95
        and _is_valid_task_create_arguments(fallback.proposedArguments)
    ):
        return decision

    if _is_executable_task_create_tool_decision(decision):
        return decision

    repaired_arguments = fallback.proposedArguments
    if _is_valid_task_create_arguments(decision.proposedArguments):
        repaired_arguments = {
            "title": re.sub(
                r"\s+",
                " ",
                str(decision.proposedArguments["title"]).strip(),
            )
        }

    return fallback.model_copy(
        update={
            "proposedArguments": repaired_arguments,
            "reason": (
                "Deterministic Tasks creation ownership floor: an unmistakable request to place one item in tasks/to-do cannot be answered by the read-only conversation lane. The model's validated title is preserved when available; otherwise only the literal task body from the current request is used. Execution still requires frontend validation and the deterministic remember-task handler."
            ),
        }
    )


def apply_task_read_ownership_floor(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
    decision: AgentShadowDecision,
) -> AgentShadowDecision:
    """Keep explicit global task reads independent from Active Focus ownership."""
    fallback = normalize_shadow_decision(_fallback_shadow_decision(request, focus))
    if not (
        fallback.turnOwner == "tasks"
        and fallback.disposition == "tool"
        and canonical_action_id(fallback.proposedAction) == "read-memory"
        and fallback.focusRelevant is False
        and fallback.confidence >= 0.95
        and _is_valid_task_read_arguments(fallback.proposedArguments)
    ):
        return decision

    if _is_executable_task_read_tool_decision(decision):
        return decision.model_copy(
            update={
                "focusRelevant": False,
                "proposedArguments": {"scope": "global"},
                "reason": (
                    "Deterministic global Tasks read ownership floor preserved the model's valid read proposal while explicitly excluding Active Focus from the requested scope."
                ),
            }
        )

    return fallback.model_copy(
        update={
            "focusRelevant": False,
            "proposedArguments": {"scope": "global"},
            "reason": (
                "Deterministic global Tasks read ownership floor: an explicit request for the user's task/to-do list cannot be swallowed by Focus or read-only conversation. The read remains non-mutating and frontend validation is still authoritative."
            ),
        }
    )


def _is_valid_note_save_arguments(arguments: dict[str, Any]) -> bool:
    if set(arguments) != {"content"}:
        return False
    content = arguments.get("content")
    if not isinstance(content, str):
        return False
    content = content.strip()
    return bool(content) and len(content) <= 6000 and not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", content)


def _is_executable_note_save_tool_decision(decision: AgentShadowDecision) -> bool:
    return (
        decision.turnOwner == "notes"
        and decision.disposition == "tool"
        and decision.proposedCapability == "notes"
        and canonical_action_id(decision.proposedAction) == "save-note"
        and _is_valid_note_save_arguments(decision.proposedArguments)
    )


def _is_executable_note_read_tool_decision(decision: AgentShadowDecision) -> bool:
    return (
        decision.turnOwner == "notes"
        and decision.disposition == "tool"
        and decision.proposedCapability == "notes"
        and canonical_action_id(decision.proposedAction) == "read-notes"
        and decision.proposedArguments == {}
    )


def apply_notes_ownership_floor(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
    decision: AgentShadowDecision,
) -> AgentShadowDecision:
    """Keep explicit Notes saves/reads out of read-only conversation.

    The model remains primary. This floor only repairs unmistakable note-container
    saves with literal content and explicit saved-note reads. It never writes or
    reads state itself; frontend validation and the existing Notes handler remain
    authoritative.
    """
    fallback = normalize_shadow_decision(_fallback_shadow_decision(request, focus))
    fallback_action = canonical_action_id(fallback.proposedAction)
    if not (
        fallback.turnOwner == "notes"
        and fallback.disposition == "tool"
        and fallback_action in {"save-note", "read-notes"}
        and fallback.confidence >= 0.95
    ):
        return decision

    if fallback_action == "save-note":
        if _is_executable_note_save_tool_decision(decision):
            return decision
        repaired_arguments = fallback.proposedArguments
        if _is_valid_note_save_arguments(decision.proposedArguments):
            repaired_arguments = {"content": str(decision.proposedArguments["content"]).strip()}
        return fallback.model_copy(
            update={
                "proposedArguments": repaired_arguments,
                "reason": (
                    "Deterministic Notes save ownership floor: an unmistakable one-note mutation cannot be answered by read-only conversation. A strictly valid model-proposed note body is preserved when available; otherwise only literal note content from the current request is used. Execution still requires frontend validation and the deterministic Notes handler."
                ),
            }
        )

    if _is_executable_note_read_tool_decision(decision):
        return decision
    return fallback.model_copy(
        update={
            "proposedArguments": {},
            "reason": (
                "Deterministic Notes read ownership floor: an explicit request for saved Notes must read authoritative Notes state instead of being answered from conversation memory."
            ),
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


_CALENDAR_EDIT_ARGUMENT_KEYS = (
    "day",
    "query",
    "currentTime",
    "changeField",
    "changeValue",
)

_LEGACY_CALENDAR_EDIT_ARGUMENT_KEYS = (
    "targetDay",
    "targetTitle",
    "targetTime",
    "newDay",
    "newTitle",
    "newTime",
)

def _normalize_calendar_edit_argument_shape(
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Canonicalize safe model-shape variation without resolving Calendar state.

    targetDay always means the source day used for deterministic lookup. Missing
    currentTime is equivalent to null. The immediately preceding `day`-key
    contract is migrated to targetDay for compatibility. Legacy six-field
    proposals are translated only when they contain exactly one supported
    day/title/time change. Unknown keys or multiple changes remain invalid.
    """
    copied = dict(arguments)
    canonical_allowed = {
        "targetDay",
        "query",
        "currentTime",
        "changeField",
        "changeValue",
    }
    if set(copied).issubset(canonical_allowed):
        if not {"targetDay", "query", "changeField", "changeValue"}.issubset(copied):
            return copied
        return {
            "targetDay": copied.get("targetDay"),
            "query": copied.get("query"),
            "currentTime": copied.get("currentTime"),
            "changeField": copied.get("changeField"),
            "changeValue": copied.get("changeValue"),
        }

    previous_allowed = {"day", "query", "currentTime", "changeField", "changeValue"}
    if set(copied).issubset(previous_allowed):
        if not {"day", "query", "changeField", "changeValue"}.issubset(copied):
            return copied
        return {
            "targetDay": copied.get("day"),
            "query": copied.get("query"),
            "currentTime": copied.get("currentTime"),
            "changeField": copied.get("changeField"),
            "changeValue": copied.get("changeValue"),
        }

    legacy_allowed = set(_LEGACY_CALENDAR_EDIT_ARGUMENT_KEYS)
    if not set(copied).issubset(legacy_allowed):
        return copied
    if "targetDay" not in copied or "targetTitle" not in copied:
        return copied
    requested = [
        ("day", copied.get("newDay")),
        ("title", copied.get("newTitle")),
        ("time", copied.get("newTime")),
    ]
    requested = [(field, value) for field, value in requested if value is not None]
    if len(requested) != 1:
        return copied
    change_field, change_value = requested[0]
    return {
        "targetDay": copied.get("targetDay"),
        "query": copied.get("targetTitle"),
        "currentTime": copied.get("targetTime"),
        "changeField": change_field,
        "changeValue": change_value,
    }


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
        updates: dict[str, Any] = {"proposedAction": canonical}
        if decision.disposition == "tool" and canonical == "edit-last-event":
            updates["proposedArguments"] = _normalize_calendar_edit_argument_shape(
                decision.proposedArguments
            )
        return decision.model_copy(update=updates)
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
    decision = apply_task_create_ownership_floor(request, focus, decision)
    decision = apply_task_read_ownership_floor(request, focus, decision)
    decision = apply_notes_ownership_floor(request, focus, decision)
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
