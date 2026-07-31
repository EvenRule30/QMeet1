from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from enum import Enum
from time import monotonic
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - mock/offline startup remains available.
    AsyncOpenAI = None  # type: ignore[assignment]

from app.focus.models import (
    FocusField,
    FocusOperation,
    FocusOperationKind,
    ResponseIntent,
    TurnPlan,
    TurnRoute,
)
from app.focus.planner import DEFAULT_MODEL, planner_enabled
from app.focus.store import get_state

LOGGER = logging.getLogger("qmeet.focus.semantic_update_intent")

BRIDGE_VERSION = "phase20d2a4c"
_OPEN_FOCUS_STATUSES = {"clarifying", "active", "waiting", "ready"}
_SUPPORTED_MODES = {
    "general",
    "coding",
    "meeting",
    "planning",
    "research",
    "personal",
}
_CACHE_TTL_SECONDS = 90.0
_MAX_CACHE_ENTRIES = 256


class SemanticUpdateIntent(str, Enum):
    UPDATE = "update"
    NOT_UPDATE = "not_update"
    CLARIFY = "clarify"


class SemanticFocusUpdateDecision(BaseModel):
    """One narrow semantic decision for the current Focus.

    This model never executes a mutation. It only decides whether the user is
    asking to change the current Focus title, objective, or mode and extracts
    those typed fields for the verified lifecycle executor.
    """

    model_config = ConfigDict(extra="forbid")

    intent: SemanticUpdateIntent = SemanticUpdateIntent.NOT_UPDATE
    title: str = Field(default="", max_length=180)
    objective: str = Field(default="", max_length=500)
    objectiveSpecified: bool = False
    mode: Literal[
        "general",
        "coding",
        "meeting",
        "planning",
        "research",
        "personal",
    ] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def validate_update_shape(self) -> "SemanticFocusUpdateDecision":
        self.title = " ".join(self.title.split()).strip()
        self.objective = " ".join(self.objective.split()).strip()

        if self.intent == SemanticUpdateIntent.UPDATE:
            if not self.title and not self.objectiveSpecified and self.mode is None:
                raise ValueError("An update decision must include at least one field.")
        else:
            self.title = ""
            self.objective = ""
            self.objectiveSpecified = False
            self.mode = None
        return self

    def has_changes(self) -> bool:
        return bool(self.title or self.objectiveSpecified or self.mode is not None)

    def command_payload(self, source_turn_id: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "semanticBridge": True,
            "semanticBridgeVersion": BRIDGE_VERSION,
            "sourceTurnId": source_turn_id.strip(),
        }
        if self.title:
            payload["title"] = self.title
        if self.objectiveSpecified:
            payload["goal"] = self.objective
        if self.mode is not None:
            payload["mode"] = self.mode
        return payload


_SYSTEM_PROMPT = """
You are QMeet's narrow semantic classifier for updates to the CURRENT Focus.
Return one strict SemanticFocusUpdateDecision. You do not execute anything and
must not write user-facing success prose.

Classify intent="update" only when the user is directing QMeet to change one or
more of these fields on the already-active Focus:
- title/name
- objective/goal, including explicitly clearing it
- mode: general, coding, meeting, planning, research, or personal

Understand ordinary natural language, pronouns, and indirect references. The
user does not need to say a magic phrase such as "rename the focus".
Examples that are updates:
- "rename my focus to designing a treehouse"
- "call this session treehouse planning"
- "the work I am doing should be called treehouse construction"
- "make the goal of this work choose the building materials"
- "switch this work into planning mode"
- "I want this to be about choosing the materials"

Return intent="not_update" for:
- starting or replacing a Focus
- ending, completing, or resuming a Focus
- asking what the Focus is
- asking for naming ideas or advice
- hypothetical questions about whether a Focus can be renamed
- negated or cancelled requests such as "don't rename my focus"
- general chat or work progress that does not direct a title/objective/mode edit

Return intent="clarify" when an update is intended but the requested new value
is missing, conflicting, or too ambiguous to execute safely.

Extraction rules:
- title is only the requested new title, without quotation marks or commentary.
- objectiveSpecified=true only when the user explicitly sets, changes, or clears
  the objective. Use objective="" only for an explicit clear/remove request.
- mode must be one of the six supported values.
- Do not infer extra changes. Preserve fields the user did not ask to change.
- Confidence describes the semantic classification, not whether execution has
  succeeded. Execution is performed and verified later by deterministic code.
""".strip()


