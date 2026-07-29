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
class MemoryReadIntent:
    surface: str
    action: str
    frontend_command: str


@dataclass(frozen=True)
class FocusReadIntent:
    mode: str
    action: str
    frontend_command: str
    timeframe: str = ""


@dataclass(frozen=True)
class MemoryMutationIntent:
    action: str
    frontend_command: str
    operation: str
    payload: str = ""


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




def focus_read_intent(message: str) -> FocusReadIntent | None:
    """Recognize read-only Focus recall and local activity recap commands.

    These routes read synchronized Focus memory through existing frontend
    handlers. They never start, resume, update, summarize-save, or end a Focus.
    """

    text = _normalize_message(message)
    if not text:
        return None

    current_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:what(?:'s|\s+is)\s+"
            r"(?:the\s+|my\s+|our\s+)?(?:current\s+|active\s+)?"
            r"(?:focus|focus\s+session|active\s+session)|"
            r"what\s+(?:am\s+i|are\s+we)\s+focused\s+on"
            r"(?:\s+right\s+now)?|"
            r"(?:read|show|display|summarize)(?:\s+me)?\s+"
            r"(?:the\s+|my\s+|our\s+)?(?:current\s+|active\s+)?"
            r"(?:focus|focus\s+session|active\s+session)|"
            r"tell\s+me\s+what\s+(?:the\s+|my\s+|our\s+)?"
            r"(?:current\s+|active\s+)?(?:focus|focus\s+session)\s+is)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:focus\s+status|current\s+focus|"
            r"active\s+focus|my\s+focus|our\s+focus|active\s+session|"
            r"session\s+status)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in current_patterns):
        return FocusReadIntent(
            mode="current",
            action="read_focus_session",
            frontend_command="what am I focused on",
        )

    last_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:what\s+was|what\s+were|"
            r"(?:show|read|display)(?:\s+me)?|tell\s+me\s+about)\s+"
            r"(?:my\s+|our\s+)?"
            r"(?:last|latest|previous|most\s+recent)\s+"
            r"(?:focus|focus\s+session|session)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:what\s+did\s+(?:i|we)\s+focus\s+on\s+last|"
            r"what\s+was\s+(?:i|we)\s+focused\s+on\s+last|"
            r"what\s+was\s+(?:i|we)\s+working\s+on\s+"
            r"(?:earlier|before|previously|last))$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:last|latest|previous|most\s+recent)\s+"
            r"(?:focus|focus\s+session|session)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in last_patterns):
        return FocusReadIntent(
            mode="last",
            action="read_last_focus_session",
            frontend_command="what was my last focus",
        )

    history_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:show|list|read|display|open)\s+"
            r"(?:my\s+|our\s+)?(?:recent\s+)?(?:focus\s+)?"
            r"(?:history|sessions|focus\s+sessions)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:show|list|read|display|open)\s+"
            r"(?:my\s+|our\s+)?recent\s+"
            r"(?:focuses|focus\s+sessions|sessions)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:what\s+(?:are|were)\s+)?"
            r"(?:my\s+|our\s+)?recent\s+"
            r"(?:focuses|focus\s+sessions|sessions)(?:\s+again)?$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:focus|session)\s+history$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in history_patterns):
        return FocusReadIntent(
            mode="history",
            action="read_focus_history",
            frontend_command="show recent focus sessions",
        )

    recap_patterns: list[tuple[re.Pattern[str], str, str]] = [
        (
            re.compile(
                rf"^{_POLITE_PREFIX}(?:summarize|recap|review)\s+"
                r"(?:what\s+)?(?:i|we)\s+"
                r"(?:worked\s+on|focused\s+on|did|accomplished)\s+today$",
                re.IGNORECASE,
            ),
            "today",
            "summarize what I worked on today",
        ),
        (
            re.compile(
                rf"^{_POLITE_PREFIX}(?:what\s+did|what\s+have)\s+"
                r"(?:i|we)\s+(?:work\s+on|focus\s+on|do|accomplish)\s+today$",
                re.IGNORECASE,
            ),
            "today",
            "summarize what I worked on today",
        ),
        (
            re.compile(
                rf"^{_POLITE_PREFIX}(?:today(?:'s)?\s+)?"
                r"(?:focus|work|activity)\s+(?:recap|summary|review)$",
                re.IGNORECASE,
            ),
            "today",
            "today focus recap",
        ),
        (
            re.compile(
                rf"^{_POLITE_PREFIX}(?:summarize|recap|review)\s+"
                r"(?:what\s+)?(?:i|we)\s+"
                r"(?:worked\s+on|focused\s+on|did|accomplished)\s+yesterday$",
                re.IGNORECASE,
            ),
            "yesterday",
            "summarize what I worked on yesterday",
        ),
        (
            re.compile(
                rf"^{_POLITE_PREFIX}(?:what\s+did|what\s+have)\s+"
                r"(?:i|we)\s+(?:work\s+on|focus\s+on|do|accomplish)\s+yesterday$",
                re.IGNORECASE,
            ),
            "yesterday",
            "summarize what I worked on yesterday",
        ),
        (
            re.compile(
                rf"^{_POLITE_PREFIX}(?:yesterday(?:'s)?\s+)?"
                r"(?:focus|work|activity)\s+(?:recap|summary|review)$",
                re.IGNORECASE,
            ),
            "yesterday",
            "yesterday focus recap",
        ),
        (
            re.compile(
                rf"^{_POLITE_PREFIX}what\s+changed\s+since\s+yesterday$",
                re.IGNORECASE,
            ),
            "since-yesterday",
            "what changed since yesterday",
        ),
        (
            re.compile(
                rf"^{_POLITE_PREFIX}(?:summarize|recap|review)\s+"
                r"(?:my|our)?\s*(?:recent\s+)?"
                r"(?:focus|focuses|focus\s+sessions|work|activity)$",
                re.IGNORECASE,
            ),
            "recent",
            "recap recent focus activity",
        ),
        (
            re.compile(
                rf"^{_POLITE_PREFIX}(?:what\s+did\s+(?:i|we)\s+"
                r"focus\s+on\s+recently|(?:what\s+have|what\s+did)\s+"
                r"(?:i|we)\s+been\s+(?:working|focusing)\s+on\s+recently)$",
                re.IGNORECASE,
            ),
            "recent",
            "recap recent focus activity",
        ),
        (
            re.compile(
                rf"^{_POLITE_PREFIX}(?:daily|weekly|recent)\s+"
                r"(?:focus|work|activity)\s+(?:recap|summary|review)$",
                re.IGNORECASE,
            ),
            "recent",
            "recap recent focus activity",
        ),
    ]
    for pattern, timeframe, frontend_command in recap_patterns:
        if pattern.fullmatch(text):
            return FocusReadIntent(
                mode="recap",
                action="recap_focus_activity",
                frontend_command=frontend_command,
                timeframe=timeframe,
            )

    return None


