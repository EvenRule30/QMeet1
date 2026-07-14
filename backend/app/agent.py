from __future__ import annotations

import os
import json
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import openai
from openai import AsyncOpenAI

try:
    from app.memory_store import get_memory_context
except Exception:  # Memory should never block chat startup.
    get_memory_context = None

try:
    from app.calendar_service import list_calendar_events
except Exception:  # Calendar should never block chat startup.
    list_calendar_events = None


SYSTEM_PROMPT = """
You are QMeet, a concise AI assistant inside a small 1024x600 tablet orb interface.

Behavior:
- Keep answers short enough to read on a small tablet screen.
- Be direct and useful.
- Prefer 1-3 short paragraphs.
- Avoid long lists unless the user asks for detail.
- Do not mention backend, API, provider, or implementation details unless asked.
- If asked what you are, say you are QMeet, the orb assistant.
""".strip()


MEMORY_CONTEXT_PROMPT = """
QMeet may receive a compact saved memory context containing tasks, notes, and recent actions.
Use it only when it helps answer the user's current message.
Do not mention that the context came from a backend, JSON file, API, or system prompt.
If the user asks what to do next, continue, or what they were working on, use the saved context directly.
If the saved context is irrelevant, ignore it.
""".strip()


CALENDAR_CONTEXT_PROMPT = """
QMeet may receive a compact calendar context for today and tomorrow.
Use it when the user asks about schedules, availability, plans, meetings, or what to do next.
Do not mention that the context came from an API, backend route, or system prompt.
If there are no events in the relevant window, say that plainly instead of inventing events.
If calendar is unavailable or disconnected, say that QMeet cannot see the calendar right now.
""".strip()



COMMAND_INTERPRETER_PROMPT = """
You are QMeet's command interpreter. Classify the user's text as either a local UI command or normal chat.

Return JSON only. Do not use markdown. Do not explain. Do not claim that you performed an action.

Allowed JSON shape:
{
  "intent": "command" | "chat",
  "action": "none" | "open_panel" | "close_panel" | "go_home" | "clear_chat" | "end_chat" | "save_note" | "read_notes" | "delete_last_note" | "clear_notes" | "read_memory" | "save_task" | "mark_task_done" | "prepare_search" | "clear_search" | "add_calendar_event" | "read_calendar" | "delete_last_calendar_event" | "edit_calendar_event" | "clear_calendar" | "voice_output_on" | "voice_output_off" | "voice_slower" | "voice_faster" | "voice_normal" | "cancel",
  "confidence": 0.0,
  "frontendCommand": "",
  "payload": {},
  "reason": ""
}

The frontend only executes the exact frontendCommand text. Use these exact frontendCommand forms:
- open menu
- open settings
- show status
- open notes
- open calendar
- open search
- close panel
- go home
- clear chat
- end chat
- note that <note text>
- read my notes
- delete last note
- clear notes
- open memory
- what was I working on
- remember to <task text> as a task
- mark task done
- mark <task text> done
- clear completed tasks
- search for <query>
- clear search
- add event today at <time> called <title>
- add event tomorrow at <time> called <title>
- what's on my calendar
- show today's events
- show tomorrow's events
- delete last event
- reschedule last event to <today|tomorrow> at <time>
- move last event to <today|tomorrow> at <time>
- rename last event to <new title>
- edit last event to <today|tomorrow> at <time> called <title>
- clear calendar
- mute voice
- unmute voice
- speak slower
- speak faster
- normal voice
- cancel

Rules:
- Use intent "chat" for normal questions, explanations, coding help, opinions, or anything that should be answered by the AI.
- Use intent "command" only for local QMeet UI/tool control.
- Memory/task commands should map to memory frontend commands.
- If the user asks what they were working on or what tasks they have, map to "what was I working on".
- If the user asks to remember something as a task or reminds themselves to do something, map to "remember to <task text> as a task".
- If the user asks to mark a task done or complete, map to "mark task done" or "mark <task text> done".
- Calendar misspellings like "calender" and "calander" should still map to calendar commands.
- If the user asks to clear/wipe/remove/delete their calendar/schedule/agenda/events, map to "clear calendar".
- If the user asks to move/reschedule/edit/rename the last/current/next calendar event, map to the closest edit/reschedule/rename frontendCommand form above.
- If the user asks to stop the current response, stop listening, never mind, forget that, or cancel, map to "cancel".
- If the user asks you to stop talking right now, map to "cancel". If they ask to disable spoken responses in general, map to "mute voice".
- If a command is clear but wording is fuzzy, return confidence 0.80 or higher.
- If command intent is possible but unclear, use intent "command" with confidence between 0.50 and 0.79 and a best frontendCommand.
- If not a command, use intent "chat", action "none", confidence below 0.50, and empty frontendCommand.
""".strip()


ALLOWED_COMMAND_ACTIONS = {
    "none",
    "open_panel",
    "close_panel",
    "go_home",
    "clear_chat",
    "end_chat",
    "save_note",
    "read_notes",
    "delete_last_note",
    "clear_notes",
    "read_memory",
    "save_task",
    "mark_task_done",
    "prepare_search",
    "clear_search",
    "add_calendar_event",
    "read_calendar",
    "delete_last_calendar_event",
    "edit_calendar_event",
    "clear_calendar",
    "voice_output_on",
    "voice_output_off",
    "voice_slower",
    "voice_faster",
    "voice_normal",
    "cancel",
}


