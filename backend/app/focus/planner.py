from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from uuid import uuid4

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - startup remains available in mock mode.
    AsyncOpenAI = None  # type: ignore[assignment]

from app.focus.legacy import load_legacy_focus_seed
from app.focus.route_bridge import (
    calendar_write_intent,
    memory_mutation_intent,
    memory_read_intent,
    visual_mutation_intent,
    visual_read_intent,
)
from app.focus.models import (
    FocusOperationKind,
    FocusState,
    ObserveTurnRequest,
    PlannedToolCall,
    ResponseIntent,
    ToolArgument,
    ToolName,
    TurnPlan,
    TurnRoute,
)
from app.focus.store import (
    apply_turn_plan,
    get_state,
    has_turn,
    list_events,
    seed_from_legacy,
)

LOGGER = logging.getLogger("qmeet.focus")

DEFAULT_MODEL = (
    os.getenv("QMEET_FOCUS_MODEL")
    or os.getenv("OPENAI_COMMAND_MODEL")
    or os.getenv("OPENAI_MODEL")
    or "gpt-4.1-mini"
)

_PLANNER_SYSTEM_PROMPT = """
You are QMeet's turn planner. You do not execute tools and you do not write the
final assistant reply. You produce one strict TurnPlan that a deterministic
executor can validate and apply.

The focus system is event-sourced. Make the smallest truthful state changes that
are supported by the user's actual words and current context.

Core rules:

1. One turn has one semantic authority: this plan. Do not invent separate
   interpretations for chat, commands, memory, and tools.

2. Use the pending question and pending action to interpret short replies such
   as "yes", "sure", "no", "that works", and voice corrections.

3. Start a focus only for durable work that benefits from continuity. Do not
   start one for a single lookup, a tiny UI command, or casual conversation.

   Source matters:

   - source="search-request-shadow" means the user already triggered QMeet's
     real Search route and userMessage is the raw search query.
   - A direct Search query is transient by default. Keep focusOperations empty,
     emit the Search tool call, and set attachToFocus=false.
   - Do not end, rescope, or replace an active Focus merely because a direct
     Search query is unrelated to it.
   - Set attachToFocus=true only when the Search directly advances the active
     Focus, or when the user explicitly asks to begin durable work that should
     be tracked across turns.
   - Emotional importance or a complicated question alone does not make a
     lookup durable. "Why did my dog run away?" is a transient Search. "Help me
     find my missing dog and keep track of what I have tried" is durable work.

   - source="calendar-read-shadow" means QMeet is reading the user's connected
     Google Calendar for the requested view. Plan one calendar_read tool call.
     Attach it only when the calendar evidence directly advances the active
     durable Focus; otherwise keep it transient.
   - A Calendar create, edit, or delete request is not calendar_read. Record a
     calendar_write tool call with requiresConfirmation=true and
     attachToFocus=false. Do not claim that the write has happened.

   - A request to read saved visual context, the latest visual observation,
     visual history, a visual summary, or visuals linked to the current Focus
     uses visual_read. It is a route-only read of existing memory: use
     requiresConfirmation=false and attachToFocus=false. Never treat camera
     capture, snapshot analysis, saving, linking, clearing, or deleting visual
     observations as visual_read.
   - A clear or delete request for saved visual context uses visual_write only
     as a protected route marker. Set requiresConfirmation=false and
     attachToFocus=false. Focus must not execute the mutation or answer as chat;
     the existing frontend visual-memory handler remains authoritative.
   - Reading saved notes uses notes_read. Reading or summarizing the task list
     uses tasks_read. Both are route-only reads: requiresConfirmation=false,
     attachToFocus=false, and no durable Focus operations.
   - Creating, completing, clearing, or deleting notes or tasks uses
     memory_write only as a protected route marker. Focus must not execute or
     narrate the mutation; the existing frontend memory handler owns it.

4. Distinguish focus continuation, correction, and replacement precisely:

   - Continue the current focus when the new turn advances the same objective.
   - Use rescope_focus only when the user is correcting, clarifying, narrowing,
     broadening, or renaming the same intended objective.
   - Use start_focus when the user begins a different durable objective that is
     not part of the current focus.
   - Do not use rescope_focus merely because only one focus may be active.
   - The deterministic executor will end the previous focus before starting a
     replacement focus, so do not preserve an unrelated objective by rescoping it.

   Examples:
   - Active focus: diagnose car starting trouble.
     User: "I meant the battery light, not the oil light."
     Result: rescope_focus or field updates within the same focus.
   - Active focus: diagnose car starting trouble.
     User: "Help me plan the next phase of QMeet."
     Result: start_focus for QMeet planning, not rescope_focus.
   - Active focus: plan QMeet's next phase.
     User: "The first priority is connecting real frontend turns."
     Result: update the current focus, not start_focus or rescope_focus.

5. Use generic state fields. Prefer objective, deliverable, subject,
   stakeholders, requirements, constraints, preferences, decisions, knownFacts,
   milestones, and completedMilestones. Domain tags may help but must not create
   domain-specific schemas.

   Classify each durable statement by meaning, not by convenient wording:

   - requirements: outcomes or capabilities the result must provide.
   - constraints: hard limits, non-negotiable boundaries, deadlines, budgets,
     compatibility rules, or behavior that must remain unchanged.
   - preferences: soft choices that may be traded off.
   - decisions: approaches the user has explicitly selected.
   - knownFacts: observations or established context that are not instructions.
   - milestones: planned work items, priorities, checkpoints, or deliverables.
   - completedMilestones: work the user clearly reports as finished.

   Split one sentence into multiple operations when it contains facts with
   different meanings. Do not collapse a milestone and a constraint into one
   preference.

   Example:
   User: "The first priority is connecting real frontend turns to the new Focus
   system without changing visible legacy behavior."
   Result:
   - add_list_item milestones: "Connect real frontend turns to the new Focus system."
   - add_list_item constraints: "Visible legacy behavior must remain unchanged."
   - clear the pending question that this answer resolves.

6. Ask at most one useful follow-up. The follow-up must be atomic: it should
   request one fact, decision, observation, or action that the user can answer
   unambiguously. Do not combine independent questions with "or", "and", a
   slash, or multiple clauses. When several unknowns matter, ask only the
   highest-information question first and leave the others for later turns.
   Do not ask a question when enough context exists to help directly.

   Example:
   - Avoid: "Have you tested or replaced the battery, or do the lights dim?"
   - Prefer: "Do the dashboard lights dim when you try to start the car?"

7. Current prices, public availability, links, news, and web research require
   a Search tool call. Reading the user's own Google Calendar or answering what
   is scheduled on it requires calendar_read, not Search. Never fabricate tool
   results, calendar contents, free time, or claim a tool has completed.

8. A tool request creates a pending action only when attachToFocus=true. Tool
   completion will arrive later as a separate event from deterministic code.
   Transient tool calls are still logged for turn tracing but must not change
   the active Focus state.

9. Do not mark a focus complete merely because a draft exists. Mark complete
   only when the user clearly reports the real-world result or asks to finish.

10. If the user asks to end or close the focus, plan the end_focus or
    save_focus_summary tool. Do not merely say it is closed.

11. Preserve uncertainty. A suspected cause is a known fact with uncertainty,
    not a confirmed decision.

12. Do not store greetings, acknowledgements, assistant prose, or malformed
    transcription fragments as facts.

13. Preserve accepted intent across prerequisite turns. If the user already
    requested or accepted instructions, an explanation, a draft, or another
    deliverable, and later turns only answer prerequisite questions, do not ask
    permission for the same deliverable again. Deliver it once the prerequisite
    is satisfied. If one prerequisite is still missing, ask only that atomic
    prerequisite and keep answerDirectly=false.

14. answerDirectly=true means responseIntent.guidance must contain the requested
    answer or deliverable now. Do not merely promise that it will be provided,
    and do not replace delivery with "Would you like..." or "Do you want..."
    after the user has already requested it.

15. The recent event context distinguishes canonical planning evidence from the
    legacy visible response. Treat turn_planned, response_candidate, focus state
    mutations, and tool results as planning evidence. An assistant_replied audit
    may report legacy mismatches, but legacy visible wording is not authoritative
    and must not override the canonical pending question or prior user intent.

16. Set responseIntent.attachToFocus=true only when the proposed visible reply
    directly advances, answers, summarizes, or closes the active durable Focus,
    including a direct answer that continues accepted intent from prior turns.
    Set it false for casual conversation, unrelated questions, transient lookups,
    and replies that should not be allowed to replace general legacy chat.

    Examples:
    - Active Focus: diagnose car starting trouble. User: "Repeat the jump-start
      instructions." Result: attachToFocus=true.
    - Active Focus: diagnose car starting trouble. User: "What's your dog's last
      name?" Result: attachToFocus=false.
    - A new start_focus operation with a direct canonical reply is attached to
      the newly started Focus.

Operation guidance:

- start_focus: use for a new durable objective; include title, objective, and
  optional tags.
- rescope_focus: use only for a correction or reframing of the same intended
  objective.
- set_field: use for one scalar field.
- add_list_item: add durable facts, constraints, preferences, decisions,
  stakeholders, requirements, milestones, or completed milestones.
- set_pending_question: include target and one concise question.
- clear_pending_question: use when the current turn answers it.
- set_pending_action: only for a non-tool waiting state.
- record_progress / complete_milestone: use only for work actually completed.
- mark_focus_complete: use when the outcome itself is complete.

Tool-call guidance:

- attachToFocus=false: one-off or unrelated tool use; log it without changing
  the active Focus.
- attachToFocus=true: the tool is part of the active or newly started Focus and
  its pending/completed state should update that Focus.
- When start_focus and a tool call occur in the same plan, use
  attachToFocus=true.

Examples:

- Active Focus: diagnose car trouble.
  source: search-request-shadow
  User query: "why my dog left me"
  Result: Search tool call with attachToFocus=false; no focusOperations.

- Active Focus: choose a machine-learning laptop under $4,000.
  source: search-request-shadow
  User query: "current RTX laptops under $4,000"
  Result: Search tool call with attachToFocus=true; continue the current Focus.

- Active Focus: prepare for today's client meetings.
  source: calendar-read-shadow
  User request: "Read my calendar for today."
  Result: calendar_read with attachToFocus=true because the verified events
  directly advance meeting preparation.

- Active Focus: diagnose car trouble.
  source: calendar-read-shadow
  User request: "What's on my calendar today?"
  Result: calendar_read with attachToFocus=false; do not let the calendar reply
  replace the unrelated car-trouble Focus response.

Tool names available in this first slice:

- search
- calendar_read
- calendar_write
- visual_read
- visual_write
- notes_read
- tasks_read
- memory_write
- open_search
- start_focus
- end_focus
- save_focus_summary

The system is currently in shadow mode. Your plan is logged and reduced into a
separate Focus state, but the legacy QMeet path still controls the visible UI.
""".strip()


