from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_POLITE_PREFIX = (
    r"(?:(?:please\s+)?(?:can|could|would|will)\s+you\s+(?:please\s+)?|"
    r"please\s+)?"
)


@dataclass(frozen=True)
class VisualReadIntent:
    mode: str
    action: str
    frontend_command: str


@dataclass(frozen=True)
class VisualMutationIntent:
    action: str
    frontend_command: str
    operation: str


@dataclass(frozen=True)
class CalendarWriteIntent:
    day: str
    time: str
    title: str

    @property
    def frontend_command(self) -> str:
        return (
            f"schedule a meeting {self.day} at {self.time} "
            f"called {self.title}"
        )


def _normalize_message(message: str) -> str:
    text = str(message or "").strip()
    text = re.sub(
        r"\b(?:a\s*\.?\s*m\.?|am)\b",
        "AM",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:p\s*\.?\s*m\.?|pm)\b",
        "PM",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[?!,;]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .")


def _clean_payload(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).strip(" .,:;?!\"'")


def _normalize_time(value: str) -> str:
    cleaned = _clean_payload(value)
    match = re.fullmatch(
        r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<period>AM|PM)?",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not match:
        return cleaned

    hour = int(match.group("hour"))
    minute = match.group("minute") or "00"
    period = (match.group("period") or "").upper()
    if period:
        return f"{hour}:{minute} {period}"
    return f"{hour}:{minute}"


def calendar_write_intent(message: str) -> CalendarWriteIntent | None:
    """Recognize conservative, fully specified Calendar-create requests."""

    text = _normalize_message(message)
    if not text:
        return None

    patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:schedule|add|create|book|make)\s+"
            r"(?:an?\s+)?(?P<title>.+?)\s+"
            r"(?P<day>today|tomorrow)\s+(?:at|for)\s+"
            r"(?P<time>(?:\d{1,2})(?::\d{2})?\s*(?:AM|PM)?|noon|midnight)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:schedule|add|create|book|make)\s+"
            r"(?:an?\s+)?(?:calendar\s+)?(?:event|appointment|meeting)\s+"
            r"(?P<day>today|tomorrow)\s+(?:at|for)\s+"
            r"(?P<time>(?:\d{1,2})(?::\d{2})?\s*(?:AM|PM)?|noon|midnight)\s+"
            r"(?:called|named|titled|for|about)\s+(?P<title>.+)$",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.fullmatch(text)
        if match is None:
            continue

        title = _clean_payload(match.group("title"))
        title = re.sub(
            r"^(?:a|an|the)\s+",
            "",
            title,
            flags=re.IGNORECASE,
        )
        day = match.group("day").casefold()
        time = _normalize_time(match.group("time"))
        if not title or day not in {"today", "tomorrow"} or not time:
            continue

        return CalendarWriteIntent(day=day, time=time, title=title)

    return None



def visual_mutation_intent(message: str) -> VisualMutationIntent | None:
    """Recognize narrow visual-memory mutations owned by legacy/local code.

    This classifier does not authorize or execute a mutation. It only repairs
    fuzzy backend interpretation so the existing frontend command handler can
    remain authoritative.
    """

    text = _normalize_message(message)
    if not text:
        return None

    delete_last_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:delete|remove|forget|erase)\s+"
            r"(?:the\s+|my\s+)?(?:last|latest|most\s+recent)\s+"
            r"(?:visual\s+)?(?:observation|visual\s+note|visual\s+memory|"
            r"camera\s+observation)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:delete|remove|forget|erase)\s+"
            r"(?:what\s+)?(?:i|we)\s+(?:just\s+)?(?:saw|looked\s+at)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in delete_last_patterns):
        return VisualMutationIntent(
            action="delete_last_visual_observation",
            frontend_command="delete last visual observation",
            operation="delete_last",
        )

    clear_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:clear|reset|wipe|forget|delete)\s+"
            r"(?:the\s+|my\s+|all\s+)?(?:visual\s+context|"
            r"visual\s+memory|visual\s+observations|camera\s+context|"
            r"camera\s+memory)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in clear_patterns):
        return VisualMutationIntent(
            action="clear_visual_context",
            frontend_command="clear visual context",
            operation="clear",
        )

    return None


