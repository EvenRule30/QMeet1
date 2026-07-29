from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

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


_NUMBERED_STEP_PATTERN = re.compile(
    r"(?:^|\n)\s*(\d{1,2})[.)]\s+",
    re.MULTILINE,
)

_SUSPICIOUS_TRAILING_FRAGMENT_PATTERN = re.compile(
    r"(?:"
    r"[,;:/\\-]\s*\d{0,3}|"
    r"\b(?:and|or|to|before|after|with|without|when|while|for)\s*"
    r")$",
    re.IGNORECASE,
)

_TERMINAL_CHARACTERS = frozenset(".?!)]}\"'")


def _clean(value: str) -> str:
    """Normalize whitespace while preserving intentional paragraph/list breaks."""

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    output_lines: list[str] = []
    previous_was_blank = False

    for raw_line in normalized.split("\n"):
        line = " ".join(raw_line.split()).strip()

        if not line:
            if output_lines and not previous_was_blank:
                output_lines.append("")
            previous_was_blank = True
            continue

        output_lines.append(line)
        previous_was_blank = False

    while output_lines and output_lines[-1] == "":
        output_lines.pop()

    return "\n".join(output_lines).strip()


def _real_tool_calls(plan: TurnPlan) -> list:
    return [
        tool_call
        for tool_call in plan.toolCalls
        if tool_call.tool.value != "none"
    ]


def _has_balanced_delimiters(value: str) -> bool:
    pairs = {
        ")": "(",
        "]": "[",
        "}": "{",
    }
    stack: list[str] = []

    for character in value:
        if character in pairs.values():
            stack.append(character)
            continue

        if character not in pairs:
            continue

        if not stack or stack.pop() != pairs[character]:
            return False

    return not stack


def _procedure_integrity_reasons(guidance: str) -> list[str]:
    """Return deterministic reasons a delivered procedure looks incomplete."""

    if not guidance or not _PROCEDURAL_DELIVERY_PATTERN.search(guidance):
        return []

    reasons: list[str] = []
    stripped = guidance.rstrip()
    numbered_matches = list(_NUMBERED_STEP_PATTERN.finditer(guidance))

    if numbered_matches:
        step_numbers = [
            int(match.group(1))
            for match in numbered_matches
        ]
        expected_numbers = list(
            range(1, len(step_numbers) + 1)
        )

        if step_numbers != expected_numbers:
            reasons.append("nonsequential_numbered_steps")

        for index, match in enumerate(numbered_matches):
            content_start = match.end()
            content_end = (
                numbered_matches[index + 1].start()
                if index + 1 < len(numbered_matches)
                else len(guidance)
            )
            step_content = guidance[content_start:content_end].strip()

            if len(step_content) < 8:
                reasons.append("incomplete_numbered_step")
                break

    if stripped and stripped[-1] not in _TERMINAL_CHARACTERS:
        reasons.append("unterminated_procedure")

    if _SUSPICIOUS_TRAILING_FRAGMENT_PATTERN.search(stripped):
        reasons.append("malformed_trailing_fragment")

    if not _has_balanced_delimiters(guidance):
        reasons.append("unbalanced_delimiters")

    return list(dict.fromkeys(reasons))


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

    if plan.responseIntent.answerDirectly and guidance:
        reasons.extend(_procedure_integrity_reasons(guidance))

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


def _clean_tool_source(raw_source: dict[str, Any]) -> dict[str, str] | None:
    url = str(raw_source.get("url", "")).strip()[:1000]
    title = _clean(str(raw_source.get("title", "")))[:240]
    domain = _clean(str(raw_source.get("domain", "")))[:160]

    if not domain and url:
        try:
            domain = urlparse(url).netloc.removeprefix("www.")[:160]
        except ValueError:
            domain = ""

    if not url or not (title or domain):
        return None

    return {
        "title": title or domain or url,
        "url": url,
        "domain": domain,
    }


def _clean_calendar_event(raw_event: dict[str, Any]) -> dict[str, Any] | None:
    title = _clean(str(raw_event.get("title") or ""))[:240]
    event_id = _clean(
        str(
            raw_event.get("id")
            or raw_event.get("googleEventId")
            or ""
        )
    )[:300]
    date_key = _clean(str(raw_event.get("dateKey") or ""))[:40]
    time_label = _clean(str(raw_event.get("time") or ""))[:80]
    start = _clean(str(raw_event.get("start") or ""))[:100]
    end = _clean(str(raw_event.get("end") or ""))[:100]
    location = _clean(str(raw_event.get("location") or ""))[:240]
    all_day = bool(raw_event.get("allDay", False))

    if not title:
        return None

    return {
        "id": event_id,
        "title": title,
        "dateKey": date_key,
        "time": time_label,
        "start": start,
        "end": end,
        "location": location,
        "allDay": all_day,
    }


def _calendar_view_label(view: str) -> str:
    return {
        "today": "today",
        "tomorrow": "tomorrow",
        "week": "this week",
    }.get(view, "the requested view")


def _calendar_text_claims_clear(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:calendar\s+(?:is|looks|seems)\s+(?:clear|open|free)|"
            r"no\s+events\s+(?:are\s+)?scheduled|nothing\s+(?:is\s+)?scheduled)\b",
            text,
            re.IGNORECASE,
        )
    )


