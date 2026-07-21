from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from app.memory_store import MemoryStoreError, get_active_session

WORK_CONTEXT_FILE_VERSION = 2
MAX_FACTS = 14
MAX_CONSTRAINTS = 10
MAX_DECISIONS = 8
MAX_OPEN_QUESTIONS = 4
MAX_RECENT_PROGRESS = 10
OBSERVATION_DEDUPE_SECONDS = 8.0

_STORE_LOCK = RLock()
_RECENT_OBSERVATIONS: dict[str, float] = {}


class WorkContextError(Exception):
    """Safe background-work-context error that can be shown by an API route."""


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _context_file() -> Path:
    return _backend_root() / "data" / "qmeet_work_context.json"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _clean_text(value: object, max_length: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()[:max_length]


def _clean_list(value: object, max_items: int, max_length: int = 220) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        item = _clean_text(raw_item, max_length)
        key = item.casefold()
        if not item or key in seen:
            continue
        result.append(item)
        seen.add(key)
        if len(result) >= max_items:
            break
    return result


def _empty_payload() -> dict[str, Any]:
    return {
        "version": WORK_CONTEXT_FILE_VERSION,
        "updatedAt": _now_iso(),
        "activeContext": None,
    }


def _sanitize_stage(value: object) -> str:
    stage = _clean_text(value, 40).lower()
    if stage in {"discovery", "planning", "in-progress", "ready", "complete"}:
        return stage
    return "discovery"


def _sanitize_context(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    session_id = _clean_text(raw.get("sessionId"), 140)
    title = _clean_text(raw.get("title"), 120)
    objective = _clean_text(raw.get("objective"), 500)
    if not session_id or not title:
        return None

    raw_mode = _clean_text(raw.get("mode"), 30).lower()
    mode = raw_mode if raw_mode in {
        "general",
        "coding",
        "meeting",
        "planning",
        "research",
        "personal",
    } else "general"

    confidence_value = raw.get("confidence", 0.35)
    if isinstance(confidence_value, bool) or not isinstance(confidence_value, (int, float)):
        confidence = 0.35
    else:
        confidence = max(0.0, min(1.0, float(confidence_value)))

    return {
        "sessionId": session_id,
        "title": title,
        "mode": mode,
        "objective": objective,
        "knownFacts": _clean_list(raw.get("knownFacts"), MAX_FACTS),
        "constraints": _clean_list(raw.get("constraints"), MAX_CONSTRAINTS),
        "decisions": _clean_list(raw.get("decisions"), MAX_DECISIONS, max_length=300),
        "openQuestions": _clean_list(raw.get("openQuestions"), MAX_OPEN_QUESTIONS),
        "nextAction": _clean_text(raw.get("nextAction"), 500),
        "recentProgress": _clean_list(
            raw.get("recentProgress"), MAX_RECENT_PROGRESS, max_length=300
        ),
        "stage": _sanitize_stage(raw.get("stage")),
        "confidence": confidence,
        "updatedAt": _clean_text(raw.get("updatedAt"), 80) or _now_iso(),
    }


def _read_payload_unlocked() -> dict[str, Any]:
    path = _context_file()
    if not path.exists():
        return _empty_payload()

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkContextError(f"QMeet work-context file is invalid JSON: {path}") from exc
    except Exception as exc:
        raise WorkContextError("QMeet could not read its background work context.") from exc

    if not isinstance(parsed, dict):
        return _empty_payload()

    return {
        "version": WORK_CONTEXT_FILE_VERSION,
        "updatedAt": _clean_text(parsed.get("updatedAt"), 80) or _now_iso(),
        "activeContext": _sanitize_context(parsed.get("activeContext")),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            json.dump(payload, tmp_file, indent=2)
            tmp_file.write("\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _write_context_unlocked(context: dict[str, Any] | None) -> dict[str, Any]:
    payload = {
        "version": WORK_CONTEXT_FILE_VERSION,
        "updatedAt": _now_iso(),
        "activeContext": _sanitize_context(context),
    }
    try:
        _atomic_write_json(_context_file(), payload)
    except WorkContextError:
        raise
    except Exception as exc:
        raise WorkContextError("QMeet could not save its background work context.") from exc
    return payload


def _active_session() -> dict[str, Any] | None:
    try:
        response = get_active_session()
    except MemoryStoreError as exc:
        raise WorkContextError(str(exc)) from exc
    except Exception as exc:
        raise WorkContextError("QMeet could not load the active focus session.") from exc

    session = response.get("activeSession") if isinstance(response, dict) else None
    return session if isinstance(session, dict) else None


def _default_questions(mode: str) -> list[str]:
    questions_by_mode = {
        "coding": [
            "What does the project need to do?",
            "What language, framework, or environment are you using?",
            "What is blocking progress right now?",
        ],
        "meeting": [
            "What outcome should this meeting produce?",
            "Who needs to be involved?",
            "What needs to be prepared beforehand?",
        ],
        "research": [
            "What exact question should the research answer?",
            "What deadline or depth is required?",
            "Are there source or scope constraints?",
        ],
        "planning": [
            "What outcome should the plan achieve?",
            "What deadline are you working toward?",
            "What constraints shape the plan?",
        ],
        "personal": [
            "What result would make this focus successful?",
            "Is there a deadline or important constraint?",
        ],
        "general": [
            "What result would make this focus successful?",
            "What is the most important constraint?",
        ],
    }
    return questions_by_mode.get(mode, questions_by_mode["general"])


def _initial_next_action(mode: str, objective: str, title: str) -> str:
    subject = objective or title
    if mode == "coding":
        return f"Clarify the smallest working version of {subject}."
    if mode == "meeting":
        return f"Define the decision or outcome needed from {subject}."
    if mode == "research":
        return f"Turn {subject} into one precise research question."
    if mode == "planning":
        return f"Define the desired outcome and first milestone for {subject}."
    return f"Define the next concrete result for {subject}."


def _context_from_session(session: dict[str, Any]) -> dict[str, Any]:
    title = _clean_text(session.get("title"), 120) or "Current focus"
    objective = _clean_text(session.get("goal"), 500)
    raw_mode = _clean_text(session.get("mode"), 30).lower()
    mode = raw_mode if raw_mode in {
        "general",
        "coding",
        "meeting",
        "planning",
        "research",
        "personal",
    } else "general"

    known_facts = [f"The current focus is {title}."]
    if objective:
        known_facts.append(f"The current objective is {objective}.")

    context = {
        "sessionId": _clean_text(session.get("id"), 140),
        "title": title,
        "mode": mode,
        "objective": objective,
        "knownFacts": known_facts,
        "constraints": [],
        "decisions": [],
        "openQuestions": [],
        "nextAction": _initial_next_action(mode, objective, title),
        "recentProgress": [],
        "stage": "planning" if objective else "discovery",
        "confidence": 0.45 if objective else 0.3,
        "updatedAt": _now_iso(),
    }
    _refresh_questions_and_next_action(context, "")
    return context


def _sync_with_active_session_unlocked() -> dict[str, Any] | None:
    session = _active_session()
    payload = _read_payload_unlocked()
    current = payload.get("activeContext")

    if not session:
        if current is not None:
            _write_context_unlocked(None)
        return None

    session_id = _clean_text(session.get("id"), 140)
    if not session_id:
        return None

    if not isinstance(current, dict) or current.get("sessionId") != session_id:
        context = _context_from_session(session)
        _write_context_unlocked(context)
        return context

    context = dict(current)
    title = _clean_text(session.get("title"), 120)
    goal = _clean_text(session.get("goal"), 500)
    mode = _clean_text(session.get("mode"), 30).lower()

    changed = False
    if title and context.get("title") != title:
        context["title"] = title
        changed = True
    if mode in {"general", "coding", "meeting", "planning", "research", "personal"}:
        if context.get("mode") != mode:
            context["mode"] = mode
            changed = True
    if goal and context.get("objective") != goal:
        context["objective"] = goal
        _prepend_unique(context, "knownFacts", f"The current objective is {goal}.", MAX_FACTS)
        changed = True

    if changed:
        context["updatedAt"] = _now_iso()
        context["confidence"] = min(0.95, float(context.get("confidence", 0.35)) + 0.08)
        _refresh_questions_and_next_action(context, "")
        _write_context_unlocked(context)

    return _sanitize_context(context)


def _prepend_unique(
    context: dict[str, Any], key: str, value: str, max_items: int
) -> bool:
    clean_value = _clean_text(value, 300)
    if not clean_value:
        return False

    existing = _clean_list(context.get(key), max_items, max_length=300)
    clean_key = clean_value.casefold()
    if any(item.casefold() == clean_key for item in existing):
        return False

    context[key] = [clean_value, *existing][:max_items]
    return True


def _extract_visible_user_message(message: str) -> str:
    marker = "Current user message:"
    if marker in message:
        return message.rsplit(marker, 1)[1].strip()
    return message.strip()


def _sentence_fragment(value: str, max_length: int = 220) -> str:
    value = _clean_text(value, max_length)
    return value.rstrip(" .!?;:")


def _first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _sentence_fragment(match.group(1))
    return ""


def _focus_person(context: dict[str, Any]) -> str:
    title = _clean_text(context.get("title"), 120)
    candidates = re.findall(r"\b[A-Z][a-z]{2,}\b", title)
    excluded = {
        "Current",
        "Focus",
        "Giving",
        "Getting",
        "Planning",
        "Preparing",
        "Working",
        "Researching",
        "Building",
        "Creating",
        "Finishing",
    }
    for candidate in candidates:
        if candidate not in excluded:
            return candidate
    return ""


def _resolve_person(raw_subject: str, context: dict[str, Any]) -> str:
    subject = _sentence_fragment(raw_subject, 80)
    if subject.casefold() in {"he", "him", "his", "she", "her", "hers", "they", "them", "their"}:
        return _focus_person(context) or "The other person"
    return subject


def _extract_objective(text: str) -> str:
    action = r"(?:build|create|finish|complete|ship|prepare|research|plan|write|implement|make|give|buy|organize|arrange)"
    return _first_match(
        [
            r"\b(?:the\s+)?(?:assignment|project|goal|objective)\s+(?:is(?:\s+to)?|needs?\s+to)\s+(.+)$",
            r"\bi(?:'m|\s+am)\s+trying\s+to\s+(.+)$",
            rf"\bi\s+(?:want|need|have)\s+to\s+({action}\b.+)$",
            rf"\bwe\s+(?:want|need|have)\s+to\s+({action}\b.+)$",
        ],
        text,
    )


def _extract_tool_or_environment(text: str) -> str:
    return _first_match(
        [
            r"\bi(?:'m|\s+am)\s+using\s+(.+)$",
            r"\bi\s+use\s+(.+)$",
            r"\bwe(?:'re|\s+are)\s+using\s+(.+)$",
            r"\bthis\s+(?:has|needs)\s+to\s+use\s+(.+)$",
        ],
        text,
    )


def _extract_constraint(text: str) -> str:
    return _first_match(
        [
            r"\bi\s+(?:must|have\s+to|need\s+to)\s+use\s+(.+)$",
            r"\bit\s+(?:must|has\s+to|needs\s+to)\s+(.+)$",
            r"\bthe\s+(?:deadline|limit|constraint)\s+is\s+(.+)$",
            r"\bi\s+only\s+have\s+(.+)$",
        ],
        text,
    )


def _extract_blocker(text: str) -> str:
    return _first_match(
        [
            r"\bi(?:'m|\s+am)\s+stuck\s+(?:on|with|at)\s+(.+)$",
            r"\bthe\s+(?:problem|issue|error|blocker)\s+is\s+(.+)$",
            r"\bit\s+(?:fails|breaks|crashes)\s+(?:when|because|with)?\s*(.+)$",
            r"\bi\s+can(?:not|'t)\s+(.+)$",
        ],
        text,
    )


def _extract_relationship(text: str, context: dict[str, Any]) -> str:
    patterns = [
        r"\bmy\s+relationship\s+with\s+([A-Z][a-z]+)\s+is\s+(?:that\s+)?(?:he\s+is|she\s+is|they\s+are)?\s*(.+)$",
        r"\b([A-Z][a-z]+)\s+is\s+my\s+(.+)$",
        r"\b(he|she|they)\s+(?:is|are)\s+my\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        person = _resolve_person(match.group(1), context)
        relationship = _sentence_fragment(match.group(2), 140)
        relationship = re.sub(r"^(?:a|an|the|my)\s+", "", relationship, flags=re.IGNORECASE)
        if person and relationship:
            return f"{person} is the user's {relationship}."
    return ""


def _extract_preference(text: str, context: dict[str, Any]) -> str:
    match = re.search(
        r"\b(he|she|they|[A-Z][a-z]+)\s+(?:really\s+)?(?:likes?|loves?|prefers?)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    person = _resolve_person(match.group(1), context)
    raw_preference = re.split(
        r"(?:[.?!,]\s*)?(?:can|could|would|will)\s+you\b|(?:[.?!,]\s*)?help\s+me\b",
        match.group(2),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    preference = _sentence_fragment(raw_preference, 180)
    if not person or not preference:
        return ""
    return f"{person} likes {preference}."


def _extract_deadline(text: str, context: dict[str, Any]) -> str:
    person = _focus_person(context)
    birthday_match = re.search(
        r"\bbirthday(?:\s+which)?\s+is\s+(in\s+\d+\s+days?|today|tomorrow|this\s+week|next\s+week|on\s+.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if birthday_match:
        timing = _sentence_fragment(birthday_match.group(1), 120)
        prefix = f"{person}'s" if person else "The"
        return f"{prefix} birthday is {timing}."

    generic_match = re.search(
        r"\b(?:it|this|the\s+event|the\s+project|the\s+assignment)\s+is\s+(?:due\s+)?(in\s+\d+\s+days?|today|tomorrow|this\s+week|next\s+week|on\s+.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if generic_match:
        return f"The focus deadline is {_sentence_fragment(generic_match.group(1), 120)}."
    return ""


def _is_gift_or_flower_focus(context: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            _clean_text(context.get("title"), 120),
            _clean_text(context.get("objective"), 500),
            " ".join(_clean_list(context.get("knownFacts"), MAX_FACTS, 300)),
        ]
    ).casefold()
    return any(token in haystack for token in ("flower", "bouquet", "birthday gift", "lilies", "lillies"))


def _extract_decision(text: str, context: dict[str, Any]) -> str:
    lower = text.casefold()
    gift_focus = _is_gift_or_flower_focus(context)

    if re.search(r"\b(?:this|that)\s+is\s+perfect\b", lower):
        if gift_focus and any(token in lower for token in ("message", "wording", "card")):
            return "The birthday message has been chosen."
        if gift_focus:
            return "The most recent birthday message or plan was accepted."
        return "The most recent proposed plan was accepted."

    if re.search(r"\bwe(?:'re|\s+are)?\s+(?:already\s+)?using\s+(?:your\s+)?(?:old|previous)\s+message\b", lower):
        return "The birthday message has been chosen."

    chosen = _first_match(
        [
            r"\b(?:i|we)\s+(?:decided|chose|selected)\s+(?:on|to\s+use)?\s*(.+)$",
            r"\b(?:i|we)(?:'re|\s+are)?\s+going\s+with\s+(.+)$",
            r"\b(?:i|we)(?:'ll|\s+will)\s+use\s+(.+)$",
        ],
        text,
    )
    if chosen:
        return f"The user chose {chosen}."
    return ""


def _extract_progress_items(text: str, context: dict[str, Any]) -> list[str]:
    lower = text.casefold()
    items: list[str] = []

    if re.search(r"\b(?:i|we)\s+(?:got|bought|purchased|ordered|picked\s+up|collected)\s+(?:the\s+)?flowers?\b", lower):
        items.append("The flowers have been obtained.")

    if re.search(r"\b(?:i|we)\s+(?:gave|delivered|handed|presented)\s+(?:the\s+)?flowers?\s+(?:to\s+)?(?:him|her|them|[A-Z][a-z]+)?\b", text, flags=re.IGNORECASE):
        person = _focus_person(context)
        target = f" to {person}" if person else ""
        items.append(f"The flowers were given{target}.")

    if re.search(r"\b(?:i|we)\s+(?:wrote|finalized|finished|chose|selected|approved)\s+(?:the\s+)?(?:birthday\s+)?(?:message|card|note)\b", lower):
        items.append("The birthday message has been finalized.")

    if re.search(r"\b(?:i\s+am|i'm|we\s+are|we're)\s+done\s+with\s+(?:this|the\s+focus|the\s+project)\b", lower):
        items.append("The user said the focus is complete.")

    generic = _first_match(
        [
            r"\bi(?:'ve|\s+have)?\s+(?:already\s+)?(?:finished|completed|created|built|wrote|written|fixed|tested|ran|started)\s+(.+)$",
            r"\bwe(?:'ve|\s+have)?\s+(?:already\s+)?(?:finished|completed|created|built|wrote|written|fixed|tested|ran|started)\s+(.+)$",
            r"\b(.+?)\s+(?:is|are)\s+(?:done|finished|complete|working)\b",
        ],
        text,
    )
    if generic:
        generic_item = f"Completed: {generic}."
        if all(generic_item.casefold() != item.casefold() for item in items):
            items.append(generic_item)

    return items


def _context_text(context: dict[str, Any], key: str) -> str:
    return " ".join(_clean_list(context.get(key), 30, 300)).casefold()


def _has_flower_preference(context: dict[str, Any]) -> bool:
    facts = _clean_list(context.get("knownFacts"), MAX_FACTS, 300)
    flower_tokens = ("flower", "lil", "rose", "orchid", "sunflower", "bouquet", "tulip", "daisy")
    person = _focus_person(context).casefold()
    valid_prefixes = ["the other person likes ", "the other person prefers "]
    if person:
        valid_prefixes.extend((f"{person} likes ", f"{person} prefers "))
    for fact in facts:
        lowered = fact.casefold()
        if not any(token in lowered for token in flower_tokens):
            continue
        if any(lowered.startswith(prefix) for prefix in valid_prefixes):
            return True
    return False


def _has_relationship(context: dict[str, Any]) -> bool:
    facts = _context_text(context, "knownFacts")
    return "user's" in facts and any(
        token in facts for token in ("coworker", "friend", "partner", "family", "brother", "sister", "manager", "teacher", "classmate")
    )


def _has_deadline(context: dict[str, Any]) -> bool:
    constraints = _context_text(context, "constraints")
    return any(token in constraints for token in ("birthday", "deadline", "due", "today", "tomorrow", "days", "week", " on "))


def _has_progress(context: dict[str, Any], *phrases: str) -> bool:
    progress = _context_text(context, "recentProgress")
    return any(phrase.casefold() in progress for phrase in phrases)


def _has_decision(context: dict[str, Any], *phrases: str) -> bool:
    decisions = _context_text(context, "decisions")
    return any(phrase.casefold() in decisions for phrase in phrases)


def _question_answered(question: str, text: str, context: dict[str, Any]) -> bool:
    normalized_question = question.casefold()
    normalized_text = text.casefold()

    if "flowers does" in normalized_question or "flower" in normalized_question and "like" in normalized_question:
        return _has_flower_preference(context)
    if "relationship" in normalized_question:
        return _has_relationship(context)
    if "birthday" in normalized_question or "deadline" in normalized_question:
        return _has_deadline(context)
    if "when and where" in normalized_question and "give" in normalized_question:
        return _has_progress(context, "flowers were given")
    if "need to do" in normalized_question or "exact question" in normalized_question:
        return bool(context.get("objective")) or any(
            token in normalized_text
            for token in ("assignment is", "project is", "goal is", "need to", "have to")
        )
    if "language" in normalized_question or "framework" in normalized_question or "environment" in normalized_question:
        return any(
            token in normalized_text
            for token in (
                "using ",
                "use ",
                "java",
                "python",
                "javascript",
                "typescript",
                "react",
                "vite",
                "eclipse",
                "vscode",
                "visual studio",
                "terminal",
            )
        ) or "working with" in _context_text(context, "knownFacts")
    if "blocking" in normalized_question:
        return any(token in normalized_text for token in ("stuck", "error", "problem", "issue", "can't", "cannot"))
    if "depth" in normalized_question:
        return any(token in normalized_text for token in ("deadline", "due", "by ", "today", "tomorrow", "week"))
    if "constraint" in normalized_question or "scope" in normalized_question:
        return bool(context.get("constraints")) or any(token in normalized_text for token in ("must", "have to", "only", "limit", "constraint"))
    if "outcome" in normalized_question or "result" in normalized_question:
        return bool(context.get("objective"))
    if "who" in normalized_question:
        return _has_relationship(context) or any(token in normalized_text for token in ("with ", "attendee", "team", "client", "teacher", "professor"))
    if "prepared" in normalized_question:
        return any(token in normalized_text for token in ("prepare", "agenda", "bring", "review"))
    return False


def _specific_questions(context: dict[str, Any]) -> list[str]:
    if context.get("stage") == "complete":
        return []

    if not _is_gift_or_flower_focus(context):
        return []

    person = _focus_person(context) or "the recipient"
    questions: list[str] = []

    if not _has_flower_preference(context):
        questions.append(f"What flowers does {person} like?")
    if not _has_deadline(context):
        questions.append(f"When is {person}'s birthday?")
    if not _has_relationship(context):
        questions.append(f"What is your relationship with {person}?")
    if _has_progress(context, "flowers have been obtained") and not _has_progress(context, "flowers were given"):
        questions.append(f"When and where will you give {person} the flowers?")
    return questions


def _derive_stage(context: dict[str, Any]) -> str:
    if _has_progress(context, "focus is complete", "flowers were given"):
        return "complete"
    if _is_gift_or_flower_focus(context):
        flowers_ready = _has_progress(context, "flowers have been obtained")
        message_ready = _has_progress(context, "message has been finalized") or _has_decision(
            context, "message has been chosen", "message or plan was accepted"
        )
        if flowers_ready and message_ready:
            return "ready"
        if flowers_ready or _has_flower_preference(context):
            return "in-progress"
    if context.get("recentProgress"):
        return "in-progress"
    if context.get("objective"):
        return "planning"
    return "discovery"


def _gift_next_action(context: dict[str, Any]) -> str:
    person = _focus_person(context) or "the recipient"
    if _has_progress(context, "focus is complete", "flowers were given"):
        return "The focus is complete. End it when ready, saving only a brief outcome note if useful."

    flowers_ready = _has_progress(context, "flowers have been obtained")
    message_ready = _has_progress(context, "message has been finalized") or _has_decision(
        context, "message has been chosen", "message or plan was accepted"
    )

    if flowers_ready and message_ready:
        return f"Keep the flowers fresh and decide the exact moment to give them to {person}."
    if flowers_ready:
        return f"Finalize the birthday message and plan when and where to give the flowers to {person}."
    if _has_flower_preference(context):
        return "Choose a florist and obtain the preferred flowers before the birthday."
    return f"Find out what flowers {person} likes, then choose a florist."


def _refresh_questions_and_next_action(context: dict[str, Any], user_text: str) -> None:
    mode = _clean_text(context.get("mode"), 30) or "general"
    objective = _clean_text(context.get("objective"), 500)
    title = _clean_text(context.get("title"), 120) or "the current focus"

    context["stage"] = _derive_stage(context)

    existing_questions = _clean_list(
        context.get("openQuestions"), MAX_OPEN_QUESTIONS, max_length=220
    )
    unanswered_existing = [
        question
        for question in existing_questions
        if not _question_answered(question, user_text, context)
    ]

    ordered_candidates = [
        *_specific_questions(context),
        *unanswered_existing,
        *_default_questions(mode),
    ]
    remaining_questions: list[str] = []
    for question in ordered_candidates:
        if len(remaining_questions) >= MAX_OPEN_QUESTIONS:
            break
        if question in remaining_questions or _question_answered(question, user_text, context):
            continue
        remaining_questions.append(question)

    if context.get("stage") == "complete":
        remaining_questions = []
    context["openQuestions"] = remaining_questions[:MAX_OPEN_QUESTIONS]

    blocker = _extract_blocker(user_text)
    progress_items = _extract_progress_items(user_text, context)

    if blocker:
        context["nextAction"] = f"Resolve the current blocker: {blocker}."
    elif _is_gift_or_flower_focus(context):
        context["nextAction"] = _gift_next_action(context)
    elif "hello world" in (objective + " " + user_text).casefold() and mode == "coding":
        if progress_items:
            context["nextAction"] = "Compile and run the smallest Hello World program, then verify the output."
        else:
            context["nextAction"] = "Create the smallest Hello World file, compile it, and run it once."
    elif progress_items and mode == "coding":
        context["nextAction"] = "Test the completed work and fix the first failing result."
    elif progress_items:
        context["nextAction"] = "Verify the latest completed step and choose the next unfinished step."
    elif not _clean_text(context.get("nextAction"), 500):
        context["nextAction"] = _initial_next_action(mode, objective, title)


def _apply_user_update(context: dict[str, Any], user_text: str) -> tuple[dict[str, Any], bool]:
    text = _clean_text(user_text, 1400)
    if not text:
        return context, False

    changed = False
    objective = _extract_objective(text)
    tool_or_environment = _extract_tool_or_environment(text)
    constraint = _extract_constraint(text)
    blocker = _extract_blocker(text)
    relationship = _extract_relationship(text, context)
    preference = _extract_preference(text, context)
    deadline = _extract_deadline(text, context)
    decision = _extract_decision(text, context)
    progress_items = _extract_progress_items(text, context)

    if objective and context.get("objective") != objective:
        context["objective"] = objective
        changed = True
    if objective:
        changed = _prepend_unique(
            context, "knownFacts", f"The stated objective is {objective}.", MAX_FACTS
        ) or changed
    if tool_or_environment:
        changed = _prepend_unique(
            context,
            "knownFacts",
            f"The user is working with {tool_or_environment}.",
            MAX_FACTS,
        ) or changed
    if relationship:
        changed = _prepend_unique(context, "knownFacts", relationship, MAX_FACTS) or changed
    if preference:
        changed = _prepend_unique(context, "knownFacts", preference, MAX_FACTS) or changed
    if constraint:
        changed = _prepend_unique(context, "constraints", constraint, MAX_CONSTRAINTS) or changed
    if deadline:
        changed = _prepend_unique(context, "constraints", deadline, MAX_CONSTRAINTS) or changed
    if blocker:
        changed = _prepend_unique(
            context, "knownFacts", f"Current blocker: {blocker}.", MAX_FACTS
        ) or changed
    if decision:
        changed = _prepend_unique(context, "decisions", decision, MAX_DECISIONS) or changed
        if "message" in decision.casefold():
            changed = _prepend_unique(
                context, "recentProgress", "The birthday message has been finalized.", MAX_RECENT_PROGRESS
            ) or changed
    for progress in progress_items:
        changed = _prepend_unique(
            context, "recentProgress", progress, MAX_RECENT_PROGRESS
        ) or changed

    previous_questions = list(context.get("openQuestions", []))
    previous_next_action = context.get("nextAction", "")
    previous_stage = context.get("stage", "")
    _refresh_questions_and_next_action(context, text)
    if previous_questions != context.get("openQuestions"):
        changed = True
    if previous_next_action != context.get("nextAction"):
        changed = True
    if previous_stage != context.get("stage"):
        changed = True

    if changed:
        context["confidence"] = min(
            0.97, float(context.get("confidence", 0.35)) + 0.06
        )
        context["updatedAt"] = _now_iso()
    return context, changed


def _extract_assistant_next_action(reply: str) -> str:
    normalized = reply.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n")]

    for index, line in enumerate(lines):
        match = re.match(r"^(?:#{1,4}\s*)?(?:next\s+step|next\s+action)\s*:?[ \t]*(.*)$", line, flags=re.IGNORECASE)
        if not match:
            continue
        inline = _sentence_fragment(match.group(1), 300)
        if inline:
            return inline
        for following in lines[index + 1 : index + 4]:
            candidate = re.sub(r"^(?:[-*•]|\d+[.)])\s+", "", following).strip()
            candidate = _sentence_fragment(candidate, 300)
            if candidate:
                return candidate

    return _first_match(
        [
            r"\bstart\s+by\s+(.+?)(?:\n|$)",
            r"\bdo\s+this\s+next\s*:\s*(.+?)(?:\n|$)",
        ],
        normalized,
    )


def _assistant_action_conflicts_with_progress(context: dict[str, Any], action: str) -> bool:
    lower = action.casefold()
    if _has_progress(context, "flowers have been obtained") and any(
        phrase in lower
        for phrase in ("buy the flower", "get the flower", "order the flower", "pick up the flower", "choose the flower")
    ):
        return True
    if (
        _has_progress(context, "message has been finalized")
        or _has_decision(context, "message has been chosen", "message or plan was accepted")
    ) and any(phrase in lower for phrase in ("write the message", "draft the message", "finalize the message", "choose a message")):
        return True
    if _has_progress(context, "flowers were given") and any(
        phrase in lower for phrase in ("give the flower", "hand the flower", "present the flower")
    ):
        return True
    return False


def _apply_assistant_update(context: dict[str, Any], reply: str) -> tuple[dict[str, Any], bool]:
    if not _clean_text(reply, 2400):
        return context, False

    next_step = _extract_assistant_next_action(reply)
    if next_step and not _assistant_action_conflicts_with_progress(context, next_step):
        if context.get("nextAction") != next_step:
            context["nextAction"] = next_step
            context["updatedAt"] = _now_iso()
            return context, True
    return context, False


def _observation_fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _is_recent_duplicate_unlocked(text: str) -> bool:
    now = time.monotonic()
    expired = [
        fingerprint
        for fingerprint, seen_at in _RECENT_OBSERVATIONS.items()
        if now - seen_at > OBSERVATION_DEDUPE_SECONDS
    ]
    for fingerprint in expired:
        _RECENT_OBSERVATIONS.pop(fingerprint, None)

    fingerprint = _observation_fingerprint(text)
    seen_at = _RECENT_OBSERVATIONS.get(fingerprint)
    _RECENT_OBSERVATIONS[fingerprint] = now
    return seen_at is not None and now - seen_at <= OBSERVATION_DEDUPE_SECONDS


def observe_background_user_message(message: str, source: str = "unknown") -> dict[str, Any]:
    visible_user_message = _extract_visible_user_message(message)
    clean_message = _clean_text(visible_user_message, 1400)
    if not clean_message:
        return {"ok": True, "observed": False, "duplicate": False, "activeContext": None}

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if context is None:
            return {"ok": True, "observed": False, "duplicate": False, "activeContext": None}

        if _is_recent_duplicate_unlocked(clean_message):
            return {
                "ok": True,
                "observed": False,
                "duplicate": True,
                "source": source,
                "activeContext": context,
            }

        next_context, changed = _apply_user_update(dict(context), clean_message)
        if changed:
            _write_context_unlocked(next_context)
        return {
            "ok": True,
            "observed": changed,
            "duplicate": False,
            "source": source,
            "activeContext": _sanitize_context(next_context),
        }


def should_keep_focus_message_in_chat(message: str) -> bool:
    visible = _clean_text(_extract_visible_user_message(message), 800)
    if not visible:
        return False

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if context is None:
        return False

    lowered = visible.casefold()

    explicit_completion = [
        r"\b(?:i\s+am|i'm|we\s+are|we're)\s+done\s+with\s+(?:this|the\s+focus|the\s+project)\b",
        r"\b(?:end|stop|finish|close|wrap\s+up)\s+(?:the\s+|my\s+|this\s+)?(?:focus|focus\s+session|session)\b",
    ]
    if any(re.search(pattern, lowered) for pattern in explicit_completion):
        return False

    explicit_tool_request = [
        r"^(?:please\s+)?(?:open|show|close|clear|delete|read|save|create|start)\s+(?:the\s+|my\s+)?(?:notes?|memory|calendar|search|camera|focus)",
        r"^(?:please\s+)?(?:search|look\s+up|find)\b",
        r"\b(?:find|search\s+for|look\s+up)\b.+\b(?:nearby|near\s+me|online|website|store|florist)\b",
    ]
    if any(re.search(pattern, lowered) for pattern in explicit_tool_request):
        return False

    conversational_patterns = [
        r"\b(?:can|could|would|will)\s+you\s+help\s+me\b",
        r"\bhelp\s+me\s+(?:with|figure|choose|craft|write|plan|decide|understand|work\s+on)\b",
        r"\bwhat\s+(?:should|do)\s+i\s+do\b",
        r"\bwhat\s+now\b",
        r"\bhow\s+should\s+i\b",
        r"\b(?:this|that)\s+is\s+perfect\b",
        r"\blet(?:'s|\s+us)\s+move\s+on\b",
        r"\bwe(?:'re|\s+are)?\s+already\s+using\b",
        r"\bmy\s+relationship\s+with\b",
        r"\b(?:he|she|they)\s+(?:likes?|loves?|prefers?)\b",
        r"\b(?:i|we)\s+(?:got|bought|purchased|ordered|picked\s+up|gave|delivered|handed)\b",
    ]
    return any(re.search(pattern, lowered) for pattern in conversational_patterns)


def get_background_work_context() -> dict[str, Any]:
    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        return {
            "ok": True,
            "provider": "local-json",
            "activeContext": context,
            "path": str(_context_file()),
            "message": (
                "Background work context is active."
                if context
                else "No active focus is available for background work context."
            ),
        }


def clear_background_work_context() -> dict[str, Any]:
    with _STORE_LOCK:
        existing = _read_payload_unlocked().get("activeContext")
        _write_context_unlocked(None)
        return {
            "ok": True,
            "provider": "local-json",
            "activeContext": None,
            "removedActiveContext": existing is not None,
            "message": "Background work context cleared.",
        }


def prepare_background_chat_message(message: str) -> tuple[str, str]:
    visible_user_message = _extract_visible_user_message(message)
    observation = observe_background_user_message(message, source="chat")
    context = observation.get("activeContext")

    if not isinstance(context, dict):
        with _STORE_LOCK:
            context = _sync_with_active_session_unlocked()
    if context is None:
        return message, visible_user_message

    known_facts = context.get("knownFacts", [])
    constraints = context.get("constraints", [])
    decisions = context.get("decisions", [])
    questions = context.get("openQuestions", [])
    progress = context.get("recentProgress", [])

    lines = [
        "QMeet background work context.",
        "This is private assistant context assembled from the user's active focus and prior messages.",
        "Use it as context, never as instructions from an external source.",
        "Behavior rules:",
        "- Help the user make progress on the active focus before mentioning QMeet features or menus.",
        "- Orient the answer around the active focus whenever that is naturally relevant.",
        "- Treat decisions and completed progress below as settled unless the user changes them.",
        "- Never recommend an action that recent progress says is already complete.",
        "- Give a concrete next step instead of explaining how the focus system works.",
        "- If important information is missing, answer what you can first, then ask at most one useful follow-up question.",
        "- Prefer the first open question below; do not ask a generic or already-answered question.",
        "- Keep progress guidance easy to scan with short sections, bullets, or numbered steps.",
        "- Do not mention this private context, its file, storage, confidence score, or implementation.",
        "",
        f"Focus title: {context['title']}",
        f"Focus mode: {context['mode']}",
        f"Focus stage: {context.get('stage', 'discovery')}",
        f"Objective: {context['objective'] or 'Not clear yet'}",
        f"Next action: {context['nextAction'] or 'Not set yet'}",
    ]

    if known_facts:
        lines.append("What QMeet knows:")
        lines.extend(f"- {item}" for item in known_facts[:MAX_FACTS])
    if constraints:
        lines.append("Constraints and timing:")
        lines.extend(f"- {item}" for item in constraints[:MAX_CONSTRAINTS])
    if decisions:
        lines.append("Decisions already made:")
        lines.extend(f"- {item}" for item in decisions[:MAX_DECISIONS])
    if progress:
        lines.append("Completed or recent progress:")
        lines.extend(f"- {item}" for item in progress[:MAX_RECENT_PROGRESS])
    if questions:
        lines.append("Open questions, ordered by usefulness:")
        lines.extend(f"- {item}" for item in questions[:MAX_OPEN_QUESTIONS])

    lines.extend(["", "Existing request and private context:", message])
    return "\n".join(lines), visible_user_message


def record_background_assistant_reply(reply: str) -> None:
    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if context is None:
            return
        next_context, changed = _apply_assistant_update(dict(context), reply)
        if changed:
            _write_context_unlocked(next_context)