_QUESTION_COORDINATOR_PATTERN = re.compile(r"\b(?:and|or)\b|[/;]", re.IGNORECASE)


def _normalize_question(question: str) -> str:
    return " ".join(question.split()).strip()


def _question_is_atomic(question: str) -> bool:
    """Return whether a follow-up asks for one unambiguous item.

    The planner prompt remains the semantic guide. This validator is a narrow
    deterministic guardrail that rejects common multi-part forms before they
    reach the event log.
    """

    normalized = _normalize_question(question)
    if not normalized:
        return True

    if not normalized.endswith("?") or normalized.count("?") != 1:
        return False

    body = normalized[:-1].strip()
    if not body:
        return False

    return _QUESTION_COORDINATOR_PATTERN.search(body) is None


def _plan_question_errors(plan: TurnPlan) -> list[str]:
    questions: list[str] = []

    response_question = _normalize_question(plan.responseIntent.askQuestion)
    if response_question:
        questions.append(response_question)

    for operation in plan.focusOperations:
        if operation.kind != FocusOperationKind.SET_PENDING_QUESTION:
            continue

        operation_question = _normalize_question(operation.question)
        if operation_question:
            questions.append(operation_question)
        else:
            questions.append("<empty pending question>")

    unique_questions: list[str] = []
    seen: set[str] = set()

    for question in questions:
        key = question.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique_questions.append(question)

    errors: list[str] = []

    if len(unique_questions) > 1:
        errors.append(
            "The plan contains more than one distinct follow-up question."
        )

    for question in unique_questions:
        if question == "<empty pending question>":
            errors.append("A set_pending_question operation has no question.")
        elif not _question_is_atomic(question):
            errors.append(
                f"The follow-up is not atomic: {question}"
            )

    return errors