_DECISION_TASKS: dict[str, asyncio.Task[SemanticFocusUpdateDecision]] = {}
_DECISION_RESULTS: dict[str, tuple[float, SemanticFocusUpdateDecision]] = {}
_CACHE_LOCK = asyncio.Lock()


def _current_mode(tags: list[str]) -> str:
    for raw_tag in reversed(tags):
        tag = " ".join(str(raw_tag).split()).strip().casefold()
        if not tag.startswith("mode:"):
            continue
        mode = tag.split(":", 1)[1].strip()
        if mode in _SUPPORTED_MODES:
            return mode
    return "general"


def _classifier_input(message: str) -> str:
    state = get_state()
    payload = {
        "userMessage": " ".join(message.split()).strip(),
        "activeFocus": {
            "exists": bool(state.focusId),
            "focusId": state.focusId,
            "title": state.title,
            "objective": state.objective,
            "mode": _current_mode(list(state.tags or [])),
            "status": getattr(state.status, "value", state.status),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _minimum_confidence() -> float:
    raw = os.getenv(
        "QMEET_SEMANTIC_FOCUS_UPDATE_MIN_CONFIDENCE",
        "0.78",
    ).strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.78
    return max(0.0, min(value, 1.0))


def looks_like_semantic_focus_update_request(message: str) -> bool:
    """Conservative safety fallback used only when the model is unavailable.

    This does not authorize execution. It only blocks likely mutation language
    from falling through to chat and falsely claiming success.
    """

    text = " ".join(message.casefold().split())
    if not text:
        return False
    if re.search(r"\b(?:don't|do not|never|cancel|stop)\b", text):
        return False

    focus_reference = re.search(
        r"\b(?:focus|session|goal|objective|mode|this work|current work|"
        r"work i(?:'m| am) doing|what i(?:'m| am) working on)\b",
        text,
    )
    change_language = re.search(
        r"\b(?:rename|retitle|call|name|title|change|set|make|switch|update|"
        r"should be|now called|turn .* into)\b",
        text,
    )
    return bool(focus_reference and change_language)


async def _classify_with_model(message: str) -> SemanticFocusUpdateDecision:
    if AsyncOpenAI is None or not planner_enabled():
        raise RuntimeError("The semantic Focus classifier is unavailable.")

    client = AsyncOpenAI()
    completion = await client.chat.completions.parse(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _classifier_input(message)},
        ],
        response_format=SemanticFocusUpdateDecision,
        temperature=0,
    )
    parsed = completion.choices[0].message.parsed
    if not isinstance(parsed, SemanticFocusUpdateDecision):
        refusal = completion.choices[0].message.refusal or ""
        raise ValueError(
            "Structured semantic Focus classification was missing. "
            f"Refusal: {refusal[:200]}"
        )
    return parsed


def _normalize_decision(
    decision: SemanticFocusUpdateDecision,
) -> SemanticFocusUpdateDecision:
    threshold = _minimum_confidence()
    state = get_state()

    if decision.intent == SemanticUpdateIntent.UPDATE:
        state_status = getattr(state.status, "value", state.status)
        if not state.focusId or str(state_status).casefold() not in _OPEN_FOCUS_STATUSES:
            return SemanticFocusUpdateDecision(
                intent=SemanticUpdateIntent.CLARIFY,
                confidence=decision.confidence,
                reason=(
                    "The user requested a current-Focus update, but no active "
                    "canonical Focus exists."
                ),
            )
        if decision.confidence < threshold:
            return SemanticFocusUpdateDecision(
                intent=SemanticUpdateIntent.CLARIFY,
                confidence=decision.confidence,
                reason=(
                    "The semantic Focus update was below the configured "
                    "execution confidence threshold."
                ),
            )
        if not decision.has_changes():
            return SemanticFocusUpdateDecision(
                intent=SemanticUpdateIntent.CLARIFY,
                confidence=decision.confidence,
                reason="The requested Focus update did not contain a value.",
            )

    return decision


async def classify_semantic_focus_update(
    message: str,
) -> SemanticFocusUpdateDecision:
    cleaned = " ".join(message.split()).strip()
    if not cleaned:
        return SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.NOT_UPDATE,
            confidence=1.0,
            reason="The message was empty.",
        )

    try:
        decision = await _classify_with_model(cleaned)
        return _normalize_decision(decision)
    except Exception as exc:
        LOGGER.warning(
            "Semantic Focus update classification failed safely: %s",
            exc,
        )
        if looks_like_semantic_focus_update_request(cleaned):
            return SemanticFocusUpdateDecision(
                intent=SemanticUpdateIntent.CLARIFY,
                confidence=0.0,
                reason=(
                    "The message may request a Focus update, but the semantic "
                    f"classifier failed safely: {type(exc).__name__}."
                ),
            )
        return SemanticFocusUpdateDecision(
            intent=SemanticUpdateIntent.NOT_UPDATE,
            confidence=0.0,
            reason=(
                "The semantic Focus classifier was unavailable and the message "
                "did not match the conservative mutation-safety fallback."
            ),
        )


