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
from app.focus.models import (
    FocusOperationKind,
    FocusState,
    ObserveTurnRequest,
    ResponseIntent,
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

7. Current prices, availability, links, schedules, news, and source research
   require a Search tool call. Never fabricate tool results or claim a tool has
   completed.

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

Tool names available in this first slice:

- search
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


def _recent_event_summary() -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []

    for event in list_events(limit=18):
        if event.type.value == "turn_planned":
            continue

        summary.append(
            {
                "type": event.type.value,
                "payload": event.payload,
                "createdAt": event.createdAt,
            }
        )

    return summary[-12:]


def _planner_input(message: str, state: FocusState, source: str) -> str:
    payload = {
        "source": source,
        "userMessage": message,
        "activeFocus": state.model_dump(mode="json"),
        "recentFocusEvents": _recent_event_summary(),
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)


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
        return _fallback_plan(
            message,
            state,
            "Focus planner is unavailable; no semantic state was guessed.",
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
        return _fallback_plan(
            message,
            state,
            f"Focus planner failed safely: {type(exc).__name__}.",
        )

    question_errors = _plan_question_errors(parsed)
    if not question_errors:
        return parsed

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
        return _strip_invalid_follow_up(parsed, question_errors)

    repaired_errors = _plan_question_errors(repaired)
    if repaired_errors:
        return _strip_invalid_follow_up(repaired, repaired_errors)

    return repaired


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
