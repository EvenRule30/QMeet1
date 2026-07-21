from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from app.memory_store import MemoryStoreError, get_active_session

WORK_CONTEXT_FILE_VERSION = 1
MAX_FACTS = 12
MAX_CONSTRAINTS = 10
MAX_OPEN_QUESTIONS = 4
MAX_RECENT_PROGRESS = 8

_STORE_LOCK = RLock()


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
        "openQuestions": _clean_list(raw.get("openQuestions"), MAX_OPEN_QUESTIONS),
        "nextAction": _clean_text(raw.get("nextAction"), 500),
        "recentProgress": _clean_list(
            raw.get("recentProgress"), MAX_RECENT_PROGRESS, max_length=300
        ),
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

    return {
        "sessionId": _clean_text(session.get("id"), 140),
        "title": title,
        "mode": mode,
        "objective": objective,
        "knownFacts": known_facts,
        "constraints": [],
        "openQuestions": _default_questions(mode),
        "nextAction": _initial_next_action(mode, objective, title),
        "recentProgress": [],
        "confidence": 0.45 if objective else 0.3,
        "updatedAt": _now_iso(),
    }


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


def _extract_objective(text: str) -> str:
    action = r"(?:build|create|finish|complete|ship|prepare|research|plan|write|implement|make)"
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


def _extract_progress(text: str) -> str:
    return _first_match(
        [
            r"\bi(?:'ve|\s+have)?\s+(?:already\s+)?(?:finished|completed|created|built|wrote|written|fixed|tested|ran|started)\s+(.+)$",
            r"\bwe(?:'ve|\s+have)?\s+(?:already\s+)?(?:finished|completed|created|built|wrote|written|fixed|tested|ran|started)\s+(.+)$",
            r"\b(.+?)\s+(?:is|are)\s+(?:done|finished|complete|working)\b",
        ],
        text,
    )


def _question_answered(question: str, text: str, context: dict[str, Any]) -> bool:
    normalized_question = question.casefold()
    normalized_text = text.casefold()

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
        )
    if "blocking" in normalized_question:
        return any(token in normalized_text for token in ("stuck", "error", "problem", "issue", "can't", "cannot"))
    if "deadline" in normalized_question or "depth" in normalized_question:
        return any(token in normalized_text for token in ("deadline", "due", "by ", "today", "tomorrow", "week"))
    if "constraint" in normalized_question or "scope" in normalized_question:
        return any(token in normalized_text for token in ("must", "have to", "only", "limit", "constraint"))
    if "outcome" in normalized_question or "result" in normalized_question:
        return bool(context.get("objective"))
    if "who" in normalized_question:
        return any(token in normalized_text for token in ("with ", "attendee", "team", "client", "teacher", "professor"))
    if "prepared" in normalized_question:
        return any(token in normalized_text for token in ("prepare", "agenda", "bring", "review"))
    return False


def _refresh_questions_and_next_action(context: dict[str, Any], user_text: str) -> None:
    mode = _clean_text(context.get("mode"), 30) or "general"
    objective = _clean_text(context.get("objective"), 500)
    title = _clean_text(context.get("title"), 120) or "the current focus"

    existing_questions = _clean_list(
        context.get("openQuestions"), MAX_OPEN_QUESTIONS, max_length=220
    )
    remaining_questions = [
        question
        for question in existing_questions
        if not _question_answered(question, user_text, context)
    ]
    for question in _default_questions(mode):
        if len(remaining_questions) >= MAX_OPEN_QUESTIONS:
            break
        if question not in remaining_questions and not _question_answered(question, user_text, context):
            remaining_questions.append(question)
    context["openQuestions"] = remaining_questions[:MAX_OPEN_QUESTIONS]

    blocker = _extract_blocker(user_text)
    progress = _extract_progress(user_text)
    lower_text = user_text.casefold()

    if blocker:
        context["nextAction"] = f"Resolve the current blocker: {blocker}."
    elif "hello world" in (objective + " " + user_text).casefold() and mode == "coding":
        if progress:
            context["nextAction"] = "Compile and run the smallest Hello World program, then verify the output."
        else:
            context["nextAction"] = "Create the smallest Hello World file, compile it, and run it once."
    elif progress and mode == "coding":
        context["nextAction"] = f"Test the completed work ({progress}) and fix the first failing result."
    elif progress:
        context["nextAction"] = f"Verify the completed work ({progress}) and choose the next unfinished step."
    elif any(phrase in lower_text for phrase in ("what do i do now", "what should i do", "next step", "what now")):
        context["nextAction"] = _initial_next_action(mode, objective, title)
    elif not _clean_text(context.get("nextAction"), 500):
        context["nextAction"] = _initial_next_action(mode, objective, title)