def visual_read_intent(message: str) -> VisualReadIntent | None:
    """Recognize conservative read-only visual-context requests.

    These commands read already-saved visual memory. They never capture a new
    image, mutate visual context, or attach an observation to a Focus.
    """

    text = _normalize_message(message)
    if not text:
        return None

    focus_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:show|read|list|display|summarize|recap|review)\s+"
            r"(?:the\s+|my\s+|our\s+)?(?:visuals|visual\s+observations|"
            r"visual\s+context|camera\s+observations|camera\s+context)\s+"
            r"(?:for|linked\s+to|related\s+to|under|with)\s+"
            r"(?:the\s+|my\s+|our\s+|current\s+|active\s+)?"
            r"(?:focus|focus\s+session|session)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:show|read|list|summarize)?\s*"
            r"(?:focus\s+visuals|focus\s+visual\s+context|"
            r"focus\s+camera\s+context)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in focus_patterns):
        return VisualReadIntent(
            mode="focus",
            action="read_focus_visuals",
            frontend_command="show visuals for my focus",
        )

    summary_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:summarize|recap|review)\s+"
            r"(?:the\s+|my\s+|our\s+)?(?:visual\s+context|visual\s+memory|"
            r"visual\s+observations|camera\s+context|camera\s+memory)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:give\s+me\s+|make\s+me\s+|create\s+)?"
            r"(?:a\s+)?(?:visual|camera)\s+(?:summary|recap|review)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in summary_patterns):
        return VisualReadIntent(
            mode="summary",
            action="summarize_visual_context",
            frontend_command="summarize visual context",
        )

    history_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:show|read|list|display|open)\s+"
            r"(?:the\s+|my\s+|our\s+)?(?:recent\s+|saved\s+|all\s+)?"
            r"(?:visual\s+observations|visual\s+history|camera\s+observations|"
            r"camera\s+history|things\s+(?:i|we)\s+saw)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:visual\s+history|camera\s+history|"
            r"visual\s+observations)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in history_patterns):
        return VisualReadIntent(
            mode="history",
            action="read_visual_history",
            frontend_command="show visual observations",
        )

    last_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:what\s+(?:was|is)|show|read|tell\s+me|display)\s+"
            r"(?:the\s+|my\s+|our\s+)?(?:last|latest|most\s+recent)\s+"
            r"(?:visual\s+observation|visual\s+note|visual\s+memory|"
            r"camera\s+observation|camera\s+memory|thing\s+(?:i|we)\s+saw)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:what\s+(?:did|do)\s+(?:i|we)\s+"
            r"(?:last\s+)?(?:see|look\s+at)|what\s+did\s+(?:you|qmeet)\s+"
            r"last\s+see|what\s+was\s+the\s+last\s+thing\s+you\s+saw)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in last_patterns):
        return VisualReadIntent(
            mode="last",
            action="read_last_visual_observation",
            frontend_command="what was the last visual observation",
        )

    read_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:what\s+(?:was|is)|show|read|tell\s+me|"
            r"display|open)\s+(?:the\s+|my\s+|our\s+)?(?:current\s+)?"
            r"(?:visual\s+context|visual\s+memory|camera\s+context|"
            r"camera\s+memory)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:visual\s+context|visual\s+memory|"
            r"camera\s+context)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in read_patterns):
        return VisualReadIntent(
            mode="current",
            action="read_visual_context",
            frontend_command="show visual context",
        )

    return None


def _visual_mutation_command(message: str) -> dict[str, Any] | None:
    intent = visual_mutation_intent(message)
    if intent is None:
        return None

    return {
        "intent": "command",
        "action": intent.action,
        "confidence": 0.99,
        "frontendCommand": intent.frontend_command,
        "payload": {"operation": intent.operation},
        "reason": (
            "Deterministic guarded-route bridge recognized a protected "
            "visual-memory mutation owned by the existing frontend handler."
        ),
    }


