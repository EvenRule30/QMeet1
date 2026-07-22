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

# ---------------------------------------------------------------------------
# Phase 18: domain-neutral workflow ledger and sale/listing continuity
# ---------------------------------------------------------------------------
# The earlier context learner was accurate for a few named domains but could
# lose ordinary project state when a conversation moved from discovery into
# execution. This layer keeps a small event ledger for any focus and adds a
# first-class sale/listing workflow without changing the public API.

FOCUS_TYPES.add("sale")
QUESTION_TARGETS.update({"detail", "price", "assets", "platform"})

_ledger_base_infer_focus_type_from_text = _infer_focus_type_from_text
_ledger_base_is_information_question = _is_information_question
_ledger_base_question_target = _question_target
_ledger_base_question_answered = _question_answered
_ledger_base_apply_answer_to_target = _apply_answer_to_target
_ledger_base_extract_explicit_structured_fields = _extract_explicit_structured_fields
_ledger_base_refresh_derived_objective = _refresh_derived_objective
_ledger_base_specific_questions = _specific_questions
_ledger_base_derive_stage = _derive_stage
_ledger_base_refresh_questions_and_next_action = _refresh_questions_and_next_action
_ledger_base_apply_user_update = _apply_user_update
_ledger_base_apply_assistant_update = _apply_assistant_update
_ledger_base_sanitize_context = _sanitize_context
_ledger_base_prepare_background_chat_message = prepare_background_chat_message


def _sale_context(context: dict[str, Any]) -> bool:
    haystack = " ".join(
        (
            _clean_text(context.get("title"), 160),
            _clean_text(context.get("objective"), 500),
            _clean_text(context.get("subject"), 300),
        )
    ).casefold()
    return _clean_text(context.get("focusType"), 40) == "sale" or bool(
        re.search(
            r"\b(?:sell|selling|sale|list(?:ing)?|marketplace|craigslist|cycle\s*trader|offerup)\b",
            haystack,
        )
    )


def _infer_focus_type_from_text(text: str, mode: str) -> str:
    lowered = _clean_text(text, 1200).casefold()
    if re.search(
        r"\b(?:sell(?:ing)?|list(?:ing)?|put(?:ting)?\s+.+\s+up\s+for\s+sale|for\s+sale|"
        r"craigslist|facebook\s+marketplace|cycle\s*trader|offerup)\b",
        lowered,
    ):
        return "sale"
    return _ledger_base_infer_focus_type_from_text(text, mode)


def _is_action_offer_question(question: str) -> bool:
    lowered = _clean_text(question, 320).casefold()
    return bool(
        re.search(
            r"^(?:would\s+you\s+like|do\s+you\s+want|want\s+me\s+to|"
            r"want\s+help|can\s+i|shall\s+i|should\s+i|ready\s+for)\b",
            lowered,
        )
        or re.search(
            r"\b(?:would\s+you\s+like|want\s+me\s+to|want\s+help|"
            r"do\s+you\s+want\s+me\s+to|let\s+me\s+know\s+if)\b",
            lowered,
        )
        or re.search(
            r"^(?:does|did)\s+(?:this|that|the\s+(?:draft|arrangement|version|listing|title))\s+"
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


def _is_information_question(question: str) -> bool:
    clean = _clean_text(question, 320)
    if not clean.endswith("?") or _is_action_offer_question(clean):
        return False
    lowered = clean.casefold()
    return bool(
        re.match(
            r"^(?:what|what's|who|which|how|when|where|why|"
            r"is\s+(?:there|the|your|this|that)|are\s+(?:there|the|your)|"
            r"do\s+you\s+already\s+have|have\s+you|could\s+you\s+tell\s+me|"
            r"can\s+you\s+tell\s+me|tell\s+me)\b",
            lowered,
        )
    )


def _question_target(question: str, context: dict[str, Any]) -> str:
    lowered = _clean_text(question, 320).casefold()
    if _sale_context(context):
        if any(
            phrase in lowered
            for phrase in (
                "target price",
                "minimum acceptable",
                "minimum price",
                "asking price",
                "lowest price",
                "how much",
            )
        ):
            return "price"
        if any(
            phrase in lowered
            for phrase in (
                "model, year",
                "year and model",
                "make and model",
                "model and year",
                "mileage",
                "odometer",
            )
        ):
            return "detail"
        if any(
            phrase in lowered
            for phrase in (
                "overall state",
                "overall condition",
                "condition is it in",
                "maintenance or issues",
                "recent maintenance",
                "known issues",
            )
        ):
            return "detail"
        if any(
            phrase in lowered
            for phrase in (
                "photos ready",
                "photos do you have",
                "pictures ready",
                "pictures do you have",
            )
        ):
            return "assets"
        if any(
            phrase in lowered
            for phrase in (
                "where will you list",
                "where do you want to list",
                "which marketplace",
                "which platform",
                "which site",
            )
        ):
            return "platform"
        if any(token in lowered for token in ("timeline", "sold by", "sell it by", "within how long")):
            return "deadline"
    target = _ledger_base_question_target(question, context)
    if target:
        return target
    return "detail" if _is_information_question(question) else ""


def _normalize_money(value: str) -> str:
    clean = _clean_text(value, 160)
    match = re.search(r"(?:\$\s*)?(\d[\d,]*(?:\.\d{1,2})?)", clean)
    if not match:
        return _sentence_fragment(clean, 120)
    number = match.group(1).replace(",", "")
    try:
        amount = float(number)
    except ValueError:
        return _sentence_fragment(clean, 120)
    if amount.is_integer():
        return f"${int(amount):,}"
    return f"${amount:,.2f}"


def _minimum_price(context: dict[str, Any]) -> str:
    for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 300):
        match = re.search(
            r"minimum(?:\s+acceptable)?\s+price\s*:\s*(\$?[\d,]+(?:\.\d{1,2})?)",
            item,
            flags=re.IGNORECASE,
        )
        if match:
            return _normalize_money(match.group(1))
    return ""


def _deadline_value(context: dict[str, Any]) -> str:
    for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 300):
        lowered = item.casefold()
        if any(token in lowered for token in ("deadline", "timing", "within", "by ", "month", "week", "day")):
            value = item.split(":", 1)[1].strip() if ":" in item else item
            return value.rstrip(".")
    return ""


def _fact_label_from_question(question: str) -> str:
    lowered = _clean_text(question, 260).casefold()
    if any(token in lowered for token in ("model", "year", "make", "mileage", "odometer")):
        return "Item details"
    if any(token in lowered for token in ("condition", "maintenance", "issues", "state")):
        return "Condition"
    if any(token in lowered for token in ("audience", "buyer", "customer")):
        return "Intended buyer"
    if any(token in lowered for token in ("requirement", "must", "constraint")):
        return "Requirement"
    return "Project detail"


def _clean_sale_detail(answer: str) -> str:
    clean = _sentence_fragment(answer, 360).strip().rstrip(".")
    clean = re.sub(r"\bit\s+has\s+(\d+)k\s+miles\b", lambda m: f"with {int(m.group(1)) * 1000:,} miles", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(\d+)k\s+miles\b", lambda m: f"{int(m.group(1)) * 1000:,} miles", clean, flags=re.IGNORECASE)
    return _clean_text(clean, 360)


def _apply_answer_to_target(
    context: dict[str, Any],
    target: str,
    raw_answer: str,
) -> bool:
    if _sale_context(context):
        if target == "price" and not _is_weak_acknowledgement(raw_answer):
            price = _normalize_money(raw_answer)
            if not price:
                return False
            context["constraints"] = [
                item
                for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 300)
                if "minimum acceptable price" not in item.casefold()
            ]
            return _prepend_unique(
                context,
                "constraints",
                f"Minimum acceptable price: {price}.",
                MAX_CONSTRAINTS,
            )
        if target == "platform" and not _is_weak_acknowledgement(raw_answer):
            platform = _clean_text(raw_answer, 180).strip().rstrip(".")
            platform = re.sub(
                r"^(?:let(?:'s|\s+us)\s+(?:go|use|start)\s+(?:with|to)?\s*|"
                r"i\s+(?:want|would\s+like)\s+to\s+(?:use|list\s+it\s+on)\s+)",
                "",
                platform,
                flags=re.IGNORECASE,
            ).strip()
            if not platform:
                return False
            context["decisions"] = [
                item
                for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 300)
                if "listing platform" not in item.casefold()
            ]
            return _prepend_unique(
                context,
                "decisions",
                f"{platform} was chosen as the listing platform.",
                MAX_DECISIONS,
            )
        if target == "assets" and not _is_weak_acknowledgement(raw_answer):
            if re.search(r"\b(?:already\s+)?(?:have|got|took|prepared)\b.*\b(?:photos?|pictures?|images?)\b", raw_answer, flags=re.IGNORECASE):
                return _prepend_unique(
                    context,
                    "recentProgress",
                    "Listing photos are ready.",
                    MAX_RECENT_PROGRESS,
                )
        if target == "detail" and not _is_weak_acknowledgement(raw_answer):
            answer = _clean_sale_detail(raw_answer)
            if not answer:
                return False
            pending = _sanitize_pending_question(context.get("pendingQuestion"))
            question = pending["question"] if pending else ""
            label = _fact_label_from_question(question)
            if label == "Item details":
                if context.get("subject") != answer:
                    context["subject"] = answer
                    return True
                return False
            return _prepend_unique(
                context,
                "knownFacts",
                f"{label}: {answer}.",
                MAX_FACTS,
            )
    return _ledger_base_apply_answer_to_target(context, target, raw_answer)


def _extract_explicit_structured_fields(text: str, context: dict[str, Any]) -> dict[str, str]:
    result = _ledger_base_extract_explicit_structured_fields(text, context)
    if not _sale_context(context):
        return result
    item_match = re.search(
        r"\b((?:19|20)\d{2}\s+[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+){0,3})\b",
        text,
    )
    if item_match:
        item = _clean_text(item_match.group(1), 220)
        mileage_match = re.search(r"\b(\d+)k\s+miles\b", text, flags=re.IGNORECASE)
        if mileage_match:
            item += f" with {int(mileage_match.group(1)) * 1000:,} miles"
        result["subject"] = item
    return result


def _sale_photos_ready(context: dict[str, Any]) -> bool:
    return _has_progress(context, "listing photos are ready", "photos are ready", "pictures are ready") or any(
        "photos are ready" in item.casefold()
        for item in _clean_list(context.get("knownFacts"), MAX_FACTS, 300)
    )


def _sale_platform(context: dict[str, Any]) -> str:
    for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 300):
        match = re.match(r"(.+?)\s+was chosen as the listing platform\.", item, flags=re.IGNORECASE)
        if match:
            return _clean_text(match.group(1), 100)
    return ""


def _sale_artifact_approved(context: dict[str, Any], artifact: str) -> bool:
    needle = artifact.casefold()
    return any(
        needle in item.casefold() and any(token in item.casefold() for token in ("approved", "finalized"))
        for item in [
            *_clean_list(context.get("decisions"), MAX_DECISIONS, 300),
            *_clean_list(context.get("recentProgress"), MAX_RECENT_PROGRESS, 300),
        ]
    )


def _sale_listing_published(context: dict[str, Any]) -> bool:
    return _has_progress(context, "listing was published", "listing has been posted", "ad was posted")


def _sale_item_sold(context: dict[str, Any]) -> bool:
    return _has_progress(context, "item was sold", "motorcycle was sold", "vehicle was sold")


def _sale_core_details_ready(context: dict[str, Any]) -> bool:
    condition_known = "condition:" in _context_text(context, "knownFacts")
    return bool(
        _clean_text(context.get("successCriteria"), 500)
        and _deadline_value(context)
        and _minimum_price(context)
        and _clean_text(context.get("subject"), 300)
        and condition_known
    )


def _refresh_derived_objective(context: dict[str, Any]) -> None:
    if not _sale_context(context):
        _ledger_base_refresh_derived_objective(context)
        return
    subject = _clean_text(context.get("subject"), 300)
    success = _clean_text(context.get("successCriteria"), 500)
    deadline = _deadline_value(context)
    price = _minimum_price(context)
    item = subject or "the item"
    objective = f"Sell {item}"
    if deadline:
        objective += f" {deadline}" if deadline.casefold().startswith(("within", "by", "before")) else f" within {deadline}"
    if price:
        objective += f" for at least {price}"
    elif success and "sold" not in success.casefold():
        objective += f" with success defined as {success}"
    context["objective"] = objective.rstrip(".") + "."


def _specific_questions(context: dict[str, Any]) -> list[str]:
    if not _sale_context(context):
        return _ledger_base_specific_questions(context)
    if context.get("stage") == "complete":
        return []
    questions: list[str] = []
    if not _clean_text(context.get("successCriteria"), 500):
        questions.append("What result would make this sale successful for you?")
    if not _deadline_value(context):
        questions.append("Within what timeline do you want the item sold?")
    if not _minimum_price(context):
        questions.append("What is your minimum acceptable price?")
    if not _clean_text(context.get("subject"), 300):
        questions.append("What are the item's year, make, model, and mileage or equivalent details?")
    if "condition:" not in _context_text(context, "knownFacts"):
        questions.append("How would you describe the item's condition, maintenance, and known issues?")
    if _sale_core_details_ready(context) and not _sale_platform(context):
        questions.append("Which marketplace or platform will you use first?")
    return questions


def _derive_stage(context: dict[str, Any]) -> str:
    if not _sale_context(context):
        return _ledger_base_derive_stage(context)
    if _sale_item_sold(context):
        return "complete"
    if _sale_listing_published(context):
        return "in-progress"
    description_ready = _sale_artifact_approved(context, "listing description")
    title_ready = _sale_artifact_approved(context, "listing title and opening")
    if _sale_photos_ready(context) and description_ready and _sale_platform(context) and title_ready:
        return "ready"
    if description_ready or _sale_photos_ready(context) or _sale_platform(context):
        return "in-progress"
    if _sale_core_details_ready(context):
        return "planning"
    return "discovery"


def _refresh_questions_and_next_action(context: dict[str, Any], user_text: str) -> None:
    _ledger_base_refresh_questions_and_next_action(context, user_text)
    if not _sale_context(context):
        return

    context["focusType"] = "sale"
    if context.get("mode") == "general":
        context["mode"] = "planning"
    _refresh_derived_objective(context)
    context["stage"] = _derive_stage(context)

    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    candidates = [
        *([pending["question"]] if pending and not _question_answered(pending["question"], user_text, context) else []),
        *_specific_questions(context),
    ]
    questions: list[str] = []
    for question in candidates:
        if question in questions or _question_answered(question, user_text, context):
            continue
        questions.append(question)
        if len(questions) >= MAX_OPEN_QUESTIONS:
            break
    context["openQuestions"] = questions

    if context["stage"] == "complete":
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["nextAction"] = "The item has been sold. End the focus and save a brief outcome summary if useful."
        return
    if _sale_listing_published(context):
        context["nextAction"] = "Monitor buyer inquiries, screen serious offers, and arrange a safe public meeting for the sale."
        return
    if context["stage"] == "ready":
        platform = _sale_platform(context) or "the chosen marketplace"
        context["nextAction"] = f"Publish the approved listing on {platform} with the prepared photos, then verify the live post."
        return
    if not _clean_text(context.get("successCriteria"), 500):
        context["nextAction"] = "Define what a successful sale looks like."
    elif not _deadline_value(context):
        context["nextAction"] = "Set the target timeline for selling the item."
    elif not _minimum_price(context):
        context["nextAction"] = "Set the minimum acceptable price."
    elif not _clean_text(context.get("subject"), 300):
        context["nextAction"] = "Record the item's year, make, model, mileage, and other identifying details."
    elif "condition:" not in _context_text(context, "knownFacts"):
        context["nextAction"] = "Record the item's honest condition, maintenance, and known issues."
    elif not _sale_photos_ready(context):
        context["nextAction"] = "Prepare clear listing photos of the item and its important details."
    elif not _sale_artifact_approved(context, "listing description"):
        context["nextAction"] = "Draft and approve the listing description using the known item details."
    elif not _sale_platform(context):
        context["nextAction"] = "Choose the first marketplace where the listing will be posted."
    elif not _sale_artifact_approved(context, "listing title and opening"):
        context["nextAction"] = "Finalize the listing title and opening lines for the chosen marketplace."
    else:
        context["nextAction"] = "Publish the listing with the approved copy and prepared photos."


def _question_answered(question: str, text: str, context: dict[str, Any]) -> bool:
    target = _question_target(question, context)
    if _sale_context(context):
        if target == "price":
            return bool(_minimum_price(context))
        if target == "platform":
            return bool(_sale_platform(context))
        if target == "assets":
            return _sale_photos_ready(context)
        if target == "detail":
            label = _fact_label_from_question(question)
            if label == "Item details":
                return bool(_clean_text(context.get("subject"), 300))
            if label == "Condition":
                return "condition:" in _context_text(context, "knownFacts")
            return False
    return _ledger_base_question_answered(question, text, context)


def _detect_workflow_artifact(reply: str, context: dict[str, Any]) -> str:
    lowered = _clean_text(reply, 4000).casefold()
    if _sale_context(context):
        if "title:" in lowered and ("opening line:" in lowered or "opening:" in lowered):
            return "listing title and opening"
        if any(
            marker in lowered
            for marker in (
                "starting draft for your listing description",
                "draft for your listing description",
                "listing description:",
            )
        ):
            return "listing description"
    return ""