def _empty_command_intent(reason: str = "") -> dict:
    return {
        "intent": "chat",
        "action": "none",
        "confidence": 0.0,
        "frontendCommand": "",
        "payload": {},
        "reason": reason,
    }


def _extract_json_object(text: str) -> dict:
    stripped = text.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found.")

    return json.loads(stripped[start : end + 1])


def _normalize_command_intent(raw: dict) -> dict:
    intent = str(raw.get("intent", "chat")).strip().lower()
    if intent not in {"command", "chat"}:
        intent = "chat"

    action = str(raw.get("action", "none")).strip()
    if action not in ALLOWED_COMMAND_ACTIONS:
        action = "none"

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    frontend_command = str(raw.get("frontendCommand", "")).strip()

    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    reason = str(raw.get("reason", "")).strip()

    if intent == "chat" or action == "none":
        return {
            "intent": "chat",
            "action": "none",
            "confidence": min(confidence, 0.49),
            "frontendCommand": "",
            "payload": {},
            "reason": reason,
        }

    if not frontend_command:
        return _empty_command_intent("Interpreter returned a command without a frontendCommand.")

    return {
        "intent": "command",
        "action": action,
        "confidence": confidence,
        "frontendCommand": frontend_command,
        "payload": payload,
        "reason": reason,
    }


async def interpret_command_intent(message: str) -> dict:
    config = get_agent_config()

    if config.provider == "mock":
        return mock_interpret_command_intent(message)

    if config.provider == "openai":
        return await openai_interpret_command_intent(message, config)

    raise AgentUserFacingError(
        f'Unsupported LLM_PROVIDER="{config.provider}". Use "mock" or "openai".'
    )


def mock_interpret_command_intent(message: str) -> dict:
    text = message.strip()
    lowered = text.lower()

    if not text:
        return _empty_command_intent("Empty input.")

    if re.search(r"\b(what was i working on|what am i working on|what are my tasks|read memory|memory summary)\b", lowered):
        return {
            "intent": "command",
            "action": "read_memory",
            "confidence": 0.95,
            "frontendCommand": "what was I working on",
            "payload": {},
            "reason": "Mock matched memory read wording.",
        }

    task_match = re.search(r"\b(?:remember|remind me|add|save|create|make)\b.*\b(?:task|to)\b", lowered)
    if task_match:
        return {
            "intent": "command",
            "action": "save_task",
            "confidence": 0.85,
            "frontendCommand": text if "task" in lowered else f"{text} as a task",
            "payload": {},
            "reason": "Mock matched task save wording.",
        }

    if re.search(r"\b(mark|complete|finish)\b.*\b(task|done|complete|completed|finished)\b", lowered):
        return {
            "intent": "command",
            "action": "mark_task_done",
            "confidence": 0.9,
            "frontendCommand": text,
            "payload": {},
            "reason": "Mock matched task completion wording.",
        }

    if re.search(r"\b(reschedule|move)\b.*\b(last|latest|next|current|this)\b.*\b(event|appointment|meeting)\b", lowered):
        return {
            "intent": "command",
            "action": "edit_calendar_event",
            "confidence": 0.9,
            "frontendCommand": text,
            "payload": {},
            "reason": "Mock matched calendar reschedule wording.",
        }

    if re.search(r"\b(rename|retitle)\b.*\b(last|latest|next|current|this)\b.*\b(event|appointment|meeting)\b", lowered):
        return {
            "intent": "command",
            "action": "edit_calendar_event",
            "confidence": 0.9,
            "frontendCommand": text,
            "payload": {},
            "reason": "Mock matched calendar rename wording.",
        }

    if re.search(r"\b(clear|wipe|delete|remove|erase)\b.*\b(calendar|calender|calander|schedule|agenda|events?)\b", lowered):
        return {
            "intent": "command",
            "action": "clear_calendar",
            "confidence": 0.95,
            "frontendCommand": "clear calendar",
            "payload": {},
            "reason": "Mock matched calendar clear wording.",
        }

    if re.search(r"\b(open|show|pull up|bring up)\b.*\b(notes?|notepad|notebook)\b", lowered):
        return {
            "intent": "command",
            "action": "open_panel",
            "confidence": 0.9,
            "frontendCommand": "open notes",
            "payload": {"panel": "notes"},
            "reason": "Mock matched notes panel wording.",
        }

    if re.search(r"\b(mute|silence)\b.*\b(voice|speech|yourself|talking)\b", lowered):
        return {
            "intent": "command",
            "action": "voice_output_off",
            "confidence": 0.9,
            "frontendCommand": "mute voice",
            "payload": {},
            "reason": "Mock matched voice mute wording.",
        }

    return _empty_command_intent("Mock did not match a local command.")