def _visual_read_command(message: str) -> dict[str, Any] | None:
    intent = visual_read_intent(message)
    if intent is None:
        return None

    return {
        "intent": "command",
        "action": intent.action,
        "confidence": 0.99,
        "frontendCommand": intent.frontend_command,
        "payload": {"mode": intent.mode},
        "reason": (
            "Deterministic guarded-route bridge recognized a safe "
            "saved visual-context read request."
        ),
    }

def _calendar_read_command(message: str) -> dict[str, Any] | None:
    text = _normalize_message(message)
    if not text:
        return None

    patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:check|see|tell\s+me|show\s+me|read|list)\s+"
            r"what(?:'s|\s+is)\s+on\s+(?:my\s+)?"
            r"(?:calendar|schedule|agenda)(?:\s+for)?(?:\s+(today|tomorrow))?$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:check|read|show|list|display)\s+"
            r"(?:what\s+is\s+on\s+)?(?:my\s+)?"
            r"(?:calendar|schedule|agenda)(?:\s+for)?\s+(today|tomorrow)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}what(?:'s|\s+is)\s+on\s+(?:my\s+)?"
            r"(?:calendar|schedule|agenda)(?:\s+for)?(?:\s+(today|tomorrow))?$",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        view = (match.group(1) or "today").casefold()
        return {
            "intent": "command",
            "action": "read_calendar",
            "confidence": 0.99,
            "frontendCommand": f"what's on my calendar {view}",
            "payload": {"view": view},
            "reason": (
                "Deterministic guarded-route bridge recognized a safe "
                "Calendar read request."
            ),
        }

    return None


def _search_command(message: str) -> dict[str, Any] | None:
    text = _normalize_message(message)
    if not text:
        return None

    patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:look\s+up|search(?:\s+the\s+"
            r"(?:web|internet))?(?:\s+for)?|research)\s+(.+?)"
            r"(?:\s+for\s+me)?$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}find\s+(?:current\s+|latest\s+)?"
            r"(?:information|details|sources)\s+(?:about|on|for)\s+(.+?)"
            r"(?:\s+for\s+me)?$",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        query = _clean_payload(match.group(1))
        query = re.sub(r"^the\s+", "", query, flags=re.IGNORECASE)
        if not query:
            continue
        return {
            "intent": "command",
            "action": "prepare_search",
            "confidence": 0.99,
            "frontendCommand": f"search for {query}",
            "payload": {"query": query},
            "reason": (
                "Deterministic guarded-route bridge recognized a safe "
                "Search request."
            ),
        }

    return None


def repair_legacy_command_payload(
    message: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Repair narrow commands that the legacy model mislabeled as chat.

    Existing command decisions are never changed. Read-only routes may enter
    guarded agreement. Calendar writes and visual-memory mutations are only
    translated into existing frontend command contracts; legacy/local code
    remains authoritative for their execution.
    """

    if not isinstance(payload, dict):
        return payload, False

    intent = str(payload.get("intent", "")).strip().casefold()
    action = str(payload.get("action", "")).strip().casefold()
    if intent != "chat" or action not in {"", "none"}:
        return payload, False

    write_intent = calendar_write_intent(message)
    if write_intent is not None:
        return (
            {
                "intent": "command",
                "action": "add_calendar_event",
                "confidence": 0.99,
                "frontendCommand": write_intent.frontend_command,
                "payload": {
                    "day": write_intent.day,
                    "time": write_intent.time,
                    "title": write_intent.title,
                },
                "reason": (
                    "Deterministic guarded-route bridge recognized a "
                    "confirmation-gated Calendar write request."
                ),
            },
            True,
        )

    visual_mutation = _visual_mutation_command(message)
    if visual_mutation is not None:
        return visual_mutation, True

    calendar_read = _calendar_read_command(message)
    if calendar_read is not None:
        return calendar_read, True

    visual_read = _visual_read_command(message)
    if visual_read is not None:
        return visual_read, True

    search = _search_command(message)
    if search is not None:
        return search, True

    return payload, False