def memory_read_intent(message: str) -> MemoryReadIntent | None:
    """Recognize read-only Notes and Tasks summaries.

    These requests use the existing synchronized frontend memory readouts. They
    never create, edit, complete, clear, or delete a note or task.
    """

    text = _normalize_message(message)
    if not text:
        return None

    notes_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:read|list|show|display|summarize|recap|review|tell\s+me)\s+"
            r"(?:me\s+)?(?:the\s+|my\s+)?(?:saved\s+|recent\s+)?notes$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:what\s+notes\s+do\s+i\s+have|"
            r"what\s+are\s+my\s+notes)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in notes_patterns):
        return MemoryReadIntent(
            surface="notes",
            action="read_notes",
            frontend_command="read my notes",
        )

    tasks_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:read|list|show|display|summarize|recap|review|tell\s+me)\s+"
            r"(?:me\s+)?(?:the\s+|my\s+)?(?:open\s+|current\s+|saved\s+)?"
            r"(?:tasks|task\s+list|to-do\s+list|todo\s+list|work\s+log)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:what\s+tasks\s+do\s+i\s+have|"
            r"what\s+are\s+my\s+tasks)$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in tasks_patterns):
        return MemoryReadIntent(
            surface="tasks",
            action="read_memory",
            frontend_command="read memory",
        )

    return None