async def openai_interpret_command_intent(message: str, config: AgentConfig) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise AgentUserFacingError(
            "OpenAI is selected, but OPENAI_API_KEY is missing in backend/.env."
        )

    client = AsyncOpenAI(api_key=api_key)

    try:
        response = await client.responses.create(
            model=config.model,
            input=[
                {
                    "role": "developer",
                    "content": COMMAND_INTERPRETER_PROMPT,
                },
                {
                    "role": "user",
                    "content": message,
                },
            ],
            max_output_tokens=260,
        )
    except openai.AuthenticationError as exc:
        raise AgentUserFacingError(
            "OpenAI authentication failed. Check backend/.env and verify the API key."
        ) from exc
    except openai.RateLimitError as exc:
        raise AgentUserFacingError(
            "OpenAI rate limit or quota was reached. Check API billing, limits, or try again later."
        ) from exc
    except openai.APIConnectionError as exc:
        raise AgentUserFacingError(
            "Could not connect to OpenAI. Check your internet connection."
        ) from exc
    except openai.APIError as exc:
        raise AgentUserFacingError(
            "OpenAI returned an API error. Try again shortly."
        ) from exc

    raw_text = response.output_text.strip()

    if not raw_text:
        return _empty_command_intent("Interpreter returned empty output.")

    try:
        raw_json = _extract_json_object(raw_text)
    except (json.JSONDecodeError, ValueError):
        return _empty_command_intent("Interpreter returned invalid JSON.")

    return _normalize_command_intent(raw_json)



SEARCH_WEB_PROMPT = """
You are QMeet's web search helper for a small 1024x600 tablet UI.

Use web search for the user's query, then return JSON only. Do not use markdown.
The frontend renders this JSON into compact cards, so each field must be specific, short, and easy to scan.

Required JSON shape:
{
  "summary": "One plain sentence explaining the answer.",
  "recommendation": "A direct recommendation or best next move for the user.",
  "steps": ["3-5 concrete action steps. Start with a verb. Do not number the items."],
  "cards": [
    {"title": "Short label", "detail": "Specific useful detail, setting, command idea, or caveat."}
  ],
  "sourceHints": [
    {"domain": "example.com", "usedFor": "Short phrase explaining what this source is useful for."}
  ]
}

Rules:
- Keep summary under 180 characters.
- Keep recommendation under 260 characters.
- Steps must not start with numbers like "1." or "2."; the UI numbers them.
- Steps must be readable UI text, not API prose. Start with a verb and avoid generic filler.
- Do not use markdown, bullets, code fences, link syntax, underscores, em dashes, en dashes, or separator dashes in any field.
- For API/tool names, write readable names like "web search tool" unless exact code syntax is essential.
- Avoid awkward phrases like "the Responses API" after a separator. Write normal sentences.
- Make cards specific enough to help the user decide what to do next.
- Card titles must be plain words under 32 characters. Do not use dash-separated titles.
- sourceHints usedFor must be under 70 characters and should not start with "Official information on" or "Best for".
- Use sourceHints only to label source usefulness; do not invent URLs.
- If results are mixed or incomplete, say so in recommendation or a card.
""".strip()


def _source_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return ""


def _canonical_source_url(url: str) -> str:
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url.strip())
        return urlunparse((
            parsed.scheme,
            parsed.netloc.replace("www.", ""),
            parsed.path.rstrip("/"),
            "",
            "",
            "",
        ))
    except Exception:
        return url.strip()


def _clean_search_text(value: object, max_length: int = 420) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    # Convert markdown links to just their labels, then strip markdown markers.
    text = re.sub(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)", r"\1", text)
    text = re.sub(r"[*`#>]+", "", text)

    # Search results are UI text, not code. Remove visual artifacts the model
    # often emits: underscores, em dashes, en dashes, and dash separators.
    text = text.replace("_", " ")
    text = re.sub(r"\s+[—–]\s+", " ", text)
    text = re.sub(r"\s+-\s+", " ", text)
    text = re.sub(r"[—–]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -•\t\n\r")

    # The UI adds numbering, so remove any numbering/bullet prefixes returned by the model.
    # Run a few passes to handle cases like "1. 1. Install Chromium".
    for _ in range(4):
        text = re.sub(r"^\s*(?:step\s+)?\d{1,2}\s*[:\.)-]\s+", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"^\s*(?:[-•*])\s+", "", text).strip()

    # Remove source-card boilerplate and citation helper phrases that read badly in the UI.
    text = re.sub(r"^best for\s*:?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^official information\s+(?:on|about)\s+", "", text, flags=re.IGNORECASE)

    # Fix artifacts like "Integrate the Responses API" only when the phrase is
    # created by separator cleanup and sounds unnatural in a command-style step.
    text = re.sub(r"\bthe\s+(?=Responses API|web search tool|Calendar API|OpenAI API)", "", text, flags=re.IGNORECASE)

    if len(text) > max_length:
        return text[: max_length - 3].rstrip() + "..."

    return text


def _as_short_list(value: object, *, max_items: int, max_length: int) -> list[str]:
    if not isinstance(value, list):
        return []

    items: list[str] = []
    for item in value:
        cleaned = _clean_search_text(item, max_length=max_length)
        if cleaned and cleaned not in items:
            items.append(cleaned)
        if len(items) >= max_items:
            break

    return items


