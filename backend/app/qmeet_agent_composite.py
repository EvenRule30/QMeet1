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

from pydantic import BaseModel, ConfigDict, Field

from app.qmeet_agent_shadow import AgentShadowRequest
from app.qmeet_capabilities import (
    ACTION_VOCABULARY_VERSION,
    CANONICAL_TOOL_ACTIONS_BY_OWNER,
    GLOBAL_CAPABILITY_CONTRACT,
)
from app.tool_continuation import active_focus_snapshot


CompositeOwner = Literal[
    "calendar",
    "search",
    "memory",
    "tasks",
    "notes",
    "device_ui",
]

COMPOSITE_PLAN_SCHEMA_VERSION = "phase21g1-v1"
DEFAULT_MODEL = (
    os.getenv("OPENAI_AGENT_MODEL")
    or os.getenv("OPENAI_COMMAND_MODEL")
    or os.getenv("OPENAI_MODEL")
    or "gpt-4.1-mini"
)

# G1 is observational only. Keep the planner restricted to capabilities whose
# single-intent execution paths are already promoted and deterministically
# validated. Focus remains intentionally excluded from this first composite
# contract because Focus ownership/context has additional canonical semantics.
COMPOSITE_ATOMIC_ACTIONS_BY_OWNER: dict[str, frozenset[str]] = {
    "calendar": frozenset(
        {
            "add-calendar-event",
            "read-calendar",
            "edit-last-event",
            "delete-calendar-event",
        }
    ),
    "search": frozenset({"run-search"}),
    "memory": frozenset({"read-memory"}),
    "tasks": frozenset(
        {
            "remember-task",
            "read-memory",
            "mark-task-done",
            "delete-task",
        }
    ),
    "notes": frozenset({"save-note", "read-notes"}),
    "device_ui": frozenset(CANONICAL_TOOL_ACTIONS_BY_OWNER.get("device_ui", ())),
}

_FORBIDDEN_IDENTITY_KEY_RE = re.compile(
    r"(?:^|_)(?:id|eventid|event_id|taskid|task_id|focusid|focus_id)$",
    re.IGNORECASE,
)

COMPOSITE_PLAN_SYSTEM_PROMPT = """
You are QMeet's Phase 21G1 composite-intent planner.

You are OBSERVATIONAL ONLY. You never execute tools, mutate state, confirm an
action, or claim that anything changed.

Your job is narrow: determine whether the current user turn explicitly requests
two to four separate QMeet capability actions that should be handled as ordered
atomic steps.

Important:
- Do not turn one action with several descriptive clauses into multiple steps.
- Do not invent helpful follow-up actions the user did not ask for.
- Do not create a task, note, Calendar event, Focus, or Search just because it
  might be useful.
- Each step must use one exact canonical action from compositeAtomicActions.
- Never propose canonical object identity. No event id, task id, Focus id, or
  other backend identity may appear in step arguments.
- Calendar/task target arguments are semantic lookup criteria only. Existing
  deterministic capability code must later resolve real identities.
- Preserve the user's requested order.
- dependsOn is ONLY for a real verified-output/data dependency: use it when a
  later step cannot have its final executable arguments determined from the
  original user turn alone and therefore needs verified output from an earlier
  step.
- Do NOT add dependsOn merely because two actions discuss the same subject, the
  user says "and" or "then", or it would be preferable for one action to happen
  first.
- If the user explicitly supplies all arguments for a later action, that step is
  dependency-free even when it is thematically related to an earlier step.
- Example: "search for Framework Laptop reviews and add a task called Compare
  Framework options" has two dependency-free steps because the task title is
  already explicit in the original turn.
- Example: "search Framework reviews and save a note with the result" has a real
  dependency because the note content requires the verified Search output.
- This contract does not create a transaction. Every future step must still pass
  its capability-specific validator, existing confirmation policy, canonical
  execution path, and verified receipt before a dependent step may proceed.
- Active Focus is context, not universal ownership. Do not add a Focus step just
  because a Focus exists.

Examples:
- "Move my 3 PM meeting Friday to Saturday and make a task called Prepare for
  the meeting" is composite with two dependency-free steps because both final
  actions are fully specified by the original turn. Calendar confirmation may
  still block live promotion in later execution phases.
- "Rename my 4 PM Project Review August 29 to Final Project Review" is one
  Calendar edit, not composite.
- "Search Framework reviews and save a note with the result" is composite only
  if the user explicitly asked for both Search and Notes. The note step depends
  on Search because its content depends on the search result.
- "Schedule my day" is not permission to invent several Calendar events.

Return compact JSON only:
{
  "isComposite": boolean,
  "steps": [
    {
      "turnOwner": one allowed owner,
      "focusRelevant": boolean,
      "proposedCapability": same owner string,
      "proposedAction": one exact allowed action,
      "proposedArguments": object with semantic arguments only,
      "dependsOn": zero or more earlier 1-based step numbers,
      "reason": short sentence
    }
  ],
  "responsePlan": short sentence,
  "confidence": number from 0 to 1,
  "reason": short sentence
}

If the request is not clearly composite, return isComposite=false and steps=[].
""".strip()


class AgentCompositeStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stepId: str
    turnOwner: CompositeOwner
    focusRelevant: bool = False
    disposition: Literal["tool"] = "tool"
    proposedCapability: str
    proposedAction: str
    proposedArguments: dict[str, Any] = Field(default_factory=dict)
    dependsOn: list[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(default="", max_length=500)


class AgentCompositePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isComposite: bool
    steps: list[AgentCompositeStep] = Field(default_factory=list, max_length=4)
    executionPolicy: Literal["sequential-verified"] = "sequential-verified"
    confirmationPolicy: Literal[
        "preserve-existing-capability-gates"
    ] = "preserve-existing-capability-gates"
    failurePolicy: Literal[
        "stop-before-dependent-step"
    ] = "stop-before-dependent-step"
    responsePlan: str = Field(default="", max_length=1000)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=1000)


class AgentCompositePlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    mode: Literal["shadow"] = "shadow"
    schemaVersion: str = COMPOSITE_PLAN_SCHEMA_VERSION
    actionVocabularyVersion: str = ACTION_VOCABULARY_VERSION
    planId: str
    plan: AgentCompositePlan


def _is_openai_enabled() -> bool:
    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    return provider in {"openai", "openai-compatible", "openai_compatible"}


def _json_object_from_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.I).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.S)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _contains_forbidden_identity(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).replace("-", "_")
            if _FORBIDDEN_IDENTITY_KEY_RE.search(normalized_key):
                return True
            if _contains_forbidden_identity(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_identity(item) for item in value)
    return False


def _validated_owner(value: Any) -> CompositeOwner | None:
    owner = str(value or "").strip().lower()
    return owner if owner in COMPOSITE_ATOMIC_ACTIONS_BY_OWNER else None  # type: ignore[return-value]


def _validated_action(owner: CompositeOwner, value: Any) -> str | None:
    action = str(value or "").strip()
    if not action:
        return None
    allowed = COMPOSITE_ATOMIC_ACTIONS_BY_OWNER.get(owner, frozenset())
    return action if action in allowed else None


def _normalize_dependency_numbers(
    raw_dependencies: Any,
    *,
    step_number: int,
) -> list[str] | None:
    if raw_dependencies is None:
        return []
    if not isinstance(raw_dependencies, list):
        return None

    normalized: list[str] = []
    for raw in raw_dependencies:
        try:
            dependency_number = int(raw)
        except (TypeError, ValueError):
            return None
        if dependency_number < 1 or dependency_number >= step_number:
            return None
        dependency_id = f"step-{dependency_number}"
        if dependency_id not in normalized:
            normalized.append(dependency_id)
    return normalized


def _invalid_plan(reason: str) -> AgentCompositePlan:
    return AgentCompositePlan(
        isComposite=False,
        steps=[],
        responsePlan="Use the existing single-intent routing path.",
        confidence=0.0,
        reason=reason,
    )


