from __future__ import annotations

import json
import logging
import os
import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - offline/mock startup remains available.
    AsyncOpenAI = None  # type: ignore[assignment]

from app.focus.planner import DEFAULT_MODEL, planner_enabled
from app.focus.store import get_state

LOGGER = logging.getLogger("qmeet.focus.semantic_lifecycle_preflight")

SEMANTIC_LIFECYCLE_BRIDGE_VERSION = "phase20d2a5b"
_OPEN_FOCUS_STATUSES = {"clarifying", "active", "waiting", "ready"}
_SUPPORTED_MODES = {
    "general",
    "coding",
    "meeting",
    "planning",
    "research",
    "personal",
}


class SemanticLifecycleIntent(str, Enum):
    UPDATE = "update"
    START = "start"
    NOT_LIFECYCLE = "not_lifecycle"
    CLARIFY = "clarify"
    CANCELLED = "cancelled"


class SemanticFocusLifecycleDecision(BaseModel):
    """One non-mutating semantic decision for the local Focus lifecycle."""

    model_config = ConfigDict(extra="forbid")

    intent: SemanticLifecycleIntent = SemanticLifecycleIntent.NOT_LIFECYCLE
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
    def validate_shape(self) -> "SemanticFocusLifecycleDecision":
        self.title = " ".join(self.title.split()).strip()
        self.objective = " ".join(self.objective.split()).strip()

        if self.intent == SemanticLifecycleIntent.UPDATE:
            if not self.title and not self.objectiveSpecified and self.mode is None:
                raise ValueError("An update decision must include at least one field.")
        elif self.intent == SemanticLifecycleIntent.START:
            if not self.title:
                raise ValueError("A start decision must include a Focus title.")
        else:
            self.title = ""
            self.objective = ""
            self.objectiveSpecified = False
            self.mode = None
        return self


class SemanticFocusLifecyclePreflightRequest(BaseModel):
    """Natural language that may update, start, or replace a Focus."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    sourceTurnId: str = Field(default="", max_length=120)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("message cannot be blank")
        return cleaned

    @field_validator("sourceTurnId")
    @classmethod
    def clean_source_turn_id(cls, value: str) -> str:
        return " ".join(value.split()).strip()


class SemanticFocusLifecyclePreflightResult(BaseModel):
    """Typed interpretation only; verified lifecycle services mutate state."""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    bridgeVersion: Literal["phase20d2a5b"] = SEMANTIC_LIFECYCLE_BRIDGE_VERSION
    intent: Literal["update", "start", "not_lifecycle", "clarify", "cancelled"]
    possibleMutation: bool = False
    title: str = ""
    objective: str = ""
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
    reason: str = ""
    message: str = ""
    sourceTurnId: str = ""


_SYSTEM_PROMPT = """
You are QMeet's narrow semantic authority for two local Focus lifecycle intents:

1. UPDATE the already-active Focus title/name, objective/goal, or mode.
2. START a new active Focus, replacing the current one when a different durable
   work context is clearly established.

Return exactly one strict SemanticFocusLifecycleDecision. You do not execute any
mutation and must not produce user-facing success prose.

Choose intent="update" when the user changes fields on the CURRENT Focus.
Examples:
- "rename my focus to designing a treehouse"
- "call this session treehouse planning"
- "the work I am doing should be called treehouse construction"
- "make the goal of this work choose the building materials"
- "switch this work into planning mode"

Choose intent="start" only when the user deliberately establishes a NEW durable
work context that should become the active Focus. Examples:
- "I want to spend some time designing a birdhouse"
- "let's work on planning my vacation"
- "my next priority is preparing the quarterly review"
- "switch my focus to studying for the exam"
- "I am done with this topic and want to work on the garden"
- "make building the prototype my main focus"

Important distinction:
- "call this session X" is UPDATE when a Focus is active.
- "make X my focus" or "my next priority is X" is START.
- "switch my focus to X" means START/replace, unless X is explicitly a
  supported mode and the user says mode.
- A change of title, goal, or mode is not a replacement.
- A different project or durable work objective is a replacement.
- Words such as planning, coding, research, or meeting inside a requested title
  do not change mode. Set mode only when the user explicitly asks for a mode.

Choose intent="not_lifecycle" for:
- ending, completing, or resuming a Focus
- asking what the Focus is
- asking for naming ideas, planning help, or advice
- ordinary task requests that do not establish a durable active Focus
- hypothetical questions
- general chat

Choose intent="cancelled" for an explicit negation or cancellation of a Focus
mutation, such as "don't rename my focus", "don't start a new focus", or
"cancel that Focus change". Do not add coaching or follow-up suggestions.