def _extract_json_object(text: str) -> dict:
    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found.")

    return json.loads(stripped[start : end + 1])


def _normalize_search_card(card: object) -> dict | None:
    if not isinstance(card, dict):
        return None

    title = _clean_search_text(card.get("title"), max_length=80)
    detail = _clean_search_text(card.get("detail"), max_length=260)

    if not title and not detail:
        return None

    return {
        "title": title or "Detail",
        "detail": detail,
    }


def _parse_search_payload(raw_text: str, query: str) -> dict:
    try:
        raw_json = _extract_json_object(raw_text)
    except (json.JSONDecodeError, ValueError):
        summary = _clean_search_text(raw_text, max_length=360)
        return {
            "summary": summary or f"Search results for {query} are available.",
            "recommendation": "Review the sources and use the steps that match your setup.",
            "steps": [],
            "cards": [],
            "sourceHints": [],
        }

    summary = _clean_search_text(raw_json.get("summary"), max_length=220)
    recommendation = _clean_search_text(raw_json.get("recommendation"), max_length=320)
    steps = _as_short_list(raw_json.get("steps"), max_items=6, max_length=180)

    cards: list[dict] = []
    raw_cards = raw_json.get("cards")
    if isinstance(raw_cards, list):
        for raw_card in raw_cards:
            card = _normalize_search_card(raw_card)
            if card:
                cards.append(card)
            if len(cards) >= 4:
                break

    source_hints: list[dict] = []
    raw_hints = raw_json.get("sourceHints")
    if isinstance(raw_hints, list):
        for hint in raw_hints:
            if not isinstance(hint, dict):
                continue

            domain = _clean_search_text(hint.get("domain"), max_length=120).lower().replace("www.", "")
            used_for = _clean_search_text(hint.get("usedFor"), max_length=160)
            if domain or used_for:
                source_hints.append({"domain": domain, "usedFor": used_for})

            if len(source_hints) >= 6:
                break

    if not summary:
        summary = f"Search results for {query} are available."

    if not recommendation:
        recommendation = "Use the source-backed steps below as the next checklist."

    if not steps and cards:
        steps = [card["detail"] for card in cards if card.get("detail")][:4]

    return {
        "summary": summary,
        "recommendation": recommendation,
        "steps": steps,
        "cards": cards,
        "sourceHints": source_hints,
    }


def _humanize_slug(slug: str) -> str:
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\.(html?|md|php)$", "", slug, flags=re.IGNORECASE)
    slug = _clean_search_text(slug, max_length=100)
    return slug[:1].upper() + slug[1:] if slug else ""


def _clean_source_title_for_display(url: str, title: str = "") -> str:
    domain = _source_domain(url)
    cleaned_title = _clean_search_text(title, max_length=140)
    lower_title = cleaned_title.lower()

    # The Responses API can surface citation text as a messy title. If the title
    # looks like a query/citation artifact, use a readable title inferred from the URL.
    bad_title = (
        not cleaned_title
        or lower_title in {domain.lower(), f"www.{domain}".lower()}
        or "best for:" in lower_title
        or "utm_source" in lower_title
        or "http" in lower_title
        or len(cleaned_title) > 95
    )

    known_domains = {
        "platform.openai.com": "OpenAI API documentation",
        "help.openai.com": "OpenAI Help Center article",
        "help-lb.openai.com": "OpenAI Help Center article",
        "openai.com": "OpenAI product update",
        "raspberrypi.com": "Official Raspberry Pi guide",
        "raspberrytips.com": "Raspberry Pi Tips guide",
        "zbotic.in": "Touchscreen kiosk guide",
    }

    try:
        from urllib.parse import urlparse, unquote

        parsed = urlparse(url)
        path = parsed.path.lower()
        original_path = parsed.path.strip("/")

        if "platform.openai.com" in domain:
            return "OpenAI API documentation"
        if "help" in domain and "openai.com" in domain:
            return "OpenAI Help Center article"
        if domain == "openai.com" and "new-tools-for-building-agents" in path:
            return "OpenAI tools for building agents"
        if "raspberrypi.com" in domain and "kiosk" in path:
            return "Official Raspberry Pi kiosk tutorial"
        if "raspberrypi.com" in domain and ("configuration" in path or "display" in path or "config" in path):
            return "Official Raspberry Pi display configuration"
        if "raspberrytips.com" in domain and "config" in path:
            return "Raspberry Pi raspi-config guide"
        if "raspberrytips.com" in domain and "kiosk" in path:
            return "Raspberry Pi kiosk walkthrough"

        if not bad_title:
            return cleaned_title

        pieces = [piece for piece in original_path.split("/") if piece]
        if pieces:
            inferred = _humanize_slug(unquote(pieces[-1]))
            if inferred:
                return inferred
    except Exception:
        pass

    if not bad_title:
        return cleaned_title

    return known_domains.get(domain, domain or url or "Source")


def _infer_title_from_url(url: str, title: str = "") -> str:
    return _clean_source_title_for_display(url, title)