def sanitize_composite_plan(value: dict[str, Any] | None) -> AgentCompositePlan:
    """Validate a model-produced composite plan without granting execution authority."""

    if not isinstance(value, dict) or value.get("isComposite") is not True:
        return _invalid_plan("No validated composite plan was proposed.")

    raw_steps = value.get("steps")
    if not isinstance(raw_steps, list) or not 2 <= len(raw_steps) <= 4:
        return _invalid_plan(
            "Composite planning requires two to four validated atomic steps."
        )

    steps: list[AgentCompositeStep] = []
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            return _invalid_plan("A composite step was not a typed object.")

        owner = _validated_owner(raw_step.get("turnOwner"))
        if owner is None:
            return _invalid_plan(
                "A composite step used an owner outside the G1 allowlist."
            )

        action = _validated_action(owner, raw_step.get("proposedAction"))
        if action is None:
            return _invalid_plan(
                "A composite step used a non-canonical or unpromoted action."
            )

        proposed_capability = str(
            raw_step.get("proposedCapability") or ""
        ).strip().lower()
        if proposed_capability != owner:
            return _invalid_plan(
                "A composite step capability did not match its owner."
            )

        arguments = raw_step.get("proposedArguments")
        if not isinstance(arguments, dict) or _contains_forbidden_identity(arguments):
            return _invalid_plan(
                "A composite step contained invalid arguments or canonical identity."
            )

        dependencies = _normalize_dependency_numbers(
            raw_step.get("dependsOn"),
            step_number=index,
        )
        if dependencies is None:
            return _invalid_plan(
                "A composite dependency must reference an earlier step only."
            )

        steps.append(
            AgentCompositeStep(
                stepId=f"step-{index}",
                turnOwner=owner,
                focusRelevant=bool(raw_step.get("focusRelevant", False)),
                proposedCapability=owner,
                proposedAction=action,
                proposedArguments=dict(arguments),
                dependsOn=dependencies,
                reason=str(raw_step.get("reason") or "").strip()[:500],
            )
        )

    try:
        confidence = float(value.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    return AgentCompositePlan(
        isComposite=True,
        steps=steps,
        responsePlan=str(value.get("responsePlan") or "").strip()[:1000],
        confidence=confidence,
        reason=str(value.get("reason") or "").strip()[:1000],
    )


def _model_payload(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "userMessage": request.userMessage,
        "recentConversation": [
            item.model_dump() for item in request.recentConversation[-10:]
        ],
        "uiState": request.uiState,
        "clientContext": request.clientContext,
        "canonicalActiveFocus": focus,
        "capabilityContract": GLOBAL_CAPABILITY_CONTRACT,
        "compositeAtomicActions": {
            owner: sorted(actions)
            for owner, actions in COMPOSITE_ATOMIC_ACTIONS_BY_OWNER.items()
        },
    }


async def _generate_model_plan(
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
) -> AgentCompositePlan | None:
    if (
        not _is_openai_enabled()
        or not os.getenv("OPENAI_API_KEY")
        or AsyncOpenAI is None
    ):
        return None

    try:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            temperature=0.0,
            max_tokens=900,
            messages=[
                {"role": "system", "content": COMPOSITE_PLAN_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        _model_payload(request, focus),
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content if response.choices else ""
        parsed = _json_object_from_text(content or "")
        if parsed is None:
            return None
        return sanitize_composite_plan(parsed)
    except Exception:
        return None


def _telemetry_path() -> Path:
    configured = os.getenv("QMEET_AGENT_COMPOSITE_LOG", "").strip()
    if configured:
        return Path(configured)
    return (
        Path(__file__).resolve().parents[1]
        / "data"
        / "qmeet_agent_composite.jsonl"
    )


def _append_telemetry(
    *,
    plan_id: str,
    request: AgentShadowRequest,
    focus: dict[str, Any] | None,
    plan: AgentCompositePlan,
) -> None:
    path = _telemetry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recordType": "composite-plan",
        "schemaVersion": COMPOSITE_PLAN_SCHEMA_VERSION,
        "actionVocabularyVersion": ACTION_VOCABULARY_VERSION,
        "mode": "shadow",
        "planId": plan_id,
        "userMessage": request.userMessage,
        "activeFocusId": (focus or {}).get("focusId"),
        "activeFocusTitle": (focus or {}).get("title"),
        "plan": plan.model_dump(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


async def plan_agent_composite(
    request: AgentShadowRequest,
) -> AgentCompositePlanResponse:
    """Produce an observational multi-intent plan; never execute its steps."""

    focus = active_focus_snapshot()
    plan = await _generate_model_plan(request, focus)
    if plan is None:
        plan = _invalid_plan(
            "Composite planning was unavailable or did not return a valid plan."
        )

    plan_id = f"composite-{uuid4().hex}"
    _append_telemetry(
        plan_id=plan_id,
        request=request,
        focus=focus,
        plan=plan,
    )
    return AgentCompositePlanResponse(
        planId=plan_id,
        plan=plan,
    )
