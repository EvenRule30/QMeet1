from __future__ import annotations

import re
from typing import Any

from app.focus.models import TurnPlan, TurnRoute

_MIN_ACTIVE_CONFIDENCE = 0.90
_TOOL_BACKED_CLAIM_PATTERNS = (
    (
        "calendar_availability_without_tool",
        re.compile(
            r"\b(?:calendar\s+(?:is|looks|seems)\s+(?:open|clear|free)|"
            r"you(?:'re| are)\s+(?:free|available))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "search_result_without_tool",
        re.compile(
            r"\b(?:i searched|search results show|current listings show|"
            r"today's prices show|latest sources show)\b",
            re.IGNORECASE,
        ),
    ),
)

_PROMISE_WITHOUT_DELIVERY_PATTERN = re.compile(
    r"\b(?:"
    r"i(?:'ll| will| can)\s+(?:provide|give|explain|show|walk you through)|"
    r"let me\s+(?:provide|give|explain|show|walk you through)|"
    r"(?:instructions|steps|details)\s+(?:will|can)\s+be\s+(?:provided|given)"
    r")\b",
    re.IGNORECASE,
)

_PROCEDURAL_DELIVERY_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:\d+[.)]|[-*])\s+|"
    r"(?:^|[.!?]\s+)(?:first|second|third|finally)\s*[, :]\s+|"
    r"\bstep\s+(?:one|two|three|four|five|\d+)\b",
    re.IGNORECASE,
)

_PERMISSION_OFFER_QUESTION_PATTERN = re.compile(
    r"^(?:"
    r"would you like|"
    r"do you want|"
    r"should i|"
    r"shall i|"
    r"would it help if i"
    r")\b",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _real_tool_calls(plan: TurnPlan) -> list:
    return [
        tool_call
        for tool_call in plan.toolCalls
        if tool_call.tool.value != "none"
    ]


def compose_response_candidate(plan: TurnPlan) -> str:
    """Compose a grounded direct reply from the structured TurnPlan.

    Tool-backed turns are intentionally excluded because their final wording
    must wait for the actual tool result.
    """

    if _real_tool_calls(plan):
        return ""

    parts: list[str] = []

    for raw in (
        plan.responseIntent.acknowledge,
        plan.responseIntent.guidance,
        plan.responseIntent.askQuestion,
    ):
        value = _clean(raw)
        if not value:
            continue

        normalized = value.casefold()
        if any(existing.casefold() == normalized for existing in parts):
            continue

        if any(normalized in existing.casefold() for existing in parts):
            continue

        parts.append(value)

    return "\n\n".join(parts).strip()


def build_response_candidate(plan: TurnPlan) -> dict[str, Any]:
    """Return the shadow candidate plus a guarded active-eligibility verdict.

    The verdict is deliberately conservative. It does not activate response
    replacement; it only records whether this candidate would be eligible for a
    future guarded cutover.
    """

    text = compose_response_candidate(plan)
    reasons: list[str] = []
    real_tool_calls = _real_tool_calls(plan)

    if real_tool_calls:
        reasons.append("tool_turn_requires_result")

    if not text:
        reasons.append("empty_candidate")

    if plan.route not in {
        TurnRoute.RESPOND,
        TurnRoute.FOCUS_ACTION,
        TurnRoute.CLARIFY,
    }:
        reasons.append("unsupported_route")

    if plan.confidence < _MIN_ACTIVE_CONFIDENCE:
        reasons.append("confidence_below_threshold")

    acknowledge = _clean(plan.responseIntent.acknowledge)
    guidance = _clean(plan.responseIntent.guidance)
    question = _clean(plan.responseIntent.askQuestion)

    if (
        plan.responseIntent.answerDirectly
        and not guidance
        and not question
        and acknowledge
    ):
        reasons.append("missing_direct_answer_content")

    if (
        plan.responseIntent.answerDirectly
        and guidance
        and _PROMISE_WITHOUT_DELIVERY_PATTERN.search(guidance)
        and not _PROCEDURAL_DELIVERY_PATTERN.search(guidance)
    ):
        reasons.append("direct_answer_promised_not_delivered")

    if (
        plan.responseIntent.answerDirectly
        and question
        and _PERMISSION_OFFER_QUESTION_PATTERN.search(question)
        and not _PROCEDURAL_DELIVERY_PATTERN.search(guidance)
    ):
        reasons.append("direct_answer_deferred_to_offer")

    if question and question.casefold() not in text.casefold():
        reasons.append("candidate_missing_canonical_question")

    for code, pattern in _TOOL_BACKED_CLAIM_PATTERNS:
        if text and pattern.search(text):
            reasons.append(code)

    if len(text) > 4000:
        reasons.append("candidate_too_long")

    deduplicated_reasons = list(dict.fromkeys(reasons))

    return {
        "text": text,
        "stage": "direct",
        "components": {
            "acknowledge": acknowledge,
            "guidance": guidance,
            "question": question,
        },
        "eligibility": {
            "eligible": not deduplicated_reasons,
            "reasons": deduplicated_reasons,
            "confidence": plan.confidence,
            "minimumConfidence": _MIN_ACTIVE_CONFIDENCE,
        },
    }
