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

WORK_CONTEXT_FILE_VERSION = 7
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


def _is_private_prompt_artifact(value: str) -> bool:
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (
            "qmeet automatic focus onboarding turn",
            "assistant-initiated follow-up after the user started a new background focus",
            "most useful unanswered question:",
            "focus title:",
            "focus mode:",
        )
    )


FOCUS_TYPES = {
    "general",
    "review",
    "presentation",
    "document",
    "coding",
    "research",
    "meeting",
    "gift",
    "planning",
    "creative",
}

QUESTION_TARGETS = {
    "objective",
    "subject",
    "audience",
    "successCriteria",
    "approach",
    "requirements",
    "deadline",
    "environment",
    "blocker",
}


def _sanitize_focus_type(value: object) -> str:
    focus_type = _clean_text(value, 40).lower()
    return focus_type if focus_type in FOCUS_TYPES else "general"


def _is_acceptance(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9']+", " ", value.casefold()).strip()
    if not normalized:
        return False
    return bool(
        normalized in {
            "sounds good", "looks good", "that works", "it works", "good",
            "great", "perfect", "excellent", "most excellent",
        }
        or re.fullmatch(
            r"(?:this|that|it|those|these|they)\s+(?:is|are|looks|look|sounds|sound)\s+"
            r"(?:really\s+|most\s+)?(?:good|great|perfect|excellent)(?:\s+thank\s+you)?",
            normalized,
        )
        or re.fullmatch(
            r"(?:i\s+)?(?:like|love)\s+(?:this|that|it|those|these|them)(?:\s+thank\s+you)?",
            normalized,
        )
    )


def _is_weak_acknowledgement(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9']+", " ", value.casefold()).strip()
    if not normalized:
        return True
    return normalized in {
        "yes", "yeah", "yep", "yup", "no", "nope", "ok", "okay", "sure",
        "thanks", "thank you", "please", "go ahead", "do it",
    } or _is_acceptance(value)


def _is_action_offer_question(question: str) -> bool:
    lowered = _clean_text(question, 320).casefold()
    return bool(
        re.search(
            r"^(?:would\s+you\s+like|do\s+you\s+want|want\s+me\s+to|"
            r"want\s+help|can\s+i|shall\s+i|should\s+i)\b",
            lowered,
        )
        or re.search(
            r"\b(?:would\s+you\s+like|want\s+me\s+to|want\s+help)\b",
            lowered,
        )
        or re.search(
            r"^(?:does|did)\s+(?:this|that|the\s+(?:draft|arrangement|version))\s+"
            r"(?:work|look|sound|feel)\b",
            lowered,
        )
        or "which would you prefer to tackle next" in lowered
    )


def _is_information_question(question: str) -> bool:
    clean = _clean_text(question, 320)
    if not clean.endswith("?") or _is_action_offer_question(clean):
        return False
    lowered = clean.casefold()
    return bool(
        re.match(
            r"^(?:what|who|which|how|when|where|why|is\s+there|are\s+there)\b",
            lowered,
        )
    )


def _sanitize_pending_question(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    target = _clean_text(value.get("target"), 40)
    question = _clean_text(value.get("question"), 240)
    if target not in QUESTION_TARGETS or not _is_information_question(question):
        return None
    return {"target": target, "question": question}


def _legacy_structured_fields(raw: dict[str, Any], facts: list[str]) -> dict[str, str]:
    title_text = _clean_text(raw.get("title"), 120).casefold()
    is_review = "review" in title_text
    structured = {
        "subject": _clean_text(raw.get("subject"), 300),
        "audience": _clean_text(raw.get("audience"), 300),
        "successCriteria": _clean_text(raw.get("successCriteria"), 500),
        "approach": _clean_text(raw.get("approach"), 300),
    }
    for fact in facts:
        candidate = _clean_text(fact, 300)
        lowered = candidate.casefold()
        if not structured["subject"]:
            match = re.match(
                r"(?:presentation topic|the presentation is about|review subject|subject)\s*:\s*(.+)$",
                candidate,
                flags=re.IGNORECASE,
            ) or re.match(r"the presentation is about\s+(.+)$", candidate, flags=re.IGNORECASE)
            if match:
                subject = _clean_text(match.group(1), 300).rstrip(".")
                subject = re.sub(
                    r"^i\s+want\s+(?:it|this|the\s+review)\s+to\s+be\s+(?:on|about)\s+",
                    "",
                    subject,
                    flags=re.IGNORECASE,
                ).strip()
                if subject.casefold().startswith("the book "):
                    subject = subject[9:].strip()
                structured["subject"] = subject
        if not structured["audience"]:
            match = re.match(
                r"(?:presentation audience/context|audience)\s*:\s*(.+)$",
                candidate,
                flags=re.IGNORECASE,
            ) or re.match(r"the presentation is for\s+(.+)$", candidate, flags=re.IGNORECASE) \
              or re.match(r"audience is\s+(.+)$", candidate, flags=re.IGNORECASE)
            if match:
                structured["audience"] = _clean_text(match.group(1), 300).rstrip(".")
        if not structured["successCriteria"]:
            match = re.match(
                r"(?:desired presentation outcome|success criteria|the presentation's key message is)\s*:\s*(.+)$",
                candidate,
                flags=re.IGNORECASE,
            )
            if match:
                value = _clean_text(match.group(1), 500).rstrip(".")
                if not _is_weak_acknowledgement(value):
                    if is_review and any(
                        token in value.casefold()
                        for token in ("strong argument", "clear example", "writing style", "personal perspective")
                    ):
                        structured["approach"] = re.sub(
                            r"^i\s+(?:want|prefer|would\s+like)\s+",
                            "",
                            value,
                            flags=re.IGNORECASE,
                        ).strip()
                    else:
                        structured["successCriteria"] = value
        if not structured["approach"] and lowered.startswith("preferred approach:"):
            structured["approach"] = candidate.split(":", 1)[1].strip().rstrip(".")
    return structured


def _is_structured_fact(value: str) -> bool:
    lowered = value.casefold().strip()
    return (
        lowered.startswith("the current focus is ")
        or lowered.startswith("the current objective is ")
        or lowered.startswith("presentation audience/context:")
        or lowered.startswith("presentation topic:")
        or lowered.startswith("desired presentation outcome:")
        or lowered.startswith("the presentation is for ")
        or lowered.startswith("the presentation is about ")
        or lowered.startswith("the presentation's key message is:")
        or lowered.startswith("audience:")
        or lowered.startswith("audience is ")
        or lowered.startswith("subject:")
        or lowered.startswith("success criteria:")
        or lowered.startswith("preferred approach:")
    )


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
    raw_source_mode = _clean_text(raw.get("sourceMode"), 30).lower()
    source_mode = raw_source_mode if raw_source_mode in {
        "general",
        "coding",
        "meeting",
        "planning",
        "research",
        "personal",
    } else mode

    confidence_value = raw.get("confidence", 0.35)
    if isinstance(confidence_value, bool) or not isinstance(confidence_value, (int, float)):
        confidence = 0.35
    else:
        confidence = max(0.0, min(1.0, float(confidence_value)))

    raw_facts = [
        item
        for item in _clean_list(raw.get("knownFacts"), MAX_FACTS, max_length=300)
        if not _is_private_prompt_artifact(item)
    ]
    structured = _legacy_structured_fields(raw, raw_facts)
    known_facts = [item for item in raw_facts if not _is_structured_fact(item)]

    focus_type = _sanitize_focus_type(raw.get("focusType"))
    if focus_type == "general":
        focus_type = _infer_focus_type_from_text(
            " ".join((title, objective, structured["subject"])), mode
        )
    if mode == "general" and focus_type in {"review", "presentation", "document", "planning", "creative"}:
        mode = "planning"

    return {
        "sessionId": session_id,
        "title": title,
        "mode": mode,
        "sourceMode": source_mode,
        "focusType": focus_type,
        "objective": objective,
        "sourceGoal": _clean_text(raw.get("sourceGoal"), 500),
        "subject": structured["subject"],
        "audience": structured["audience"],
        "successCriteria": structured["successCriteria"],
        "approach": structured["approach"],
        "lastAssistantArtifact": _clean_text(raw.get("lastAssistantArtifact"), 80),
        "pendingQuestion": _sanitize_pending_question(raw.get("pendingQuestion")),
        "knownFacts": known_facts,
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


def _infer_context_mode(raw_mode: str, title: str, objective: str) -> str:
    if raw_mode in {"coding", "meeting", "planning", "research", "personal"}:
        return raw_mode

    haystack = f"{title} {objective}".casefold()
    if any(token in haystack for token in (
        "code", "program", "software", "app", "website", "api", "database",
        "java", "python", "javascript", "typescript", "react", "bug", "debug",
    )):
        return "coding"
    if any(token in haystack for token in (
        "research", "paper", "essay", "sources", "literature review", "study",
    )):
        return "research"
    if any(token in haystack for token in (
        "presentation", "proposal", "plan", "roadmap", "strategy", "deadline",
        "event", "trip", "launch", "portfolio", "application", "book review",
        "movie review", "product review", "write a review", "writing a review",
        "song", "lyrics", "poem", "story", "screenplay", "creative writing",
    )):
        return "planning"
    if any(token in haystack for token in (
        "birthday", "gift", "flowers", "family", "friend", "coworker", "personal",
    )):
        return "personal"
    return "general"


def _infer_focus_type_from_text(text: str, mode: str = "general") -> str:
    haystack = text.casefold()
    if any(token in haystack for token in ("book review", "movie review", "film review", "product review", "write a review", "writing a review")):
        return "review"
    if any(token in haystack for token in (
        "song", "lyrics", "lyric", "poem", "poetry", "story", "screenplay",
        "script", "creative writing", "diss track", "chorus", "verse",
    )):
        return "creative"
    if any(token in haystack for token in ("presentation", "slide deck", "slides", "pitch deck")):
        return "presentation"
    if any(token in haystack for token in ("code", "program", "software", "app", "website", "api", "java", "python", "javascript", "typescript", "react")):
        return "coding"
    if any(token in haystack for token in ("birthday gift", "flowers", "bouquet", "present for", "gift for")):
        return "gift"
    if any(token in haystack for token in ("research", "literature review", "sources", "study question")):
        return "research"
    if any(token in haystack for token in ("report", "essay", "paper", "proposal", "article", "document")):
        return "document"
    if "meeting" in haystack:
        return "meeting"
    if mode == "coding":
        return "coding"
    if mode == "research":
        return "research"
    if mode == "meeting":
        return "meeting"
    if mode in {"planning", "personal"}:
        return "planning"
    return "general"


def _refresh_focus_type(context: dict[str, Any]) -> None:
    context["focusType"] = _infer_focus_type_from_text(
        " ".join(
            (
                _clean_text(context.get("title"), 120),
                _clean_text(context.get("objective"), 500),
                _clean_text(context.get("subject"), 300),
            )
        ),
        _clean_text(context.get("mode"), 30) or "general",
    )


def _context_from_session(session: dict[str, Any]) -> dict[str, Any]:
    title = _clean_text(session.get("title"), 120) or "Current focus"
    objective = _clean_text(session.get("goal"), 500)
    raw_mode = _clean_text(session.get("mode"), 30).lower()
    source_mode = raw_mode if raw_mode in {
        "general",
        "coding",
        "meeting",
        "planning",
        "research",
        "personal",
    } else "general"
    mode = _infer_context_mode(source_mode, title, objective)

    known_facts: list[str] = []

    context = {
        "sessionId": _clean_text(session.get("id"), 140),
        "title": title,
        "mode": mode,
        "sourceMode": source_mode,
        "objective": objective,
        "sourceGoal": objective,
        "focusType": _infer_focus_type_from_text(f"{title} {objective}", mode),
        "subject": "",
        "audience": "",
        "successCriteria": "",
        "approach": "",
        "lastAssistantArtifact": "",
        "pendingQuestion": None,
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

    # The first natural focus request often already contains useful context: a
    # deadline, language, tool, event, person, preference, or concrete outcome.
    # Seed the richer context from the session title and goal so Memory is useful
    # immediately instead of waiting for the user to repeat those details.
    seed_text = ". ".join(part for part in (title, objective) if part)
    if seed_text:
        context, _ = _apply_user_update(context, seed_text)
    else:
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
    raw_mode = _clean_text(session.get("mode"), 30).lower()
    source_mode = raw_mode if raw_mode in {
        "general", "coding", "meeting", "planning", "research", "personal"
    } else "general"
    previous_source_mode = _clean_text(context.get("sourceMode"), 30).lower()
    previous_source_goal = _clean_text(context.get("sourceGoal"), 500)

    changed = False
    if title and context.get("title") != title:
        context["title"] = title
        changed = True
    if source_mode != previous_source_mode:
        context["sourceMode"] = source_mode
        inferred_mode = _infer_context_mode(source_mode, title or context.get("title", ""), goal)
        if context.get("mode") != inferred_mode:
            context["mode"] = inferred_mode
        changed = True

    # Do not repeatedly replace a more precise conversational objective with the
    # broad goal used to start the session. A genuinely changed session goal is
    # still treated as an explicit update and becomes the new objective.
    if goal != previous_source_goal:
        context["sourceGoal"] = goal
        if goal:
            context["objective"] = goal
        changed = True
    elif goal and not _clean_text(context.get("objective"), 500):
        context["objective"] = goal
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
    clean_message = message.strip()
    lowered = clean_message.casefold()

    # Assistant-only focus onboarding is sent through the same chat endpoint as a
    # user turn. It is private generation context, not something the user said, and
    # must never be learned as a fact about the focus.
    assistant_only_markers = (
        "qmeet automatic focus onboarding turn.",
        "this is an assistant-initiated follow-up after the user started a new background focus.",
    )
    if any(marker in lowered for marker in assistant_only_markers):
        return ""

    marker = "Current user message:"
    if marker in message:
        return message.rsplit(marker, 1)[1].strip()
    return clean_message


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
    candidate = _first_match(
        [
            r"\bi(?:'m|\s+am)\s+using\s+(.+)$",
            r"\bi\s+use\s+(.+)$",
            r"\bwe(?:'re|\s+are)\s+using\s+(.+)$",
            r"\bthis\s+(?:has|needs)\s+to\s+use\s+(.+)$",
        ],
        text,
    )
    if not candidate:
        return ""

    # Decisions such as "we are using your old message" describe chosen work,
    # not a software tool or environment.
    if re.search(
        r"\b(?:message|wording|draft|note|card|plan|idea|suggestion|response|answer)\b",
        candidate,
        flags=re.IGNORECASE,
    ):
        return ""
    return candidate


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
        raw_person = _sentence_fragment(match.group(1), 80)
        if raw_person.casefold() in {
            "audience", "topic", "subject", "book", "review", "presentation",
            "goal", "result", "approach", "message", "project", "focus",
        }:
            continue
        person = _resolve_person(raw_person, context)
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
    day_count = r"(?:\d+|one|two|three|four|five|six|seven|a|an)"
    birthday_match = re.search(
        rf"\b(?:(?:his|her|their|[A-Z][a-z]+['’]s)\s+)?birthday(?:\s+which)?\s+is\s+(in\s+{day_count}\s+days?|today|tomorrow|this\s+week|next\s+week|on\s+.+?)(?:[.?!])?$",
        text,
        flags=re.IGNORECASE,
    )
    if birthday_match:
        timing = _sentence_fragment(birthday_match.group(1), 120)
        prefix = f"{person}'s" if person else "The"
        return f"{prefix} birthday is {timing}."

    generic_match = re.search(
        rf"\b(?:it|this|the\s+event|the\s+project|the\s+assignment)\s+is\s+(?:due\s+)?(in\s+{day_count}\s+days?|today|tomorrow|this\s+week|next\s+week|on\s+.+?)(?:[.?!])?$",
        text,
        flags=re.IGNORECASE,
    )
    if generic_match:
        return f"The focus deadline is {_sentence_fragment(generic_match.group(1), 120)}."

    # A naturally started focus often places its deadline directly inside the
    # objective: "finish the report by Friday" or "presentation due next week."
    inline_match = re.search(
        rf"\b(?:due(?:\s+by)?|by)\s+"
        rf"(today|tomorrow|tonight|this\s+week|next\s+week|next\s+month|"
        rf"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        rf"\d{{1,2}}[/-]\d{{1,2}}(?:[/-]\d{{2,4}})?|"
        rf"[A-Z][a-z]+\s+\d{{1,2}}(?:,\s+\d{{4}})?)(?:\b|[.?!])",
        text,
        flags=re.IGNORECASE,
    )
    if inline_match:
        return f"The focus deadline is {_sentence_fragment(inline_match.group(1), 120)}."

    relative_match = re.search(
        rf"\b(in\s+{day_count}\s+(?:hours?|days?|weeks?|months?))(?:\b|[.?!])",
        text,
        flags=re.IGNORECASE,
    )
    if relative_match:
        return f"The focus deadline is {_sentence_fragment(relative_match.group(1), 120)}."

    # Natural focus titles often omit the word "due": "presentation at work
    # next week" or "meeting tomorrow." Preserve that timing instead of
    # forcing the user to repeat it during onboarding.
    scheduled_match = re.search(
        r"\b(?:presentation|meeting|event|assignment|homework|report|paper|project|interview)\b"
        r".*?\b(today|tomorrow|tonight|this\s+week|next\s+week|next\s+month|"
        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        text,
        flags=re.IGNORECASE,
    )
    if scheduled_match:
        return f"The focus deadline or scheduled date is {_sentence_fragment(scheduled_match.group(1), 120)}."
    return ""


def _is_gift_or_flower_focus(context: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            _clean_text(context.get("title"), 120),
            _clean_text(context.get("objective"), 500),
            _clean_text(context.get("subject"), 300),
            _clean_text(context.get("successCriteria"), 500),
            " ".join(_clean_list(context.get("knownFacts"), MAX_FACTS, 300)),
        ]
    ).casefold()
    return any(token in haystack for token in ("flower", "bouquet", "birthday gift", "lilies", "lillies"))



def _is_presentation_focus(context: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            _clean_text(context.get("title"), 120),
            _clean_text(context.get("objective"), 500),
            _clean_text(context.get("subject"), 300),
            _clean_text(context.get("successCriteria"), 500),
            " ".join(_clean_list(context.get("knownFacts"), MAX_FACTS, 300)),
        ]
    ).casefold()
    return "presentation" in haystack or "slide deck" in haystack or "slides" in haystack


def _is_apology_presentation(context: dict[str, Any]) -> bool:
    if not _is_presentation_focus(context):
        return False
    haystack = " ".join(
        [
            _clean_text(context.get("objective"), 500),
            " ".join(_clean_list(context.get("knownFacts"), MAX_FACTS, 300)),
            " ".join(_clean_list(context.get("decisions"), MAX_DECISIONS, 300)),
        ]
    ).casefold()
    return any(
        token in haystack
        for token in (
            "apolog",
            "sorry",
            "take responsibility",
            "not repeat",
        )
    )


def _presentation_fact_flags(context: dict[str, Any]) -> tuple[bool, bool, bool]:
    facts = _context_text(context, "knownFacts")
    has_audience = "presentation is for " in facts or "presentation audience" in facts
    has_topic = "presentation is about " in facts or "presentation topic" in facts
    has_message = "presentation's key message" in facts or "desired presentation outcome" in facts
    return has_audience, has_topic, has_message


def _extract_presentation_details(text: str, context: dict[str, Any]) -> list[str]:
    if not _is_presentation_focus(context):
        return []

    facts: list[str] = []
    audience = ""
    topic = ""

    combined = re.search(
        r"\b(?:it(?:'s|\s+is)|the\s+presentation\s+is)\s+for\s+(.+?)\s+and\s+"
        r"(?:it(?:'s|\s+is)\s+)?(?:about|on)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if combined:
        audience = _sentence_fragment(combined.group(1), 140)
        topic = _sentence_fragment(combined.group(2), 220)
    else:
        audience = _first_match(
            [
                r"\b(?:it(?:'s|\s+is)|the\s+presentation\s+is)\s+for\s+(.+)$",
                r"\b(?:the\s+)?audience\s+is\s+(.+)$",
                r"\bi(?:'m|\s+am)\s+presenting\s+to\s+(.+)$",
            ],
            text,
        )
        topic = _first_match(
            [
                r"\b(?:it(?:'s|\s+is)|the\s+presentation\s+is)\s+(?:about|on)\s+(.+)$",
                r"\b(?:the\s+)?(?:topic|subject)\s+is\s+(.+)$",
            ],
            text,
        )

    if audience:
        facts.append(f"The presentation is for {audience}.")
    if topic:
        facts.append(f"The presentation is about {topic}.")
    return facts


def _extract_presentation_outcome(text: str, context: dict[str, Any]) -> str:
    if not _is_presentation_focus(context):
        return ""

    raw_outcome = _first_match(
        [
            r"\bi\s+want\s+(?:him|her|them|my\s+boss|the\s+boss|the\s+audience)\s+to\s+(?:know|understand|believe|remember|take\s+away)\s+(.+)$",
            r"\bi\s+want\s+the\s+(?:main\s+)?message\s+to\s+be\s+(.+)$",
            r"\b(?:the\s+)?(?:main|key)\s+message\s+is\s+(.+)$",
            r"\bsuccess\s+(?:means|would\s+mean)\s+(.+)$",
        ],
        text,
    )
    if not raw_outcome:
        return ""

    lowered = raw_outcome.casefold()
    if "sorry" in lowered or "apolog" in lowered:
        if any(token in lowered for token in ("won't", "will not", "not do", "never happen", "again")):
            return "Deliver a sincere apology and make clear that the inappropriate conduct will not happen again."
        return "Deliver a sincere apology and take responsibility for the inappropriate conduct."
    return f"Ensure the audience understands {raw_outcome}."


def _extract_assistant_progress_items(reply: str, context: dict[str, Any]) -> list[str]:
    lowered = reply.casefold()
    items: list[str] = []
    focus_type = _clean_text(context.get("focusType"), 40)

    if focus_type == "review":
        if "opening statement" in lowered and any(token in lowered for token in ("supporting point", "key point", "argument")):
            items.append("QMeet drafted an opening statement and supporting points for the review.")
        elif re.search(r"\bhere(?:'s|\s+is)\s+(?:a|the)\s+(?:draft|start)\b", lowered) and "review" in lowered:
            items.append("QMeet drafted part of the review.")
        return items

    if not _is_presentation_focus(context):
        return items
    if re.search(r"\b(?:here(?:'s|\s+is)|below\s+is)\s+(?:a|the)\s+draft\b", lowered) or re.search(
        r"\bdraft\s+for\s+(?:your|the)\s+(?:apology|presentation|statement)\b",
        lowered,
    ):
        label = "apology statement" if _is_apology_presentation(context) else "presentation draft"
        items.append(f"QMeet drafted the {label}.")
    if re.search(r"\b(?:specific|concrete)\s+(?:actions|steps)\b", lowered) and (
        "prevent" in lowered or "improve" in lowered
    ):
        items.append("QMeet proposed concrete improvement and prevention steps.")
    return items


def _extract_decision(text: str, context: dict[str, Any]) -> str:
    lower = text.casefold()
    gift_focus = _is_gift_or_flower_focus(context)
    accepted_proposal = bool(
        re.search(
            r"\b(?:this|that|it)\s+is\s+perfect\b|"
            r"\b(?:this|that|it)\s+(?:looks|sounds)\s+good\b|"
            r"\b(?:this|that|it)\s+works\b|"
            r"\b(?:let(?:'s|\s+us)|we(?:'ll|\s+will))\s+use\s+(?:this|that|it)\b",
            lower,
        )
    )

    if accepted_proposal:
        if gift_focus and any(token in lower for token in ("message", "wording", "card")):
            return "The birthday message has been chosen."
        if gift_focus:
            return "The most recent birthday message or plan was accepted."
        if _is_apology_presentation(context):
            return "The apology draft was approved."
        if _is_presentation_focus(context):
            return "The presentation draft was approved."
        return "The most recent proposed plan or draft was accepted."

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

    accepted_draft = bool(
        re.search(
            r"\b(?:this|that|it)\s+(?:is\s+perfect|looks\s+good|sounds\s+good|works)\b",
            lower,
        )
    )
    if accepted_draft and _is_apology_presentation(context):
        items.append("The apology statement has been finalized.")
    elif accepted_draft and _is_presentation_focus(context):
        items.append("The presentation draft has been approved.")

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


def _normalize_answer_text(value: str, target: str) -> str:
    answer = _sentence_fragment(value, 500).strip().rstrip(".?!")
    patterns_by_target = {
        "audience": [
            r"^(?:my|the)\s+audience\s+is\s+",
            r"^(?:it|this|that)(?:'s|\s+is)\s+for\s+",
            r"^for\s+",
        ],
        "subject": [
            r"^i\s+want\s+(?:it|this|the\s+review|the\s+presentation)\s+to\s+be\s+(?:on|about)\s+",
            r"^(?:it|this|that)(?:'s|\s+is)\s+(?:on|about)\s+",
            r"^(?:the\s+)?(?:topic|subject|book)\s+is\s+",
            r"^i(?:'m|\s+am)\s+reviewing\s+",
        ],
        "successCriteria": [
            r"^what\s+would\s+make\s+(?:it|this|the\s+focus)\s+successful(?:\s+is|\s+would\s+be|\s+as\s+if)?\s*",
            r"^(?:success|a\s+successful\s+result)\s+(?:means|would\s+mean|is)\s+",
            r"^it\s+would\s+be\s+successful\s+if\s+",
        ],
        "approach": [
            r"^i\s+(?:want|prefer|would\s+like)\s+(?:to\s+focus\s+on\s+)?",
            r"^(?:focus\s+on|use)\s+",
        ],
        "objective": [
            r"^(?:my|the)\s+(?:goal|objective)\s+is\s+",
            r"^i\s+(?:want|need)\s+to\s+",
        ],
    }
    for pattern in patterns_by_target.get(target, []):
        answer = re.sub(pattern, "", answer, flags=re.IGNORECASE).strip()
    if target == "subject" and answer.casefold().startswith("the book "):
        answer = answer[9:].strip()
    if target == "audience" and answer.casefold().startswith("my "):
        answer = "the user's " + answer[3:]
    return _clean_text(answer, 500)


def _question_target(question: str, context: dict[str, Any]) -> str:
    lowered = question.casefold()
    if any(token in lowered for token in ("who is the audience", "who is your audience", "who is this for", "who will read", "who will see", "who will receive", "who is the presentation for", "who is the review for")):
        return "audience"
    if any(token in lowered for token in ("which book", "what book", "what are you reviewing", "what is the topic", "what's the topic", "what is the presentation about", "what is the review about", "main topic", "subject")):
        return "subject"
    if any(token in lowered for token in ("strong arguments", "clear examples", "writing style", "personal perspective", "approach", "focus more on", "how should", "tone")):
        return "approach"
    if any(token in lowered for token in ("successful", "success", "what should the audience", "what do you want it to achieve", "what should it achieve", "main message", "key message", "take away", "outcome", "result")):
        return "successCriteria"
    if "requirement" in lowered or "constraint" in lowered or "scope" in lowered:
        return "requirements"
    if any(token in lowered for token in ("deadline", "due", "when does", "when is")):
        return "deadline"
    if any(token in lowered for token in ("language", "framework", "environment", "editor", "ide")):
        return "environment"
    if any(token in lowered for token in ("blocking", "blocker", "stuck", "what is going wrong")):
        return "blocker"
    if any(token in lowered for token in ("what does the project need to do", "what is the goal", "what are you trying to accomplish")):
        return "objective"
    return ""


def _apply_answer_to_target(
    context: dict[str, Any],
    target: str,
    raw_answer: str,
) -> bool:
    if target not in QUESTION_TARGETS or _is_weak_acknowledgement(raw_answer):
        return False
    answer = _normalize_answer_text(raw_answer, target)
    if not answer or answer.endswith("?") or _is_weak_acknowledgement(answer):
        return False

    if target == "successCriteria" and _clean_text(context.get("focusType"), 40) == "review":
        answer = re.sub(r"^i\s+", "", answer, flags=re.IGNORECASE)
        answer = re.sub(r"\bbelieve\s+me\b", "believe the review", answer, flags=re.IGNORECASE)
        if answer:
            answer = answer[0].upper() + answer[1:]
    if target in {"subject", "audience", "successCriteria", "approach", "objective"}:
        if context.get(target) == answer:
            return False
        context[target] = answer
        return True
    if target == "requirements":
        return _prepend_unique(context, "constraints", f"Requirement: {answer}.", MAX_CONSTRAINTS)
    if target == "deadline":
        return _prepend_unique(context, "constraints", f"Deadline or timing: {answer}.", MAX_CONSTRAINTS)
    if target == "environment":
        return _prepend_unique(context, "knownFacts", f"Working environment: {answer}.", MAX_FACTS)
    if target == "blocker":
        return _prepend_unique(context, "knownFacts", f"Current blocker: {answer}.", MAX_FACTS)
    return False


def _capture_pending_question_answer(text: str, context: dict[str, Any]) -> bool:
    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    if not pending:
        questions = _clean_list(context.get("openQuestions"), MAX_OPEN_QUESTIONS, 220)
        if not questions:
            return False
        target = _question_target(questions[0], context)
        if not target:
            return False
        pending = {"target": target, "question": questions[0]}

    if _is_weak_acknowledgement(text):
        return False
    if re.match(
        r"^(?:open|show|search|find|look up|help me|can you|could you|would you|what|why|when|where|who|how)\b",
        text,
        flags=re.IGNORECASE,
    ) and pending["target"] not in {"successCriteria", "subject"}:
        return False

    changed = _apply_answer_to_target(context, pending["target"], text)
    if changed:
        context["pendingQuestion"] = None
    return changed


def _extract_explicit_structured_fields(text: str, context: dict[str, Any]) -> dict[str, str]:
    result = {"subject": "", "audience": "", "successCriteria": "", "approach": ""}

    combined = re.search(
        r"\b(?:it|this|that)(?:'s|\s+is)\s+for\s+(.+?)\s+and\s+(?:it(?:'s|\s+is)\s+)?(?:about|on)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if combined:
        result["audience"] = _normalize_answer_text(combined.group(1), "audience")
        result["subject"] = _normalize_answer_text(combined.group(2), "subject")
    else:
        audience = _first_match(
            [
                r"\b(?:my|the)\s+audience\s+is\s+(.+)$",
                r"\b(?:it|this|that)(?:'s|\s+is)\s+for\s+(.+)$",
                r"\bi(?:'m|\s+am)\s+(?:presenting|writing)\s+to\s+(.+)$",
            ],
            text,
        )
        if audience:
            result["audience"] = _normalize_answer_text(audience, "audience")

        subject = _first_match(
            [
                r"\bi\s+want\s+(?:it|this|the\s+review|the\s+presentation)\s+to\s+be\s+(?:on|about)\s+(.+)$",
                r"\b(?:it|this|that)(?:'s|\s+is)\s+(?:on|about)\s+(.+)$",
                r"\b(?:the\s+)?(?:topic|subject|book)\s+is\s+(.+)$",
                r"\bi(?:'m|\s+am)\s+reviewing\s+(.+)$",
            ],
            text,
        )
        if subject:
            result["subject"] = _normalize_answer_text(subject, "subject")

    success = _first_match(
        [
            r"\bi\s+want\s+(?:him|her|them|the\s+audience|readers?|people)\s+to\s+(.+)$",
            r"\b(?:success|a\s+successful\s+result)\s+(?:means|would\s+mean|is)\s+(.+)$",
            r"\b(?:the\s+)?(?:main|key)\s+message\s+is\s+(.+)$",
        ],
        text,
    )
    if success:
        result["successCriteria"] = _normalize_answer_text(success, "successCriteria")

    focus_type = _clean_text(context.get("focusType"), 40)
    approach = _first_match(
        [
            r"\bi\s+(?:want|prefer|would\s+like)\s+(strong\s+arguments?|clear\s+examples?|a\s+formal\s+tone|a\s+casual\s+tone|a\s+persuasive\s+style|a\s+personal\s+perspective)\b.*$",
            r"\bi\s+want\s+to\s+focus\s+on\s+(.+)$",
            r"\bthe\s+approach\s+should\s+be\s+(.+)$",
        ],
        text,
    )
    if approach and not (focus_type == "general" and len(approach.split()) > 16):
        result["approach"] = _normalize_answer_text(approach, "approach")
    return result


def _refresh_derived_objective(context: dict[str, Any]) -> None:
    focus_type = _clean_text(context.get("focusType"), 40)
    subject = _clean_text(context.get("subject"), 300)
    audience = _clean_text(context.get("audience"), 300)
    success = _clean_text(context.get("successCriteria"), 500)
    source_goal = _clean_text(context.get("sourceGoal"), 500)

    if focus_type == "review" and subject:
        adjective = "persuasive " if any(token in (success + " " + _clean_text(context.get("approach"), 300)).casefold() for token in ("persuad", "convinc", "strong argument", "believe")) else ""
        objective = f"Write a {adjective}review of {subject}"
        if audience:
            objective += f" for {audience}"
        context["objective"] = objective.rstrip(".") + "."
    elif focus_type == "presentation" and subject:
        objective = f"Prepare a presentation about {subject}"
        if audience:
            objective += f" for {audience}"
        context["objective"] = objective.rstrip(".") + "."
    elif not _clean_text(context.get("objective"), 500) and source_goal:
        context["objective"] = source_goal


def _question_answered(question: str, text: str, context: dict[str, Any]) -> bool:
    target = _question_target(question, context)
    if target == "subject":
        return bool(_clean_text(context.get("subject"), 300))
    if target == "audience":
        return bool(_clean_text(context.get("audience"), 300))
    if target == "successCriteria":
        return bool(_clean_text(context.get("successCriteria"), 500))
    if target == "approach":
        return bool(_clean_text(context.get("approach"), 300))
    if target == "objective":
        return bool(_clean_text(context.get("objective"), 500))
    if target == "requirements":
        return bool(context.get("constraints"))
    if target == "deadline":
        return _has_deadline(context)
    if target == "environment":
        return "working environment:" in _context_text(context, "knownFacts") or "working with" in _context_text(context, "knownFacts")
    if target == "blocker":
        return "current blocker:" in _context_text(context, "knownFacts")

    normalized_question = question.casefold()
    if "flowers does" in normalized_question or "flower" in normalized_question and "like" in normalized_question:
        return _has_flower_preference(context)
    if "relationship" in normalized_question:
        return _has_relationship(context)
    if "birthday" in normalized_question:
        return _has_deadline(context)
    if "when and where" in normalized_question and "give" in normalized_question:
        return _has_progress(context, "flowers were given")
    if "concrete changes" in normalized_question or "prevent this" in normalized_question:
        return _has_decision(context, "prevention steps", "improvement plan") or _has_progress(
            context, "prevention steps", "improvement and prevention"
        )
    return False


def _specific_questions(context: dict[str, Any]) -> list[str]:
    if context.get("stage") == "complete":
        return []

    focus_type = _clean_text(context.get("focusType"), 40) or "general"
    if focus_type == "review":
        questions: list[str] = []
        if not _clean_text(context.get("successCriteria"), 500):
            questions.append("What would make this review successful or complete for you?")
        if not _clean_text(context.get("approach"), 300):
            questions.append("What should make the review convincing: strong arguments, evidence from the book, or your personal perspective?")
        if not _clean_text(context.get("audience"), 300):
            questions.append("Who is the review for?")
        if not _clean_text(context.get("subject"), 300):
            questions.append("Which book are you reviewing?")
        return questions

    if _is_gift_or_flower_focus(context):
        person = _focus_person(context) or "the recipient"
        questions = []
        if not _has_flower_preference(context):
            questions.append(f"What flowers does {person} like?")
        if not _has_deadline(context):
            questions.append(f"When is {person}'s birthday?")
        if not _has_relationship(context):
            questions.append(f"What is your relationship with {person}?")
        if _has_progress(context, "flowers have been obtained") and not _has_progress(context, "flowers were given"):
            questions.append(f"When and where will you give {person} the flowers?")
        return questions

    if focus_type == "presentation":
        questions = []
        if not _clean_text(context.get("audience"), 300):
            questions.append("Who is the presentation for?")
        if not _clean_text(context.get("subject"), 300):
            questions.append("What is the presentation about?")
        if not _clean_text(context.get("successCriteria"), 500) and not _is_apology_presentation(context):
            questions.append("What should the audience understand or do after the presentation?")
        if _is_apology_presentation(context) and not _has_progress(context, "prevention steps", "improvement and prevention"):
            questions.append("What concrete changes will you describe to prevent this from happening again?")
        return questions

    haystack = " ".join((
        _clean_text(context.get("title"), 120),
        _clean_text(context.get("objective"), 500),
    )).casefold()
    questions = []
    if focus_type == "document" or any(token in haystack for token in ("report", "paper", "essay", "proposal")):
        if not _clean_text(context.get("successCriteria"), 500):
            questions.append("What result should this document achieve?")
        if not _clean_text(context.get("audience"), 300):
            questions.append("Who will read this document?")
        if not _clean_text(context.get("subject"), 300):
            questions.append("What exact subject should the document cover?")
    elif "assignment" in haystack or "homework" in haystack:
        questions.append("What requirements does the assignment have?")

    if focus_type == "coding" or context.get("mode") == "coding":
        if not _clean_text(context.get("successCriteria"), 500):
            questions.append("What does the smallest working version need to do?")
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

    focus_type = _clean_text(context.get("focusType"), 40)
    if focus_type == "review":
        if context.get("recentProgress"):
            return "in-progress"
        if all(_clean_text(context.get(key), 300) for key in ("subject", "audience", "successCriteria", "approach")):
            return "planning"
        return "discovery"

    if focus_type == "presentation" or _is_presentation_focus(context):
        draft_ready = _has_progress(
            context,
            "drafted the apology statement",
            "drafted the presentation draft",
            "apology statement has been finalized",
            "presentation draft has been approved",
        ) or _has_decision(context, "draft was approved")
        prevention_ready = _has_progress(
            context, "prevention steps", "improvement and prevention"
        ) or _has_decision(context, "prevention steps", "improvement plan")
        if draft_ready and (not _is_apology_presentation(context) or prevention_ready):
            return "ready"
        if draft_ready or context.get("objective"):
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
    _refresh_focus_type(context)
    _refresh_derived_objective(context)
    mode = _clean_text(context.get("mode"), 30) or "general"
    objective = _clean_text(context.get("objective"), 500)
    title = _clean_text(context.get("title"), 120) or "the current focus"
    focus_type = _clean_text(context.get("focusType"), 40)

    context["stage"] = _derive_stage(context)

    existing_questions = _clean_list(
        context.get("openQuestions"), MAX_OPEN_QUESTIONS, max_length=220
    )
    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    unanswered_existing = [
        question
        for question in existing_questions
        if not _question_answered(question, user_text, context)
    ]

    specific_candidates = _specific_questions(context)
    default_candidates = (
        _default_questions(mode)
        if focus_type in {"general", "planning", "research", "meeting"}
        else []
    )
    ordered_candidates = [
        *([pending["question"]] if pending and not _question_answered(pending["question"], user_text, context) else []),
        *specific_candidates,
        *unanswered_existing,
        *default_candidates,
    ]
    remaining_questions: list[str] = []
    for question in ordered_candidates:
        if len(remaining_questions) >= MAX_OPEN_QUESTIONS:
            break
        if question in remaining_questions or _question_answered(question, user_text, context):
            continue
        remaining_questions.append(question)

    if context.get("stage") == "complete":
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["nextAction"] = (
            "The focus is complete. End it when ready and save a concise outcome summary; "
            "do not create follow-up work unless the user explicitly asks for it."
        )
        return

    context["openQuestions"] = remaining_questions[:MAX_OPEN_QUESTIONS]

    blocker = _extract_blocker(user_text)
    progress_items = _extract_progress_items(user_text, context)
    lowered_user = user_text.casefold()

    if blocker:
        context["nextAction"] = f"Resolve the current blocker: {blocker}."
    elif focus_type == "review":
        subject = _clean_text(context.get("subject"), 300) or "the book"
        if not _clean_text(context.get("successCriteria"), 500):
            context["nextAction"] = "Clarify what a successful review needs to accomplish."
        elif not _clean_text(context.get("approach"), 300):
            context["nextAction"] = "Choose the main persuasive approach for the review."
        elif not _clean_text(context.get("audience"), 300):
            context["nextAction"] = "Identify who the review is written for."
        elif not _clean_text(context.get("subject"), 300):
            context["nextAction"] = "Identify the exact book being reviewed."
        else:
            context["nextAction"] = f"Add your own opinion and specific evidence from {subject} to support each main argument."
    elif _is_gift_or_flower_focus(context):
        context["nextAction"] = _gift_next_action(context)
    elif focus_type == "presentation" or _is_presentation_focus(context):
        draft_ready = _has_progress(
            context,
            "drafted the apology statement",
            "drafted the presentation draft",
            "apology statement has been finalized",
            "presentation draft has been approved",
        ) or _has_decision(context, "draft was approved")
        prevention_ready = _has_progress(
            context, "prevention steps", "improvement and prevention"
        ) or _has_decision(context, "prevention steps", "improvement plan")
        has_audience = bool(_clean_text(context.get("audience"), 300))
        has_topic = bool(_clean_text(context.get("subject"), 300))
        has_message = bool(_clean_text(context.get("successCriteria"), 500))

        if _is_apology_presentation(context) and draft_ready and not prevention_ready:
            context["nextAction"] = "Outline specific actions that show how the conduct will be prevented from happening again."
        elif draft_ready:
            context["nextAction"] = "Turn the approved draft into a short presentation outline and rehearse it once."
        elif any(token in lowered_user for token in ("draft for me", "do the draft", "write the draft", "draft it")):
            context["nextAction"] = "Draft a concise statement that matches the audience, subject, and desired result."
        elif has_audience and has_topic and (has_message or _is_apology_presentation(context)):
            context["nextAction"] = "Draft the opening statement and the first two supporting points."
        elif not has_audience:
            context["nextAction"] = "Clarify who will receive the presentation."
        elif not has_topic:
            context["nextAction"] = "Clarify the exact subject and situation the presentation must address."
        else:
            context["nextAction"] = "Define the main result the presentation should produce."
    elif "hello world" in (objective + " " + user_text).casefold() and mode == "coding":
        context["nextAction"] = "Compile and run the smallest Hello World program, then verify the output." if progress_items else "Create the smallest Hello World file, compile it, and run it once."
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
    weak_acknowledgement = _is_weak_acknowledgement(text)
    if not weak_acknowledgement:
        changed = _capture_pending_question_answer(text, context) or changed

    structured = _extract_explicit_structured_fields(text, context)
    for key, value in structured.items():
        if value and not _is_weak_acknowledgement(value) and context.get(key) != value:
            context[key] = value
            changed = True

    objective = _extract_objective(text)
    tool_or_environment = _extract_tool_or_environment(text)
    constraint = _extract_constraint(text)
    blocker = _extract_blocker(text)
    relationship = _extract_relationship(text, context)
    preference = _extract_preference(text, context)
    deadline = _extract_deadline(text, context)
    decision = _extract_decision(text, context)
    progress_items = _extract_progress_items(text, context)

    if objective and not weak_acknowledgement and context.get("objective") != objective:
        context["objective"] = objective
        changed = True
    if tool_or_environment:
        changed = _prepend_unique(context, "knownFacts", f"The user is working with {tool_or_environment}.", MAX_FACTS) or changed
    if relationship:
        changed = _prepend_unique(context, "knownFacts", relationship, MAX_FACTS) or changed
    if preference:
        changed = _prepend_unique(context, "knownFacts", preference, MAX_FACTS) or changed
    if constraint:
        changed = _prepend_unique(context, "constraints", constraint, MAX_CONSTRAINTS) or changed
    if deadline:
        changed = _prepend_unique(context, "constraints", deadline, MAX_CONSTRAINTS) or changed
    if blocker:
        changed = _prepend_unique(context, "knownFacts", f"Current blocker: {blocker}.", MAX_FACTS) or changed
    if decision:
        changed = _prepend_unique(context, "decisions", decision, MAX_DECISIONS) or changed
        if "message" in decision.casefold():
            changed = _prepend_unique(context, "recentProgress", "The birthday message has been finalized.", MAX_RECENT_PROGRESS) or changed
    for progress in progress_items:
        changed = _prepend_unique(context, "recentProgress", progress, MAX_RECENT_PROGRESS) or changed

    _refresh_focus_type(context)
    _refresh_derived_objective(context)

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
        context["confidence"] = min(0.97, float(context.get("confidence", 0.35)) + 0.06)
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



def _extract_assistant_pending_question(reply: str, context: dict[str, Any]) -> dict[str, str] | None:
    normalized = re.sub(r"\s+", " ", reply).strip()
    questions = re.findall(r"([^?]{4,320}\?)", normalized)
    for raw_question in reversed(questions):
        question = _clean_text(raw_question, 320)
        clause = re.search(
            r"((?:what|who|which|how|when|where|why|would|do|does|is|are|can|could)\b[^?]{2,240}\?)$",
            question,
            flags=re.IGNORECASE,
        )
        if clause:
            question = _clean_text(clause.group(1), 240)
        question = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", question).strip()
        target = _question_target(question, context)
        if not target:
            continue
        if _question_answered(question, "", context):
            continue
        return {"target": target, "question": question}
    return None


def _apply_assistant_update(context: dict[str, Any], reply: str) -> tuple[dict[str, Any], bool]:
    if not _clean_text(reply, 2400):
        return context, False

    if context.get("stage") == "complete":
        completion_action = (
            "The focus is complete. End it when ready and save a concise outcome summary; "
            "do not create follow-up work unless the user explicitly asks for it."
        )
        if context.get("nextAction") != completion_action:
            context["nextAction"] = completion_action
            context["pendingQuestion"] = None
            context["openQuestions"] = []
            context["updatedAt"] = _now_iso()
            return context, True
        return context, False

    changed = False
    for progress in _extract_assistant_progress_items(reply, context):
        changed = _prepend_unique(context, "recentProgress", progress, MAX_RECENT_PROGRESS) or changed

    next_step = _extract_assistant_next_action(reply)
    if next_step and not _assistant_action_conflicts_with_progress(context, next_step):
        if context.get("nextAction") != next_step:
            context["nextAction"] = next_step
            changed = True

    previous_stage = context.get("stage", "")
    previous_questions = list(context.get("openQuestions", []))
    if changed:
        _refresh_questions_and_next_action(context, "")

    pending = _extract_assistant_pending_question(reply, context)
    if pending and context.get("pendingQuestion") != pending:
        context["pendingQuestion"] = pending
        existing = _clean_list(context.get("openQuestions"), MAX_OPEN_QUESTIONS, 220)
        context["openQuestions"] = [pending["question"]] + [
            question
            for question in existing
            if question.casefold() != pending["question"].casefold()
            and _question_target(question, context) != pending["target"]
        ][: MAX_OPEN_QUESTIONS - 1]
        changed = True

    if previous_stage != context.get("stage") or previous_questions != context.get("openQuestions"):
        changed = True

    if changed:
        context["confidence"] = min(0.98, float(context.get("confidence", 0.35)) + 0.03)
        context["updatedAt"] = _now_iso()
    return context, changed


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
        r"^(?:please\s+)?(?:create|add|save|make)\s+(?:these\s+|those\s+|a\s+)?(?:tasks?|to-?dos?|checklist)\b",
    ]
    if any(re.search(pattern, lowered) for pattern in explicit_tool_request):
        return False

    conversational_patterns = [
        r"\b(?:can|could|would|will)\s+you\s+help\s+me\b",
        r"\bhelp\s+me\s+(?:with|figure|choose|craft|write|plan|decide|understand|work\s+on)\b",
        r"\bwhat\s+(?:should|do)\s+i\s+do\b",
        r"\bwhat\s+now\b",
        r"\bhow\s+should\s+i\b",
        r"\b(?:this|that|it)\s+(?:is\s+perfect|looks\s+good|sounds\s+good|works)\b",
        r"\blet(?:'s|\s+us)\s+move\s+on\b",
        r"\bwe(?:'re|\s+are)?\s+already\s+using\b",
        r"\bmy\s+relationship\s+with\b",
        r"\b(?:he|she|they)\s+(?:likes?|loves?|prefers?)\b",
        r"\b(?:i|we)\s+(?:got|bought|purchased|ordered|picked\s+up|gave|delivered|handed)\b",
        r"^(?:(?:yes|yeah|yep|sure|okay|ok|alright|all\s+right)[, ]+)?"
        r"(?:(?:can|could|would|will)\s+you\s+)?(?:give|write|show|make)\s+me\s+"
        r"(?:a\s+)?list\b",
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
        "- Never invent a person's name, role, relationship, deadline, requirement, or outcome; use exactly what the user provided.",
        "- Never recommend an action that recent progress says is already complete.",
        "- A request such as 'give me a list' asks for a conversational list. Only create or save stored tasks when the user explicitly says tasks, to-dos, checklist, or asks to save them.",
        "- Give a concrete next step instead of explaining how the focus system works.",
        "- If important information is missing, answer what you can first, then ask exactly one useful follow-up question.",
        "- Prefer the first open question below; do not ask a generic or already-answered question.",
        "- When the user answers an open question and another useful open question remains, briefly acknowledge the new detail and ask the next question in the same reply.",
        "- Keep onboarding conversational rather than form-like: one question at a time, no questionnaires, and no long list of choices unless the user asks for options.",
        "- Stop interviewing once the objective and immediate constraints are clear enough to help; then move naturally into concrete guidance.",
        "- Keep progress guidance easy to scan with short sections, bullets, or numbered steps.",
        "- Match the response to the current stage: discovery asks one useful question; planning gives a concrete first step and may ask one question that materially improves the plan; in-progress advances the next unfinished step; ready prepares the final handoff; complete acknowledges the result and stops adding work.",
        "- If the focus stage is complete, briefly acknowledge what was accomplished. Do not propose another project step, do not ask a follow-up question, and do not create tasks unless the user explicitly requests them.",
        "- Do not mention this private context, its file, storage, confidence score, or implementation.",
        "",
        f"Focus title: {context['title']}",
        f"Focus mode: {context['mode']}",
        f"Focus stage: {context.get('stage', 'discovery')}",
        f"Focus type: {context.get('focusType', 'general')}",
        f"Objective: {context['objective'] or 'Not clear yet'}",
        f"Subject: {context.get('subject') or 'Not clear yet'}",
        f"Audience: {context.get('audience') or 'Not clear yet'}",
        f"Success criteria: {context.get('successCriteria') or 'Not clear yet'}",
        f"Preferred approach: {context.get('approach') or 'Not clear yet'}",
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

# ---------------------------------------------------------------------------
# Phase 18: creative-project learning and safer conversational memory
# ---------------------------------------------------------------------------
# These overrides keep the public API stable while making the learner domain-
# neutral for songs and other creative work. They also prevent optional
# assistant offers from becoming Memory questions.

QUESTION_TARGETS.add("content")

_base_sanitize_context = _sanitize_context
_base_question_target = _question_target
_base_apply_answer_to_target = _apply_answer_to_target
_base_extract_explicit_structured_fields = _extract_explicit_structured_fields
_base_refresh_derived_objective = _refresh_derived_objective
_base_specific_questions = _specific_questions
_base_derive_stage = _derive_stage
_base_refresh_questions_and_next_action = _refresh_questions_and_next_action
_base_extract_decision = _extract_decision
_base_extract_progress_items = _extract_progress_items
_base_extract_assistant_progress_items = _extract_assistant_progress_items
_base_extract_assistant_next_action = _extract_assistant_next_action
_base_apply_user_update = _apply_user_update
_base_apply_assistant_update = _apply_assistant_update
_base_should_keep_focus_message_in_chat = should_keep_focus_message_in_chat


def _creative_context(context: dict[str, Any]) -> bool:
    return _clean_text(context.get("focusType"), 40) == "creative" or any(
        token in " ".join(
            (
                _clean_text(context.get("title"), 120),
                _clean_text(context.get("objective"), 500),
                _clean_text(context.get("subject"), 300),
            )
        ).casefold()
        for token in ("song", "lyrics", "lyric", "poem", "story", "screenplay", "diss track")
    )


def _is_action_offer_question(question: str) -> bool:
    lowered = _clean_text(question, 320).casefold()
    return bool(
        re.search(
            r"^(?:would\s+you\s+like|do\s+you\s+want|want\s+me\s+to|"
            r"want\s+help|can\s+i|shall\s+i|should\s+i)\b",
            lowered,
        )
        or re.search(
            r"\b(?:would\s+you\s+like|want\s+me\s+to|want\s+help|"
            r"do\s+you\s+want\s+me\s+to)\b",
            lowered,
        )
        or re.search(
            r"^(?:does|did)\s+(?:this|that|the\s+(?:draft|arrangement|version))\s+"
            r"(?:work|look|sound|feel)\b",
            lowered,
        )
        or bool(
            re.search(
                r"\b(?:prefer|tackle|work\s+on|focus\s+on|polish|expand|tweak|add)\b.*\bnext\b",
                lowered,
            )
        )
    )


def _sanitize_context(raw: object) -> dict[str, Any] | None:
    context = _base_sanitize_context(raw)
    if context is None:
        return None

    if _creative_context(context):
        context["focusType"] = "creative"
        if context.get("mode") == "general":
            context["mode"] = "planning"

        stale_subject = _clean_text(context.get("subject"), 300)
        stale_approach = _clean_text(context.get("approach"), 300)
        if re.match(r"^i(?:'m|\s+am)\s+inspired", stale_subject, flags=re.IGNORECASE):
            if not stale_approach or _needs_approach_refinement(context):
                moved = re.sub(
                    r"^i(?:'m|\s+am)\s+inspired(?:\s+greatly)?\s+(?:by\s+)?",
                    "Inspired by ",
                    stale_subject,
                    flags=re.IGNORECASE,
                )
                context["approach"] = _clean_text(moved, 300)
            context["subject"] = ""
        elif stale_approach.casefold().startswith("i want "):
            context["approach"] = _normalize_answer_text(stale_approach, "approach")

        # Migrate two bad values produced by the earlier presentation-oriented
        # learner instead of making the user restart the focus.
        cleaned_facts: list[str] = []
        for fact in _clean_list(context.get("knownFacts"), MAX_FACTS, 300):
            if fact.casefold().startswith("working environment:"):
                value = fact.split(":", 1)[1].strip().rstrip(".")
                if _is_weak_acknowledgement(value) or _is_acceptance(value):
                    continue
            cleaned_facts.append(fact)
        context["knownFacts"] = cleaned_facts

        cleaned_constraints: list[str] = []
        for constraint in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 300):
            value = constraint.split(":", 1)[1].strip().rstrip(".") if ":" in constraint else constraint
            if re.search(r"\b(?:style|genre|mood|tone|inspir(?:ed|ation))\b", value, flags=re.IGNORECASE):
                if not _clean_text(context.get("approach"), 300):
                    context["approach"] = _normalize_answer_text(value, "approach")
                continue
            cleaned_constraints.append(constraint)
        context["constraints"] = cleaned_constraints

        decisions = _clean_list(context.get("decisions"), MAX_DECISIONS, 300)
        has_specific_approval = any(
            any(label in item.casefold() for label in ("lyric", "chorus", "song draft", "polished"))
            for item in decisions
        )
        if has_specific_approval:
            decisions = [
                item
                for item in decisions
                if item.casefold() != "the most recent proposed plan or draft was accepted."
            ]
        context["decisions"] = decisions

    context["openQuestions"] = [
        question
        for question in _clean_list(context.get("openQuestions"), MAX_OPEN_QUESTIONS, 240)
        if _is_information_question(question)
    ]
    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    context["pendingQuestion"] = pending
    context["lastAssistantArtifact"] = _clean_text(
        context.get("lastAssistantArtifact"), 80
    )
    return context


def _question_target(question: str, context: dict[str, Any]) -> str:
    lowered = _clean_text(question, 320).casefold()
    if _creative_context(context):
        if any(
            phrase in lowered
            for phrase in (
                "what kind of style",
                "what style",
                "which style",
                "genre",
                "mood",
                "artist influence",
                "inspired by",
                "sound are you aiming",
                "tone are you aiming",
            )
        ):
            return "approach"
        if any(
            phrase in lowered
            for phrase in (
                "theme or message",
                "theme should",
                "message should the song",
                "what is the song about",
                "what should the song be about",
                "central idea",
            )
        ):
            return "subject"
        if any(
            phrase in lowered
            for phrase in (
                "key points",
                "details do you want",
                "what do you want to call out",
                "what should the lyrics mention",
                "specific ideas",
            )
        ):
            return "content"
        if any(
            phrase in lowered
            for phrase in (
                "who should hear",
                "who is the song for",
                "intended listener",
                "who are the listeners",
            )
        ):
            return "audience"
    return _base_question_target(question, context)


def _creative_audience_from_text(text: str) -> str:
    match = re.search(
        r"\b(?:to|for)\s+my\s+(peers?|friends?|coworkers?|co-workers?|classmates?|team|audience)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    label = match.group(1).replace("co-workers", "coworkers")
    return f"the user's {label}"


def _apply_answer_to_target(
    context: dict[str, Any],
    target: str,
    raw_answer: str,
) -> bool:
    if _creative_context(context):
        if target == "requirements" and re.search(
            r"\b(?:style|genre|mood|tone|flow|sound|inspir(?:ed|ation))\b",
            raw_answer,
            flags=re.IGNORECASE,
        ):
            target = "approach"
        answer = _normalize_answer_text(raw_answer, target)
        if target == "content":
            answer = re.sub(
                r"^i\s+want\s+to\s+(?:call\s+out|mention|include)\s+",
                "",
                answer,
                flags=re.IGNORECASE,
            ).strip()
            if not answer or _is_weak_acknowledgement(answer):
                return False
            return _prepend_unique(
                context,
                "knownFacts",
                f"Creative brief: {answer}.",
                MAX_FACTS,
            )
        if target == "successCriteria":
            audience = _creative_audience_from_text(raw_answer)
            changed = False
            if audience and context.get("audience") != audience:
                context["audience"] = audience
                changed = True
            if answer:
                answer = re.sub(r"^i\s+", "", answer, flags=re.IGNORECASE)
                answer = answer[0].upper() + answer[1:] if answer else answer
                if context.get("successCriteria") != answer:
                    context["successCriteria"] = answer
                    changed = True
            return changed
        if target == "approach" and answer:
            answer = re.sub(
                r"^i(?:'m|\s+am)\s+inspired(?:\s+greatly)?\s+(?:by\s+)?",
                "Inspired by ",
                answer,
                flags=re.IGNORECASE,
            )
            if context.get("approach") != answer:
                context["approach"] = answer
                return True
            return False
        if target == "subject" and answer:
            answer = re.sub(
                r"^i\s+want(?:ed)?\s+(?:(?:it|this|the\s+song)\s+)?to\s+be\s+",
                "",
                answer,
                flags=re.IGNORECASE,
            ).strip()
            if context.get("subject") != answer:
                context["subject"] = answer
                return True
            return False
    return _base_apply_answer_to_target(context, target, raw_answer)


def _extract_explicit_structured_fields(
    text: str,
    context: dict[str, Any],
) -> dict[str, str]:
    result = _base_extract_explicit_structured_fields(text, context)
    if not _creative_context(context):
        return result

    success = _first_match(
        [
            r"\b(?:a|the)\s+completed?\s+song\s+(.+)$",
            r"\b(?:success|successful)\s+(?:means|is|would\s+be)\s+(.+)$",
            r"\bi\s+want\s+(?:a|the)\s+(?:finished|complete)\s+song\s+(.+)$",
        ],
        text,
    )
    if success and not result["successCriteria"]:
        result["successCriteria"] = _normalize_answer_text(
            f"A completed song {success}", "successCriteria"
        )

    audience = _creative_audience_from_text(text)
    if audience and not result["audience"]:
        result["audience"] = audience

    subject = _first_match(
        [
            r"\bi\s+want(?:ed)?\s+(?:it|this|the\s+song)\s+to\s+be\s+(.+)$",
            r"\b(?:the\s+)?(?:song|track|lyrics?)\s+(?:is|are|should\s+be)\s+about\s+(.+)$",
            r"\b(?:the\s+)?(?:theme|message)\s+(?:is|should\s+be)\s+(.+)$",
        ],
        text,
    )
    if subject and not result["subject"]:
        result["subject"] = _normalize_answer_text(subject, "subject")

    approach = _first_match(
        [
            r"\bi(?:'m|\s+am)\s+(?:greatly\s+)?inspired\s+by\s+(.+)$",
            r"\bi\s+want\s+(?:a\s+)?(?:good\s+)?(?:style|genre|mood|tone)\s*(?:of|like|that\s+is)?\s*(.*)$",
            r"\b(?:the\s+)?(?:style|genre|mood|tone)\s+(?:is|should\s+be)\s+(.+)$",
        ],
        text,
    )
    if approach and not result["approach"]:
        approach = approach or "a strong style"
        if re.search(r"inspired\s+by", text, flags=re.IGNORECASE):
            approach = f"Inspired by {approach}"
        result["approach"] = _normalize_answer_text(approach, "approach")
    return result


def _refresh_derived_objective(context: dict[str, Any]) -> None:
    _base_refresh_derived_objective(context)
    if not _creative_context(context):
        return

    subject = _clean_text(context.get("subject"), 300)
    audience = _clean_text(context.get("audience"), 300)
    success = _clean_text(context.get("successCriteria"), 500)
    title = _clean_text(context.get("title"), 120)

    if subject.casefold().startswith("a diss track against "):
        objective = f"Write and refine a complete diss track against {subject[len('a diss track against '):]}"
    elif subject.casefold().startswith("diss track against "):
        objective = f"Write and refine a complete {subject}"
    else:
        objective = "Write and refine a complete song"
        if subject:
            objective += f" about {subject}"
    if audience:
        objective += f" for {audience}"
    if success and success.casefold() not in objective.casefold():
        objective += f", with success defined as {success[0].lower() + success[1:]}"
    if not subject and not success:
        objective = "Write and refine a complete song"
    context["objective"] = objective.rstrip(". ") + "."


def _specific_questions(context: dict[str, Any]) -> list[str]:
    if _creative_context(context):
        if context.get("stage") == "complete":
            return []
        questions: list[str] = []
        if not _clean_text(context.get("successCriteria"), 500):
            questions.append("What would make the finished song successful for you?")
        if not _clean_text(context.get("approach"), 300):
            questions.append("What style, genre, mood, or influences should shape the song?")
        if not _clean_text(context.get("subject"), 300):
            questions.append("What theme or message should the song center on?")
        return questions
    return _base_specific_questions(context)


def _creative_progress_text(context: dict[str, Any]) -> str:
    return _context_text(context, "recentProgress")


def _derive_stage(context: dict[str, Any]) -> str:
    if _creative_context(context):
        if _has_progress(context, "focus is complete"):
            return "complete"
        progress = _creative_progress_text(context)
        decisions = _context_text(context, "decisions")
        if any(
            token in progress + " " + decisions
            for token in (
                "full song draft has been finalized",
                "polished lyrics have been finalized",
                "full song draft was approved",
                "polished lyrics were approved",
            )
        ):
            return "ready"
        if any(
            token in progress
            for token in (
                "drafted lyric lines",
                "drafted a chorus",
                "assembled a full song draft",
                "polished the song",
            )
        ):
            return "in-progress"
        if all(
            _clean_text(context.get(key), 300)
            for key in ("successCriteria", "approach", "subject")
        ):
            return "planning"
        return "discovery"
    return _base_derive_stage(context)


def _refresh_questions_and_next_action(
    context: dict[str, Any],
    user_text: str,
) -> None:
    _base_refresh_questions_and_next_action(context, user_text)
    if not _creative_context(context):
        return

    context["focusType"] = "creative"
    if context.get("mode") == "general":
        context["mode"] = "planning"
    context["stage"] = _derive_stage(context)

    # Remove stale offer questions and keep only questions that fill actual
    # context fields.
    context["openQuestions"] = [
        question
        for question in _specific_questions(context)
        if _is_information_question(question)
    ][:MAX_OPEN_QUESTIONS]
    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    if pending:
        answered = _question_answered(pending["question"], "", context)
        if pending["target"] == "approach" and _needs_approach_refinement(context):
            answered = False
        if answered:
            context["pendingQuestion"] = None
        else:
            context["pendingQuestion"] = pending
            context["openQuestions"] = [pending["question"]] + [
                question
                for question in context["openQuestions"]
                if question.casefold() != pending["question"].casefold()
                and _question_target(question, context) != pending["target"]
            ]
            context["openQuestions"] = context["openQuestions"][:MAX_OPEN_QUESTIONS]

    if context["stage"] == "complete":
        return
    if context["stage"] == "ready":
        context["nextAction"] = (
            "Read the assembled lyrics once for rhythm and flow, then decide whether the song is finished."
        )
    elif "assembled a full song draft" in _creative_progress_text(context):
        context["nextAction"] = "Polish the full draft for rhythm, rhyme, and consistent wordplay."
    elif any(
        token in _creative_progress_text(context)
        for token in ("drafted lyric lines", "drafted a chorus")
    ):
        context["nextAction"] = "Assemble the approved verses and chorus into one complete song draft."
    elif not _clean_text(context.get("successCriteria"), 500):
        context["nextAction"] = "Define what a successful finished song should sound like."
    elif not _clean_text(context.get("approach"), 300):
        context["nextAction"] = "Choose the song's style, genre, mood, or influences."
    elif not _clean_text(context.get("subject"), 300):
        context["nextAction"] = "Choose the song's central theme or message."
    else:
        context["nextAction"] = "Draft the opening verse and a memorable hook from the creative brief."


def _detect_creative_artifact(reply: str) -> str:
    lowered = reply.casefold()
    if "polished sample" in lowered or (
        "polish" in lowered and any(token in lowered for token in ("wordplay", "rhythm", "flow"))
    ):
        return "polished lyrics"
    if any(
        token in lowered
        for token in (
            "draft assembly",
            "here's a draft assembly",
            "here is a draft assembly",
            "full song draft",
        )
    ) or ("verse 1:" in lowered and "chorus:" in lowered):
        return "full song draft"
    if "chorus:" in lowered or "for the chorus" in lowered:
        return "chorus"
    if any(
        token in lowered
        for token in ("punchy lines", "starting punchline", "catchy line", "verse:", "verse 1:")
    ):
        return "lyric lines"
    return ""


def _extract_assistant_progress_items(
    reply: str,
    context: dict[str, Any],
) -> list[str]:
    items = _base_extract_assistant_progress_items(reply, context)
    if not _creative_context(context):
        return items
    artifact = _detect_creative_artifact(reply)
    mapping = {
        "lyric lines": "QMeet drafted lyric lines.",
        "chorus": "QMeet drafted a chorus.",
        "full song draft": "QMeet assembled a full song draft.",
        "polished lyrics": "QMeet polished the song's wordplay and flow.",
    }
    item = mapping.get(artifact)
    if item and all(item.casefold() != existing.casefold() for existing in items):
        items.append(item)
    return items


def _artifact_approval_text(artifact: str) -> str:
    if artifact in {"lyric lines", "polished lyrics"}:
        return f"The {artifact} were approved."
    return f"The {artifact} was approved."


def _artifact_finalized_text(artifact: str) -> str:
    if artifact in {"lyric lines", "polished lyrics"}:
        return f"The {artifact} were finalized."
    return f"The {artifact} was finalized."


def _extract_decision(text: str, context: dict[str, Any]) -> str:
    if _creative_context(context) and _is_acceptance(text):
        artifact = _clean_text(context.get("lastAssistantArtifact"), 80)
        if artifact:
            return _artifact_approval_text(artifact)
        return "The most recent creative draft was approved."
    return _base_extract_decision(text, context)


def _extract_progress_items(text: str, context: dict[str, Any]) -> list[str]:
    items = _base_extract_progress_items(text, context)
    if _creative_context(context):
        # "I completed song that sounds good..." is a success criterion in
        # natural speech, not evidence that the song is already finished.
        if re.match(r"^i\s+completed?\s+song\s+that\b", text, flags=re.IGNORECASE):
            items = [item for item in items if not item.casefold().startswith("completed:")]
        if _is_acceptance(text):
            artifact = _clean_text(context.get("lastAssistantArtifact"), 80)
            if artifact:
                item = _artifact_finalized_text(artifact)
                if all(item.casefold() != existing.casefold() for existing in items):
                    items.append(item)
    return items


def _creative_brief_item(text: str) -> str:
    detail = _first_match(
        [
            r"\bi\s+want\s+to\s+call\s+out\s+(.+)$",
            r"\blet(?:'s|\s+us)\s+talk\s+about\s+(.+)$",
            r"\b(?:next\s+with\s+.+?\s+)?let(?:'s|\s+us)\s+make\s+fun\s+of\s+(.+)$",
            r"\bi\s+want\s+the\s+lyrics?\s+to\s+mention\s+(.+)$",
        ],
        text,
    )
    return detail


def _apply_user_update(
    context: dict[str, Any],
    user_text: str,
) -> tuple[dict[str, Any], bool]:
    next_context, changed = _base_apply_user_update(context, user_text)
    if not _creative_context(next_context):
        return next_context, changed

    next_context["focusType"] = "creative"
    if next_context.get("mode") == "general":
        next_context["mode"] = "planning"

    detail = _creative_brief_item(user_text)
    if detail:
        changed = _prepend_unique(
            next_context,
            "knownFacts",
            f"Creative brief: {detail}.",
            MAX_FACTS,
        ) or changed

    before = (
        list(next_context.get("openQuestions", [])),
        next_context.get("nextAction", ""),
        next_context.get("stage", ""),
        next_context.get("objective", ""),
    )
    _refresh_derived_objective(next_context)
    _refresh_questions_and_next_action(next_context, user_text)
    after = (
        list(next_context.get("openQuestions", [])),
        next_context.get("nextAction", ""),
        next_context.get("stage", ""),
        next_context.get("objective", ""),
    )
    if before != after:
        changed = True
    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _extract_assistant_next_action(reply: str) -> str:
    action = _base_extract_assistant_next_action(reply)
    if not action:
        return ""
    action = re.split(
        r"\s+(?:Would\s+you\s+like|Do\s+you\s+want|Want\s+me\s+to|Want\s+help|Can\s+I)\b",
        action,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    if "?" in action:
        action = action.split("?", 1)[0]
    return _sentence_fragment(action, 300)


def _needs_approach_refinement(context: dict[str, Any]) -> bool:
    approach = _clean_text(context.get("approach"), 300).casefold()
    return approach in {"", "style", "good style", "a good style", "a strong style"}


def _extract_assistant_pending_question(
    reply: str,
    context: dict[str, Any],
) -> dict[str, str] | None:
    normalized = reply.replace("\r\n", "\n").replace("\r", "\n")
    candidates: list[str] = []
    for match in re.finditer(
        r"(?i)(?<![A-Za-z])(?:what|who|which|how|when|where|why|is\s+there|are\s+there)\b[^?\n]{2,240}\?",
        normalized,
    ):
        question = _clean_text(match.group(0), 240)
        if _is_information_question(question):
            candidates.append(question)

    for question in reversed(candidates):
        target = _question_target(question, context)
        if not target:
            continue
        if _question_answered(question, "", context):
            if not (target == "approach" and _needs_approach_refinement(context)):
                continue
        return {"target": target, "question": question}
    return None


def _apply_assistant_update(
    context: dict[str, Any],
    reply: str,
) -> tuple[dict[str, Any], bool]:
    next_context, changed = _base_apply_assistant_update(context, reply)
    if not _creative_context(next_context):
        return next_context, changed

    artifact = _detect_creative_artifact(reply)
    if artifact and next_context.get("lastAssistantArtifact") != artifact:
        next_context["lastAssistantArtifact"] = artifact
        changed = True

    before = (
        list(next_context.get("openQuestions", [])),
        next_context.get("nextAction", ""),
        next_context.get("stage", ""),
    )
    _refresh_questions_and_next_action(next_context, "")
    after = (
        list(next_context.get("openQuestions", [])),
        next_context.get("nextAction", ""),
        next_context.get("stage", ""),
    )
    if before != after:
        changed = True
    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def should_keep_focus_message_in_chat(message: str) -> bool:
    visible = _clean_text(_extract_visible_user_message(message), 800)
    if not visible:
        return False

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if context is None:
        return False

    lowered = visible.casefold()
    explicit_commands = [
        r"^(?:please\s+)?(?:open|show|close|clear|delete|read)\s+(?:the\s+|my\s+)?(?:notes?|memory|calendar|camera|search)",
        r"^(?:please\s+)?(?:search|look\s+up|find)\b",
        r"^(?:please\s+)?(?:create|add|save|make)\s+(?:these\s+|those\s+|a\s+)?(?:tasks?|to-?dos?|checklist)\b",
        r"^(?:please\s+)?(?:(?:i|we)\s+)?(?:mark|complete|completed|finish|finished|check\s+off)\b.*\b(?:tasks?|to-?dos?|items?)\b",
        r"^(?:please\s+)?set\s+(?:my\s+|the\s+)?goal\b",
        r"^(?:please\s+)?(?:end|stop|close|finish|wrap\s+up)\s+(?:the\s+|my\s+|this\s+)?(?:focus|session|project)\b",
        r"^(?:please\s+)?(?:save|add)\b.*\bnote\b",
    ]
    if any(re.search(pattern, lowered) for pattern in explicit_commands):
        return False

    # A deliverable described as "a completed song/report/draft" is an answer,
    # not a request to mutate a task. Whole-focus completion has already been
    # handled by the middleware before this function is called.
    if re.match(r"^i\s+(?:completed|finished)\s+(?!.*\b(?:task|tasks|to-?do|item|items)\b).+", lowered):
        return True

    # While a focus is active, natural language belongs to the conversation by
    # default. Only the explicit command patterns above should bypass chat.
    return True