def _strip_invalid_follow_up(
    plan: TurnPlan,
    errors: list[str],
) -> TurnPlan:
    """Preserve valid state changes while omitting an unsafe follow-up."""

    repaired = plan.model_copy(deep=True)
    repaired.focusOperations = [
        operation
        for operation in repaired.focusOperations
        if operation.kind != FocusOperationKind.SET_PENDING_QUESTION
    ]
    repaired.responseIntent.askQuestion = ""

    suffix = " Follow-up omitted after atomic-question validation."
    if suffix.strip() not in repaired.reason:
        repaired.reason = f"{repaired.reason.rstrip()}{suffix}".strip()

    LOGGER.warning(
        "Focus planner follow-up omitted after validation: %s",
        "; ".join(errors),
    )
    return repaired


async def _parse_plan(
    client: Any,
    messages: list[dict[str, str]],
) -> TurnPlan:
    completion = await client.chat.completions.parse(
        model=DEFAULT_MODEL,
        messages=messages,
        response_format=TurnPlan,
    )
    parsed = completion.choices[0].message.parsed

    if isinstance(parsed, TurnPlan):
        return parsed

    refusal = completion.choices[0].message.refusal or ""
    raise ValueError(
        "Structured planner response did not include a TurnPlan. "
        f"Refusal: {refusal[:200]}"
    )