def _infer_source_use(domain: str, title: str, url: str) -> str:
    haystack = f"{domain} {title} {url}".lower()

    if "raspberrypi.com" in haystack:
        if "configuration" in haystack or "display" in haystack or "config" in haystack:
            return "Official Raspberry Pi display/configuration reference."
        if "kiosk" in haystack or "tutorial" in haystack:
            return "Official Raspberry Pi kiosk setup pattern."
        return "Official Raspberry Pi documentation."

    if "help" in haystack and "openai.com" in haystack:
        return "Help article or implementation note."

    if "openai.com" in haystack:
        return "Official OpenAI reference."

    if "raspberrytips" in haystack:
        return "Practical Raspberry Pi walkthrough and setup notes."

    if "github" in haystack:
        return "Example commands, config files, or implementation references."

    if "forum" in haystack or "stack" in haystack or "reddit" in haystack:
        return "Community troubleshooting and edge cases."

    if "zbotic" in haystack or "touch" in haystack:
        return "Touchscreen or display-specific setup notes."

    return "Additional reference for this search result."


def _apply_source_hints(sources: list[dict], hints: list[dict]) -> list[dict]:
    if not hints:
        return sources

    for source in sources:
        domain = str(source.get("domain", "")).lower().replace("www.", "")
        url = str(source.get("url", "")).lower()

        for hint in hints:
            hint_domain = str(hint.get("domain", "")).lower().replace("www.", "")
            used_for = str(hint.get("usedFor", "")).strip()

            if used_for and hint_domain and (hint_domain in domain or hint_domain in url):
                source["usedFor"] = used_for
                break

    return sources


def _source_score(source: dict) -> int:
    haystack = f"{source.get('domain','')} {source.get('title','')} {source.get('url','')}".lower()
    score = 0
    for preferred in ("platform.openai.com", "help.openai.com", "openai.com", "raspberrypi.com", "raspberrytips.com"):
        if preferred in haystack:
            score += 4
    for useful in ("docs", "documentation", "guide", "tutorial", "kiosk", "configuration", "api", "responses"):
        if useful in haystack:
            score += 1
    return score


def _dedupe_sources(sources: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}

    for source in sources:
        url = str(source.get("url", "")).strip()
        if not url:
            continue

        canonical_url = _canonical_source_url(url)
        domain = str(source.get("domain", "")).strip() or _source_domain(url)
        title = _infer_title_from_url(url, str(source.get("title", "")))
        candidate = {
            "title": title[:120],
            "url": url,
            "domain": domain[:120],
            "usedFor": _infer_source_use(domain, title, url),
        }

        existing = by_url.get(canonical_url)
        if not existing or _source_score(candidate) > _source_score(existing):
            by_url[canonical_url] = candidate

    # Sort useful/official-looking sources first, then prevent visual repetition.
    ordered = sorted(by_url.values(), key=_source_score, reverse=True)
    domain_counts: dict[str, int] = {}
    title_domain_seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []

    for source in ordered:
        domain = source["domain"]
        title = source["title"]
        key = (title.lower(), domain.lower())
        if key in title_domain_seen:
            continue

        # The panel is small; one source per domain is usually clearer. Allow a
        # second only when the titles are meaningfully different.
        domain_count = domain_counts.get(domain, 0)
        if domain_count >= 1 and len(deduped) >= 3:
            continue
        if domain_count >= 2:
            continue

        title_domain_seen.add(key)
        domain_counts[domain] = domain_count + 1
        deduped.append(source)

        if len(deduped) >= 4:
            break

    return deduped


def _collect_web_sources(response) -> list[dict]:
    """Best-effort extraction for Responses API web-search sources/citations."""
    sources: list[dict] = []

    try:
        data = response.model_dump()
    except Exception:
        data = {}

    def add_source(candidate: dict) -> None:
        if not isinstance(candidate, dict):
            return

        url = (
            candidate.get("url")
            or candidate.get("uri")
            or candidate.get("link")
        )
        if not url:
            return

        sources.append({
            "title": candidate.get("title") or candidate.get("name") or "",
            "url": url,
            "domain": candidate.get("domain") or candidate.get("site") or "",
        })

    for source in data.get("sources", []) if isinstance(data.get("sources"), list) else []:
        add_source(source)

    output = data.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue

            action = item.get("action")
            if isinstance(action, dict):
                for source in action.get("sources", []) if isinstance(action.get("sources"), list) else []:
                    add_source(source)

            content = item.get("content", [])
            if isinstance(content, list):
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue

                    annotations = content_item.get("annotations", [])
                    if not isinstance(annotations, list):
                        continue

                    for annotation in annotations:
                        if not isinstance(annotation, dict):
                            continue

                        if annotation.get("type") == "url_citation":
                            add_source({
                                "title": annotation.get("title") or "",
                                "url": annotation.get("url") or "",
                            })

    return _dedupe_sources(sources)


async def search_web(query: str) -> dict:
    config = get_agent_config()

    if config.provider == "mock":
        return mock_search_web(query)

    if config.provider == "openai":
        return await openai_search_web(query, config)

    raise AgentUserFacingError(
        f'Unsupported LLM_PROVIDER="{config.provider}". Use "mock" or "openai".'
    )