Choose intent="clarify" when a lifecycle mutation is intended but the operation
or requested value is missing, conflicting, or too ambiguous to execute safely.

Extraction rules:
- title contains only the requested new title or concise new Focus name.
- objectiveSpecified=true only when the user explicitly sets, changes, or clears
  a goal. Use objective="" only for an explicit clear.
- mode is one of general, coding, meeting, planning, research, or personal.
- For START, do not invent a goal from the title.
- Do not infer extra field changes.
- Confidence covers semantic interpretation only. Deterministic lifecycle code
  executes and verifies the mutation later.
""".strip()


def _current_mode(tags: list[str]) -> str:
    for raw_tag in reversed(tags):
        tag = " ".join(str(raw_tag).split()).strip().casefold()
        if not tag.startswith("mode:"):
            continue
        mode = tag.split(":", 1)[1].strip()
        if mode in _SUPPORTED_MODES:
            return mode
    return "general"


def _normalized_message(message: str) -> str:
    return " ".join(message.casefold().split()).strip()


def _explicit_lifecycle_negation(message: str) -> bool:
    """Recognize explicit cancellation without interpreting a new mutation."""

    text = _normalized_message(message)
    if not text:
        return False

    direct_negation = re.search(
        r"\b(?:don't|do not|never)\s+(?:please\s+)?"
        r"(?:start|begin|create|open|rename|retitle|change|update|switch|"
        r"replace|make|set)\b.{0,80}\b(?:focus|session|goal|objective|mode)\b",
        text,
    )
    cancellation = re.search(
        r"\b(?:cancel|ignore|discard)\s+(?:that|the|this)?\s*"
        r"(?:focus|session)?\s*(?:change|update|rename|start|replacement)\b",
        text,
    )
    return bool(direct_negation or cancellation)


def _explicit_mode_request(message: str) -> str | None:
    """Return a mode only when mode-setting language is explicit."""

    text = _normalized_message(message)
    if not text:
        return None

    mode_names = "general|coding|meeting|planning|research|personal"
    patterns = [
        rf"\b(?:set|change|update)\b.{{0,45}}\bmode\s+(?:to|as|into|=|is)\s*({mode_names})\b",
        rf"\b(?:switch|put|move|turn)\b.{{0,55}}\b(?:into|to|in)\s+({mode_names})\s+mode\b",
        rf"\b(?:make|set)\b.{{0,45}}\b({mode_names})\s+mode\b",
        rf"\b(?:use|enter)\s+({mode_names})\s+mode\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _explicit_replacement_signal(message: str) -> bool:
    """Recognize a clear new-Focus transition, not a title/mode update."""

    text = _normalized_message(message)
    if not text or _explicit_mode_request(text):
        return False

    patterns = [
        r"\b(?:switch|move|change)\s+(?:(?:my|our|the|current|active)\s+)?focus\s+(?:to|onto|over\s+to)\b",
        r"\b(?:make|set)\s+.+?\s+(?:my|our|the)\s+(?:main\s+|active\s+)?focus\b",
        r"\b(?:my|our)\s+next\s+(?:focus|priority|project)\s+is\b",
        r"\b(?:done|finished)\s+with\s+(?:this|that|it).{0,60}\b(?:work\s+on|focus\s+on|move\s+to|switch\s+to)\b",
        r"\b(?:move\s+on\s+to|switch\s+to)\s+.+",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _explicit_current_focus_update_signal(message: str) -> bool:
    """Recognize field-update language that should not replace the Focus."""

    text = _normalized_message(message)
    if not text:
        return False
    if _explicit_mode_request(text):
        return True

    title_update = re.search(
        r"\b(?:rename|retitle)\b.{0,55}\b(?:focus|session|work)\b"
        r"|\bcall\s+(?:this|the|my|our|current)\s+(?:focus|session|work)\b"
        r"|\b(?:focus|session|work)\b.{0,45}\b(?:should\s+be\s+called|is\s+now\s+called)\b",
        text,
    )
    goal_update = re.search(
        r"\b(?:set|change|update|make|clear|remove)\b.{0,50}"
        r"\b(?:goal|objective)\b",
        text,
    )
    return bool(title_update or goal_update)


def _apply_semantic_boundary_guards(
    decision: "SemanticFocusLifecycleDecision",
    message: str,
) -> "SemanticFocusLifecycleDecision":
    """Correct category boundaries without replacing semantic classification."""

    if decision.intent not in {
        SemanticLifecycleIntent.UPDATE,
        SemanticLifecycleIntent.START,
    }:
        return decision

    adjusted = decision.model_copy(deep=True)
    explicit_mode = _explicit_mode_request(message)

    # Never infer a mode merely because a title contains words such as
    # "planning" or "research". Preserve mode only for explicit mode language.
    adjusted.mode = explicit_mode

    if (
        adjusted.intent == SemanticLifecycleIntent.UPDATE
        and _explicit_replacement_signal(message)
    ):
        if not adjusted.title:
            return SemanticFocusLifecycleDecision(
                intent=SemanticLifecycleIntent.CLARIFY,
                confidence=adjusted.confidence,
                reason=(
                    "The user clearly requested a new Focus, but no safe new "
                    "Focus title was extracted."
                ),
            )
        adjusted.intent = SemanticLifecycleIntent.START
        adjusted.reason = (
            f"{adjusted.reason} " if adjusted.reason else ""
        ) + "A clear replacement phrase requires native Focus start/replacement."

    if (
        adjusted.intent == SemanticLifecycleIntent.START
        and _explicit_current_focus_update_signal(message)
        and not _explicit_replacement_signal(message)
    ):
        adjusted.intent = SemanticLifecycleIntent.UPDATE
        adjusted.reason = (
            f"{adjusted.reason} " if adjusted.reason else ""
        ) + "Explicit current-Focus field language requires an update."

    return adjusted


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


def _minimum_update_confidence() -> float:
    raw = os.getenv(
        "QMEET_SEMANTIC_FOCUS_UPDATE_MIN_CONFIDENCE",
        "0.78",
    ).strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.78
    return max(0.0, min(value, 1.0))


def _minimum_start_confidence() -> float:
    raw = os.getenv(
        "QMEET_SEMANTIC_FOCUS_START_MIN_CONFIDENCE",
        "0.82",
    ).strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.82
    return max(0.0, min(value, 1.0))


def looks_like_semantic_focus_lifecycle_mutation(message: str) -> bool:
    """Conservative safety fallback; never authorizes execution."""

    text = " ".join(message.casefold().split())
    if not text:
        return False
    if re.search(r"\b(?:don't|do not|never|cancel|stop)\b", text):
        return False

    update_reference = re.search(
        r"\b(?:focus|session|goal|objective|mode|this work|current work|"
        r"work i(?:'m| am) doing|what i(?:'m| am) working on)\b",
        text,
    )
    update_language = re.search(
        r"\b(?:rename|retitle|call|name|title|change|set|make|switch|update|"
        r"should be|now called|turn .* into)\b",
        text,
    )

    explicit_start = re.search(
        r"\b(?:start|begin|create|open|set|make|switch|change|move|turn)\b.{0,50}"
        r"\b(?:focus|focus session|active focus|main focus)\b",
        text,
    ) or re.search(
        r"\b(?:focus|focus session|active focus|main focus)\b.{0,35}"
        r"\b(?:on|to|for|into|about)\b",
        text,
    )
    durable_transition = re.search(
        r"\b(?:let(?:'s| us)|lets|i want to|i need to|we should|we need to)\s+"
        r"(?:start|begin|work on|focus on|move on to|switch to)\b",
        text,
    ) or re.search(
        r"\b(?:my|our)\s+next\s+(?:focus|priority|project)\s+is\b",
        text,
    ) or re.search(
        r"\b(?:done|finished)\s+with\s+(?:this|that|it).{0,60}"
        r"\b(?:work on|focus on|move to|switch to)\b",
        text,
    )

    return bool((update_reference and update_language) or explicit_start or durable_transition)


async def _classify_with_model(message: str) -> SemanticFocusLifecycleDecision:
    if AsyncOpenAI is None or not planner_enabled():
        raise RuntimeError("The semantic Focus lifecycle classifier is unavailable.")

    client = AsyncOpenAI()
    completion = await client.chat.completions.parse(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _classifier_input(message)},
        ],
        response_format=SemanticFocusLifecycleDecision,
        temperature=0,
    )
    parsed = completion.choices[0].message.parsed
    if not isinstance(parsed, SemanticFocusLifecycleDecision):
        refusal = completion.choices[0].message.refusal or ""
        raise ValueError(
            "Structured semantic Focus lifecycle classification was missing. "
            f"Refusal: {refusal[:200]}"
        )
    return parsed


def _normalize_decision(
    decision: SemanticFocusLifecycleDecision,
    message: str,
) -> SemanticFocusLifecycleDecision:
    decision = _apply_semantic_boundary_guards(decision, message)
    state = get_state()
    state_status = str(getattr(state.status, "value", state.status)).casefold()
    has_open_focus = bool(state.focusId) and state_status in _OPEN_FOCUS_STATUSES

    if decision.intent == SemanticLifecycleIntent.UPDATE:
        if not has_open_focus:
            return SemanticFocusLifecycleDecision(
                intent=SemanticLifecycleIntent.CLARIFY,
                confidence=decision.confidence,
                reason=(
                    "The user requested a current-Focus update, but no active "
                    "canonical Focus exists."
                ),
            )
        if decision.confidence < _minimum_update_confidence():
            return SemanticFocusLifecycleDecision(
                intent=SemanticLifecycleIntent.CLARIFY,
                confidence=decision.confidence,
                reason=(
                    "The semantic Focus update was below the configured "
                    "execution confidence threshold."
                ),
            )

    if decision.intent == SemanticLifecycleIntent.START:
        if decision.confidence < _minimum_start_confidence():
            return SemanticFocusLifecycleDecision(
                intent=SemanticLifecycleIntent.CLARIFY,
                confidence=decision.confidence,
                reason=(
                    "The semantic Focus start was below the configured "
                    "execution confidence threshold."
                ),
            )

    return decision


async def classify_semantic_focus_lifecycle(
    message: str,
) -> SemanticFocusLifecycleDecision:
    cleaned = " ".join(message.split()).strip()
    if not cleaned:
        return SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.NOT_LIFECYCLE,
            confidence=1.0,
            reason="The message was empty.",
        )

    if _explicit_lifecycle_negation(cleaned):
        return SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.CANCELLED,
            confidence=1.0,
            reason="The user explicitly cancelled or negated a Focus mutation.",
        )

    try:
        return _normalize_decision(await _classify_with_model(cleaned), cleaned)
    except Exception as exc:
        LOGGER.warning(
            "Semantic Focus lifecycle classification failed safely: %s",
            exc,
        )
        if looks_like_semantic_focus_lifecycle_mutation(cleaned):
            return SemanticFocusLifecycleDecision(
                intent=SemanticLifecycleIntent.CLARIFY,
                confidence=0.0,
                reason=(
                    "The message may request a Focus lifecycle mutation, but "
                    f"the semantic classifier failed safely: {type(exc).__name__}."
                ),
            )
        return SemanticFocusLifecycleDecision(
            intent=SemanticLifecycleIntent.NOT_LIFECYCLE,
            confidence=0.0,
            reason=(
                "The semantic Focus lifecycle classifier was unavailable and "
                "the message did not match the conservative mutation fallback."
            ),
        )


async def semantic_focus_lifecycle_preflight(
    request: SemanticFocusLifecyclePreflightRequest,
) -> SemanticFocusLifecyclePreflightResult:
    decision = await classify_semantic_focus_lifecycle(request.message)
    possible_mutation = (
        decision.intent != SemanticLifecycleIntent.NOT_LIFECYCLE
        or looks_like_semantic_focus_lifecycle_mutation(request.message)
    )

    if decision.intent in {
        SemanticLifecycleIntent.UPDATE,
        SemanticLifecycleIntent.START,
    }:
        return SemanticFocusLifecyclePreflightResult(
            intent=decision.intent.value,
            possibleMutation=True,
            title=decision.title,
            objective=decision.objective,
            objectiveSpecified=decision.objectiveSpecified,
            mode=decision.mode,
            confidence=decision.confidence,
            reason=decision.reason,
            sourceTurnId=request.sourceTurnId,
        )

    if decision.intent == SemanticLifecycleIntent.CANCELLED:
        return SemanticFocusLifecyclePreflightResult(
            intent="cancelled",
            possibleMutation=False,
            confidence=decision.confidence,
            reason=decision.reason,
            message="Okay—no Focus change was made.",
            sourceTurnId=request.sourceTurnId,
        )

    if decision.intent == SemanticLifecycleIntent.CLARIFY:
        return SemanticFocusLifecyclePreflightResult(
            intent="clarify",
            possibleMutation=True,
            confidence=decision.confidence,
            reason=decision.reason,
            message=(
                "I understood this as a possible Focus change, but I could not "
                "identify one safe update or new Focus. The Focus was not changed."
            ),
            sourceTurnId=request.sourceTurnId,
        )

    return SemanticFocusLifecyclePreflightResult(
        intent="not_lifecycle",
        possibleMutation=possible_mutation,
        confidence=decision.confidence,
        reason=decision.reason,
        sourceTurnId=request.sourceTurnId,
    )