async def _repair_non_atomic_plan(
    client: Any,
    *,
    planner_input: str,
    original_plan: TurnPlan,
    errors: list[str],
) -> TurnPlan:
    repair_instruction = {
        "task": "Repair the TurnPlan without changing its correct meaning.",
        "validationErrors": errors,
        "requirements": [
            "Preserve all correct focus operations and tool calls.",
            "Keep at most one follow-up question.",
            "The follow-up must request exactly one fact, decision, observation, or action.",
            "Do not use 'and', 'or', a slash, a semicolon, or multiple clauses in the follow-up.",
            "Make responseIntent.askQuestion and set_pending_question identical when both are present.",
            "If no useful atomic follow-up is needed, remove it from both locations.",
        ],
    }

    return await _parse_plan(
        client,
        [
            {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": planner_input},
            {
                "role": "assistant",
                "content": original_plan.model_dump_json(indent=2),
            },
            {
                "role": "user",
                "content": json.dumps(
                    repair_instruction,
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
    )


def focus_mode() -> str:
    mode = os.getenv("QMEET_FOCUS_MODE", "shadow").strip().casefold()
    return mode if mode in {"off", "shadow", "active"} else "shadow"


def planner_enabled() -> bool:
    if focus_mode() == "off":
        return False

    provider = os.getenv("LLM_PROVIDER", "mock").strip().casefold()
    return provider in {"openai", "openai-compatible", "openai_compatible"}


def _compact_recent_event_payload(
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Keep canonical continuity without replaying untrusted legacy prose."""

    if event_type == "turn_planned":
        plan = payload.get("plan", {})
        response_intent = plan.get("responseIntent", {})
        return {
            "message": payload.get("message", ""),
            "route": payload.get("route", plan.get("route", "")),
            "reason": payload.get("reason", plan.get("reason", "")),
            "responseIntent": {
                "acknowledge": response_intent.get("acknowledge", ""),
                "answerDirectly": response_intent.get(
                    "answerDirectly",
                    False,
                ),
                "attachToFocus": response_intent.get(
                    "attachToFocus",
                    False,
                ),
                "guidance": response_intent.get("guidance", ""),
                "askQuestion": response_intent.get("askQuestion", ""),
            },
        }

    if event_type == "response_candidate":
        return {
            "text": payload.get("text", ""),
            "eligibility": payload.get("eligibility", {}),
        }

    if event_type == "assistant_replied":
        audit = payload.get("audit", {})
        return {
            "audit": {
                "expectedQuestion": audit.get("expectedQuestion", ""),
                "questionMatch": audit.get("questionMatch"),
                "candidateEligible": audit.get("candidateEligible"),
                "findings": [
                    finding.get("code", "")
                    for finding in audit.get("findings", [])
                    if isinstance(finding, dict)
                ],
            }
        }

    if event_type in {
        "list_item_added",
        "field_set",
        "question_set",
        "question_cleared",
        "tool_requested",
        "tool_completed",
        "focus_started",
        "focus_rescoped",
        "focus_ended",
        "focus_completed",
    }:
        return payload

    return {}


def _recent_event_summary() -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []

    for event in list_events(limit=24):
        event_type = event.type.value
        compact_payload = _compact_recent_event_payload(
            event_type,
            event.payload,
        )

        if not compact_payload and event_type not in {
            "question_cleared",
        }:
            continue

        summary.append(
            {
                "type": event_type,
                "payload": compact_payload,
                "createdAt": event.createdAt,
            }
        )

    return summary[-16:]


def _planner_input(message: str, state: FocusState, source: str) -> str:
    payload = {
        "source": source,
        "userMessage": message,
        "activeFocus": state.model_dump(mode="json"),
        "recentFocusEvents": _recent_event_summary(),
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)


_CALENDAR_FOCUS_RELEVANCE_PATTERN = re.compile(
    r"\b(?:calendar|meeting|meetings|appointment|appointments|agenda|"
    r"schedule|scheduling|interview|interviews|standup|stand-up|demo|"
    r"briefing|briefings|presentation|presentations|client call|sales call|"
    r"conference call|video call)\b",
    re.IGNORECASE,
)


def _calendar_view_from_message(message: str) -> str:
    normalized = " ".join(message.split()).casefold()
    if "tomorrow" in normalized:
        return "tomorrow"
    if "week" in normalized:
        return "week"
    return "today"


def _calendar_focus_is_relevant(state: FocusState) -> bool:
    if not state.focusId.strip() or state.status.value in {"inactive", "complete"}:
        return False

    durable_context = " ".join(
        [
            state.title,
            state.objective,
            state.deliverable,
            state.subject,
            state.nextAction,
            *state.tags,
            *state.requirements,
            *state.milestones,
            *state.knownFacts,
        ]
    )
    return bool(_CALENDAR_FOCUS_RELEVANCE_PATTERN.search(durable_context))



def _normalize_memory_mutation_plan(
    plan: TurnPlan,
    *,
    source: str,
    message: str,
) -> TurnPlan:
    """Normalize Notes and Tasks mutations as protected route-only markers."""

    if source != "command-interpret-shadow":
        return plan

    mutation = memory_mutation_intent(message)
    if mutation is None:
        return plan

    arguments = [
        ToolArgument(key="operation", value=mutation.operation),
    ]
    if mutation.payload:
        arguments.append(ToolArgument(key="value", value=mutation.payload))

    return plan.model_copy(
        update={
            "route": TurnRoute.TOOL,
            "focusOperations": [],
            "toolCalls": [
                PlannedToolCall(
                    tool=ToolName.MEMORY_WRITE,
                    arguments=arguments,
                    reason=(
                        "Mark a protected Notes or Tasks mutation for the "
                        "existing deterministic frontend handler."
                    ),
                    requiresConfirmation=False,
                    attachToFocus=False,
                )
            ],
            "responseIntent": ResponseIntent(
                answerDirectly=False,
                attachToFocus=False,
            ),
            "confidence": max(plan.confidence, 0.99),
            "reason": (
                "Notes or Tasks mutation normalized as a protected route-only "
                "tool; Focus does not execute or narrate the mutation."
            ),
        }
    )


def _normalize_memory_read_plan(
    plan: TurnPlan,
    *,
    source: str,
    message: str,
) -> TurnPlan:
    """Normalize read-only Notes and Tasks summaries as route-only tools."""

    if source != "command-interpret-shadow":
        return plan

    read_intent = memory_read_intent(message)
    if read_intent is None:
        return plan

    tool = (
        ToolName.NOTES_READ
        if read_intent.surface == "notes"
        else ToolName.TASKS_READ
    )
    return plan.model_copy(
        update={
            "route": TurnRoute.TOOL,
            "focusOperations": [],
            "toolCalls": [
                PlannedToolCall(
                    tool=tool,
                    arguments=[
                        ToolArgument(key="surface", value=read_intent.surface),
                    ],
                    reason=(
                        "Read synchronized Notes or Tasks through the existing "
                        "deterministic frontend command."
                    ),
                    requiresConfirmation=False,
                    attachToFocus=False,
                )
            ],
            "responseIntent": ResponseIntent(
                answerDirectly=False,
                attachToFocus=False,
            ),
            "confidence": max(plan.confidence, 0.99),
            "reason": (
                "Notes or Tasks read normalized as a safe route-only tool "
                "with no memory mutation."
            ),
        }
    )


def _normalize_visual_mutation_plan(
    plan: TurnPlan,
    *,
    source: str,
    message: str,
) -> TurnPlan:
    """Normalize protected visual-memory mutations as route-only markers.

    The existing frontend handler owns the actual delete or clear operation.
    This marker prevents the planner from producing a chat answer or a durable
    Focus mutation, while avoiding an orphan backend tool request.
    """

    if source != "command-interpret-shadow":
        return plan

    mutation = visual_mutation_intent(message)
    if mutation is None:
        return plan

    return plan.model_copy(
        update={
            "route": TurnRoute.TOOL,
            "focusOperations": [],
            "toolCalls": [
                PlannedToolCall(
                    tool=ToolName.VISUAL_WRITE,
                    arguments=[
                        ToolArgument(key="operation", value=mutation.operation),
                    ],
                    reason=(
                        "Mark a protected visual-memory mutation for the "
                        "existing deterministic frontend handler."
                    ),
                    requiresConfirmation=False,
                    attachToFocus=False,
                )
            ],
            "responseIntent": ResponseIntent(
                answerDirectly=False,
                attachToFocus=False,
            ),
            "confidence": max(plan.confidence, 0.99),
            "reason": (
                "Visual-memory mutation normalized as a protected route-only "
                "tool; Focus does not execute or narrate the mutation."
            ),
        }
    )


def _normalize_visual_read_plan(
    plan: TurnPlan,
    *,
    source: str,
    message: str,
) -> TurnPlan:
    """Normalize saved visual-context reads as safe route-only tools.

    The frontend already owns the deterministic readout from synchronized local
    visual memory. This plan exists only so guarded routing can independently
    agree with the legacy command class. It must not capture an image, mutate
    visual memory, attach to the durable Focus, or create a pending tool action.
    """

    if source != "command-interpret-shadow":
        return plan

    read_intent = visual_read_intent(message)
    if read_intent is None:
        return plan

    return plan.model_copy(
        update={
            "route": TurnRoute.TOOL,
            "focusOperations": [],
            "toolCalls": [
                PlannedToolCall(
                    tool=ToolName.VISUAL_READ,
                    arguments=[
                        ToolArgument(key="mode", value=read_intent.mode),
                    ],
                    reason=(
                        "Read already-saved visual context through the "
                        "existing deterministic frontend command."
                    ),
                    requiresConfirmation=False,
                    attachToFocus=False,
                )
            ],
            "responseIntent": ResponseIntent(
                answerDirectly=False,
                attachToFocus=False,
            ),
            "confidence": max(plan.confidence, 0.99),
            "reason": (
                "Saved visual-context read normalized as a safe route-only "
                "tool with no visual-memory mutation."
            ),
        }
    )

def _normalize_calendar_write_plan(
    plan: TurnPlan,
    *,
    source: str,
    message: str,
) -> TurnPlan:
    """Keep Calendar writes transient and confirmation-gated.

    Natural Calendar-create wording can otherwise be mistaken for
    calendar_read and attached to a meeting Focus, leaving that Focus waiting
    for a read result that will never arrive. The frontend remains authoritative
    for confirmation and execution of the real write.
    """

    if source != "command-interpret-shadow":
        return plan

    write_intent = calendar_write_intent(message)
    if write_intent is None:
        return plan

    return plan.model_copy(
        update={
            "route": TurnRoute.TOOL,
            "focusOperations": [],
            "toolCalls": [
                PlannedToolCall(
                    tool=ToolName.CALENDAR_WRITE,
                    arguments=[
                        ToolArgument(key="day", value=write_intent.day),
                        ToolArgument(key="time", value=write_intent.time),
                        ToolArgument(key="title", value=write_intent.title),
                    ],
                    reason=(
                        "Record the Calendar write request while preserving "
                        "the frontend confirmation gate."
                    ),
                    requiresConfirmation=True,
                    attachToFocus=False,
                )
            ],
            "responseIntent": ResponseIntent(
                answerDirectly=False,
                attachToFocus=False,
            ),
            "confidence": max(plan.confidence, 0.99),
            "reason": (
                "Calendar write intent normalized as confirmation-gated and "
                "transient; no Calendar read was requested."
            ),
        }
    )


def _normalize_calendar_read_plan(
    plan: TurnPlan,
    *,
    state: FocusState,
    source: str,
    message: str,
) -> TurnPlan:
    """Deterministically record Calendar reads and repair Focus attachment.

    The endpoint itself is already executing a Calendar read. The planner may
    describe that read imperfectly, but the event log must still contain one
    calendar_read tool request. Attachment is repaired from durable Focus
    context so a meeting-preparation Focus cannot silently fall back merely
    because the model omitted attachToFocus.
    """

    plan = _normalize_memory_mutation_plan(
        plan,
        source=source,
        message=message,
    )
    plan = _normalize_memory_read_plan(
        plan,
        source=source,
        message=message,
    )
    plan = _normalize_visual_mutation_plan(
        plan,
        source=source,
        message=message,
    )
    plan = _normalize_visual_read_plan(
        plan,
        source=source,
        message=message,
    )
    plan = _normalize_calendar_write_plan(
        plan,
        source=source,
        message=message,
    )
    if source != "calendar-read-shadow":
        return plan

    should_attach = _calendar_focus_is_relevant(state)
    view = _calendar_view_from_message(message)
    normalized_calls: list[PlannedToolCall] = []
    found_calendar_read = False

    for tool_call in plan.toolCalls:
        if tool_call.tool != ToolName.CALENDAR_READ:
            normalized_calls.append(tool_call)
            continue

        if found_calendar_read:
            continue
        found_calendar_read = True
        normalized_calls.append(
            tool_call.model_copy(
                update={
                    "arguments": [ToolArgument(key="view", value=view)],
                    "requiresConfirmation": False,
                    "attachToFocus": should_attach,
                }
            )
        )

    if not found_calendar_read:
        normalized_calls.append(
            PlannedToolCall(
                tool=ToolName.CALENDAR_READ,
                arguments=[ToolArgument(key="view", value=view)],
                reason="Record the verified Calendar read already being executed.",
                requiresConfirmation=False,
                attachToFocus=should_attach,
            )
        )

    return plan.model_copy(
        update={
            "route": TurnRoute.TOOL,
            "toolCalls": normalized_calls,
        }
    )


def _fallback_plan(message: str, state: FocusState, reason: str) -> TurnPlan:
    """Safe fallback that does not recreate the old phrase-matching system."""
    stripped = " ".join(message.split()).strip()

    if not stripped:
        return TurnPlan(
            route=TurnRoute.NOOP,
            confidence=0.0,
            reason=reason,
        )

    return TurnPlan(
        route=TurnRoute.RESPOND,
        responseIntent=ResponseIntent(answerDirectly=True),
        confidence=0.15,
        reason=reason,
    )


async def preview_turn_plan(
    message: str,
    *,
    source: str = "manual-preview",
) -> TurnPlan:
    seed_from_legacy(load_legacy_focus_seed())
    state = get_state()

    if not planner_enabled() or AsyncOpenAI is None:
        return _normalize_calendar_read_plan(
            _fallback_plan(
                message,
                state,
                "Focus planner is unavailable; no semantic state was guessed.",
            ),
            state=state,
            source=source,
            message=message,
        )

    client = AsyncOpenAI()
    planner_input = _planner_input(message, state, source)

    try:
        parsed = await _parse_plan(
            client,
            [
                {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": planner_input},
            ],
        )
    except Exception as exc:
        LOGGER.exception("Focus planner failed")
        return _normalize_calendar_read_plan(
            _fallback_plan(
                message,
                state,
                f"Focus planner failed safely: {type(exc).__name__}.",
            ),
            state=state,
            source=source,
            message=message,
        )

    question_errors = _plan_question_errors(parsed)
    if not question_errors:
        return _normalize_calendar_read_plan(
            parsed,
            state=state,
            source=source,
            message=message,
        )

    LOGGER.warning(
        "Focus planner produced a non-atomic follow-up; requesting repair: %s",
        "; ".join(question_errors),
    )

    try:
        repaired = await _repair_non_atomic_plan(
            client,
            planner_input=planner_input,
            original_plan=parsed,
            errors=question_errors,
        )
    except Exception:
        LOGGER.exception("Focus planner question repair failed")
        return _normalize_calendar_read_plan(
            _strip_invalid_follow_up(parsed, question_errors),
            state=state,
            source=source,
            message=message,
        )

    repaired_errors = _plan_question_errors(repaired)
    if repaired_errors:
        return _normalize_calendar_read_plan(
            _strip_invalid_follow_up(repaired, repaired_errors),
            state=state,
            source=source,
            message=message,
        )

    return _normalize_calendar_read_plan(
        repaired,
        state=state,
        source=source,
        message=message,
    )


async def observe_turn(
    request: ObserveTurnRequest,
    *,
    turn_id: str | None = None,
) -> tuple[TurnPlan, FocusState]:
    effective_turn_id = turn_id or f"focus-turn-{uuid4().hex}"
    seed_from_legacy(load_legacy_focus_seed())

    if has_turn(effective_turn_id):
        return (
            TurnPlan(
                route=TurnRoute.NOOP,
                confidence=1.0,
                reason="This turn was already recorded.",
            ),
            get_state(),
        )

    plan = await preview_turn_plan(request.message, source=request.source)

    if request.apply:
        state = apply_turn_plan(
            plan,
            message=request.message,
            turn_id=effective_turn_id,
            source=request.source,
        )
    else:
        state = get_state()

    return plan, state