def _cache_key(message: str, source_turn_id: str) -> str:
    turn_id = source_turn_id.strip()
    if turn_id:
        return f"turn:{turn_id}"
    state = get_state()
    return (
        "message:"
        f"{state.focusId.casefold()}:{' '.join(message.casefold().split())}"
    )


def _prune_cache(now: float) -> None:
    expired = [
        key
        for key, (stored_at, _) in _DECISION_RESULTS.items()
        if now - stored_at > _CACHE_TTL_SECONDS
    ]
    for key in expired:
        _DECISION_RESULTS.pop(key, None)

    if len(_DECISION_RESULTS) <= _MAX_CACHE_ENTRIES:
        return
    oldest = sorted(
        _DECISION_RESULTS.items(),
        key=lambda item: item[1][0],
    )[: len(_DECISION_RESULTS) - _MAX_CACHE_ENTRIES]
    for key, _ in oldest:
        _DECISION_RESULTS.pop(key, None)


async def get_semantic_focus_update_decision(
    message: str,
    *,
    source_turn_id: str = "",
) -> SemanticFocusUpdateDecision:
    """Share one semantic decision between middleware observation and routing."""

    key = _cache_key(message, source_turn_id)
    now = monotonic()

    async with _CACHE_LOCK:
        _prune_cache(now)
        cached = _DECISION_RESULTS.get(key)
        if cached is not None:
            return cached[1]

        task = _DECISION_TASKS.get(key)
        if task is None:
            task = asyncio.create_task(
                classify_semantic_focus_update(message),
                name=f"qmeet-semantic-focus-update-{key[:80]}",
            )
            _DECISION_TASKS[key] = task

    try:
        result = await asyncio.shield(task)
    finally:
        async with _CACHE_LOCK:
            if _DECISION_TASKS.get(key) is task and task.done():
                _DECISION_TASKS.pop(key, None)

    async with _CACHE_LOCK:
        _DECISION_RESULTS[key] = (monotonic(), result)
        _prune_cache(monotonic())
    return result


def semantic_update_turn_plan(
    decision: SemanticFocusUpdateDecision,
) -> TurnPlan:
    """Create a non-applying plan for telemetry and guarded route comparison."""

    operations: list[FocusOperation] = []
    if decision.intent == SemanticUpdateIntent.UPDATE:
        if decision.title:
            operations.append(
                FocusOperation(
                    kind=FocusOperationKind.SET_FIELD,
                    field=FocusField.TITLE,
                    value=decision.title,
                    confidence=decision.confidence,
                    reason="Semantic current-Focus title update.",
                )
            )
        if decision.objectiveSpecified:
            operations.append(
                FocusOperation(
                    kind=FocusOperationKind.SET_FIELD,
                    field=FocusField.OBJECTIVE,
                    value=decision.objective,
                    confidence=decision.confidence,
                    reason="Semantic current-Focus objective update.",
                )
            )
        if decision.mode is not None:
            operations.append(
                FocusOperation(
                    kind=FocusOperationKind.SET_FIELD,
                    field=FocusField.TAGS,
                    value=f"mode:{decision.mode}",
                    confidence=decision.confidence,
                    reason="Semantic current-Focus mode update.",
                )
            )

    route = (
        TurnRoute.FOCUS_ACTION
        if decision.intent == SemanticUpdateIntent.UPDATE
        else TurnRoute.CLARIFY
    )
    return TurnPlan(
        route=route,
        focusOperations=operations,
        responseIntent=ResponseIntent(
            acknowledge="",
            answerDirectly=False,
            attachToFocus=False,
            guidance="",
            askQuestion="",
        ),
        confidence=decision.confidence,
        reason=decision.reason,
    )


def clear_semantic_update_decision_cache() -> None:
    """Test/support hook; production code normally relies on TTL pruning."""

    _DECISION_RESULTS.clear()
    for task in _DECISION_TASKS.values():
        if not task.done():
            task.cancel()
    _DECISION_TASKS.clear()