def memory_mutation_intent(message: str) -> MemoryMutationIntent | None:
    """Recognize protected note/task mutations owned by frontend handlers."""

    text = _normalize_message(message)
    if not text:
        return None

    delete_note_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:delete|remove|erase|clear)\s+"
            r"(?:the\s+|my\s+)?(?:last|latest|newest|most\s+recent)\s+note$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in delete_note_patterns):
        return MemoryMutationIntent(
            action="delete_last_note",
            frontend_command="delete last note",
            operation="delete_last_note",
        )

    clear_notes_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:clear|delete|remove|wipe)\s+"
            r"(?:all\s+|my\s+)?notes$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in clear_notes_patterns):
        return MemoryMutationIntent(
            action="clear_notes",
            frontend_command="clear notes",
            operation="clear_notes",
        )

    save_note_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:note|remember)\s+that\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:save|add|take|write|create|make)\s+"
            r"(?:a\s+)?note(?:\s+(?:that|saying|called|about))?\s+(.+)$",
            re.IGNORECASE,
        ),
    ]
    for pattern in save_note_patterns:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        payload = _clean_payload(match.group(1))
        if payload:
            return MemoryMutationIntent(
                action="save_note",
                frontend_command=f"note that {payload}",
                operation="save_note",
                payload=payload,
            )

    delete_task_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:delete|remove|erase|clear)\s+"
            r"(?:the\s+|my\s+)?(?:last|latest|newest|most\s+recent)\s+task$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in delete_task_patterns):
        return MemoryMutationIntent(
            action="delete_last_task",
            frontend_command="delete last task",
            operation="delete_last_task",
        )

    clear_tasks_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:clear|remove|delete)\s+"
            r"(?:the\s+|my\s+)?(?:completed|done|finished)\s+tasks$",
            re.IGNORECASE,
        ),
    ]
    if any(pattern.fullmatch(text) for pattern in clear_tasks_patterns):
        return MemoryMutationIntent(
            action="clear_done_tasks",
            frontend_command="clear completed tasks",
            operation="clear_done_tasks",
        )

    complete_task_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:mark|set|complete|finish)\s+"
            r"(?:the\s+)?(?:task\s+)?(?:called|named|about)?\s*(.+?)\s+"
            r"(?:as\s+)?(?:done|complete|completed|finished)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:complete|finish)\s+"
            r"(?:the\s+)?(?:next|latest|last|current)\s+task$",
            re.IGNORECASE,
        ),
    ]
    for pattern in complete_task_patterns:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        payload = _clean_payload(match.group(1)) if match.lastindex else ""
        payload = re.sub(r"\s+task$", "", payload, flags=re.IGNORECASE).strip()
        command = f"mark task {payload} done" if payload else "complete task"
        return MemoryMutationIntent(
            action="mark_task_done",
            frontend_command=command,
            operation="complete_task",
            payload=payload,
        )

    save_task_patterns = [
        re.compile(
            rf"^{_POLITE_PREFIX}(?:remember|remind\s+me)\s+to\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^{_POLITE_PREFIX}(?:remember|save|add|create|make)\s+"
            r"(?:this\s+)?(?:as\s+)?(?:a\s+)?task\s*"
            r"(?:to|that|called|named|:)?\s+(.+)$",
            re.IGNORECASE,
        ),
    ]
    for pattern in save_task_patterns:
        match = pattern.fullmatch(text)
        if match is None:
            continue
        payload = _clean_payload(match.group(1))
        if payload:
            return MemoryMutationIntent(
                action="remember_task",
                frontend_command=f"remember to {payload}",
                operation="save_task",
                payload=payload,
            )

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


def _memory_mutation_command(message: str) -> dict[str, Any] | None:
    intent = memory_mutation_intent(message)
    if intent is None:
        return None

    payload: dict[str, str] = {"operation": intent.operation}
    if intent.payload:
        payload["value"] = intent.payload

    return {
        "intent": "command",
        "action": intent.action,
        "confidence": 0.99,
        "frontendCommand": intent.frontend_command,
        "payload": payload,
        "reason": (
            "Deterministic guarded-route bridge recognized a protected "
            "Notes or Tasks mutation owned by the existing frontend handler."
        ),
    }


