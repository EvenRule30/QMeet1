from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

FocusContextField = Literal[
    "requirements",
    "constraints",
    "preferences",
    "decisions",
    "knownFacts",
]

_CONTEXT_REASON_PREFIX = "phase20i-context"


@dataclass(frozen=True)
class FocusContextSignal:
    field: FocusContextField
    value: str


def _clean(value: str) -> str:
    return " ".join(str(value).split()).strip().strip(" .!?;:")


def _normalized(value: str) -> str:
    return _clean(value).casefold()


def _has_explicit_lifecycle_language(message: str) -> bool:
    text = _normalized(message)
    if not text:
        return False

    if re.search(
        r"\b(?:start|begin|create|open|resume|restart|end|stop|finish|complete|"
        r"rename|retitle|replace|switch|move|change|update|set|clear|remove|make)\b"
        r".{0,65}\b(?:focus|focus session|session|goal|objective|mode)\b",
        text,
    ):
        return True
    if re.search(
        r"\b(?:focus|focus session|session|goal|objective|mode)\b.{0,55}"
        r"\b(?:to|as|into|is|should be|called|named)\b",
        text,
    ):
        return True
    if re.search(
        r"\b(?:let(?:'s| us)|lets|i want to|i need to|we should|we need to)\s+"
        r"(?:start|begin|work on|focus on|move on to|switch to)\b",
        text,
    ):
        return True
    if re.search(r"\b(?:my|our)\s+next\s+(?:focus|priority|project)\s+is\b", text):
        return True
    return False


def _preference_value(message: str) -> str:
    patterns = [
        r"^(?:i|we)\s+(?:really\s+)?(?:want|prefer|would like|would rather|like)\s+(.+)$",
        r"^(?:my|our)\s+preference\s+is\s+(.+)$",
        r"^(?:please\s+)?(?:favor|prioritize)\s+(.+)$",
    ]
    text = _clean(message)
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1))
    return ""


def _availability_value(message: str) -> str:
    text = _clean(message)
    patterns = [
        r"^(?:i|we)\s+have\s+(.+?(?:available|free|to work with))$",
        r"^(?:i am|i'm|we are|we're)\s+(?:only\s+)?available\s+(.+)$",
        r"^(?:i|we)\s+can\s+(?:spare|use|take)\s+(.+)$",
        r"^(?:the|our|my)\s+(?:available\s+)?time\s+is\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _clean(match.group(1))
            if re.search(r"\b(?:minute|hour|day|week|month|date|weekend)s?\b", value, re.I):
                return value
    if re.match(r"^(?:i|we)\s+have\s+", text, flags=re.IGNORECASE) and re.search(
        r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
        r"(?:minute|hour|day|week|month|weekend)s?\b",
        text,
        flags=re.IGNORECASE,
    ):
        return _clean(re.sub(r"^(?:i|we)\s+have\s+", "", text, flags=re.IGNORECASE))
    return ""


def _looks_like_constraint(message: str) -> bool:
    text = _normalized(message)
    if not text:
        return False
    return bool(
        re.search(
            r"\b(?:under|below|within|at most|no more than|less than|maximum|max|"
            r"minimum|min|budget|cost|spend|deadline|by\s+(?:monday|tuesday|"
            r"wednesday|thursday|friday|saturday|sunday)|must not|cannot|can't|"
            r"avoid|only)\b",
            text,
        )
        or re.match(r"^(?:keep|limit|cap|stay|fit|finish|complete)\b", text)
    )


def _decision_value(message: str) -> str:
    text = _clean(message)
    patterns = [
        r"^(?:i|we)(?:'ve| have)?\s+decided\s+(?:to|on|that)?\s*(.+)$",
        r"^(?:the\s+)?decision\s+is\s+(.+)$",
        r"^(?:we will|i will|we're going to|i'm going to)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1))
    return ""


def _requirement_value(message: str) -> str:
    text = _clean(message)
    patterns = [
        r"^(?:it|this|the\s+result|the\s+plan)\s+(?:needs|has)\s+to\s+(.+)$",
        r"^(?:a|one)\s+requirement\s+is\s+(.+)$",
        r"^(?:we|i)\s+need\s+(?:it|this|the\s+result|the\s+plan)\s+to\s+(.+)$",
        r"^must\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1))
    return ""


def classify_focus_context(message: str) -> FocusContextSignal | None:
    """Classify one explicit durable Focus detail without changing lifecycle fields.

    The classifier is intentionally deterministic. It recognizes statements that
    add context to an already-active Focus and refuses messages that explicitly
    name lifecycle fields or transitions.
    """

    cleaned = _clean(message)
    if not cleaned or _has_explicit_lifecycle_language(cleaned):
        return None

    decision = _decision_value(cleaned)
    if decision:
        return FocusContextSignal("decisions", decision)

    requirement = _requirement_value(cleaned)
    if requirement:
        return FocusContextSignal("requirements", requirement)

    availability = _availability_value(cleaned)
    if availability:
        return FocusContextSignal("knownFacts", availability)

    preference = _preference_value(cleaned)
    if preference:
        return FocusContextSignal("preferences", preference)

    if _looks_like_constraint(cleaned):
        return FocusContextSignal("constraints", cleaned)

    fact_patterns = [
        r"^(?:the|our|my)\s+(?:trip|project|meeting|deadline|date|schedule|budget)\s+(?:is|has|starts|ends)\s+.+$",
        r"^(?:we|i)\s+already\s+have\s+.+$",
        r"^(?:the|our|my)\s+dates?\s+(?:are|is)\s+.+$",
    ]
    if any(re.match(pattern, cleaned, flags=re.IGNORECASE) for pattern in fact_patterns):
        return FocusContextSignal("knownFacts", cleaned)

    return None


def encode_focus_context_reason(signal: FocusContextSignal) -> str:
    return f"{_CONTEXT_REASON_PREFIX}:{signal.field}:{signal.value}"


def decode_focus_context_reason(reason: str) -> FocusContextSignal | None:
    prefix = f"{_CONTEXT_REASON_PREFIX}:"
    if not reason.startswith(prefix):
        return None
    remainder = reason[len(prefix) :]
    field, separator, value = remainder.partition(":")
    if not separator or field not in {
        "requirements",
        "constraints",
        "preferences",
        "decisions",
        "knownFacts",
    }:
        return None
    cleaned = _clean(value)
    if not cleaned:
        return None
    return FocusContextSignal(field, cleaned)  # type: ignore[arg-type]