def mock_search_web(query: str) -> dict:
    cleaned = query.strip()

    if not cleaned:
        raise AgentUserFacingError("Search query cannot be empty.")

    return {
        "ok": True,
        "query": cleaned,
        "summary": f'Mock web search result for "{cleaned}".',
        "recommendation": "Switch LLM_PROVIDER to openai to get current source-backed web results.",
        "steps": [
            "Keep the search query short and specific.",
            "Review the source cards before applying a setup change.",
            "Use normal chat for follow-up explanation after the search result loads.",
        ],
        "cards": [
            {
                "title": "Mock mode",
                "detail": "The backend route is working, but it is not performing a real web lookup until OpenAI mode is enabled.",
            }
        ],
        "sources": [],
        "provider": "mock",
        "message": "Mock search complete.",
    }


async def openai_search_web(query: str, config: AgentConfig) -> dict:
    cleaned = query.strip()

    if not cleaned:
        raise AgentUserFacingError("Search query cannot be empty.")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise AgentUserFacingError(
            "OpenAI is selected, but OPENAI_API_KEY is missing in backend/.env."
        )

    client = AsyncOpenAI(api_key=api_key)

    try:
        response = await client.responses.create(
            model=config.model,
            tools=[{"type": "web_search"}],
            tool_choice="required",
            include=["web_search_call.action.sources"],
            input=[
                {
                    "role": "developer",
                    "content": SEARCH_WEB_PROMPT,
                },
                {
                    "role": "user",
                    "content": cleaned,
                },
            ],
            max_output_tokens=max(700, min(config.max_output_tokens, 1200)),
        )
    except openai.AuthenticationError as exc:
        raise AgentUserFacingError(
            "OpenAI authentication failed. Check backend/.env and verify the API key."
        ) from exc
    except openai.RateLimitError as exc:
        raise AgentUserFacingError(
            "OpenAI rate limit or quota was reached. Check API billing, limits, or try again later."
        ) from exc
    except openai.APIConnectionError as exc:
        raise AgentUserFacingError(
            "Could not connect to OpenAI for web search. Check your internet connection."
        ) from exc
    except openai.APIError as exc:
        raise AgentUserFacingError(
            "OpenAI returned a web search API error. Try again shortly."
        ) from exc

    raw_text = response.output_text.strip()

    if not raw_text:
        raise AgentUserFacingError("Web search returned an empty response.")

    payload = _parse_search_payload(raw_text, cleaned)
    sources = _apply_source_hints(_collect_web_sources(response), payload.get("sourceHints", []))

    return {
        "ok": True,
        "query": cleaned,
        "summary": payload["summary"],
        "recommendation": payload["recommendation"],
        "steps": payload["steps"],
        "cards": payload["cards"],
        "sources": sources,
        "provider": "openai",
        "message": "Search complete.",
    }


# Simple in-memory history for the current backend process.
# This resets when the backend restarts.
MESSAGE_HISTORY: list[dict[str, str]] = []


@dataclass
class AgentConfig:
    provider: str
    model: str
    max_output_tokens: int
    has_openai_key: bool


class AgentUserFacingError(Exception):
    """Safe error message that can be shown in the UI."""


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def get_agent_config() -> AgentConfig:
    provider = os.getenv("LLM_PROVIDER", "mock").lower().strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()

    try:
        max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "300"))
    except ValueError:
        max_output_tokens = 300

    # OpenAI currently documents 16 as the minimum for max_output_tokens.
    max_output_tokens = max(16, min(max_output_tokens, 1200))

    return AgentConfig(
        provider=provider,
        model=model,
        max_output_tokens=max_output_tokens,
        has_openai_key=bool(os.getenv("OPENAI_API_KEY")),
    )


def get_public_status() -> dict:
    config = get_agent_config()

    return {
        "ok": True,
        "provider": config.provider,
        "model": config.model if config.provider == "openai" else "mock",
        "hasOpenAIKey": config.has_openai_key,
        "maxOutputTokens": config.max_output_tokens,
    }


def reset_conversation() -> None:
    global MESSAGE_HISTORY
    MESSAGE_HISTORY.clear()


def _compact_memory_text(value: object, max_length: int = 160) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)

    if len(text) <= max_length:
        return text

    return text[: max_length - 3].rstrip() + "..."


def _format_action_for_memory(action: dict) -> str:
    label = _compact_memory_text(action.get("label"), 64)
    detail = _compact_memory_text(action.get("detail"), 120)

    if label and detail:
        return f"{label}: {detail}"

    return label or detail


