from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import uuid4

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - startup remains available in mock mode.
    AsyncOpenAI = None  # type: ignore[assignment]

from app.focus.legacy import load_legacy_focus_seed
from app.focus.models import (
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

6. Ask at most one useful follow-up. Do not ask a question when enough context
   exists to help directly.

7. Current prices, availability, links, schedules, news, and source research
   require a Search tool call. Never fabricate tool results or claim a tool has
   completed.

8. A tool request creates a pending action. Tool completion will arrive later as
   a separate event from deterministic code.

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

Tool names available in this first slice:

- search
- open_search
- start_focus
- end_focus
- save_focus_summary

The system is currently in shadow mode. Your plan is logged and reduced into a
separate Focus state, but the legacy QMeet path still controls the visible UI.
""".strip()


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

    try:
        completion = await client.chat.completions.parse(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": _planner_input(message, state, source)},
            ],
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
    except Exception as exc:
        LOGGER.exception("Focus planner failed")
        return _fallback_plan(
            message,
            state,
            f"Focus planner failed safely: {type(exc).__name__}.",
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