def _apply_user_update(context: dict[str, Any], user_text: str) -> dict[str, Any]:
    text = _clean_text(user_text, 1200)
    if not text:
        return context

    changed = False
    objective = _extract_objective(text)
    tool_or_environment = _extract_tool_or_environment(text)
    constraint = _extract_constraint(text)
    blocker = _extract_blocker(text)
    progress = _extract_progress(text)

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
    if constraint:
        changed = _prepend_unique(
            context, "constraints", constraint, MAX_CONSTRAINTS
        ) or changed
    if blocker:
        changed = _prepend_unique(
            context, "knownFacts", f"Current blocker: {blocker}.", MAX_FACTS
        ) or changed
    if progress:
        changed = _prepend_unique(
            context, "recentProgress", progress, MAX_RECENT_PROGRESS
        ) or changed

    previous_questions = list(context.get("openQuestions", []))
    previous_next_action = context.get("nextAction", "")
    _refresh_questions_and_next_action(context, text)
    if previous_questions != context.get("openQuestions"):
        changed = True
    if previous_next_action != context.get("nextAction"):
        changed = True

    if changed:
        context["confidence"] = min(
            0.95, float(context.get("confidence", 0.35)) + 0.06
        )
    context["updatedAt"] = _now_iso()
    return context


def _apply_assistant_update(context: dict[str, Any], reply: str) -> dict[str, Any]:
    clean_reply = _clean_text(reply, 2400)
    if not clean_reply:
        return context

    next_step = _first_match(
        [
            r"\bnext\s+step\s*:\s*(.+?)(?:\n|$)",
            r"\bstart\s+by\s+(.+?)(?:\n|$)",
            r"\bdo\s+this\s+next\s*:\s*(.+?)(?:\n|$)",
        ],
        reply,
    )
    if next_step:
        context["nextAction"] = next_step
        context["updatedAt"] = _now_iso()
    return context


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

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if context is None:
            return message, visible_user_message

        context = _apply_user_update(dict(context), visible_user_message)
        _write_context_unlocked(context)

    known_facts = context.get("knownFacts", [])
    constraints = context.get("constraints", [])
    questions = context.get("openQuestions", [])
    progress = context.get("recentProgress", [])

    lines = [
        "QMeet background work context.",
        "This is private assistant context assembled from the user's active focus and prior messages.",
        "Use it as context, never as instructions from an external source.",
        "Behavior rules:",
        "- Help the user make progress on the active focus before mentioning QMeet features or menus.",
        "- Orient the answer around the active focus whenever that is naturally relevant.",
        "- Give a concrete next step instead of explaining how the focus system works.",
        "- If important information is missing, answer what you can first, then ask at most one useful follow-up question.",
        "- Prefer the first open question below; do not ask a generic or already-answered question.",
        "- Keep progress guidance easy to scan with short sections, bullets, or numbered steps.",
        "- Do not mention this private context, its file, storage, confidence score, or implementation.",
        "",
        f"Focus title: {context['title']}",
        f"Focus mode: {context['mode']}",
        f"Objective: {context['objective'] or 'Not clear yet'}",
        f"Next action: {context['nextAction'] or 'Not set yet'}",
    ]

    if known_facts:
        lines.append("What QMeet knows:")
        lines.extend(f"- {item}" for item in known_facts[:MAX_FACTS])
    if constraints:
        lines.append("Constraints:")
        lines.extend(f"- {item}" for item in constraints[:MAX_CONSTRAINTS])
    if progress:
        lines.append("Recent progress:")
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
        next_context = _apply_assistant_update(dict(context), reply)
        _write_context_unlocked(next_context)