def build_tool_response_candidate(
    *,
    tool: str,
    success: bool,
    query: str = "",
    summary: str = "",
    recommendation: str = "",
    steps: list[str] | None = None,
    sources: list[dict[str, Any]] | None = None,
    calendar_connected: bool | None = None,
    calendar_view: str = "",
    calendar_events: list[dict[str, Any]] | None = None,
    attach_to_focus: bool,
) -> dict[str, Any]:
    """Build a deterministic candidate from verified tool output.

    This does not call a second model. Search output remains the source of truth
    for Search candidates. Calendar candidates are composed only from the
    connected-calendar flag, requested view, and returned event records.
    """

    clean_tool = _clean(tool).casefold()
    reasons: list[str] = []

    if not attach_to_focus:
        reasons.append("tool_result_not_attached_to_focus")
    if not success:
        reasons.append("tool_result_failed")

    if clean_tool == "search":
        clean_query = _clean(query)[:500]
        clean_summary = _clean(summary)[:2200]
        clean_recommendation = _clean(recommendation)[:800]

        clean_steps: list[str] = []
        for raw_step in steps or []:
            step = _clean(str(raw_step))[:500]
            if step and step.casefold() not in {
                existing.casefold() for existing in clean_steps
            }:
                clean_steps.append(step)
            if len(clean_steps) >= 3:
                break

        citations: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for raw_source in sources or []:
            if not isinstance(raw_source, dict):
                continue
            citation = _clean_tool_source(raw_source)
            if citation is None:
                continue
            key = citation["url"].casefold()
            if key in seen_urls:
                continue
            seen_urls.add(key)
            citations.append(citation)
            if len(citations) >= 5:
                break

        sections: list[str] = []
        if clean_query:
            sections.append(f'Search complete for "{clean_query}".')
        else:
            sections.append("Search complete.")

        if clean_summary:
            sections.append(clean_summary)

        if (
            clean_recommendation
            and clean_recommendation.casefold() not in clean_summary.casefold()
        ):
            sections.append(f"Recommendation: {clean_recommendation}")

        if clean_steps:
            step_lines = ["Next steps:"]
            step_lines.extend(
                f"{index}. {step}"
                for index, step in enumerate(clean_steps, start=1)
            )
            sections.append("\n".join(step_lines))

        if citations:
            source_lines = ["Sources:"]
            source_lines.extend(
                f'[{index}] [{citation["title"]}]({citation["url"]})'
                for index, citation in enumerate(citations, start=1)
            )
            sections.append("\n".join(source_lines))

        text = "\n\n".join(
            section for section in sections if section
        ).strip()

        if not clean_summary:
            reasons.append("missing_tool_summary")
        if not citations:
            reasons.append("missing_tool_citations")

        components: dict[str, Any] = {
            "summary": clean_summary,
            "recommendation": clean_recommendation,
            "steps": clean_steps,
        }
        tool_evidence: dict[str, Any] = {
            "tool": clean_tool,
            "success": bool(success),
            "query": clean_query,
            "resultIds": [citation["url"] for citation in citations],
            "citationCount": len(citations),
        }

    elif clean_tool == "calendar_read":
        clean_view = _clean(calendar_view).casefold()
        connected = calendar_connected is True
        clean_events: list[dict[str, Any]] = []
        seen_events: set[str] = set()

        for raw_event in calendar_events or []:
            if not isinstance(raw_event, dict):
                continue
            event = _clean_calendar_event(raw_event)
            if event is None:
                continue
            identity = (
                event["id"]
                or "|".join(
                    [event["title"], event["start"], event["dateKey"]]
                )
            ).casefold()
            if identity in seen_events:
                continue
            seen_events.add(identity)
            clean_events.append(event)
            if len(clean_events) >= 20:
                break

        view_label = _calendar_view_label(clean_view)
        sections = [f"Calendar read complete for {view_label}."]

        if not connected:
            sections.append(
                "Google Calendar is not connected, so QMeet cannot verify "
                "the schedule for this view."
            )
        elif clean_events:
            event_lines = ["Scheduled events:"]
            for event in clean_events:
                time_label = event["time"] or (
                    "All day" if event["allDay"] else "Time not provided"
                )
                location_suffix = (
                    f" · {event['location']}" if event["location"] else ""
                )
                event_lines.append(
                    f"- {time_label} — {event['title']}{location_suffix}"
                )
            sections.append("\n".join(event_lines))
        else:
            sections.append(
                f"No events are scheduled for {view_label}, so the calendar "
                "is clear for that view."
            )

        text = "\n\n".join(sections).strip()
        event_count = len(clean_events)

        if clean_view not in {"today", "tomorrow", "week"}:
            reasons.append("invalid_calendar_view")
        if not connected:
            reasons.append("calendar_not_connected")
        if _calendar_text_claims_clear(text) and (
            not connected or event_count != 0
        ):
            reasons.append("unsupported_calendar_availability_claim")

        components = {
            "calendarView": clean_view,
            "eventCount": event_count,
            "events": clean_events,
        }
        tool_evidence = {
            "tool": clean_tool,
            "success": bool(success),
            "calendarConnected": connected,
            "calendarView": clean_view,
            "eventCount": event_count,
            "eventIds": [
                event["id"] for event in clean_events if event["id"]
            ],
            "events": clean_events,
        }
        citations = []

    else:
        text = ""
        components = {}
        citations = []
        tool_evidence = {
            "tool": clean_tool,
            "success": bool(success),
        }
        reasons.append("unsupported_tool_result")

    if not text:
        reasons.append("empty_candidate")
    if len(text) > 4000:
        reasons.append("candidate_too_long")

    deduplicated_reasons = list(dict.fromkeys(reasons))

    return {
        "text": text[:4000],
        "stage": "tool_result",
        "components": components,
        "citations": citations,
        "toolEvidence": tool_evidence,
        "eligibility": {
            "eligible": not deduplicated_reasons,
            "reasons": deduplicated_reasons,
            "confidence": 1.0 if success else 0.0,
            "minimumConfidence": 1.0,
        },
    }

