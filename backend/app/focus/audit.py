from __future__ import annotations

import re
from typing import Any, Iterable

from app.focus.models import FocusEvent, FocusEventType

_QUESTION_PATTERN = re.compile(r"[^?]+\?")
_CALENDAR_WORD_PATTERN = re.compile(r"\bcalendar\b", re.IGNORECASE)
_CALENDAR_CLAIM_PATTERNS = (
    re.compile(r"\bcalendar\s+(?:looks|is|seems)\s+(?:open|clear|free)\b", re.IGNORECASE),
    re.compile(r"\bnothing\s+(?:is\s+)?scheduled\b", re.IGNORECASE),
    re.compile(r"\byou(?:'re| are)\s+(?:free|available)\b", re.IGNORECASE),
)
_CALENDAR_ACCESS_DENIALS = (
    "can't access your calendar",
    "cannot access your calendar",
    "do not have access to your calendar",
    "don't have access to your calendar",
    "unable to access your calendar",
)


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _normalize_question(value: str) -> str:
    cleaned = _clean_text(value).casefold().rstrip("?").strip()
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def extract_visible_questions(text: str) -> list[str]:
    questions: list[str] = []

    for match in _QUESTION_PATTERN.finditer(text):
        question = _clean_text(match.group(0))
        if question and question not in questions:
            questions.append(question)

    return questions


def _expected_question(
    events: Iterable[FocusEvent],
    source_turn_id: str,
) -> str:
    turn_events = [
        event
        for event in events
        if event.sourceTurnId == source_turn_id
    ]

    for event in reversed(turn_events):
        if event.type != FocusEventType.QUESTION_SET:
            continue
        question = _clean_text(str(event.payload.get("question", "")))
        if question:
            return question

    for event in reversed(turn_events):
        if event.type != FocusEventType.TURN_PLANNED:
            continue

        plan = event.payload.get("plan")
        if not isinstance(plan, dict):
            continue

        response_intent = plan.get("responseIntent")
        if not isinstance(response_intent, dict):
            continue

        question = _clean_text(
            str(response_intent.get("askQuestion", ""))
        )
        if question:
            return question

    return ""


def _tool_evidence(
    events: Iterable[FocusEvent],
    source_turn_id: str,
) -> list[str]:
    names: list[str] = []

    for event in events:
        if event.sourceTurnId != source_turn_id:
            continue
        if event.type not in {
            FocusEventType.TOOL_REQUESTED,
            FocusEventType.TOOL_COMPLETED,
            FocusEventType.TOOL_FAILED,
        }:
            continue

        tool = _clean_text(str(event.payload.get("tool", ""))).casefold()
        if tool and tool not in names:
            names.append(tool)

    return names


def _calendar_claim_without_evidence(
    text: str,
    tool_evidence: list[str],
) -> bool:
    lowered = _clean_text(text).casefold()
    if not _CALENDAR_WORD_PATTERN.search(text):
        return False
    if any(denial in lowered for denial in _CALENDAR_ACCESS_DENIALS):
        return False
    if any("calendar" in tool for tool in tool_evidence):
        return False
    return any(pattern.search(text) for pattern in _CALENDAR_CLAIM_PATTERNS)


def build_response_audit(
    reply_text: str,
    events: Iterable[FocusEvent],
    *,
    source_turn_id: str,
) -> dict[str, Any]:
    event_list = list(events)
    expected_question = _expected_question(
        event_list,
        source_turn_id,
    )
    visible_questions = extract_visible_questions(reply_text)
    tool_evidence = _tool_evidence(event_list, source_turn_id)

    normalized_expected = _normalize_question(expected_question)
    normalized_visible = {
        _normalize_question(question)
        for question in visible_questions
        if _normalize_question(question)
    }

    if normalized_expected:
        question_match: bool | None = (
            normalized_expected in normalized_visible
        )
    else:
        question_match = None

    findings: list[dict[str, str]] = []

    if normalized_expected and question_match is False:
        findings.append(
            {
                "code": "question_mismatch",
                "detail": (
                    "The visible reply did not ask the canonical pending "
                    "question exactly."
                ),
            }
        )

    if len(visible_questions) > 1:
        findings.append(
            {
                "code": "multiple_visible_questions",
                "detail": (
                    "The visible reply contains more than one question."
                ),
            }
        )

    if _calendar_claim_without_evidence(reply_text, tool_evidence):
        findings.append(
            {
                "code": "calendar_claim_without_tool_evidence",
                "detail": (
                    "The visible reply described calendar availability "
                    "without a calendar tool event for this turn."
                ),
            }
        )

    return {
        "expectedQuestion": expected_question,
        "visibleQuestions": visible_questions,
        "questionMatch": question_match,
        "toolEvidence": tool_evidence,
        "findings": findings,
    }