def _build_memory_context_summary() -> str:
    if get_memory_context is None:
        return ""

    try:
        context = get_memory_context()
    except Exception:
        return ""

    tasks = context.get("tasks", []) if isinstance(context, dict) else []
    recent_actions = context.get("recentActions", []) if isinstance(context, dict) else []
    notes = context.get("notes", []) if isinstance(context, dict) else []

    if not isinstance(tasks, list):
        tasks = []
    if not isinstance(recent_actions, list):
        recent_actions = []
    if not isinstance(notes, list):
        notes = []

    open_tasks = [task for task in tasks if isinstance(task, dict) and not task.get("completedAt")]
    completed_tasks = [task for task in tasks if isinstance(task, dict) and task.get("completedAt")]
    saved_notes = [note for note in notes if isinstance(note, dict) and note.get("content")]
    actions = [action for action in recent_actions if isinstance(action, dict) and action.get("label")]

    lines: list[str] = []

    if open_tasks:
        task_text = "; ".join(
            _compact_memory_text(task.get("title"), 120)
            for task in open_tasks[:5]
            if _compact_memory_text(task.get("title"), 120)
        )
        if task_text:
            lines.append(f"Open tasks: {task_text}.")

    if completed_tasks:
        completed_text = "; ".join(
            _compact_memory_text(task.get("title"), 100)
            for task in completed_tasks[:3]
            if _compact_memory_text(task.get("title"), 100)
        )
        if completed_text:
            lines.append(f"Recently completed tasks: {completed_text}.")

    if saved_notes:
        note_text = " | ".join(
            _compact_memory_text(note.get("content"), 160)
            for note in saved_notes[:4]
            if _compact_memory_text(note.get("content"), 160)
        )
        if note_text:
            lines.append(f"Saved notes: {note_text}.")

    if actions:
        action_text = " | ".join(
            _format_action_for_memory(action)
            for action in actions[:6]
            if _format_action_for_memory(action)
        )
        if action_text:
            lines.append(f"Recent actions: {action_text}.")

    if not lines:
        return ""

    return "\n".join(f"- {line}" for line in lines)




def _message_wants_calendar_context(message: str) -> bool:
    text = (message or "").strip().lower()

    if not text:
        return False

    return bool(
        re.search(
            r"\b("
            r"calendar|schedule|agenda|event|events|meeting|meetings|appointment|appointments|"
            r"today|tomorrow|tonight|morning|afternoon|evening|busy|free|available|availability|"
            r"plan|plans|next|what should i do|what do i have|do i have anything|am i free|"
            r"continue|left off|working on"
            r")\b",
            text,
        )
    )


def _format_calendar_event_for_context(event: dict) -> str:
    title = _compact_memory_text(event.get("title") or "(No title)", 90)
    time = _compact_memory_text(event.get("time") or "Later", 32)
    location = _compact_memory_text(event.get("location"), 60)

    if location:
        return f"{time}: {title} at {location}"

    return f"{time}: {title}"


def _calendar_day_line(label: str, events: list[dict]) -> str:
    if not events:
        return f"{label}: no events found."

    event_text = "; ".join(
        _format_calendar_event_for_context(event)
        for event in events[:6]
        if isinstance(event, dict)
    )

    remaining_count = max(0, len(events) - 6)
    suffix = f"; plus {remaining_count} more" if remaining_count else ""

    return f"{label}: {event_text}{suffix}."


def _build_calendar_context_summary(message: str) -> str:
    if list_calendar_events is None or not _message_wants_calendar_context(message):
        return ""

    try:
        today_payload = list_calendar_events("today")
        tomorrow_payload = list_calendar_events("tomorrow")
    except Exception:
        return ""

    if not isinstance(today_payload, dict):
        today_payload = {}
    if not isinstance(tomorrow_payload, dict):
        tomorrow_payload = {}

    today_events = today_payload.get("events", [])
    tomorrow_events = tomorrow_payload.get("events", [])

    if not isinstance(today_events, list):
        today_events = []
    if not isinstance(tomorrow_events, list):
        tomorrow_events = []

    connected = bool(today_payload.get("connected") or tomorrow_payload.get("connected"))
    configured = bool(today_payload.get("configured") or tomorrow_payload.get("configured"))

    if not connected:
        status_message = (
            today_payload.get("message")
            or tomorrow_payload.get("message")
            or "Calendar is not connected."
        )
        if not configured:
            status_message = status_message or "Calendar is not configured."

        return f"- Calendar status: {_compact_memory_text(status_message, 180)}"

    lines = [
        _calendar_day_line("Today", today_events),
        _calendar_day_line("Tomorrow", tomorrow_events),
    ]

    return "\n".join(f"- {line}" for line in lines if line)


def _build_chat_input_messages(message: str) -> list[dict[str, str]]:
    # Keep recent context small for now.
    recent_history = MESSAGE_HISTORY[-10:]
    memory_summary = _build_memory_context_summary()
    calendar_summary = _build_calendar_context_summary(message)

    input_messages: list[dict[str, str]] = [
        {
            "role": "developer",
            "content": SYSTEM_PROMPT,
        }
    ]

    if memory_summary:
        input_messages.append(
            {
                "role": "developer",
                "content": f"{MEMORY_CONTEXT_PROMPT}\n\nSaved QMeet context:\n{memory_summary}",
            }
        )

    if calendar_summary:
        input_messages.append(
            {
                "role": "developer",
                "content": f"{CALENDAR_CONTEXT_PROMPT}\n\nQMeet calendar context:\n{calendar_summary}",
            }
        )

    input_messages.extend(recent_history)
    input_messages.append(
        {
            "role": "user",
            "content": message,
        }
    )

    return input_messages