def _workflow_acceptance(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9']+", " ", text.casefold()).strip()
    return _is_acceptance(text) or bool(
        re.fullmatch(
            r"(?:no\s+)?(?:this|that|it)\s+(?:is|looks|sounds)\s+(?:really\s+)?(?:good|great|perfect|fine)",
            normalized,
        )
        or normalized in {"no this is good", "no that's good", "this is good", "that's good"}
    )


def _workflow_artifact_decision(artifact: str) -> str:
    verb = "were" if artifact == "listing title and opening" else "was"
    return f"The {artifact} {verb} approved."


def _workflow_artifact_progress(artifact: str) -> str:
    verb = "were" if artifact == "listing title and opening" else "was"
    return f"The {artifact} {verb} finalized."


def _apply_user_update(
    context: dict[str, Any],
    user_text: str,
) -> tuple[dict[str, Any], bool]:
    next_context, changed = _ledger_base_apply_user_update(context, user_text)
    if not _sale_context(next_context):
        return next_context, changed

    next_context["focusType"] = "sale"
    if next_context.get("mode") == "general":
        next_context["mode"] = "planning"
    text = _clean_text(user_text, 1400)
    lowered = text.casefold()

    # Remove the generic requirement produced by older versions when the value
    # is actually a sale deadline, then add a normalized timing constraint.
    sale_deadline = re.search(
        r"\b(?:want|need|would\s+like)\s+(?:it|the\s+(?:item|motorcycle|bike|car|vehicle))\s+sold\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if sale_deadline:
        timing = _sentence_fragment(sale_deadline.group(1), 140).rstrip(".")
        next_context["constraints"] = [
            item
            for item in _clean_list(next_context.get("constraints"), MAX_CONSTRAINTS, 300)
            if not (
                item.casefold().startswith("requirement:")
                and "sold" in item.casefold()
            )
            and not item.casefold().startswith("deadline or timing:")
        ]
        changed = _prepend_unique(
            next_context,
            "constraints",
            f"Deadline or timing: {timing}.",
            MAX_CONSTRAINTS,
        ) or changed

    price_match = re.search(
        r"\b(?:minimum(?:\s+acceptable)?|lowest|at\s+least|won't\s+take\s+less\s+than|"
        r"would\s+accept(?:\s+a\s+minimum\s+of)?|would\s+except\s+minimum)\D{0,18}(\$?\s*\d[\d,]*(?:\.\d{1,2})?)",
        text,
        flags=re.IGNORECASE,
    )
    if price_match:
        price = _normalize_money(price_match.group(1))
        next_context["constraints"] = [
            item
            for item in _clean_list(next_context.get("constraints"), MAX_CONSTRAINTS, 300)
            if "minimum acceptable price" not in item.casefold()
        ]
        changed = _prepend_unique(
            next_context,
            "constraints",
            f"Minimum acceptable price: {price}.",
            MAX_CONSTRAINTS,
        ) or changed

    item_match = re.search(
        r"\b((?:19|20)\d{2}\s+[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+){0,3})\b",
        text,
    )
    if item_match:
        subject = _clean_text(item_match.group(1), 220)
        mileage_match = re.search(r"\b(\d+)k\s+miles\b", text, flags=re.IGNORECASE)
        if mileage_match:
            subject += f" with {int(mileage_match.group(1)) * 1000:,} miles"
        if next_context.get("subject") != subject:
            next_context["subject"] = subject
            changed = True

    if re.search(r"\b(?:works?|runs?|rides?)\s+(?:fine|well|great|good)\b", lowered):
        condition = "Runs well"
        if re.search(r"\b(?:high\s+mileage|getting\s+up\s+in\s+miles|a\s+lot\s+of\s+miles)\b", lowered):
            condition += "; mileage is high"
        next_context["knownFacts"] = [
            item
            for item in _clean_list(next_context.get("knownFacts"), MAX_FACTS, 300)
            if not item.casefold().startswith("condition:")
        ]
        changed = _prepend_unique(
            next_context,
            "knownFacts",
            f"Condition: {condition}.",
            MAX_FACTS,
        ) or changed

    if re.search(
        r"\b(?:already\s+)?(?:have|got|took|prepared)\b.*\b(?:photos?|pictures?|images?)\b",
        text,
        flags=re.IGNORECASE,
    ):
        changed = _prepend_unique(
            next_context,
            "recentProgress",
            "Listing photos are ready.",
            MAX_RECENT_PROGRESS,
        ) or changed

    platform_match = re.search(
        r"\b(?:let(?:'s|\s+us)\s+(?:go|use|start)\s+(?:with|to)?\s*|"
        r"i\s+(?:want|would\s+like)\s+to\s+(?:use|list\s+it\s+on)\s+)"
        r"(craigslist|facebook\s+marketplace|cycle\s*trader|offerup|ebay(?:\s+motors)?)\b",
        text,
        flags=re.IGNORECASE,
    )
    if platform_match:
        platform = platform_match.group(1)
        platform = "Craigslist" if platform.casefold() == "craigslist" else platform.title()
        next_context["decisions"] = [
            item
            for item in _clean_list(next_context.get("decisions"), MAX_DECISIONS, 300)
            if "listing platform" not in item.casefold()
        ]
        changed = _prepend_unique(
            next_context,
            "decisions",
            f"{platform} was chosen as the listing platform.",
            MAX_DECISIONS,
        ) or changed

    if re.search(r"\b(?:i|we)\s+(?:posted|published|listed)\b.*\b(?:listing|ad|motorcycle|bike|item|vehicle)\b", lowered):
        changed = _prepend_unique(
            next_context,
            "recentProgress",
            "The listing was published.",
            MAX_RECENT_PROGRESS,
        ) or changed
    if re.search(r"\b(?:i|we)\s+(?:sold|have\s+sold)\b.*\b(?:motorcycle|bike|item|vehicle|it)\b", lowered):
        changed = _prepend_unique(
            next_context,
            "recentProgress",
            "The item was sold.",
            MAX_RECENT_PROGRESS,
        ) or changed

    # Remove generic pending-question facts when a more specific sale event was
    # captured from the same message.
    next_context["knownFacts"] = [
        item
        for item in _clean_list(next_context.get("knownFacts"), MAX_FACTS, 300)
        if not (
            item.casefold().startswith("project detail:")
            and any(
                token in item.casefold()
                for token in (
                    "photo", "picture", "image", "craigslist", "marketplace",
                    "cycle trader", "offerup", "let's go", "already have",
                )
            )
        )
    ]

    artifact = _clean_text(next_context.get("lastAssistantArtifact"), 100)
    if artifact and _workflow_acceptance(text):
        decision = _workflow_artifact_decision(artifact)
        progress = _workflow_artifact_progress(artifact)
        changed = _prepend_unique(next_context, "decisions", decision, MAX_DECISIONS) or changed
        changed = _prepend_unique(next_context, "recentProgress", progress, MAX_RECENT_PROGRESS) or changed
        next_context["decisions"] = [
            item
            for item in _clean_list(next_context.get("decisions"), MAX_DECISIONS, 300)
            if item.casefold() != "the most recent proposed plan or draft was accepted."
        ]

    before = (
        next_context.get("objective", ""),
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    _refresh_derived_objective(next_context)
    _refresh_questions_and_next_action(next_context, text)
    after = (
        next_context.get("objective", ""),
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    if before != after:
        changed = True
    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _extract_assistant_pending_question(
    reply: str,
    context: dict[str, Any],
) -> dict[str, str] | None:
    normalized = reply.replace("\r\n", "\n").replace("\r", "\n")
    candidates: list[str] = []
    for match in re.finditer(
        r"(?i)(?<![A-Za-z])(?:what|what's|who|which|how|when|where|why|"
        r"is\s+(?:there|the|your|this|that)|are\s+(?:there|the|your)|"
        r"do\s+you\s+already\s+have|have\s+you|could\s+you\s+tell\s+me|"
        r"can\s+you\s+tell\s+me|tell\s+me)\b[^?\n]{2,260}\?",
        normalized,
    ):
        question = _clean_text(match.group(0), 260)
        if _is_information_question(question):
            candidates.append(question)
    for question in reversed(candidates):
        target = _question_target(question, context)
        if target and not _question_answered(question, "", context):
            return {"target": target, "question": question}
    return None


def _apply_assistant_update(
    context: dict[str, Any],
    reply: str,
) -> tuple[dict[str, Any], bool]:
    next_context, changed = _ledger_base_apply_assistant_update(context, reply)
    if not _sale_context(next_context):
        return next_context, changed

    next_context["focusType"] = "sale"
    if next_context.get("mode") == "general":
        next_context["mode"] = "planning"

    artifact = _detect_workflow_artifact(reply, next_context)
    if artifact:
        if next_context.get("lastAssistantArtifact") != artifact:
            next_context["lastAssistantArtifact"] = artifact
            changed = True
        progress_text = (
            "QMeet drafted the listing description."
            if artifact == "listing description"
            else "QMeet drafted the listing title and opening."
        )
        changed = _prepend_unique(
            next_context,
            "recentProgress",
            progress_text,
            MAX_RECENT_PROGRESS,
        ) or changed

    pending = _extract_assistant_pending_question(reply, next_context)
    if pending and next_context.get("pendingQuestion") != pending:
        next_context["pendingQuestion"] = pending
        changed = True

    # An assistant suggestion cannot undo a completed user asset. Keep the
    # durable next action derived from the ledger instead of a repeated offer.
    before = (
        next_context.get("objective", ""),
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    _refresh_derived_objective(next_context)
    _refresh_questions_and_next_action(next_context, "")
    after = (
        next_context.get("objective", ""),
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    if before != after:
        changed = True
    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _sanitize_context(raw: object) -> dict[str, Any] | None:
    context = _ledger_base_sanitize_context(raw)
    if context is None:
        return None
    _refresh_focus_type(context)
    if not _sale_context(context):
        return context

    context["focusType"] = "sale"
    if context.get("mode") == "general":
        context["mode"] = "planning"

    # Clean the generic values produced by the previous learner.
    constraints: list[str] = []
    for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 300):
        if item.casefold().startswith("requirement:") and "sold" in item.casefold():
            value = item.split(":", 1)[1].strip().rstrip(".")
            match = re.search(r"\bsold\s+(.+)$", value, flags=re.IGNORECASE)
            if match:
                item = f"Deadline or timing: {match.group(1).strip()}."
        constraints.append(item)
    context["constraints"] = _clean_list(constraints, MAX_CONSTRAINTS, 300)

    context["decisions"] = [
        item
        for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 300)
        if item.casefold() != "the most recent proposed plan or draft was accepted."
        or not context.get("lastAssistantArtifact")
    ]
    _refresh_derived_objective(context)
    _refresh_questions_and_next_action(context, "")
    return context


def prepare_background_chat_message(message: str) -> tuple[str, str]:
    contextual_message, visible_user_message = _ledger_base_prepare_background_chat_message(message)
    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if not isinstance(context, dict) or not _sale_context(context):
        return contextual_message, visible_user_message

    continuity_rules = [
        "Sale/listing continuity rules:",
        "- Treat the objective, constraints, decisions, and completed progress as a durable sale checklist.",
        "- Do not ask for photos when progress says the listing photos are ready.",
        "- Do not redraft copy that decisions say was approved unless the user requests revisions.",
        "- Advance in order: collect item facts, prepare photos, approve copy, choose a platform, publish, handle inquiries, complete the sale.",
        "- When the context stage is ready, guide the user to publish the prepared listing rather than returning to discovery.",
        "- If the user says they are good, done for now, or thanks while the stage is ready, acknowledge that the preparation is finished but do not imply the listing is published or the item is sold.",
        "- Never claim an item is well-maintained, regularly serviced, issue-free, or ready to ride unless the user actually said so.",
        "",
    ]
    marker = "Existing request and private context:"
    if marker in contextual_message:
        contextual_message = contextual_message.replace(
            marker,
            "\n".join(continuity_rules) + marker,
            1,
        )
    return contextual_message, visible_user_message

# ---------------------------------------------------------------------------
# Phase 18: sale transaction milestones and completion continuity
# ---------------------------------------------------------------------------
# The workflow ledger above understands sale preparation, but ordinary short
# updates such as "I posted it" and "got it sold in cash" can omit the noun that
# the original regular expressions expected. This final layer records those
# durable transaction events, keeps discovery questions closed after a listing
# is live, and prevents the assistant from assuming assets the user never said
# were ready.

_sale_tx_base_apply_answer_to_target = _apply_answer_to_target
_sale_tx_base_sale_listing_published = _sale_listing_published
_sale_tx_base_sale_item_sold = _sale_item_sold
_sale_tx_base_specific_questions = _specific_questions
_sale_tx_base_derive_stage = _derive_stage
_sale_tx_base_refresh_questions_and_next_action = _refresh_questions_and_next_action
_sale_tx_base_apply_user_update = _apply_user_update
_sale_tx_base_sanitize_context = _sanitize_context
_sale_tx_base_prepare_background_chat_message = prepare_background_chat_message


def _sale_subject_label(context: dict[str, Any]) -> str:
    subject = _clean_text(context.get("subject"), 300)
    lowered = subject.casefold()
    if "motorcycle" in lowered or re.search(r"\b(?:sv\d+|bike)\b", lowered):
        return "motorcycle"
    if "car" in lowered or "vehicle" in lowered:
        return "vehicle"
    return "item"


def _normalize_sale_platform(value: str) -> str:
    clean = _clean_text(value, 180).strip().rstrip(".")
    clean = re.sub(
        r"^(?:probably|maybe|likely|i\s+think|i'd\s+say|"
        r"let(?:'s|\s+us)\s+(?:go|use|start)\s+(?:with|to)?\s*|"
        r"i\s+(?:want|would\s+like)\s+to\s+(?:use|list\s+it\s+on)\s+)",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()
    aliases = {
        "caigslist": "Craigslist",
        "craiglist": "Craigslist",
        "craigslist": "Craigslist",
        "facebook marketplace": "Facebook Marketplace",
        "cycle trader": "Cycle Trader",
        "offerup": "OfferUp",
        "ebay motors": "eBay Motors",
    }
    return aliases.get(clean.casefold(), clean)


def _normalize_sale_timing(value: str) -> str:
    clean = _normalize_answer_text(value, "deadline")
    clean = re.sub(
        r"(?:,?\s+)?(?:i(?:'d|\s+would)\s+say|i\s+think|probably|maybe)$",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip().rstrip(".")
    return _clean_text(clean, 180)


def _extract_money_values(text: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"(?:\$\s*)?(\d[\d,]*(?:\.\d{1,2})?)", text):
        raw = match.group(1)
        try:
            numeric = float(raw.replace(",", ""))
        except ValueError:
            continue
        # Years, mileage fragments, and tiny incidental numbers are not offers.
        if numeric < 100:
            continue
        normalized = _normalize_money(raw)
        if normalized and normalized not in seen:
            values.append(normalized)
            seen.add(normalized)
    return values


def _sale_offer_amount(context: dict[str, Any]) -> str:
    entries = [
        *_clean_list(context.get("knownFacts"), MAX_FACTS, 300),
        *_clean_list(context.get("decisions"), MAX_DECISIONS, 300),
        *_clean_list(context.get("recentProgress"), MAX_RECENT_PROGRESS, 300),
    ]
    for item in entries:
        if not any(token in item.casefold() for token in ("offer", "sold for", "sale price")):
            continue
        values = _extract_money_values(item)
        if values:
            return values[0]
    return ""


def _sale_offer_received(context: dict[str, Any]) -> bool:
    return any(
        "offer received" in item.casefold() or "buyer offered" in item.casefold()
        for item in [
            *_clean_list(context.get("knownFacts"), MAX_FACTS, 300),
            *_clean_list(context.get("recentProgress"), MAX_RECENT_PROGRESS, 300),
        ]
    )


def _sale_buyer_verified(context: dict[str, Any]) -> bool:
    return _has_progress(
        context,
        "buyer and payment were verified",
        "buyer was verified",
        "safe handoff was completed",
    )


def _sale_listing_published(context: dict[str, Any]) -> bool:
    if _sale_tx_base_sale_listing_published(context):
        return True
    return any(
        any(
            token in item.casefold()
            for token in (
                "listing is live",
                "listing went live",
                "listing was published",
                "listing was posted",
                "listing has been published",
                "listing has been posted",
                "ad is live",
                "ad went live",
                "ad was published",
                "ad was posted",
            )
        )
        for item in _clean_list(context.get("recentProgress"), MAX_RECENT_PROGRESS, 300)
    )


def _sale_item_sold(context: dict[str, Any]) -> bool:
    if _sale_tx_base_sale_item_sold(context):
        return True
    return any(
        any(
            token in item.casefold()
            for token in (
                "sale was completed",
                "sale is complete",
                "transaction was completed",
                "payment was received and the item was handed over",
                "sold for $",
                "sold in cash",
            )
        )
        for item in _clean_list(context.get("recentProgress"), MAX_RECENT_PROGRESS, 300)
    )


def _apply_answer_to_target(
    context: dict[str, Any],
    target: str,
    raw_answer: str,
) -> bool:
    if _sale_context(context):
        if target == "successCriteria" and not _is_weak_acknowledgement(raw_answer):
            values = _extract_money_values(raw_answer)
            lowered = raw_answer.casefold()
            changed = False
            if values and any(
                token in lowered
                for token in ("minimum", "asking", "at least", "lowest", "accept", "except")
            ):
                price = values[0]
                context["constraints"] = [
                    item
                    for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 300)
                    if "minimum acceptable price" not in item.casefold()
                ]
                changed = _prepend_unique(
                    context,
                    "constraints",
                    f"Minimum acceptable price: {price}.",
                    MAX_CONSTRAINTS,
                ) or changed
                success = f"Sell the item for at least {price}."
            else:
                answer = _normalize_answer_text(raw_answer, target)
                if not answer:
                    return changed
                answer = re.sub(r"^eventually\s+", "", answer, flags=re.IGNORECASE)
                if "sold" in answer.casefold() or "sell" in answer.casefold():
                    success = answer[0].upper() + answer[1:]
                    success = success.rstrip(".") + "."
                else:
                    success = answer
            if context.get("successCriteria") != success:
                context["successCriteria"] = success
                changed = True
            return changed
        if target == "platform" and not _is_weak_acknowledgement(raw_answer):
            platform = _normalize_sale_platform(raw_answer)
            if not platform:
                return False
            context["decisions"] = [
                item
                for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 300)
                if "listing platform" not in item.casefold()
            ]
            return _prepend_unique(
                context,
                "decisions",
                f"{platform} was chosen as the listing platform.",
                MAX_DECISIONS,
            )
        if target == "deadline" and not _is_weak_acknowledgement(raw_answer):
            timing = _normalize_sale_timing(raw_answer)
            if not timing:
                return False
            context["constraints"] = [
                item
                for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 300)
                if not item.casefold().startswith("deadline or timing:")
            ]
            return _prepend_unique(
                context,
                "constraints",
                f"Deadline or timing: {timing}.",
                MAX_CONSTRAINTS,
            )
    return _sale_tx_base_apply_answer_to_target(context, target, raw_answer)


def _record_sale_publication(context: dict[str, Any]) -> bool:
    changed = _prepend_unique(
        context,
        "recentProgress",
        "The listing was published and is live.",
        MAX_RECENT_PROGRESS,
    )
    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    if pending and pending.get("target") in {"assets", "platform", "detail"}:
        context["pendingQuestion"] = None
        changed = True
    return changed


def _record_sale_offer(context: dict[str, Any], amount: str) -> bool:
    changed = False
    context["knownFacts"] = [
        item
        for item in _clean_list(context.get("knownFacts"), MAX_FACTS, 300)
        if "offer received" not in item.casefold()
        and "buyer offered" not in item.casefold()
    ]
    if amount:
        changed = _prepend_unique(
            context,
            "knownFacts",
            f"Offer received: {amount}.",
            MAX_FACTS,
        ) or changed
        changed = _prepend_unique(
            context,
            "recentProgress",
            f"A buyer offered {amount}.",
            MAX_RECENT_PROGRESS,
        ) or changed
    else:
        changed = _prepend_unique(
            context,
            "recentProgress",
            "A buyer made an offer.",
            MAX_RECENT_PROGRESS,
        ) or changed
    return changed


def _record_sale_completion(
    context: dict[str, Any],
    text: str,
    amount: str,
) -> bool:
    changed = False
    item_label = _sale_subject_label(context)
    payment = " in cash" if re.search(r"\b(?:cash|cash payment)\b", text, flags=re.IGNORECASE) else ""
    amount_text = f" for {amount}" if amount else ""
    changed = _prepend_unique(
        context,
        "recentProgress",
        f"The {item_label} was sold{amount_text}{payment}.",
        MAX_RECENT_PROGRESS,
    ) or changed
    changed = _prepend_unique(
        context,
        "recentProgress",
        "The sale was completed.",
        MAX_RECENT_PROGRESS,
    ) or changed
    if amount:
        changed = _prepend_unique(
            context,
            "decisions",
            f"The {amount} offer was accepted.",
            MAX_DECISIONS,
        ) or changed
    if payment:
        changed = _prepend_unique(
            context,
            "knownFacts",
            "Payment was received in cash.",
            MAX_FACTS,
        ) or changed
    context["pendingQuestion"] = None
    context["openQuestions"] = []
    return changed


def _capture_sale_transaction_events(context: dict[str, Any], text: str) -> bool:
    if not _sale_context(context):
        return False
    clean = _clean_text(text, 1600)
    lowered = clean.casefold()
    changed = False

    published = bool(
        re.search(
            r"\b(?:i|we)\s+(?:(?:have|'ve)\s+)?(?:posted|published|listed|put\s+up)\s+"
            r"(?:it|the\s+(?:listing|ad|motorcycle|bike|item|vehicle))\b",
            lowered,
        )
        or re.search(
            r"\b(?:the\s+)?(?:listing|ad)\s+(?:is|went|has\s+gone)\s+(?:live|up|online|posted|published)\b",
            lowered,
        )
        or re.fullmatch(r"(?:i\s+)?(?:posted|published|listed)\s+it[.!]?", lowered)
    )
    if published:
        changed = _record_sale_publication(context) or changed

    offer_match = re.search(
        r"\b(?:i|we)\s+(?:got|received|have|have\s+got)\s+"
        r"(?:someone\s+)?(?:who\s+is\s+)?offer(?:ing|ed)?\s*(?:me\s+)?(?:of\s+|for\s+)?"
        r"\$?\s*(\d[\d,]*(?:\.\d{1,2})?)\b",
        lowered,
    )
    if not offer_match:
        offer_match = re.search(
            r"\b(?:someone|a\s+buyer|the\s+buyer)\s+(?:is\s+)?offer(?:ing|ed)\s+"
            r"(?:me\s+)?\$?\s*(\d[\d,]*(?:\.\d{1,2})?)\b",
            lowered,
        )
    if offer_match:
        changed = _record_sale_offer(context, _normalize_money(offer_match.group(1))) or changed

    if re.search(
        r"\b(?:verified|checked)\b.*\b(?:buyer|identity|payment)\b|"
        r"\b(?:buyer|payment)\b.*\b(?:verified|checked|secure)\b|"
        r"\bmet\s+(?:with\s+)?(?:the\s+buyer|him|her|them)\b.*\b(?:safe|public|daylight)\b",
        lowered,
    ):
        changed = _prepend_unique(
            context,
            "recentProgress",
            "The buyer and payment were verified.",
            MAX_RECENT_PROGRESS,
        ) or changed

    sold = bool(
        re.search(
            r"\b(?:i|we)\s+(?:(?:have|'ve)\s+)?(?:sold\s+(?:it|the\s+(?:motorcycle|bike|item|vehicle))|"
            r"got\s+(?:it|the\s+(?:motorcycle|bike|item|vehicle))\s+sold)\b",
            lowered,
        )
        or re.search(
            r"\b(?:it|the\s+(?:motorcycle|bike|item|vehicle))\s+(?:is|was|has\s+been)\s+sold\b",
            lowered,
        )
        or re.search(
            r"\b(?:sale|transaction)\s+(?:is|was|has\s+been)\s+(?:complete|completed|done|finished)\b",
            lowered,
        )
        or (
            re.search(r"\bgot\s+(?:it|the\s+(?:motorcycle|bike|item|vehicle))\s+sold\b", lowered)
            and re.search(r"\b(?:cash|paid|payment)\b", lowered)
        )
    )
    if sold:
        values = _extract_money_values(clean)
        amount = values[-1] if values else _sale_offer_amount(context)
        changed = _record_sale_completion(context, clean, amount) or changed

    return changed


def _specific_questions(context: dict[str, Any]) -> list[str]:
    if _sale_context(context) and (_sale_listing_published(context) or _sale_item_sold(context)):
        return []
    return _sale_tx_base_specific_questions(context)


def _derive_stage(context: dict[str, Any]) -> str:
    if not _sale_context(context):
        return _sale_tx_base_derive_stage(context)
    if _sale_item_sold(context):
        return "complete"
    if _sale_listing_published(context) or _sale_offer_received(context):
        return "in-progress"
    return _sale_tx_base_derive_stage(context)


def _refresh_questions_and_next_action(context: dict[str, Any], user_text: str) -> None:
    _sale_tx_base_refresh_questions_and_next_action(context, user_text)
    if not _sale_context(context):
        return

    context["focusType"] = "sale"
    context["stage"] = _derive_stage(context)

    if context["stage"] == "complete":
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["nextAction"] = (
            "The sale is complete. End the focus and save a brief outcome summary; "
            "only handle title transfer or listing removal if either is still outstanding."
        )
        return

    if _sale_offer_received(context):
        amount = _sale_offer_amount(context)
        minimum = _minimum_price(context)
        comparison = ""
        if amount and minimum:
            comparison = f" The {amount} offer is above the {minimum} minimum."
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["nextAction"] = (
            f"Verify the buyer and payment method, decide whether to accept the offer, "
            f"and arrange a safe handoff.{comparison}"
        ).strip()
        return

    if _sale_listing_published(context):
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["nextAction"] = (
            "Monitor inquiries, screen serious offers, verify payment, and arrange a safe handoff."
        )


def _apply_user_update(
    context: dict[str, Any],
    user_text: str,
) -> tuple[dict[str, Any], bool]:
    next_context, changed = _sale_tx_base_apply_user_update(context, user_text)
    if not _sale_context(next_context):
        return next_context, changed

    next_context["focusType"] = "sale"
    text = _clean_text(user_text, 1600)
    changed = _capture_sale_transaction_events(next_context, text) or changed

    # Correct generic success text that is really a minimum-price statement.
    success = _clean_text(next_context.get("successCriteria"), 500)
    success_values = _extract_money_values(success)
    if success_values and any(
        token in success.casefold()
        for token in ("minimum", "asking", "at least", "lowest", "accept", "except")
    ):
        normalized_success = f"Sell the item for at least {success_values[0]}."
        if next_context.get("successCriteria") != normalized_success:
            next_context["successCriteria"] = normalized_success
            changed = True

    before = (
        next_context.get("objective", ""),
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    _refresh_derived_objective(next_context)
    _refresh_questions_and_next_action(next_context, text)
    after = (
        next_context.get("objective", ""),
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    if before != after:
        changed = True
    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _sanitize_context(raw: object) -> dict[str, Any] | None:
    context = _sale_tx_base_sanitize_context(raw)
    if context is None or not _sale_context(context):
        return context

    context["focusType"] = "sale"

    # Normalize platform decisions created from tentative wording or common
    # speech-to-text spellings such as "probably caigslist".
    normalized_decisions: list[str] = []
    for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 300):
        match = re.match(r"(.+?)\s+was chosen as the listing platform\.", item, flags=re.IGNORECASE)
        if match:
            platform = _normalize_sale_platform(match.group(1))
            item = f"{platform} was chosen as the listing platform."
        normalized_decisions.append(item)
    context["decisions"] = _clean_list(normalized_decisions, MAX_DECISIONS, 300)

    normalized_constraints: list[str] = []
    for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 300):
        if item.casefold().startswith("deadline or timing:"):
            value = item.split(":", 1)[1].strip()
            timing = _normalize_sale_timing(value)
            item = f"Deadline or timing: {timing}." if timing else item
        normalized_constraints.append(item)
    context["constraints"] = _clean_list(normalized_constraints, MAX_CONSTRAINTS, 300)

    success = _clean_text(context.get("successCriteria"), 500)
    values = _extract_money_values(success)
    if values and any(
        token in success.casefold()
        for token in ("minimum", "asking", "at least", "lowest", "accept", "except")
    ):
        context["successCriteria"] = f"Sell the item for at least {values[0]}."

    _refresh_derived_objective(context)
    _refresh_questions_and_next_action(context, "")
    return context


def prepare_background_chat_message(message: str) -> tuple[str, str]:
    contextual_message, visible_user_message = _sale_tx_base_prepare_background_chat_message(message)
    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if not isinstance(context, dict) or not _sale_context(context):
        return contextual_message, visible_user_message

    transaction_rules = [
        "Sale transaction-state rules:",
        "- Never assume photos, a clean title, service history, maintenance quality, ownership paperwork, or buyer verification unless the user explicitly provided it or progress records it.",
        "- A live or published listing closes the preparation interview. Do not return to photo, copy, price, condition, or platform questions unless the user asks to revise the listing.",
        "- When an offer exists, compare it with the recorded minimum price and focus on buyer verification, secure payment, safe handoff, and the accept-or-decline decision.",
        "- When progress says the item was sold or the sale was completed, acknowledge completion. Do not ask another sales question or suggest more listing work.",
        "- Do not claim the sale is complete merely because an offer was received; completion requires the user's confirmation that payment and handoff occurred.",
        "",
    ]
    marker = "Existing request and private context:"
    if marker in contextual_message:
        contextual_message = contextual_message.replace(
            marker,
            "\n".join(transaction_rules) + marker,
            1,
        )
    return contextual_message, visible_user_message

# ---------------------------------------------------------------------------
# Phase 18: purchase workflow continuity and current-product safety
# ---------------------------------------------------------------------------
# A purchase focus is the inverse of the sale workflow: discover requirements,
# compare current options, choose a real listing, order, receive, and verify the
# product. This layer keeps those milestones durable and prevents current prices,
# availability, or retailer links from being invented in normal chat.

WORK_CONTEXT_FILE_VERSION = 8
FOCUS_TYPES.add("purchase")
QUESTION_TARGETS.update({"budget", "size", "brand", "model", "retailer", "placement"})

_purchase_base_infer_focus_type_from_text = _infer_focus_type_from_text
_purchase_base_question_target = _question_target
_purchase_base_question_answered = _question_answered
_purchase_base_apply_answer_to_target = _apply_answer_to_target
_purchase_base_refresh_derived_objective = _refresh_derived_objective
_purchase_base_specific_questions = _specific_questions
_purchase_base_derive_stage = _derive_stage
_purchase_base_refresh_questions_and_next_action = _refresh_questions_and_next_action
_purchase_base_apply_user_update = _apply_user_update
_purchase_base_apply_assistant_update = _apply_assistant_update
_purchase_base_sanitize_context = _sanitize_context
_purchase_base_prepare_background_chat_message = prepare_background_chat_message
_purchase_base_should_keep_focus_message_in_chat = should_keep_focus_message_in_chat

_PURCHASE_PRODUCT_RE = re.compile(
    r"\b(?:television|tv|laptop|computer|desktop|phone|smartphone|tablet|"
    r"monitor|camera|headphones?|speaker|soundbar|appliance|refrigerator|"
    r"washer|dryer|dishwasher|furniture|couch|sofa|desk|vehicle|car|"
    r"motorcycle|bike|console|projector)\b",
    flags=re.IGNORECASE,
)
_PURCHASE_INTENT_RE = re.compile(
    r"\b(?:buy|buying|purchase|purchasing|shop|shopping|order|ordering|"
    r"get|getting|pick(?:ing)?\s+out|choose|choosing|compare|comparing)\b",
    flags=re.IGNORECASE,
)


def _purchase_context(context: dict[str, Any]) -> bool:
    if _sale_context(context):
        return False
    haystack = " ".join(
        (
            _clean_text(context.get("title"), 180),
            _clean_text(context.get("objective"), 600),
            _clean_text(context.get("subject"), 360),
            " ".join(_clean_list(context.get("knownFacts"), MAX_FACTS, 300)),
            " ".join(_clean_list(context.get("decisions"), MAX_DECISIONS, 300)),
        )
    )
    return _clean_text(context.get("focusType"), 40) == "purchase" or bool(
        _PURCHASE_PRODUCT_RE.search(haystack) and _PURCHASE_INTENT_RE.search(haystack)
    )


def _infer_focus_type_from_text(text: str, mode: str) -> str:
    base_type = _purchase_base_infer_focus_type_from_text(text, mode)
    if base_type == "sale":
        return base_type
    clean = _clean_text(text, 1600)
    if _PURCHASE_PRODUCT_RE.search(clean) and _PURCHASE_INTENT_RE.search(clean):
        return "purchase"
    if re.search(
        r"\b(?:product|item)\s+(?:purchase|shopping|comparison)\b|"
        r"\b(?:best|current)\s+(?:model|deal|price)\b",
        clean,
        flags=re.IGNORECASE,
    ):
        return "purchase"
    return base_type


def _purchase_fact(context: dict[str, Any], prefix: str) -> str:
    prefix_key = prefix.casefold().rstrip(":")
    for item in _clean_list(context.get("knownFacts"), MAX_FACTS, 320):
        if item.casefold().startswith(f"{prefix_key}:"):
            return item.split(":", 1)[1].strip().rstrip(".")
    return ""


def _purchase_constraint(context: dict[str, Any], prefix: str) -> str:
    prefix_key = prefix.casefold().rstrip(":")
    for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 320):
        if item.casefold().startswith(f"{prefix_key}:"):
            return item.split(":", 1)[1].strip().rstrip(".")
    return ""


def _purchase_decision(context: dict[str, Any], suffix: str) -> str:
    suffix_key = suffix.casefold()
    for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 360):
        if suffix_key in item.casefold():
            return item.rstrip(".")
    return ""


def _replace_prefixed_item(
    context: dict[str, Any],
    key: str,
    prefix: str,
    value: str,
    max_items: int,
) -> bool:
    clean_value = _clean_text(value, 300).strip().rstrip(".")
    if not clean_value:
        return False
    prefix_key = prefix.casefold().rstrip(":")
    existing = _clean_list(context.get(key), max_items, 360)
    replacement = f"{prefix}: {clean_value}."
    filtered = [
        item
        for item in existing
        if not item.casefold().startswith(f"{prefix_key}:")
    ]
    changed = filtered != existing or replacement.casefold() not in {
        item.casefold() for item in existing
    }
    context[key] = [replacement, *filtered][:max_items]
    return changed


def _replace_purchase_decision(
    context: dict[str, Any],
    marker: str,
    decision: str,
) -> bool:
    clean_decision = _clean_text(decision, 340).strip().rstrip(".")
    if not clean_decision:
        return False
    marker_key = marker.casefold()
    existing = _clean_list(context.get("decisions"), MAX_DECISIONS, 360)
    replacement = f"{clean_decision}."
    filtered = [item for item in existing if marker_key not in item.casefold()]
    changed = filtered != existing or replacement.casefold() not in {
        item.casefold() for item in existing
    }
    context["decisions"] = [replacement, *filtered][:MAX_DECISIONS]
    return changed


def _normalize_screen_size(value: str) -> str:
    clean = _clean_text(value, 180)
    match = re.search(
        r"\b(\d{2,3})(?:\s*[- ]?\s*(?:inch(?:es)?|in\.?|\"))?\b",
        clean,
        flags=re.IGNORECASE,
    )
    if match:
        size = int(match.group(1))
        if 20 <= size <= 150:
            return f"{size}-inch"
    if re.search(r"\b(?:very\s+)?large\b", clean, flags=re.IGNORECASE):
        return "large"
    return ""


def _normalize_brand(value: str) -> str:
    clean = _sentence_fragment(value, 160).strip().rstrip(".")
    clean = re.sub(
        r"^(?:i\s+(?:prefer|want|would\s+like)|let(?:'s|\s+us)\s+(?:use|go\s+with)|"
        r"probably|maybe)\s+",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()
    brands = {
        "sony": "Sony",
        "samsung": "Samsung",
        "lg": "LG",
        "tcl": "TCL",
        "hisense": "Hisense",
        "panasonic": "Panasonic",
        "vizio": "Vizio",
        "apple": "Apple",
        "dell": "Dell",
        "lenovo": "Lenovo",
        "hp": "HP",
        "asus": "ASUS",
        "acer": "Acer",
    }
    lowered = clean.casefold()
    for token, label in brands.items():
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return label
    if 1 <= len(clean.split()) <= 3 and re.fullmatch(r"[A-Za-z0-9&+\- ]+", clean):
        return clean
    return ""


def _normalize_retailer(value: str) -> str:
    clean = _sentence_fragment(value, 180).strip().rstrip(".")
    lowered = clean.casefold()
    retailers = {
        "amazon": "Amazon",
        "best buy": "Best Buy",
        "walmart": "Walmart",
        "costco": "Costco",
        "target": "Target",
        "sony": "Sony",
        "ebay": "eBay",
        "newegg": "Newegg",
    }
    for token, label in retailers.items():
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return label
    return ""


def _purchase_size(context: dict[str, Any]) -> str:
    return _purchase_constraint(context, "Screen size") or _purchase_constraint(
        context, "Screen size preference"
    )


def _purchase_budget(context: dict[str, Any]) -> str:
    return _purchase_constraint(context, "Budget")


def _purchase_brand(context: dict[str, Any]) -> str:
    decision = _purchase_decision(context, "chosen as the brand")
    if decision:
        return decision.split(" was chosen", 1)[0].strip()
    return _purchase_constraint(context, "Brand preference")


def _purchase_model(context: dict[str, Any]) -> str:
    decision = _purchase_decision(context, "chosen as the model")
    if decision:
        return decision.split(" was chosen", 1)[0].strip()
    return ""


def _purchase_retailer(context: dict[str, Any]) -> str:
    decision = _purchase_decision(context, "chosen as the retailer")
    if decision:
        return decision.split(" was chosen", 1)[0].strip()
    listing = _purchase_decision(context, "listing was selected")
    if listing:
        return listing.split(" listing", 1)[0].strip()
    return ""


def _purchase_listing_price(context: dict[str, Any]) -> str:
    for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 360):
        match = re.search(
            r"listing was selected(?:\s+for|\s+at)\s+(\$[\d,]+(?:\.\d{1,2})?)",
            item,
            flags=re.IGNORECASE,
        )
        if match:
            return _normalize_money(match.group(1))
    return ""


def _purchase_ordered(context: dict[str, Any]) -> bool:
    return _has_progress(
        context,
        "order was placed",
        "product was ordered",
        "tv was ordered",
        "purchase was placed",
    )


def _purchase_delivered(context: dict[str, Any]) -> bool:
    return _has_progress(
        context,
        "product arrived",
        "tv arrived",
        "order arrived",
        "product was delivered",
    )


def _purchase_verified(context: dict[str, Any]) -> bool:
    return _has_progress(
        context,
        "works correctly",
        "works great",
        "was tested and works",
        "purchase was completed successfully",
    )


def _purchase_subject_base(context: dict[str, Any]) -> str:
    text = " ".join(
        (
            _clean_text(context.get("title"), 180),
            _clean_text(context.get("objective"), 600),
            _clean_text(context.get("subject"), 360),
        )
    )
    if re.search(r"\b(?:television|tv)\b", text, flags=re.IGNORECASE):
        return "TV"
    match = _PURCHASE_PRODUCT_RE.search(text)
    return match.group(0) if match else "product"


def _refresh_purchase_subject(context: dict[str, Any]) -> None:
    product = _purchase_subject_base(context)
    size = _purchase_size(context)
    brand = _purchase_brand(context)
    model = _purchase_model(context)
    placement = _purchase_fact(context, "Placement")

    if model:
        subject = model
        if size and size.casefold() not in model.casefold():
            subject = f"{size} {subject}"
        if product.casefold() not in subject.casefold():
            subject = f"{subject} {product}"
    else:
        parts = [part for part in (size, brand, product) if part]
        subject = " ".join(parts)
    if placement:
        subject += f" for the {placement}"
    context["subject"] = _clean_text(subject, 360)


def _question_target(question: str, context: dict[str, Any]) -> str:
    lowered = _clean_text(question, 360).casefold()
    if _purchase_context(context):
        if any(token in lowered for token in ("budget", "spend", "price range", "maximum price")):
            return "budget"
        if any(token in lowered for token in ("screen size", "what size", "how large", "inch", "viewing distance")):
            return "size"
        if "brand" in lowered:
            return "brand"
        if any(token in lowered for token in ("which model", "what model", "specific model")):
            return "model"
        if any(token in lowered for token in ("where to buy", "where will you buy", "retailer", "seller", "store")):
            return "retailer"
        if any(token in lowered for token in ("which room", "where will it go", "placement", "living room")):
            return "placement"
    return _purchase_base_question_target(question, context)


def _apply_answer_to_target(
    context: dict[str, Any],
    target: str,
    raw_answer: str,
) -> bool:
    if not _purchase_context(context):
        return _purchase_base_apply_answer_to_target(context, target, raw_answer)
    if _is_weak_acknowledgement(raw_answer):
        return False

    if target == "budget":
        if re.search(r"\b(?:any|flexible|no|unlimited)\s+(?:budget|price)\b|\bany\s+budget\b", raw_answer, flags=re.IGNORECASE):
            return _replace_prefixed_item(context, "constraints", "Budget", "flexible", MAX_CONSTRAINTS)
        values = _extract_money_values(raw_answer)
        value = values[-1] if values else _sentence_fragment(raw_answer, 160)
        return _replace_prefixed_item(context, "constraints", "Budget", value, MAX_CONSTRAINTS)

    if target == "size":
        size = _normalize_screen_size(raw_answer)
        if not size:
            return False
        return _replace_prefixed_item(context, "constraints", "Screen size", size, MAX_CONSTRAINTS)

    if target == "brand":
        brand = _normalize_brand(raw_answer)
        if not brand:
            return False
        return _replace_purchase_decision(context, "chosen as the brand", f"{brand} was chosen as the brand")

    if target == "model":
        model = _sentence_fragment(raw_answer, 220).strip().rstrip(".")
        model = re.sub(
            r"^(?:let(?:'s|\s+us)\s+(?:go\s+with|choose)|i\s+(?:want|choose|pick)|"
            r"go\s+with)\s+",
            "",
            model,
            flags=re.IGNORECASE,
        ).strip()
        if not model:
            return False
        return _replace_purchase_decision(context, "chosen as the model", f"{model} was chosen as the model")

    if target == "retailer":
        retailer = _normalize_retailer(raw_answer)
        if not retailer:
            return False
        return _replace_purchase_decision(context, "chosen as the retailer", f"{retailer} was chosen as the retailer")

    if target == "placement":
        placement = _sentence_fragment(raw_answer, 180).strip().rstrip(".")
        placement = re.sub(r"^(?:in|for)\s+(?:the\s+)?", "", placement, flags=re.IGNORECASE)
        return _replace_prefixed_item(context, "knownFacts", "Placement", placement, MAX_FACTS)

    changed = _purchase_base_apply_answer_to_target(context, target, raw_answer)
    return changed


def _capture_purchase_requirements(context: dict[str, Any], text: str) -> bool:
    if not _purchase_context(context):
        return False
    changed = False
    lower = text.casefold()

    if re.search(r"\b(?:living|family|bed|game|media)\s+room\b", text, flags=re.IGNORECASE):
        room_match = re.search(r"\b((?:living|family|bed|game|media)\s+room)\b", text, flags=re.IGNORECASE)
        if room_match:
            changed = _replace_prefixed_item(
                context,
                "knownFacts",
                "Placement",
                room_match.group(1).lower(),
                MAX_FACTS,
            ) or changed

    size = _normalize_screen_size(text)
    if size:
        changed = _replace_prefixed_item(
            context, "constraints", "Screen size", size, MAX_CONSTRAINTS
        ) or changed
    elif re.search(r"\b(?:want|need|prefer).{0,30}\b(?:large|big)\s+(?:television|tv)\b", text, flags=re.IGNORECASE):
        changed = _replace_prefixed_item(
            context,
            "constraints",
            "Screen size preference",
            "large",
            MAX_CONSTRAINTS,
        ) or changed

    if re.search(r"\b(?:any\s+budget|budget\s+is\s+flexible|no\s+(?:real\s+)?budget|"
                 r"can\s+do\s+any\s+budget|price\s+doesn'?t\s+matter)\b", lower):
        changed = _replace_prefixed_item(
            context, "constraints", "Budget", "flexible", MAX_CONSTRAINTS
        ) or changed
    elif re.search(r"\b(?:budget|max(?:imum)?|up\s+to|spend)\b", lower):
        values = _extract_money_values(text)
        if values:
            changed = _replace_prefixed_item(
                context, "constraints", "Budget", values[-1], MAX_CONSTRAINTS
            ) or changed

    if re.search(r"\b(?:good|reputable|reliable|top)\s+brand\b", lower):
        changed = _replace_prefixed_item(
            context,
            "constraints",
            "Brand quality",
            "reputable brand",
            MAX_CONSTRAINTS,
        ) or changed

    brand = _normalize_brand(text)
    if brand and (
        re.fullmatch(r"\s*[A-Za-z0-9&+\- ]{2,20}\s*", text)
        or re.search(r"\b(?:prefer|choose|go\s+with|want|brand)\b", lower)
    ):
        changed = _replace_purchase_decision(
            context, "chosen as the brand", f"{brand} was chosen as the brand"
        ) or changed

    if not _clean_text(context.get("successCriteria"), 500):
        if re.search(r"\b(?:buy|purchase|get|shop\s+for)\b", lower) and _PURCHASE_PRODUCT_RE.search(text):
            product = _PURCHASE_PRODUCT_RE.search(text).group(0)
            context["successCriteria"] = (
                f"Purchase a {product} that fits the user's requirements and arrives working correctly."
            )
            changed = True

    return changed


def _purchase_price_from_text(text: str) -> str:
    clean_without_urls = re.sub(r"https?://\S+", " ", _clean_text(text, 1400))
    explicit = re.search(
        r"\$\s*(\d[\d,]*(?:\.\d{1,2})?)|"
        r"\b(?:price(?:d)?\s*(?:is|at)?|costs?|for|it(?:'s|s|\s+is))\s+"
        r"(?:about\s+|around\s+)?(\d[\d,]*(?:\.\d{1,2})?)\b",
        clean_without_urls,
        flags=re.IGNORECASE,
    )
    if not explicit:
        return ""
    return _normalize_money(explicit.group(1) or explicit.group(2))


def _capture_purchase_decisions_and_milestones(context: dict[str, Any], text: str) -> bool:
    if not _purchase_context(context):
        return False
    changed = False
    lower = text.casefold()

    model_match = re.search(
        r"\b(?:let(?:'s|\s+us)\s+(?:go\s+with|choose)|i\s+(?:choose|pick)|"
        r"go\s+with)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9+\-]*(?:\s+[A-Za-z0-9+\-]+){1,5})",
        text,
        flags=re.IGNORECASE,
    )
    if model_match:
        model = _sentence_fragment(model_match.group(1), 200).rstrip(".")
        model = re.sub(r"\s+(?:first|instead|please)$", "", model, flags=re.IGNORECASE)
        if _PURCHASE_PRODUCT_RE.search(model) or re.search(r"\b[A-Z]\d{2,}[A-Z0-9-]*\b", model):
            changed = _replace_purchase_decision(
                context, "chosen as the model", f"{model} was chosen as the model"
            ) or changed

    retailer = _normalize_retailer(text)
    if retailer and re.search(
        r"\b(?:amazon|best\s+buy|walmart|costco|target|ebay|newegg|retailer|seller|store|listing|link)\b",
        lower,
    ):
        if re.search(r"\b(?:(?:let(?:'s|\s+us)|lets)\s+(?:see|use|go\s+with)|choose|buy\s+from|order\s+from|found)\b", lower):
            changed = _replace_purchase_decision(
                context, "chosen as the retailer", f"{retailer} was chosen as the retailer"
            ) or changed

    url_match = re.search(r"https?://\S+", text)
    price = _purchase_price_from_text(text)
    if url_match:
        retailer = _normalize_retailer(text) or _purchase_retailer(context) or "Retailer"
        decision = f"{retailer} listing was selected"
        if price:
            decision += f" for {price}"
        changed = _replace_purchase_decision(
            context, "listing was selected", decision
        ) or changed
        clean_url = url_match.group(0).rstrip(".,;!?)\"]'")
        changed = _replace_prefixed_item(
            context, "knownFacts", "Selected listing", clean_url, MAX_FACTS
        ) or changed

    if re.search(
        r"\b(?:i|we)\s+(?:just\s+)?(?:ordered|bought|purchased|placed\s+the\s+order)\b|"
        r"\border\s+(?:is|was)\s+placed\b",
        lower,
    ):
        changed = _prepend_unique(
            context, "recentProgress", "The product was ordered.", MAX_RECENT_PROGRESS
        ) or changed
        if re.search(r"\b(?:ship|shipping|on\s+its\s+way|arrive)\b", lower):
            changed = _prepend_unique(
                context,
                "recentProgress",
                "The order is awaiting delivery.",
                MAX_RECENT_PROGRESS,
            ) or changed

    arrived = bool(
        re.search(
            r"\b(?:it(?:'s|s|\s+has)?|the\s+(?:tv|television|product|order|item)(?:\s+has)?)\s+arrived\b|"
            r"\b(?:it|the\s+(?:tv|television|product|order|item))\s+(?:was\s+)?delivered\b",
            lower,
        )
    )
    works = bool(
        re.search(
            r"\b(?:works?|working|runs?)\s+(?:great|well|fine|perfectly|correctly)\b|"
            r"\bno\s+(?:problems?|issues?)\b",
            lower,
        )
    )
    if arrived:
        changed = _prepend_unique(
            context, "recentProgress", "The product arrived.", MAX_RECENT_PROGRESS
        ) or changed
    if arrived and works:
        existing_progress = _clean_list(
            context.get("recentProgress"), MAX_RECENT_PROGRESS, 340
        )
        filtered_progress = [
            item
            for item in existing_progress
            if "awaiting delivery" not in item.casefold()
        ]
        if filtered_progress != existing_progress:
            context["recentProgress"] = filtered_progress
            changed = True
        changed = _prepend_unique(
            context,
            "recentProgress",
            "The product was tested and works correctly.",
            MAX_RECENT_PROGRESS,
        ) or changed
        changed = _prepend_unique(
            context,
            "recentProgress",
            "The purchase was completed successfully.",
            MAX_RECENT_PROGRESS,
        ) or changed
        context["pendingQuestion"] = None
        context["openQuestions"] = []

    if re.search(r"\bpage\s+not\s+found\b|\blink\s+(?:isn'?t|is\s+not|wasn'?t|was\s+not)\s+working\b", lower):
        changed = _prepend_unique(
            context,
            "recentProgress",
            "A proposed retailer link was invalid and should not be reused.",
            MAX_RECENT_PROGRESS,
        ) or changed

    return changed


def _refresh_derived_objective(context: dict[str, Any]) -> None:
    if not _purchase_context(context):
        _purchase_base_refresh_derived_objective(context)
        return
    _refresh_purchase_subject(context)
    subject = _clean_text(context.get("subject"), 360) or "the product"
    price = _purchase_listing_price(context)
    retailer = _purchase_retailer(context)
    objective = f"Buy {subject}"
    if retailer:
        objective += f" from {retailer}"
    if price:
        objective += f" for {price}"
    objective += " and confirm it arrives working correctly"
    context["objective"] = objective.rstrip(".") + "."


def _specific_questions(context: dict[str, Any]) -> list[str]:
    if not _purchase_context(context):
        return _purchase_base_specific_questions(context)
    if _purchase_verified(context):
        return []
    product = _purchase_subject_base(context)
    questions: list[str] = []
    if not _purchase_budget(context):
        questions.append("What budget or price range should guide this purchase?")
    if product.casefold() in {"tv", "television", "monitor", "projector"} and not _purchase_size(context):
        questions.append("What screen size do you want, or what is the viewing distance?")
    if not _purchase_brand(context):
        questions.append("Do you have a preferred brand, or should QMeet compare reputable brands?")
    return questions


def _derive_stage(context: dict[str, Any]) -> str:
    if not _purchase_context(context):
        return _purchase_base_derive_stage(context)
    if _purchase_delivered(context) and _purchase_verified(context):
        return "complete"
    if _purchase_ordered(context):
        return "in-progress"
    if _purchase_model(context) and _purchase_retailer(context) and (
        _purchase_listing_price(context) or _purchase_fact(context, "Selected listing")
    ):
        return "ready"
    if _purchase_model(context) or _purchase_retailer(context):
        return "in-progress"
    if _purchase_size(context) or _purchase_brand(context) or _purchase_budget(context):
        return "planning"
    return "discovery"


def _refresh_questions_and_next_action(context: dict[str, Any], user_text: str) -> None:
    _purchase_base_refresh_questions_and_next_action(context, user_text)
    if not _purchase_context(context):
        return

    context["focusType"] = "purchase"
    if context.get("mode") == "general":
        context["mode"] = "planning"
    _refresh_derived_objective(context)
    context["stage"] = _derive_stage(context)

    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    candidates = [
        *([pending["question"]] if pending and not _question_answered(pending["question"], user_text, context) else []),
        *_specific_questions(context),
    ]
    questions: list[str] = []
    for question in candidates:
        if question in questions or _question_answered(question, user_text, context):
            continue
        questions.append(question)
        if len(questions) >= MAX_OPEN_QUESTIONS:
            break
    context["openQuestions"] = questions

    stage = context["stage"]
    if stage == "complete":
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["nextAction"] = (
            "The purchase is complete and the product is working. End the focus or save "
            "the result only if useful."
        )
        return
    if _purchase_ordered(context):
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["nextAction"] = (
            "Track the shipment. When it arrives, inspect the product, test it, and keep "
            "the packaging until you know it works correctly."
        )
        return
    if stage == "ready":
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["nextAction"] = (
            "Verify the selected listing, seller, return policy, delivery terms, and "
            "warranty using current retailer information, then place the order."
        )
        return
    if _purchase_model(context) and not _purchase_retailer(context):
        context["nextAction"] = (
            "Run a current web search for reputable retailers, live availability, and "
            "real prices for the chosen model."
        )
        return
    if _purchase_size(context) and _purchase_brand(context) and not _purchase_model(context):
        context["nextAction"] = (
            "Run a current model comparison using the recorded size, brand, placement, "
            "and budget requirements."
        )
        return
    if not _purchase_budget(context):
        context["nextAction"] = "Set the budget or confirm that the budget is flexible."
    elif _purchase_subject_base(context).casefold() in {"tv", "television", "monitor", "projector"} and not _purchase_size(context):
        context["nextAction"] = "Choose the screen size using the room and viewing distance."
    elif not _purchase_brand(context):
        context["nextAction"] = "Choose a preferred brand or compare reputable brands."
    else:
        context["nextAction"] = "Compare current models that match the recorded requirements."


def _question_answered(question: str, text: str, context: dict[str, Any]) -> bool:
    if not _purchase_context(context):
        return _purchase_base_question_answered(question, text, context)
    target = _question_target(question, context)
    if target == "budget":
        return bool(_purchase_budget(context))
    if target == "size":
        return bool(_purchase_size(context))
    if target == "brand":
        return bool(_purchase_brand(context))
    if target == "model":
        return bool(_purchase_model(context))
    if target == "retailer":
        return bool(_purchase_retailer(context))
    if target == "placement":
        return bool(_purchase_fact(context, "Placement"))
    return _purchase_base_question_answered(question, text, context)


def _apply_user_update(context: dict[str, Any], user_text: str) -> tuple[dict[str, Any], bool]:
    next_context, changed = _purchase_base_apply_user_update(context, user_text)
    text = _clean_text(user_text, 1400)
    if not text:
        return next_context, changed

    inferred_type = _infer_focus_type_from_text(
        " ".join(
            (
                _clean_text(next_context.get("title"), 180),
                _clean_text(next_context.get("objective"), 600),
                _clean_text(next_context.get("subject"), 360),
                text,
            )
        ),
        _clean_text(next_context.get("mode"), 30) or "general",
    )
    if inferred_type == "purchase" and not _sale_context(next_context):
        if next_context.get("focusType") != "purchase":
            next_context["focusType"] = "purchase"
            changed = True

    if not _purchase_context(next_context):
        return next_context, changed

    changed = _capture_purchase_requirements(next_context, text) or changed
    changed = _capture_purchase_decisions_and_milestones(next_context, text) or changed

    before = (
        next_context.get("objective", ""),
        next_context.get("subject", ""),
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    _refresh_derived_objective(next_context)
    _refresh_questions_and_next_action(next_context, text)
    after = (
        next_context.get("objective", ""),
        next_context.get("subject", ""),
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    if before != after:
        changed = True
    if changed:
        next_context["confidence"] = min(
            0.99, float(next_context.get("confidence", 0.35)) + 0.04
        )
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _apply_assistant_update(
    context: dict[str, Any],
    assistant_text: str,
) -> tuple[dict[str, Any], bool]:
    next_context, changed = _purchase_base_apply_assistant_update(context, assistant_text)
    if not _purchase_context(next_context):
        return next_context, changed

    before = (
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    _refresh_questions_and_next_action(next_context, "")
    after = (
        next_context.get("stage", ""),
        next_context.get("nextAction", ""),
        list(next_context.get("openQuestions", [])),
    )
    if before != after:
        changed = True
    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _sanitize_context(raw: object) -> dict[str, Any] | None:
    context = _purchase_base_sanitize_context(raw)
    if context is None:
        return None

    inferred = _infer_focus_type_from_text(
        " ".join(
            (
                _clean_text(context.get("title"), 180),
                _clean_text(context.get("objective"), 600),
                _clean_text(context.get("subject"), 360),
            )
        ),
        _clean_text(context.get("mode"), 30) or "general",
    )
    if inferred == "purchase" and not _sale_context(context):
        context["focusType"] = "purchase"
    if not _purchase_context(context):
        return context

    context["focusType"] = "purchase"
    if context.get("mode") == "general":
        context["mode"] = "planning"

    # Remove generic or malformed entries produced before purchase continuity
    # existed. The durable purchase fields below replace them.
    context["knownFacts"] = [
        item
        for item in _clean_list(context.get("knownFacts"), MAX_FACTS, 340)
        if not item.casefold().startswith(("working environment:", "project detail:"))
    ]
    context["constraints"] = [
        item
        for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 340)
        if not item.casefold().startswith("requirement:")
    ]

    _refresh_derived_objective(context)
    _refresh_questions_and_next_action(context, "")
    return context


def should_keep_focus_message_in_chat(message: str) -> bool:
    base = _purchase_base_should_keep_focus_message_in_chat(message)
    visible = _clean_text(_extract_visible_user_message(message), 900)
    if not visible:
        return base
    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if not isinstance(context, dict) or not _purchase_context(context):
        return base

    # Current prices, availability, links, and deal comparisons should be given
    # to the command/search route rather than answered from model memory.
    if re.search(
        r"\b(?:find|search|look\s+for|check|compare|show|give\s+me)\b.*"
        r"\b(?:current|deal|deals|price|prices|promotion|discount|availability|"
        r"available|retailer|seller|store|amazon|best\s+buy|walmart|costco|link|listing)\b",
        visible,
        flags=re.IGNORECASE,
    ):
        return False
    if re.search(r"\b(?:amazon|retailer|product)\s+link\b", visible, flags=re.IGNORECASE):
        return False
    return base


def prepare_background_chat_message(message: str) -> tuple[str, str]:
    contextual_message, visible_user_message = _purchase_base_prepare_background_chat_message(message)
    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if not isinstance(context, dict) or not _purchase_context(context):
        return contextual_message, visible_user_message

    purchase_rules = [
        "Purchase-workflow rules:",
        "- Treat product prices, stock, promotions, model availability, retailer pages, and URLs as time-sensitive facts.",
        "- Never invent a current price, deal, seller, stock status, product identifier, or retailer URL.",
        "- Do not claim that you searched, are searching, or will return with results unless the actual Search action is running and supplied evidence.",
        "- For current models, live deals, or purchase links, use real Search results. If none are present, say that a current search is required instead of guessing.",
        "- A user-provided retailer URL may be remembered as the selected listing, but only repeat price or availability details that the user explicitly supplied or a current search verified.",
        "- Treat size, brand, model, retailer, selected listing, order placement, delivery, and successful testing as durable milestones. Do not return to an earlier decision unless the user changes it.",
        "- Once the order is placed, stop recommending more model comparisons. Focus on delivery, inspection, setup, returns, and warranty only as relevant.",
        "- Once the product arrived and the user confirmed it works, mark the focus complete and stop adding purchase steps.",
        "",
    ]
    marker = "Existing request and private context:"
    if marker in contextual_message:
        contextual_message = contextual_message.replace(
            marker,
            "\n".join(purchase_rules) + marker,
            1,
        )
    return contextual_message, visible_user_message


# ---------------------------------------------------------------------------
# Phase 18: purchase confirmation safety and live-search handoff
# ---------------------------------------------------------------------------
# Purchase conversations often use short confirmations after QMeet offers to
# search. Those confirmations are actions, not product facts. This layer keeps
# words such as "sure" and "yes" out of the brand field and exposes a small
# search-handoff API for the request middleware.

WORK_CONTEXT_FILE_VERSION = 9

_purchase_handoff_base_normalize_brand = _normalize_brand
_purchase_handoff_base_purchase_brand = _purchase_brand
_purchase_handoff_base_capture_requirements = _capture_purchase_requirements
_purchase_handoff_base_apply_user_update = _apply_user_update
_purchase_handoff_base_apply_assistant_update = _apply_assistant_update
_purchase_handoff_base_sanitize_context = _sanitize_context
_purchase_handoff_base_refresh_objective = _refresh_derived_objective
_purchase_handoff_base_refresh_questions = _refresh_questions_and_next_action
_purchase_handoff_base_prepare_chat = prepare_background_chat_message

_PURCHASE_ACK_WORDS = {
    "yes", "yeah", "yep", "yup", "sure", "okay", "ok", "alright",
    "all right", "please", "go ahead", "do it", "sounds good",
}
_PURCHASE_INVALID_BRANDS = {
    *_PURCHASE_ACK_WORDS,
    "no", "nope", "maybe", "whatever", "anything", "either", "both",
    "search", "current", "now", "help", "compare", "options", "models",
}
_PURCHASE_KNOWN_BRANDS = {
    "acer": "Acer",
    "alienware": "Alienware",
    "apple": "Apple",
    "asus": "ASUS",
    "dell": "Dell",
    "framework": "Framework",
    "gigabyte": "Gigabyte",
    "google": "Google",
    "hisense": "Hisense",
    "hp": "HP",
    "lenovo": "Lenovo",
    "lg": "LG",
    "microsoft": "Microsoft",
    "msi": "MSI",
    "panasonic": "Panasonic",
    "razer": "Razer",
    "samsung": "Samsung",
    "sony": "Sony",
    "tcl": "TCL",
    "vizio": "Vizio",
}


def _normalized_purchase_reply(value: str) -> str:
    return re.sub(r"[^a-z0-9']+", " ", _clean_text(value, 240).casefold()).strip()


def _is_purchase_acknowledgement(value: str) -> bool:
    normalized = _normalized_purchase_reply(value)
    return normalized in _PURCHASE_ACK_WORDS or bool(
        re.fullmatch(
            r"(?:yes|yeah|yep|sure|okay|ok|alright|all right)(?: i would| i do| please)?",
            normalized,
        )
    )


def _normalize_brand(value: str) -> str:
    clean = _sentence_fragment(value, 220).strip().rstrip(".")
    normalized = _normalized_purchase_reply(clean)
    if not normalized or _is_purchase_acknowledgement(clean):
        return ""

    for token, label in _PURCHASE_KNOWN_BRANDS.items():
        if re.search(rf"\b{re.escape(token)}\b", normalized):
            return label

    explicit = re.search(
        r"\b(?:brand(?: is)?|prefer|preferred|like|want|choose|go with)\s+"
        r"(?:the\s+)?([A-Za-z][A-Za-z0-9&+\-]*(?:\s+[A-Za-z0-9&+\-]+){0,2})",
        clean,
        flags=re.IGNORECASE,
    )
    if not explicit:
        return ""

    candidate = _clean_text(explicit.group(1), 80).strip().rstrip(".")
    candidate = re.split(
        r"\s+(?:but|although|though|and|or|if)\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    if not candidate or candidate.casefold() in _PURCHASE_INVALID_BRANDS:
        return ""
    if any(word in _PURCHASE_INVALID_BRANDS for word in candidate.casefold().split()):
        return ""
    return candidate


def _brand_is_flexible(text: str) -> bool:
    lowered = _clean_text(text, 500).casefold()
    return bool(
        re.search(
            r"\b(?:doesn'?t|desn'?t|does not|isn'?t|is not)\s+matter(?:\s+too\s+much)?(?:\s+to\s+me)?\b|"
            r"\b(?:open|flexible)\s+to\s+(?:other|different)\s+brands?\b|"
            r"\b(?:other|different)\s+brands?\s+(?:are|would be)\s+(?:fine|okay|ok)\b|"
            r"\b(?:not|isn'?t)\s+(?:too\s+)?(?:important|strict|set)\s+on\s+(?:the\s+)?brand\b|"
            r"\bbut\s+(?:it|brand)\s+(?:doesn'?t|does not)\s+matter\b",
            lowered,
        )
    )


def _brand_decision_value(context: dict[str, Any]) -> str:
    for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 360):
        lowered = item.casefold()
        if "preferred brand" in lowered or "is preferred" in lowered:
            match = re.match(r"(.+?)\s+(?:is\s+the\s+preferred\s+brand|is\s+preferred)", item, flags=re.IGNORECASE)
            if match:
                return _clean_text(match.group(1), 100).strip()
    return ""


def _purchase_brand(context: dict[str, Any]) -> str:
    preferred = _brand_decision_value(context)
    return preferred or _purchase_handoff_base_purchase_brand(context)


def _remove_invalid_purchase_brand_decisions(context: dict[str, Any]) -> bool:
    existing = _clean_list(context.get("decisions"), MAX_DECISIONS, 360)
    filtered: list[str] = []
    changed = False
    for item in existing:
        lowered = item.casefold()
        if "chosen as the brand" in lowered:
            brand = item.split(" was chosen", 1)[0].strip().casefold()
            if brand in _PURCHASE_INVALID_BRANDS:
                changed = True
                continue
        filtered.append(item)
    if filtered != existing:
        context["decisions"] = filtered
    return changed


def _remove_purchase_chat_artifacts(context: dict[str, Any]) -> bool:
    changed = _remove_invalid_purchase_brand_decisions(context)

    facts = _clean_list(context.get("knownFacts"), MAX_FACTS, 340)
    filtered_facts = [
        item
        for item in facts
        if not re.search(
            r"\b(?:would likes?|wants?|asked)\s+(?:you|qmeet)\s+to\s+search\b|"
            r"\b(?:yes|yeah|sure|okay)\s+(?:brand|was chosen)\b",
            item,
            flags=re.IGNORECASE,
        )
    ]
    if filtered_facts != facts:
        context["knownFacts"] = filtered_facts
        changed = True

    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    if pending and (
        _is_action_offer_question(pending["question"])
        or re.search(r"\b(?:search|gather|find|list|compare)\b.*\b(?:options?|models?|deals?)\b", pending["question"], flags=re.IGNORECASE)
    ):
        context["pendingQuestion"] = None
        changed = True

    questions = _clean_list(context.get("openQuestions"), MAX_OPEN_QUESTIONS, 260)
    filtered_questions = [
        question
        for question in questions
        if not _is_action_offer_question(question)
        and not re.search(
            r"\b(?:search|gather|find|list|compare)\b.*\b(?:options?|models?|deals?)\b",
            question,
            flags=re.IGNORECASE,
        )
    ]
    if filtered_questions != questions:
        context["openQuestions"] = filtered_questions
        changed = True
    return changed


def _sanitize_pending_action(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    action_type = _clean_text(value.get("type"), 40).casefold()
    query = _clean_text(value.get("query"), 320)
    prompt = _clean_text(value.get("prompt"), 320)
    if action_type != "search" or not query:
        return None
    return {"type": "search", "query": query, "prompt": prompt}


def _purchase_prefers_alternatives(context: dict[str, Any]) -> bool:
    return any(
        "other reputable brands are acceptable" in item.casefold()
        or "other brands are acceptable" in item.casefold()
        for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 360)
    )


def _build_purchase_search_query(context: dict[str, Any]) -> str:
    product = _purchase_subject_base(context)
    brand = _purchase_brand(context)
    size = _purchase_size(context)
    budget = _purchase_budget(context)
    placement = _purchase_fact(context, "Placement")

    subject_parts: list[str] = []
    if size and size.casefold() not in {"large", "big"}:
        subject_parts.append(size)
    if brand:
        subject_parts.append(brand)
    subject_parts.append(product)

    query = "current " + " ".join(part for part in subject_parts if part)
    if budget and budget.casefold() != "flexible":
        query += f" under {budget}"
    if placement:
        query += f" for {placement}"
    if brand and _purchase_prefers_alternatives(context):
        query += f", plus comparable alternatives to {brand} from reputable brands"
    query += "; compare real current models, prices, availability, and reputable retailers"
    return _clean_text(query, 320)


def _assistant_offers_purchase_search(text: str) -> bool:
    clean = _clean_text(text, 1600)
    lowered = clean.casefold()
    if not re.search(r"\b(?:search|find|gather|look for|list|compare|show)\b", lowered):
        return False
    if not re.search(r"\b(?:current|available|options?|models?|deals?|prices?|retailers?)\b", lowered):
        return False
    return bool(
        re.search(
            r"\b(?:would you like|do you want|want me to|shall i|should i|ready for me to)\b",
            lowered,
        )
    )


def _capture_purchase_requirements(context: dict[str, Any], text: str) -> bool:
    changed = _purchase_handoff_base_capture_requirements(context, text)
    if not _purchase_context(context):
        return changed

    changed = _remove_invalid_purchase_brand_decisions(context) or changed
    if _is_purchase_acknowledgement(text):
        return changed

    brand = _normalize_brand(text)
    if brand and _brand_is_flexible(text):
        existing = _clean_list(context.get("decisions"), MAX_DECISIONS, 360)
        filtered = [
            item
            for item in existing
            if "chosen as the brand" not in item.casefold()
            and "preferred brand" not in item.casefold()
            and "is preferred" not in item.casefold()
        ]
        decision = f"{brand} is the preferred brand, but other reputable brands are acceptable."
        context["decisions"] = [decision, *filtered][:MAX_DECISIONS]
        changed = True
    return changed


def _refresh_derived_objective(context: dict[str, Any]) -> None:
    _purchase_handoff_base_refresh_objective(context)
    if not _purchase_context(context):
        return
    subject = _clean_text(context.get("subject"), 360) or "the product"
    preferred_brand = _brand_decision_value(context)
    if preferred_brand and _purchase_prefers_alternatives(context):
        product = _purchase_subject_base(context)
        budget = _purchase_budget(context)
        objective = f"Buy a {product}, preferably {preferred_brand}"
        if budget and budget.casefold() != "flexible":
            objective += f", within {budget}"
        objective += ", and confirm it arrives working correctly."
        context["objective"] = objective


def _refresh_questions_and_next_action(context: dict[str, Any], user_text: str) -> None:
    _purchase_handoff_base_refresh_questions(context, user_text)
    if not _purchase_context(context):
        return
    _remove_purchase_chat_artifacts(context)
    pending_action = _sanitize_pending_action(context.get("pendingAction"))
    if pending_action:
        context["pendingAction"] = pending_action
        context["nextAction"] = "Run the prepared live product search and review the real results."


def _apply_user_update(context: dict[str, Any], user_text: str) -> tuple[dict[str, Any], bool]:
    prior_brand = _purchase_brand(context) if _purchase_context(context) else ""
    prior_pending_action = _sanitize_pending_action(context.get("pendingAction"))
    next_context, changed = _purchase_handoff_base_apply_user_update(context, user_text)
    if not _purchase_context(next_context):
        return next_context, changed

    if _remove_purchase_chat_artifacts(next_context):
        changed = True

    if _is_purchase_acknowledgement(user_text):
        current_brand = _purchase_brand(next_context)
        if current_brand.casefold() in _PURCHASE_INVALID_BRANDS:
            _remove_invalid_purchase_brand_decisions(next_context)
            changed = True
        if prior_brand and not _purchase_brand(next_context):
            changed = _replace_purchase_decision(
                next_context,
                "chosen as the brand",
                f"{prior_brand} was chosen as the brand",
            ) or changed
        if prior_pending_action:
            next_context["pendingAction"] = prior_pending_action

    changed = _capture_purchase_requirements(next_context, user_text) or changed
    _refresh_derived_objective(next_context)
    _refresh_questions_and_next_action(next_context, user_text)
    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _apply_assistant_update(
    context: dict[str, Any],
    assistant_text: str,
) -> tuple[dict[str, Any], bool]:
    next_context, changed = _purchase_handoff_base_apply_assistant_update(context, assistant_text)
    if not _purchase_context(next_context):
        return next_context, changed

    if _remove_purchase_chat_artifacts(next_context):
        changed = True

    if _assistant_offers_purchase_search(assistant_text):
        pending_action = {
            "type": "search",
            "query": _build_purchase_search_query(next_context),
            "prompt": _clean_text(assistant_text, 320),
        }
        if next_context.get("pendingAction") != pending_action:
            next_context["pendingAction"] = pending_action
            changed = True
        next_context["pendingQuestion"] = None
        next_context["openQuestions"] = []
        next_context["nextAction"] = "Run the prepared live product search and review the real results."

    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _sanitize_context(raw: object) -> dict[str, Any] | None:
    raw_pending_action = raw.get("pendingAction") if isinstance(raw, dict) else None
    context = _purchase_handoff_base_sanitize_context(raw)
    if context is None:
        return None
    if not _purchase_context(context):
        context.pop("pendingAction", None)
        return context

    pending_action = _sanitize_pending_action(raw_pending_action)
    if pending_action:
        context["pendingAction"] = pending_action
    else:
        context.pop("pendingAction", None)

    _remove_purchase_chat_artifacts(context)
    _refresh_derived_objective(context)
    _refresh_questions_and_next_action(context, "")
    return context


def get_purchase_search_handoff(message: str, consume: bool = False) -> dict[str, str] | None:
    """Return a concrete live-search query for a purchase continuation.

    A bare acknowledgement only triggers when QMeet previously offered a search.
    Explicit requests such as "search now" can build a query directly from the
    active purchase context.
    """

    visible = _clean_text(_extract_visible_user_message(message), 900)
    if not visible:
        return None
    normalized = _normalized_purchase_reply(visible)

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if not isinstance(context, dict) or not _purchase_context(context):
            return None

        pending_action = _sanitize_pending_action(context.get("pendingAction"))
        acknowledgement = _is_purchase_acknowledgement(visible)
        explicit_search = bool(
            re.search(
                r"\b(?:search|look\s+for|find|gather|compare|show\s+me)\b",
                visible,
                flags=re.IGNORECASE,
            )
            and re.search(
                r"\b(?:now|current|available|options?|models?|laptops?|tvs?|deals?|prices?|products?)\b",
                visible,
                flags=re.IGNORECASE,
            )
        )
        search_challenge = bool(
            re.search(
                r"\b(?:don'?t|do not)\s+you\s+have\s+(?:a\s+)?search\b|"
                r"\bwhy\s+can'?t\s+you\s+search\b|"
                r"\buse\s+(?:your\s+)?search(?:\s+function)?\b",
                visible,
                flags=re.IGNORECASE,
            )
        )
        if not ((acknowledgement and pending_action) or explicit_search or search_challenge):
            return None

        query = pending_action["query"] if pending_action else _build_purchase_search_query(context)
        if not query:
            return None

        result = {
            "query": query,
            "reason": (
                "The user accepted QMeet's prepared live product search."
                if acknowledgement and pending_action
                else "The user explicitly requested QMeet's live product search."
            ),
        }
        if consume:
            context.pop("pendingAction", None)
            context["pendingQuestion"] = None
            context["openQuestions"] = []
            context["nextAction"] = "Review the live search results and compare the strongest options."
            _prepend_unique(
                context,
                "recentProgress",
                "A live product search was requested.",
                MAX_RECENT_PROGRESS,
            )
            context["updatedAt"] = _now_iso()
            _write_context_unlocked(context)
        return result


def prepare_background_chat_message(message: str) -> tuple[str, str]:
    contextual_message, visible_user_message = _purchase_handoff_base_prepare_chat(message)
    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if not isinstance(context, dict) or not _purchase_context(context):
        return contextual_message, visible_user_message

    extra_rules = [
        "Purchase confirmation and search-handoff rules:",
        "- Never interpret yes, yeah, sure, okay, go ahead, or do it as a brand, model, retailer, requirement, or fact.",
        "- If the user says a brand is preferred but not essential, preserve it as a preference and keep other reputable brands eligible.",
        "- Do not ask the user to authorize a live search more than once. A confirmation should run QMeet's Search action, not become another chat turn.",
        "- Never say QMeet lacks web search. QMeet has a Search action; current products, prices, availability, and retailer links must be routed to it.",
        "",
    ]
    marker = "Existing request and private context:"
    if marker in contextual_message:
        contextual_message = contextual_message.replace(
            marker,
            "\n".join(extra_rules) + marker,
            1,
        )
    return contextual_message, visible_user_message


# ---------------------------------------------------------------------------
# Phase 18: purchase intent repair, requirement continuity, and search routing
# ---------------------------------------------------------------------------
# This layer addresses three cross-cutting failures:
# 1. a corrected purchase can remain attached to a generic focus;
# 2. short confirmations can become product attributes;
# 3. current-product requests can fall through to ordinary chat.
# It keeps the public work-context API stable while adding durable purchase
# requirements and a deterministic handoff to QMeet's real Search action.

WORK_CONTEXT_FILE_VERSION = 10

_purchase_intent_base_question_target = _question_target
_purchase_intent_base_apply_answer = _apply_answer_to_target
_purchase_intent_base_capture_requirements = _capture_purchase_requirements
_purchase_intent_base_apply_user = _apply_user_update
_purchase_intent_base_apply_assistant = _apply_assistant_update
_purchase_intent_base_refresh_objective = _refresh_derived_objective
_purchase_intent_base_specific_questions = _specific_questions
_purchase_intent_base_refresh_questions = _refresh_questions_and_next_action
_purchase_intent_base_sanitize = _sanitize_context
_purchase_intent_base_prepare_chat = prepare_background_chat_message
_purchase_intent_base_keep_in_chat = should_keep_focus_message_in_chat

_PURCHASE_SEARCH_CONTINUATION_RE = re.compile(
    r"\b(?:did|have|would|could|can)\s+you\s+(?:find|found|get|got)\s+(?:it|them|anything)|"
    r"\b(?:i(?:'m| am)\s+still\s+)?waiting\b|"
    r"\bgive\s+me\s+(?:the\s+)?(?:links?|listings?)\b|"
    r"\b(?:find|get|show)\s+(?:me\s+)?(?:a\s+)?(?:real\s+)?(?:current\s+)?(?:listing|link)\b",
    flags=re.IGNORECASE,
)
_PURCHASE_UNAVAILABLE_RE = re.compile(
    r"\b(?:both|all|those|the)\s+(?:products?|models?|links?|listings?)\s+"
    r"(?:were|are|seem|look)\s+(?:unavailable|out\s+of\s+stock|sold\s+out|dead|invalid)|"
    r"\b(?:unavailable|out\s+of\s+stock|sold\s+out)\s+(?:too|again|as\s+well)\b|"
    r"\b(?:link|listing|page)\s+(?:doesn'?t|does\s+not|didn'?t|did\s+not)\s+(?:work|open|exist)\b",
    flags=re.IGNORECASE,
)


def _purchase_primary_use(context: dict[str, Any]) -> str:
    return _purchase_fact(context, "Primary use")


def _purchase_operating_system(context: dict[str, Any]) -> str:
    return _purchase_constraint(context, "Operating system")


def _purchase_portability_preference(context: dict[str, Any]) -> str:
    return _purchase_constraint(context, "Portability and size")


def _normalize_primary_use(value: str) -> str:
    clean = _clean_text(value, 500)
    lowered = clean.casefold()
    use_cases = [
        (r"\b(?:machine\s+learning|ml\s+tasks?|deep\s+learning|training\s+(?:ai|models?)|cuda)\b", "machine learning workloads"),
        (r"\b(?:data\s+science|data\s+analysis|analytics)\b", "data science and analysis"),
        (r"\b(?:video\s+editing|edit(?:ing)?\s+video|premiere|davinci)\b", "video editing"),
        (r"\b(?:graphic\s+design|3d\s+rendering|rendering|blender|cad)\b", "graphics and rendering work"),
        (r"\b(?:gaming|play(?:ing)?\s+games?)\b", "gaming"),
        (r"\b(?:software\s+development|programming|coding|developer\s+work)\b", "software development"),
        (r"\b(?:school|college|university|coursework|student\s+work)\b", "schoolwork"),
        (r"\b(?:office\s+work|work\s+tasks?|business\s+use)\b", "general work"),
        (r"\b(?:general\s+use|everyday\s+use|web\s+browsing)\b", "general everyday use"),
    ]
    for pattern, label in use_cases:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return label
    return ""


def _normalize_operating_system(value: str) -> str:
    lowered = _clean_text(value, 300).casefold()
    if re.search(r"\bwindows\b", lowered):
        return "Windows"
    if re.search(r"\b(?:mac|macos|macbook|apple)\b", lowered):
        return "macOS"
    if re.search(r"\blinux\b", lowered):
        return "Linux"
    if re.search(r"\b(?:no\s+preference|either|doesn'?t\s+matter|any\s+os)\b", lowered):
        return "no strong preference"
    return ""


def _plain_maximum_budget(value: str) -> str:
    clean = _clean_text(value, 300)
    match = re.search(
        r"\b(?:at\s+most|no\s+more\s+than|not\s+over|under|up\s+to|max(?:imum)?(?:\s+of)?)\s*"
        r"\$?\s*(\d[\d,]*(?:\.\d{1,2})?)\b",
        clean,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    raw = match.group(1).replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        return ""
    if amount <= 0:
        return ""
    if amount.is_integer():
        return f"${int(amount):,}"
    return f"${amount:,.2f}"


def _question_target(question: str, context: dict[str, Any]) -> str:
    lowered = _clean_text(question, 500).casefold()
    if _purchase_context(context):
        if any(
            token in lowered
            for token in (
                "what will you mainly use",
                "what will you use",
                "main use",
                "primary use",
                "use the laptop for",
                "what kind of work",
                "workload",
            )
        ):
            return "primary_use"
        if any(token in lowered for token in ("windows or mac", "operating system", "which os", "prefer windows", "prefer a mac")):
            return "operating_system"
        if any(token in lowered for token in ("weight for portability", "screen size or weight", "portability", "easy to carry", "laptop weight")):
            return "portability"
    return _purchase_intent_base_question_target(question, context)


def _apply_answer_to_target(
    context: dict[str, Any],
    target: str,
    raw_answer: str,
) -> bool:
    if _purchase_context(context):
        if target == "primary_use":
            primary_use = _normalize_primary_use(raw_answer)
            if not primary_use:
                answer = _sentence_fragment(raw_answer, 220).strip().rstrip(".?!")
                if _is_weak_acknowledgement(answer):
                    return False
                primary_use = answer
            return _replace_prefixed_item(
                context, "knownFacts", "Primary use", primary_use, MAX_FACTS
            )

        if target == "operating_system":
            operating_system = _normalize_operating_system(raw_answer)
            if not operating_system:
                return False
            return _replace_prefixed_item(
                context,
                "constraints",
                "Operating system",
                operating_system,
                MAX_CONSTRAINTS,
            )

        if target == "portability":
            lowered = _clean_text(raw_answer, 300).casefold()
            if re.fullmatch(
                r"(?:no|nope|not\s+really|doesn'?t\s+matter|no\s+preference|anything\s+is\s+fine)",
                re.sub(r"[^a-z0-9']+", " ", lowered).strip(),
            ):
                value = "no strong preference"
            else:
                value = _sentence_fragment(raw_answer, 180).strip().rstrip(".?!")
                if _is_weak_acknowledgement(value):
                    return False
            return _replace_prefixed_item(
                context,
                "constraints",
                "Portability and size",
                value,
                MAX_CONSTRAINTS,
            )

        if target == "budget":
            maximum = _plain_maximum_budget(raw_answer)
            if maximum:
                return _replace_prefixed_item(
                    context, "constraints", "Budget", maximum, MAX_CONSTRAINTS
                )

    return _purchase_intent_base_apply_answer(context, target, raw_answer)


def _capture_purchase_requirements(context: dict[str, Any], text: str) -> bool:
    changed = _purchase_intent_base_capture_requirements(context, text)
    if not _purchase_context(context):
        return changed

    if _is_purchase_acknowledgement(text):
        return changed

    primary_use = _normalize_primary_use(text)
    if primary_use:
        changed = _replace_prefixed_item(
            context, "knownFacts", "Primary use", primary_use, MAX_FACTS
        ) or changed

    operating_system = _normalize_operating_system(text)
    if operating_system and re.search(
        r"\b(?:windows|mac|macos|macbook|linux|operating\s+system|\bos\b|no\s+preference|either)\b",
        text,
        flags=re.IGNORECASE,
    ):
        changed = _replace_prefixed_item(
            context,
            "constraints",
            "Operating system",
            operating_system,
            MAX_CONSTRAINTS,
        ) or changed

    maximum = _plain_maximum_budget(text)
    if maximum:
        changed = _replace_prefixed_item(
            context, "constraints", "Budget", maximum, MAX_CONSTRAINTS
        ) or changed

    return changed


def _refresh_derived_objective(context: dict[str, Any]) -> None:
    _purchase_intent_base_refresh_objective(context)
    if not _purchase_context(context):
        return

    product = _purchase_subject_base(context)
    primary_use = _purchase_primary_use(context)
    operating_system = _purchase_operating_system(context)
    budget = _purchase_budget(context)
    brand = _purchase_brand(context)
    flexible_brand = _purchase_prefers_alternatives(context)

    subject_parts: list[str] = []
    if operating_system and operating_system.casefold() != "no strong preference":
        subject_parts.append(operating_system)
    if brand and not flexible_brand:
        subject_parts.append(brand)
    subject_parts.append(product)
    subject = " ".join(part for part in subject_parts if part)
    if primary_use:
        subject += f" for {primary_use}"
    context["subject"] = _clean_text(subject, 360)

    article = "an" if context["subject"][:1].casefold() in {"a", "e", "i", "o", "u"} else "a"
    objective = f"Buy {article} {context['subject']}"
    if brand and flexible_brand:
        objective += f", preferably {brand}"
    if budget and budget.casefold() != "flexible":
        objective += f", within {budget}"
    objective += ", and confirm it arrives working correctly."
    context["objective"] = _clean_text(objective, 600)

    success = _clean_text(context.get("successCriteria"), 500)
    if (
        not success
        or success.casefold() in {
            "learning tasks as well",
            "buy product and confirm it arrives working correctly",
        }
        or (primary_use and "fits the user's requirements" in success.casefold())
    ):
        result = f"Purchase a {product} that"
        if primary_use:
            result += f" handles {primary_use} well"
        else:
            result += " fits the user's requirements"
        result += " and arrives working correctly."
        context["successCriteria"] = result


def _specific_questions(context: dict[str, Any]) -> list[str]:
    if not _purchase_context(context):
        return _purchase_intent_base_specific_questions(context)

    if _purchase_verified(context):
        return []

    product = _purchase_subject_base(context).casefold()
    questions: list[str] = []
    if product in {"laptop", "computer", "desktop"} and not _purchase_primary_use(context):
        questions.append("What will you mainly use the computer for?")
    if not _purchase_budget(context):
        questions.append("What budget or maximum price should guide this purchase?")
    if product in {"laptop", "computer", "desktop"} and not _purchase_operating_system(context):
        questions.append("Do you prefer Windows, macOS, Linux, or have no operating-system preference?")
    if product in {"tv", "television", "monitor", "projector"} and not _purchase_size(context):
        questions.append("What screen size do you want, or what is the viewing distance?")
    if not _purchase_brand(context):
        questions.append("Do you have a preferred brand, or should QMeet compare reputable brands?")
    return questions[:MAX_OPEN_QUESTIONS]


def _build_purchase_search_query(context: dict[str, Any]) -> str:
    product = _purchase_subject_base(context)
    primary_use = _purchase_primary_use(context)
    operating_system = _purchase_operating_system(context)
    budget = _purchase_budget(context)
    brand = _purchase_brand(context)
    size = _purchase_size(context)

    parts = ["current in-stock"]
    if size and size.casefold() not in {"large", "big"}:
        parts.append(size)
    if operating_system and operating_system.casefold() != "no strong preference":
        parts.append(operating_system)
    if brand:
        parts.append(brand)
    parts.append(product)
    if primary_use:
        parts.append(f"for {primary_use}")
    query = " ".join(parts)
    if budget and budget.casefold() != "flexible":
        query += f" under {budget}"
    if brand and _purchase_prefers_alternatives(context):
        query += f", plus comparable alternatives to {brand} from reputable brands"
    query += (
        "; return verified current availability, current prices, exact configurations, "
        "and direct retailer product pages; exclude archived, discontinued, unavailable, "
        "or generic category pages"
    )
    return _clean_text(query, 500)


def _assistant_promises_purchase_search(text: str) -> bool:
    lowered = _clean_text(text, 1600).casefold()
    return bool(
        re.search(
            r"\b(?:i(?:'ll| will)|let\s+me)\s+(?:find|search|gather|look\s+for|prepare|pull)\b",
            lowered,
        )
        and re.search(
            r"\b(?:current|in-stock|available|models?|options?|deals?|prices?|listings?|buying\s+options?)\b",
            lowered,
        )
    )


def _apply_user_update(context: dict[str, Any], user_text: str) -> tuple[dict[str, Any], bool]:
    next_context, changed = _purchase_intent_base_apply_user(context, user_text)
    if not _purchase_context(next_context):
        return next_context, changed

    changed = _capture_purchase_requirements(next_context, user_text) or changed
    visible = _clean_text(_extract_visible_user_message(user_text), 1200)

    if _PURCHASE_UNAVAILABLE_RE.search(visible):
        changed = _prepend_unique(
            next_context,
            "recentProgress",
            "Previously suggested product listings were unavailable or invalid.",
            MAX_RECENT_PROGRESS,
        ) or changed
        pending = {
            "type": "search",
            "query": _build_purchase_search_query(next_context),
            "prompt": "Find replacement listings that are verified as currently available.",
        }
        if next_context.get("pendingAction") != pending:
            next_context["pendingAction"] = pending
            changed = True
        next_context["pendingQuestion"] = None
        next_context["openQuestions"] = []
        next_context["nextAction"] = (
            "Run a fresh live search for verified in-stock listings and discard the unavailable results."
        )

    _refresh_derived_objective(next_context)
    _refresh_questions_and_next_action(next_context, visible)
    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _apply_assistant_update(
    context: dict[str, Any],
    assistant_text: str,
) -> tuple[dict[str, Any], bool]:
    next_context, changed = _purchase_intent_base_apply_assistant(context, assistant_text)
    if not _purchase_context(next_context):
        return next_context, changed

    if _assistant_promises_purchase_search(assistant_text):
        pending = {
            "type": "search",
            "query": _build_purchase_search_query(next_context),
            "prompt": _clean_text(assistant_text, 320),
        }
        if next_context.get("pendingAction") != pending:
            next_context["pendingAction"] = pending
            changed = True
        next_context["pendingQuestion"] = None
        next_context["openQuestions"] = []
        next_context["nextAction"] = "Run the prepared live product search now."

    _refresh_derived_objective(next_context)
    _refresh_questions_and_next_action(next_context, "")
    if changed:
        next_context["updatedAt"] = _now_iso()
    return next_context, changed


def _refresh_questions_and_next_action(context: dict[str, Any], user_text: str) -> None:
    _purchase_intent_base_refresh_questions(context, user_text)
    if not _purchase_context(context):
        return

    _refresh_derived_objective(context)
    context["focusType"] = "purchase"
    if context.get("mode") == "general":
        context["mode"] = "planning"

    if _purchase_verified(context) or _purchase_ordered(context):
        return

    pending_action = _sanitize_pending_action(context.get("pendingAction"))
    if pending_action:
        context["pendingAction"] = pending_action
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["nextAction"] = "Run the prepared live product search now."
        return

    questions = _specific_questions(context)
    context["openQuestions"] = questions
    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    if pending and _question_target(pending["question"], context) not in {
        "primary_use",
        "budget",
        "operating_system",
        "portability",
        "size",
        "brand",
        "model",
        "retailer",
        "placement",
    }:
        context["pendingQuestion"] = None

    product = _purchase_subject_base(context).casefold()
    essential_ready = bool(_purchase_budget(context))
    if product in {"laptop", "computer", "desktop"}:
        essential_ready = essential_ready and bool(_purchase_primary_use(context)) and bool(
            _purchase_operating_system(context)
        )

    if essential_ready:
        context["nextAction"] = (
            "Run a live search for current in-stock models that match the recorded requirements."
        )
    elif questions:
        context["nextAction"] = questions[0]


def _sanitize_context(raw: object) -> dict[str, Any] | None:
    context = _purchase_intent_base_sanitize(raw)
    if context is None or not _purchase_context(context):
        return context

    context["knownFacts"] = [
        item
        for item in _clean_list(context.get("knownFacts"), MAX_FACTS, 340)
        if not re.search(
            r"\b(?:just|would)\s+likes?\s+(?:you|qmeet)\s+to\s+search\b|"
            r"\b(?:yes|sure|okay)\s+(?:was|is)\s+(?:the\s+)?brand\b",
            item,
            flags=re.IGNORECASE,
        )
    ]
    context["constraints"] = [
        item
        for item in _clean_list(context.get("constraints"), MAX_CONSTRAINTS, 340)
        if not item.casefold().startswith("requirement: no, the voice")
    ]
    _refresh_derived_objective(context)
    _refresh_questions_and_next_action(context, "")
    return context


def get_purchase_search_handoff(message: str, consume: bool = False) -> dict[str, str] | None:
    """Resolve purchase-search confirmations and continuations into a real Search query."""

    visible = _clean_text(_extract_visible_user_message(message), 1000)
    if not visible:
        return None

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if not isinstance(context, dict) or not _purchase_context(context):
            return None

        pending_action = _sanitize_pending_action(context.get("pendingAction"))
        acknowledgement = _is_purchase_acknowledgement(visible)
        unavailable = bool(_PURCHASE_UNAVAILABLE_RE.search(visible))
        continuation = bool(_PURCHASE_SEARCH_CONTINUATION_RE.search(visible))
        explicit_search = bool(
            re.search(
                r"\b(?:search|look\s+for|find|gather|compare|show\s+me|get\s+me|give\s+me)\b",
                visible,
                flags=re.IGNORECASE,
            )
            and re.search(
                r"\b(?:now|current|in-stock|available|options?|models?|laptops?|tvs?|deals?|prices?|products?|listings?|links?|retailers?)\b",
                visible,
                flags=re.IGNORECASE,
            )
        )
        search_challenge = bool(
            re.search(
                r"\b(?:don'?t|do\s+not)\s+you\s+have\s+(?:a\s+)?search\b|"
                r"\bwhy\s+can'?t\s+you\s+search\b|"
                r"\buse\s+(?:your\s+)?search(?:\s+function)?\b",
                visible,
                flags=re.IGNORECASE,
            )
        )

        should_search = bool(
            (acknowledgement and pending_action)
            or explicit_search
            or search_challenge
            or continuation
            or unavailable
        )
        if not should_search:
            return None

        query = _build_purchase_search_query(context)
        if pending_action and not unavailable:
            query = pending_action["query"]
        if unavailable or re.search(r"\b(?:real|working|valid)\s+(?:current\s+)?(?:listing|link)\b", visible, flags=re.IGNORECASE):
            query = _clean_text(
                query
                + "; verify each result is in stock now and use exact direct product pages, not category pages",
                600,
            )
        if re.search(r"\b(?:links?|listings?)\b", visible, flags=re.IGNORECASE):
            query = _clean_text(query + "; prioritize direct purchase links", 600)

        reason = "The user explicitly requested QMeet's live product Search action."
        if acknowledgement and pending_action:
            reason = "The user accepted QMeet's prepared live product search."
        elif continuation:
            reason = "The user followed up on a promised product search; run Search instead of fabricating results."
        elif unavailable:
            reason = "The prior product results were unavailable; run a replacement live search with availability verification."

        result = {"query": query, "reason": reason}
        if consume:
            context.pop("pendingAction", None)
            context["pendingQuestion"] = None
            context["openQuestions"] = []
            context["nextAction"] = "Review the live Search results and compare the verified available options."
            _prepend_unique(
                context,
                "recentProgress",
                "A live product search was requested.",
                MAX_RECENT_PROGRESS,
            )
            context["updatedAt"] = _now_iso()
            _write_context_unlocked(context)
        return result


def should_keep_focus_message_in_chat(message: str) -> bool:
    base = _purchase_intent_base_keep_in_chat(message)
    visible = _clean_text(_extract_visible_user_message(message), 1000)
    if not visible:
        return base
    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if not isinstance(context, dict) or not _purchase_context(context):
        return base
    if _PURCHASE_SEARCH_CONTINUATION_RE.search(visible) or _PURCHASE_UNAVAILABLE_RE.search(visible):
        return False
    return base


def prepare_background_chat_message(message: str) -> tuple[str, str]:
    contextual_message, visible_user_message = _purchase_intent_base_prepare_chat(message)
    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if not isinstance(context, dict) or not _purchase_context(context):
        return contextual_message, visible_user_message

    rules = [
        "Purchase intent-continuity rules:",
        "- Preserve the product being purchased when the user describes its purpose. A purpose such as machine learning is not a replacement focus title.",
        "- Treat yes, sure, okay, no, and not really as answers or action confirmations, never as brands, products, models, or memory facts.",
        "- Never promise to search and then answer from model memory. Current products, prices, availability, and links must use QMeet's actual Search action.",
        "- Never invent or guess a current retailer link, stock state, configuration, model year, or price.",
        "- If a prior recommendation is unavailable, discard it and run a fresh current search rather than weakening requirements without the user's approval.",
        "- For machine-learning laptops, keep the user's budget, operating system, brand flexibility, and ML workload together in every comparison.",
        "",
    ]
    marker = "Existing request and private context:"
    if marker in contextual_message:
        contextual_message = contextual_message.replace(
            marker, "\n".join(rules) + marker, 1
        )
    return contextual_message, visible_user_message


# Phase 18: tool-result assimilation and completed-search reuse
#
# Search requests were previously remembered, but successful Search results did not
# advance the focus. This layer records completed searches, resolves "compare
# reputable brands" confirmations, and reuses the existing Search panel instead of
# rerunning the same query for follow-ups such as "did you find it?".

WORK_CONTEXT_FILE_VERSION = 8

_tool_result_base_sanitize_context = _sanitize_context
_tool_result_base_get_purchase_search_handoff = get_purchase_search_handoff
_tool_result_base_specific_questions = _specific_questions
_tool_result_base_build_purchase_search_query = _build_purchase_search_query
_tool_result_base_purchase_prefers_alternatives = _purchase_prefers_alternatives

_TOOL_RESULT_COMPARE_BRANDS_DECISION = "No fixed brand; compare reputable brands."
_TOOL_RESULT_REUSE_SEARCH_RE = re.compile(
    r"^(?:"
    r"did\s+you\s+(?:find|finish|get)\s+(?:it|them|anything)|"
    r"what\s+did\s+you\s+find|"
    r"what\s+were\s+the\s+results|"
    r"show\s+(?:me\s+)?(?:the\s+)?results|"
    r"open\s+(?:the\s+)?search(?:\s+results)?|"
    r"give\s+me\s+(?:the\s+)?(?:results|links)|"
    r"(?:i(?:'m|\s+am)\s+)?still\s+waiting|"
    r"waiting"
    r")[?!.\s]*$",
    flags=re.IGNORECASE,
)
_TOOL_RESULT_FORCE_REFRESH_RE = re.compile(
    r"\b(?:search|look|find|check|try)\s+(?:again|another|more)|"
    r"\b(?:refresh|rerun|redo|repeat)\s+(?:the\s+)?search\b",
    flags=re.IGNORECASE,
)


def _sanitize_last_search(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    status = _clean_text(value.get("status"), 30).casefold()
    if status not in {"completed", "failed"}:
        return None

    query = _clean_text(value.get("query"), 600)
    if not query:
        return None

    result_count = value.get("resultCount", 0)
    source_count = value.get("sourceCount", 0)
    if isinstance(result_count, bool) or not isinstance(result_count, int):
        result_count = 0
    if isinstance(source_count, bool) or not isinstance(source_count, int):
        source_count = 0

    return {
        "status": status,
        "query": query,
        "completedAt": _clean_text(value.get("completedAt"), 80) or _now_iso(),
        "summary": _clean_text(value.get("summary"), 700),
        "recommendation": _clean_text(value.get("recommendation"), 500),
        "resultCount": max(0, result_count),
        "sourceCount": max(0, source_count),
        "topResults": _clean_list(value.get("topResults"), 5, 180),
        "error": _clean_text(value.get("error"), 400),
    }


def _compare_reputable_brands_selected(context: dict[str, Any]) -> bool:
    return any(
        item.casefold() == _TOOL_RESULT_COMPARE_BRANDS_DECISION.casefold()
        or "compare reputable brands" in item.casefold()
        or "no fixed brand" in item.casefold()
        for item in _clean_list(context.get("decisions"), MAX_DECISIONS, 360)
    )


def _purchase_prefers_alternatives(context: dict[str, Any]) -> bool:
    return (
        _compare_reputable_brands_selected(context)
        or _tool_result_base_purchase_prefers_alternatives(context)
    )


def _specific_questions(context: dict[str, Any]) -> list[str]:
    questions = _tool_result_base_specific_questions(context)
    if not isinstance(context, dict) or not _purchase_context(context):
        return questions
    if not _compare_reputable_brands_selected(context):
        return questions
    return [
        question
        for question in questions
        if "brand" not in question.casefold()
    ][:MAX_OPEN_QUESTIONS]


def _build_purchase_search_query(context: dict[str, Any]) -> str:
    query = _tool_result_base_build_purchase_search_query(context)
    if (
        _purchase_context(context)
        and not _purchase_brand(context)
        and _compare_reputable_brands_selected(context)
        and "reputable brands" not in query.casefold()
    ):
        query = _clean_text(
            query + "; compare options from reputable brands",
            600,
        )
    return query


def _sanitize_context(raw: object) -> dict[str, Any] | None:
    context = _tool_result_base_sanitize_context(raw)
    if context is None:
        return None

    raw_dict = raw if isinstance(raw, dict) else {}
    last_search = _sanitize_last_search(raw_dict.get("lastSearch"))
    if last_search is not None:
        context["lastSearch"] = last_search

    if not _purchase_context(context):
        return context

    if _compare_reputable_brands_selected(context):
        context["pendingQuestion"] = None
        context["openQuestions"] = [
            question
            for question in _clean_list(
                context.get("openQuestions"), MAX_OPEN_QUESTIONS, 260
            )
            if "brand" not in question.casefold()
        ]

    if last_search is not None and last_search["status"] == "completed":
        context.pop("pendingAction", None)
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        if context.get("stage") not in {"ready", "complete"} and not _purchase_ordered(context):
            context["stage"] = "in-progress"
        context["nextAction"] = (
            "Review the current Search results and select two or three options to compare."
        )
    elif last_search is not None and last_search["status"] == "failed":
        context["nextAction"] = (
            "Retry the live search or refine the requirements before comparing products."
        )

    return context


def _resolve_brand_comparison_confirmation(
    context: dict[str, Any],
    visible_message: str,
) -> bool:
    if not _is_purchase_acknowledgement(visible_message) or _purchase_brand(context):
        return False

    pending_question = _sanitize_pending_question(context.get("pendingQuestion"))
    pending_action = _sanitize_pending_action(context.get("pendingAction"))
    question_text = pending_question["question"] if pending_question else ""
    action_prompt = pending_action["prompt"] if pending_action else ""
    combined = f"{question_text} {action_prompt}".casefold()
    if "brand" not in combined or not any(
        phrase in combined
        for phrase in ("compare", "reputable", "other brands", "options")
    ):
        return False

    changed = _prepend_unique(
        context,
        "decisions",
        _TOOL_RESULT_COMPARE_BRANDS_DECISION,
        MAX_DECISIONS,
    )
    if pending_action is not None:
        refreshed_action = {
            **pending_action,
            "query": _build_purchase_search_query(context),
        }
        if context.get("pendingAction") != refreshed_action:
            context["pendingAction"] = refreshed_action
            changed = True
    context["pendingQuestion"] = None
    context["openQuestions"] = [
        question
        for question in _clean_list(context.get("openQuestions"), MAX_OPEN_QUESTIONS, 260)
        if "brand" not in question.casefold()
    ]
    return changed


def _last_completed_search(context: dict[str, Any]) -> dict[str, Any] | None:
    last_search = _sanitize_last_search(context.get("lastSearch"))
    if last_search is None or last_search["status"] != "completed":
        return None
    return last_search


def get_purchase_search_handoff(
    message: str,
    consume: bool = False,
) -> dict[str, str] | None:
    visible = _clean_text(_extract_visible_user_message(message), 1000)
    if not visible:
        return None

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if not isinstance(context, dict) or not _purchase_context(context):
            return None

        changed = _resolve_brand_comparison_confirmation(context, visible)
        last_search = _last_completed_search(context)
        reuse_existing = bool(
            last_search
            and _TOOL_RESULT_REUSE_SEARCH_RE.fullmatch(visible.strip())
            and not _TOOL_RESULT_FORCE_REFRESH_RE.search(visible)
            and not _PURCHASE_UNAVAILABLE_RE.search(visible)
        )
        if reuse_existing:
            context.pop("pendingAction", None)
            context["pendingQuestion"] = None
            context["openQuestions"] = []
            context["nextAction"] = (
                "Review the current Search results and select two or three options to compare."
            )
            if context.get("stage") not in {"ready", "complete"} and not _purchase_ordered(context):
                context["stage"] = "in-progress"
            context["updatedAt"] = _now_iso()
            if consume or changed:
                _write_context_unlocked(context)
            return {
                "action": "open_existing",
                "query": last_search["query"],
                "reason": (
                    "A matching live Search has already completed. Reopen the existing "
                    "Search results instead of running the same query again."
                ),
            }

        if changed:
            context["updatedAt"] = _now_iso()
            _write_context_unlocked(context)

    handoff = _tool_result_base_get_purchase_search_handoff(message, consume=consume)
    if handoff is None:
        return None
    return {
        **handoff,
        "action": "run_search",
    }


def _search_query_matches_purchase_context(
    context: dict[str, Any],
    query: str,
) -> bool:
    if not _purchase_context(context):
        return False

    lowered_query = query.casefold()
    progress = _clean_list(context.get("recentProgress"), MAX_RECENT_PROGRESS, 320)
    if any("live product search was requested" in item.casefold() for item in progress):
        return True

    next_action = _clean_text(context.get("nextAction"), 500).casefold()
    if "search" in next_action and any(
        token in next_action for token in ("product", "model", "listing", "option")
    ):
        return True

    match_text = " ".join(
        part
        for part in (
            _purchase_subject_base(context),
            _purchase_primary_use(context),
            _purchase_operating_system(context),
            _purchase_brand(context),
        )
        if part
    ).casefold()
    terms = {
        token
        for token in re.findall(r"[a-z0-9]+", match_text)
        if len(token) >= 4 and token not in {"with", "from", "that", "this"}
    }
    return bool(terms and any(term in lowered_query for term in terms))


def _search_result_titles(result: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for collection_name in ("cards", "sources"):
        collection = result.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title"), 180)
            if title and title.casefold() not in {value.casefold() for value in titles}:
                titles.append(title)
            if len(titles) >= 5:
                return titles
    return titles


def record_background_search_result(
    query: str,
    result: object,
) -> dict[str, Any]:
    clean_query = _clean_text(query, 600)
    result_dict = result if isinstance(result, dict) else {}
    if not clean_query:
        return {"ok": True, "recorded": False, "activeContext": None}

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if (
            not isinstance(context, dict)
            or not _purchase_context(context)
            or not _search_query_matches_purchase_context(context, clean_query)
        ):
            return {
                "ok": True,
                "recorded": False,
                "activeContext": context,
            }

        cards = result_dict.get("cards")
        sources = result_dict.get("sources")
        card_count = len(cards) if isinstance(cards, list) else 0
        source_count = len(sources) if isinstance(sources, list) else 0
        last_search = {
            "status": "completed",
            "query": clean_query,
            "completedAt": _now_iso(),
            "summary": _clean_text(result_dict.get("summary"), 700),
            "recommendation": _clean_text(result_dict.get("recommendation"), 500),
            "resultCount": card_count,
            "sourceCount": source_count,
            "topResults": _search_result_titles(result_dict),
            "error": "",
        }
        context["lastSearch"] = last_search
        context.pop("pendingAction", None)
        context["pendingQuestion"] = None
        context["openQuestions"] = []
        context["recentProgress"] = [
            item
            for item in _clean_list(
                context.get("recentProgress"), MAX_RECENT_PROGRESS, 320
            )
            if "live product search was requested" not in item.casefold()
        ]
        _prepend_unique(
            context,
            "recentProgress",
            "Current matching products and sources are available in Search.",
            MAX_RECENT_PROGRESS,
        )
        _prepend_unique(
            context,
            "recentProgress",
            "A live product search was completed.",
            MAX_RECENT_PROGRESS,
        )
        if context.get("stage") not in {"ready", "complete"} and not _purchase_ordered(context):
            context["stage"] = "in-progress"
        context["nextAction"] = (
            "Review the current Search results and select two or three options to compare."
        )
        context["confidence"] = min(
            0.99,
            float(context.get("confidence", 0.35)) + 0.04,
        )
        context["updatedAt"] = _now_iso()
        payload = _write_context_unlocked(context)
        return {
            "ok": True,
            "recorded": True,
            "activeContext": payload.get("activeContext"),
        }


def record_background_search_failure(
    query: str,
    error: str,
) -> dict[str, Any]:
    clean_query = _clean_text(query, 600)
    clean_error = _clean_text(error, 400)
    if not clean_query:
        return {"ok": True, "recorded": False, "activeContext": None}

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if (
            not isinstance(context, dict)
            or not _purchase_context(context)
            or not _search_query_matches_purchase_context(context, clean_query)
        ):
            return {
                "ok": True,
                "recorded": False,
                "activeContext": context,
            }

        context["lastSearch"] = {
            "status": "failed",
            "query": clean_query,
            "completedAt": _now_iso(),
            "summary": "",
            "recommendation": "",
            "resultCount": 0,
            "sourceCount": 0,
            "topResults": [],
            "error": clean_error,
        }
        context.pop("pendingAction", None)
        context["nextAction"] = (
            "Retry the live search or refine the requirements before comparing products."
        )
        _prepend_unique(
            context,
            "recentProgress",
            "The most recent live product search did not complete successfully.",
            MAX_RECENT_PROGRESS,
        )
        context["updatedAt"] = _now_iso()
        payload = _write_context_unlocked(context)
        return {
            "ok": True,
            "recorded": True,
            "activeContext": payload.get("activeContext"),
        }

# ---------------------------------------------------------------------------
# Phase 18: research-source continuity and truthful focus/tool state
# ---------------------------------------------------------------------------
# This layer generalizes Search assimilation beyond purchases, keeps factual
# research grounded in real sources, and recognizes completed/submitted writing.

_phase18_research_base_apply_user_update = _apply_user_update
_phase18_research_base_prepare_background_chat_message = prepare_background_chat_message
_phase18_research_base_record_search_result = record_background_search_result
_phase18_research_base_record_search_failure = record_background_search_failure


def _research_or_document_context(context: dict[str, Any] | None) -> bool:
    if not isinstance(context, dict):
        return False
    mode = _clean_text(context.get("mode"), 40).casefold()
    focus_type = _clean_text(context.get("focusType"), 40).casefold()
    if mode == "research" or focus_type in {
        "research",
        "document",
        "review",
        "presentation",
    }:
        return True
    haystack = " ".join(
        _clean_text(context.get(key), 260)
        for key in ("title", "objective", "subject")
    ).casefold()
    return bool(
        re.search(
            r"\b(?:essay|paper|report|research|review|article|sources?|"
            r"literature|history|school assignment)\b",
            haystack,
        )
    )


def _research_search_query_matches_context(
    context: dict[str, Any],
    query: str,
) -> bool:
    if not _research_or_document_context(context):
        return False
    lowered = query.casefold()
    if re.search(
        r"\b(?:sources?|articles?|papers?|studies|citations?|references?|"
        r"peer[ -]?reviewed|academic|scholarly|evidence)\b",
        lowered,
    ):
        return True

    context_text = " ".join(
        _clean_text(context.get(key), 260)
        for key in ("title", "objective", "subject")
    ).casefold()
    terms = {
        token
        for token in re.findall(r"[a-z0-9]+", context_text)
        if len(token) >= 4
        and token
        not in {
            "with",
            "from",
            "that",
            "this",
            "write",
            "essay",
            "paper",
            "report",
            "research",
        }
    }
    return bool(terms and any(term in lowered for term in terms))


def _clear_source_questions(context: dict[str, Any]) -> None:
    pending = _sanitize_pending_question(context.get("pendingQuestion"))
    if pending and pending.get("target") in {
        "sources",
        "evidence",
        "research",
        "references",
    }:
        context["pendingQuestion"] = None

    context["openQuestions"] = [
        question
        for question in _clean_list(
            context.get("openQuestions"),
            MAX_OPEN_QUESTIONS,
            260,
        )
        if not re.search(
            r"\b(?:source|article|citation|reference|evidence|where.*find)\b",
            question,
            flags=re.IGNORECASE,
        )
    ]


def _research_next_action_for_query(query: str) -> str:
    if re.search(
        r"\b(?:peer[ -]?reviewed|academic|scholarly|journal)\b",
        query,
        flags=re.IGNORECASE,
    ):
        return (
            "Review the gathered sources, verify which entries are genuinely "
            "peer-reviewed, and select the strongest evidence for the outline or draft."
        )
    return (
        "Review the gathered sources, select the strongest evidence, and update "
        "the outline or draft with supported claims."
    )


def _apply_user_update(
    context: dict[str, Any],
    visible_message: str,
) -> tuple[dict[str, Any], bool]:
    next_context, changed = _phase18_research_base_apply_user_update(
        context,
        visible_message,
    )
    if not _research_or_document_context(next_context):
        return next_context, changed

    visible = _clean_text(_extract_visible_user_message(visible_message), 1200)
    lowered = visible.casefold()
    completed_and_submitted = bool(
        re.search(
            r"\b(?:i|we)\s+(?:just\s+)?(?:wrote|finished|completed|finalized)\b",
            lowered,
        )
        and re.search(r"\b(?:essay|paper|report|review|article|draft|it)\b", lowered)
        and re.search(
            r"\b(?:sent|submitted|turned\s+in|handed\s+in|emailed|uploaded)\b",
            lowered,
        )
    )
    if not completed_and_submitted:
        return next_context, changed

    progress_items = (
        "The written work was completed.",
        "The completed work was submitted or sent to its intended recipient.",
    )
    for item in progress_items:
        changed = _prepend_unique(
            next_context,
            "recentProgress",
            item,
            MAX_RECENT_PROGRESS,
        ) or changed

    completion_action = (
        "The writing is complete and submitted. End the focus and save a brief "
        "outcome summary unless the user identifies another required step."
    )
    if next_context.get("stage") != "complete":
        next_context["stage"] = "complete"
        changed = True
    if next_context.get("nextAction") != completion_action:
        next_context["nextAction"] = completion_action
        changed = True
    if next_context.get("pendingQuestion") is not None:
        next_context["pendingQuestion"] = None
        changed = True
    if next_context.get("openQuestions"):
        next_context["openQuestions"] = []
        changed = True
    return next_context, changed


def prepare_background_chat_message(message: str) -> tuple[str, str]:
    prepared, visible = _phase18_research_base_prepare_background_chat_message(message)

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
    if not isinstance(context, dict):
        return prepared, visible

    general_truth_rule = (
        "- Never claim that a focus, task, Search, note, or other QMeet action "
        "was completed unless the corresponding local tool or command actually ran."
    )
    extra_rules = [general_truth_rule]

    if _research_or_document_context(context):
        extra_rules.extend(
            [
                "- For factual research or school writing, never invent historical claims, dates, inventors, development processes, impacts, quotations, citations, links, authors, or publication details.",
                "- Never label a source peer-reviewed or scholarly unless the available Search result supports that classification.",
                "- When the user asks QMeet to find sources, the real Search action must run; do not merely suggest databases, promise to search later, or fabricate links.",
                "- If no completed Search evidence is available and the user requests a factual draft, provide a clearly labeled outline or provisional draft with evidence placeholders instead of presenting unsupported claims as fact.",
                "- When completed Search evidence is available, ground factual prose in that evidence and clearly separate sourced facts from interpretation.",
            ]
        )

        last_search = _sanitize_last_search(context.get("lastSearch"))
        if last_search and last_search.get("status") == "completed":
            search_lines = [
                "Latest completed research Search:",
                f"- Query: {last_search.get('query') or 'Not recorded'}",
                f"- Summary: {last_search.get('summary') or 'No summary was returned'}",
                f"- Recommendation: {last_search.get('recommendation') or 'No recommendation was returned'}",
            ]
            top_results = last_search.get("topResults")
            if isinstance(top_results, list) and top_results:
                search_lines.append("- Top source titles:")
                search_lines.extend(f"  - {title}" for title in top_results[:5])
            prepared = prepared.replace(
                "\n\nExisting request and private context:",
                "\n" + "\n".join(search_lines) + "\n\nExisting request and private context:",
                1,
            )

    insertion = "\n".join(extra_rules)
    prepared = prepared.replace(
        "Behavior rules:\n",
        f"Behavior rules:\n{insertion}\n",
        1,
    )
    return prepared, visible


def record_background_search_result(
    query: str,
    result: object,
) -> dict[str, Any]:
    base_result = _phase18_research_base_record_search_result(query, result)
    if bool(base_result.get("recorded")):
        return base_result

    clean_query = _clean_text(query, 600)
    result_dict = result if isinstance(result, dict) else {}
    if not clean_query:
        return base_result

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if (
            not isinstance(context, dict)
            or not _research_or_document_context(context)
            or not _research_search_query_matches_context(context, clean_query)
        ):
            return base_result

        cards = result_dict.get("cards")
        sources = result_dict.get("sources")
        card_count = len(cards) if isinstance(cards, list) else 0
        source_count = len(sources) if isinstance(sources, list) else 0
        context["lastSearch"] = {
            "status": "completed",
            "query": clean_query,
            "completedAt": _now_iso(),
            "summary": _clean_text(result_dict.get("summary"), 700),
            "recommendation": _clean_text(result_dict.get("recommendation"), 500),
            "resultCount": card_count,
            "sourceCount": source_count,
            "topResults": _search_result_titles(result_dict),
            "error": "",
        }
        context.pop("pendingAction", None)
        _clear_source_questions(context)
        _prepend_unique(
            context,
            "recentProgress",
            "Research sources and results are available in Search.",
            MAX_RECENT_PROGRESS,
        )
        _prepend_unique(
            context,
            "recentProgress",
            "A live source search was completed.",
            MAX_RECENT_PROGRESS,
        )
        if context.get("stage") not in {"ready", "complete"}:
            context["stage"] = "in-progress"
        context["nextAction"] = _research_next_action_for_query(clean_query)
        context["confidence"] = min(
            0.99,
            float(context.get("confidence", 0.35)) + 0.04,
        )
        context["updatedAt"] = _now_iso()
        payload = _write_context_unlocked(context)
        return {
            "ok": True,
            "recorded": True,
            "activeContext": payload.get("activeContext"),
        }


def record_background_search_failure(
    query: str,
    error: str,
) -> dict[str, Any]:
    base_result = _phase18_research_base_record_search_failure(query, error)
    if bool(base_result.get("recorded")):
        return base_result

    clean_query = _clean_text(query, 600)
    clean_error = _clean_text(error, 400)
    if not clean_query:
        return base_result

    with _STORE_LOCK:
        context = _sync_with_active_session_unlocked()
        if (
            not isinstance(context, dict)
            or not _research_or_document_context(context)
            or not _research_search_query_matches_context(context, clean_query)
        ):
            return base_result

        context["lastSearch"] = {
            "status": "failed",
            "query": clean_query,
            "completedAt": _now_iso(),
            "summary": "",
            "recommendation": "",
            "resultCount": 0,
            "sourceCount": 0,
            "topResults": [],
            "error": clean_error,
        }
        context.pop("pendingAction", None)
        context["nextAction"] = (
            "Retry the source search with a narrower query or adjust the source requirements."
        )
        _prepend_unique(
            context,
            "recentProgress",
            "The most recent source search did not complete successfully.",
            MAX_RECENT_PROGRESS,
        )
        context["updatedAt"] = _now_iso()
        payload = _write_context_unlocked(context)
        return {
            "ok": True,
            "recorded": True,
            "activeContext": payload.get("activeContext"),
        }