def _focus_read_command(message: str) -> dict[str, Any] | None:
    intent = focus_read_intent(message)
    if intent is None:
        return None

    payload = {"mode": intent.mode}
    if intent.timeframe:
        payload["timeframe"] = intent.timeframe
    return {
        "intent": "command",
        "action": intent.action,
        "confidence": 0.99,
        "frontendCommand": intent.frontend_command,
        "payload": payload,
        "reason": (
            "Deterministic guarded-route bridge recognized a safe read of "
            "synchronized Focus memory."
        ),
    }


def _memory_read_command(message: str) -> dict[str, Any] | None:
    intent = memory_read_intent(message)
    if intent is None:
        return None

    return {
        "intent": "command",
        "action": intent.action,
        "confidence": 0.99,
        "frontendCommand": intent.frontend_command,
        "payload": {"surface": intent.surface},
        "reason": (
            "Deterministic guarded-route bridge recognized a safe read of "
            "synchronized Notes or Tasks memory."
        ),
    }


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


def _repair_specific_task_completion_payload(
    message: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Preserve a named task target when legacy routing drops its payload.

    This does not change the selected command class or execute the mutation.
    It only restores the deterministic frontend command and payload from the
    original user message before the existing confirmation gate stores it.
    """

    intent = memory_mutation_intent(message)
    if (
        intent is None
        or intent.operation != "complete_task"
        or not intent.payload
    ):
        return None

    legacy_intent = str(payload.get("intent", "")).strip().casefold()
    legacy_action = str(payload.get("action", "")).strip().casefold()
    if legacy_intent != "command" or legacy_action not in {
        "mark_task_done",
        "mark-task-done",
    }:
        return None

    raw_payload = payload.get("payload")
    legacy_payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
    legacy_value = str(legacy_payload.get("value", "")).strip()
    legacy_command = str(payload.get("frontendCommand", "")).strip()
    normalized_target = _clean_payload(intent.payload).casefold()

    target_already_preserved = (
        legacy_value.casefold() == normalized_target
        and normalized_target in legacy_command.casefold()
    )
    if target_already_preserved:
        return None

    legacy_payload.update({
        "operation": intent.operation,
        "value": intent.payload,
    })

    repaired = dict(payload)
    repaired.update({
        "intent": "command",
        "action": "mark_task_done",
        "confidence": max(
            float(payload.get("confidence", 0.0) or 0.0),
            0.99,
        ),
        "frontendCommand": intent.frontend_command,
        "payload": legacy_payload,
        "reason": (
            "Deterministic guarded-route bridge preserved the named task "
            "target for the existing confirmation-gated completion command."
        ),
    })
    return repaired


def repair_legacy_command_payload(
    message: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Repair narrow commands that the legacy model mislabeled as chat.

    Existing command route classes are never changed. A narrow protected-write
    repair may restore a task title that the legacy command already selected
    but omitted from its frontend payload. Read-only routes may enter guarded
    agreement. Calendar writes and local-memory mutations are translated into
    existing frontend command contracts; legacy/local code remains
    authoritative for their execution.
    """

    if not isinstance(payload, dict):
        return payload, False

    specific_task_repair = _repair_specific_task_completion_payload(
        message,
        payload,
    )
    if specific_task_repair is not None:
        return specific_task_repair, True

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

    memory_mutation = _memory_mutation_command(message)
    if memory_mutation is not None:
        return memory_mutation, True

    calendar_read = _calendar_read_command(message)
    if calendar_read is not None:
        return calendar_read, True

    visual_read = _visual_read_command(message)
    if visual_read is not None:
        return visual_read, True

    focus_read = _focus_read_command(message)
    if focus_read is not None:
        return focus_read, True

    memory_read = _memory_read_command(message)
    if memory_read is not None:
        return memory_read, True

    search = _search_command(message)
    if search is not None:
        return search, True

    return payload, False