async def generate_reply(message: str) -> str:
    config = get_agent_config()

    if config.provider == "mock":
        return mock_reply(message)

    if config.provider == "openai":
        return await openai_reply(message, config)

    raise AgentUserFacingError(
        f'Unsupported LLM_PROVIDER="{config.provider}". Use "mock" or "openai".'
    )


async def stream_reply(message: str) -> AsyncGenerator[str, None]:
    config = get_agent_config()

    if config.provider == "mock":
        async for chunk in mock_stream_reply(message):
            yield chunk
        return

    if config.provider == "openai":
        async for chunk in openai_stream_reply(message, config):
            yield chunk
        return

    raise AgentUserFacingError(
        f'Unsupported LLM_PROVIDER="{config.provider}". Use "mock" or "openai".'
    )


async def mock_stream_reply(message: str) -> AsyncGenerator[str, None]:
    import asyncio

    reply = mock_reply(message)

    for word in reply.split(" "):
        yield word + " "
        await asyncio.sleep(0.04)


def mock_reply(message: str) -> str:
    text = message.strip()

    if not text:
        return "I did not receive a message."

    memory_summary = _build_memory_context_summary()
    calendar_summary = _build_calendar_context_summary(text)
    wants_memory = re.search(
        r"\b(what should i do next|continue|left off|working on|tasks?|notes?|memory|remember)\b",
        text,
        flags=re.IGNORECASE,
    )
    wants_calendar = _message_wants_calendar_context(text)

    if (wants_memory or wants_calendar) and (memory_summary or calendar_summary):
        parts: list[str] = []

        if memory_summary:
            parts.append(
                f"Saved context: {_compact_memory_text(memory_summary.replace(chr(10), ' '), 360)}"
            )

        if calendar_summary:
            parts.append(
                f"Calendar: {_compact_memory_text(calendar_summary.replace(chr(10), ' '), 320)}"
            )

        return " ".join(parts)

    return (
        "QMeet backend is connected. "
        f'You said: "{text}". '
    )


async def openai_reply(message: str, config: AgentConfig) -> str:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise AgentUserFacingError(
            "OpenAI is selected, but OPENAI_API_KEY is missing in backend/.env."
        )

    client = AsyncOpenAI(api_key=api_key)

    input_messages = _build_chat_input_messages(message)

    try:
        response = await client.responses.create(
            model=config.model,
            input=input_messages,
            max_output_tokens=config.max_output_tokens,
        )
    except openai.AuthenticationError as exc:
        raise AgentUserFacingError(
            "OpenAI authentication failed. Check backend/.env and verify the API key."
        ) from exc
    except openai.RateLimitError as exc:
        raise AgentUserFacingError(
            "OpenAI rate limit or quota was reached. Check API billing, limits, or try again later."
        ) from exc
    except openai.APIConnectionError as exc:
        raise AgentUserFacingError(
            "Could not connect to OpenAI. Check your internet connection."
        ) from exc
    except openai.APIError as exc:
        raise AgentUserFacingError(
            "OpenAI returned an API error. Try again shortly."
        ) from exc

    reply = response.output_text.strip()

    if not reply:
        raise AgentUserFacingError("The model returned an empty response.")


    MESSAGE_HISTORY.append({"role": "user", "content": message})
    MESSAGE_HISTORY.append({"role": "assistant", "content": reply})

    return reply


async def openai_stream_reply(
    message: str,
    config: AgentConfig,
) -> AsyncGenerator[str, None]:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise AgentUserFacingError(
            "OpenAI is selected, but OPENAI_API_KEY is missing in backend/.env."
        )

    client = AsyncOpenAI(api_key=api_key)
    input_messages = _build_chat_input_messages(message)

    full_reply = ""

    try:
        stream = await client.responses.create(
            model=config.model,
            input=input_messages,
            max_output_tokens=config.max_output_tokens,
            stream=True,
        )

        async for event in stream:
            if event.type == "response.output_text.delta":
                delta = event.delta
                full_reply += delta
                yield delta

            elif event.type == "response.completed":
                break

            elif event.type == "response.failed":
                raise AgentUserFacingError("The model failed while generating a response.")

    except openai.AuthenticationError as exc:
        raise AgentUserFacingError(
            "OpenAI authentication failed. Check backend/.env and verify the API key."
        ) from exc
    except openai.RateLimitError as exc:
        raise AgentUserFacingError(
            "OpenAI rate limit or quota was reached. Check API billing, limits, or try again later."
        ) from exc
    except openai.APIConnectionError as exc:
        raise AgentUserFacingError(
            "Could not connect to OpenAI. Check your internet connection."
        ) from exc
    except openai.APIError as exc:
        raise AgentUserFacingError(
            "OpenAI returned an API error. Try again shortly."
        ) from exc

    full_reply = full_reply.strip()

    if full_reply:
        MESSAGE_HISTORY.append({"role": "user", "content": message})
        MESSAGE_HISTORY.append({"role": "assistant", "content": full_reply})