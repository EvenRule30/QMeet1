from __future__ import annotations

import json
import re
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.work_context import (
    WorkContextError,
    get_background_work_context,
    get_purchase_search_handoff,
    observe_background_user_message,
    should_keep_focus_message_in_chat,
)

_MAX_OBSERVED_BODY_BYTES = 1_000_000
_OBSERVED_PATHS = {
    "/api/command/interpret",
    "/api/chat",
    "/api/chat/stream",
    "/api/search",
}

_IMPLICIT_FOCUS_DURABLE_RE = re.compile(
    r"\b(?:"
    r"project|assignment|coursework|homework|class|course|exam|test|study plan|"
    r"report|paper|essay|research|proposal|presentation|portfolio|application|"
    r"website|web site|dashboard|app|application|program|code|feature|bug|"
    r"launch|release|deadline|milestone|roadmap|strategy|budget|trip|travel|"
    r"event|party|birthday|gift|flowers?|wedding|interview|meeting|workshop|"
    r"renovation|move|moving|job search|certification|purchase|shopping|buying|"
    r"television|tv|laptop|computer|phone|tablet|appliance|furniture|vehicle|"
    r"car|motorcycle|truck|engine|battery|problem|issue|trouble|repair|"
    r"troubleshooting|diagnosis|not working|won't start|will not start"
    r")\b",
    flags=re.IGNORECASE,
)
_IMPLICIT_FOCUS_ACTION_RE = re.compile(
    r"\b(?:finish(?:ing)?|complet(?:e|ing)|build(?:ing)?|creat(?:e|ing)|"
    r"develop(?:ing)?|design(?:ing)?|redesign(?:ing)?|prepar(?:e|ing)|"
    r"stud(?:y|ying)|research(?:ing)?|writ(?:e|ing)|plan(?:ning)?|"
    r"organiz(?:e|ing)|fix(?:ing)?|debug(?:ging)?|diagnos(?:e|ing)|"
    r"troubleshoot(?:ing)?|repair(?:ing)?|launch(?:ing)?|"
    r"submit(?:ting)?|apply(?:ing)?|practic(?:e|ing)|learn(?:ing)?|"
    r"set(?:ting)? up|figur(?:e|ing) out|tackl(?:e|ing)|work(?:ing)? on|"
    r"giv(?:e|ing)|buy(?:ing)?|purchas(?:e|ing)|shop(?:ping)?(?:\s+for)?|"
    r"order(?:ing)?|compar(?:e|ing)|arrang(?:e|ing)|choos(?:e|ing)|get(?:ting)?|"
    r"get(?:ting)? ready for)\b",
    flags=re.IGNORECASE,
)
_IMPLICIT_FOCUS_DEADLINE_RE = re.compile(
    r"\b(?:due|deadline|by\s+(?:today|tomorrow|tonight|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday|next\s+week|next\s+month|the\s+end\s+of)|"
    r"in\s+\d+\s+(?:hours?|days?|weeks?|months?)|coming\s+up|before\s+.+)\b",
    flags=re.IGNORECASE,
)
_IMPLICIT_FOCUS_PERSONAL_RE = re.compile(
    r"\b(?:birthday|gift|flowers?|family|friend|coworker|partner|wedding|home|"
    r"personal|move|moving|trip|travel|party)\b",
    flags=re.IGNORECASE,
)
_IMPLICIT_FOCUS_CODING_RE = re.compile(
    r"\b(?:code|coding|program|programming|software|app|website|web site|api|"
    r"database|dashboard|java|python|javascript|typescript|react|bug|debug|"
    r"compile|repository|repo|github)\b",
    flags=re.IGNORECASE,
)
_IMPLICIT_FOCUS_MEETING_RE = re.compile(
    r"\b(?:meeting|standup|sync|workshop|agenda|client call|team call)\b",
    flags=re.IGNORECASE,
)
_IMPLICIT_FOCUS_RESEARCH_RE = re.compile(
    r"\b(?:research|study|paper|essay|sources?|literature|exam|test|coursework|"
    r"homework|class assignment)\b",
    flags=re.IGNORECASE,
)
_IMPLICIT_FOCUS_PLANNING_RE = re.compile(
    r"\b(?:plan|planning|organize|schedule|roadmap|strategy|budget|trip|travel|"
    r"event|party|presentation|proposal|launch|deadline|milestone|prepare|"
    r"purchase|shopping|buying|compare|troubleshoot|diagnose|repair)\b",
    flags=re.IGNORECASE,
)
_IMPLICIT_FOCUS_EXCLUSION_RE = re.compile(
    r"^(?:please\s+)?(?:open|show|display|close|hide|search|look\s+up|find|"
    r"google|remind\s+me|set\s+(?:a\s+)?timer|what|why|when|where|who|"
    r"which|how\s+(?:many|much|old|long|far)|is|are|do|does|did|tell\s+me)\b",
    flags=re.IGNORECASE,
)


def _header_value(scope: Scope, header_name: bytes) -> str:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() == header_name:
            return raw_value.decode("latin-1", errors="ignore")
    return ""


def _extract_payload(body: bytes, content_type: str) -> dict[str, Any]:
    if not body or "application/json" not in content_type.casefold():
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_message(path: str, payload: dict[str, Any]) -> str:
    candidate_keys = ("query",) if path == "/api/search" else ("message", "query")
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_natural_focus_completion(message: str) -> bool:
    """Match completion of the whole focus, not completion of an individual task."""

    normalized = re.sub(r"[?!.,;:]+", " ", message.casefold())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    patterns = [
        r"^(?:okay |ok |alright |all right )?(?:i(?:'m| am)|we(?:'re| are)) (?:done|finished|complete|through|all done) (?:with )?(?:this|that|it|the focus|the project|the session|what we were doing)(?: now)?(?: thank you| thanks)?$",
        r"^(?:okay |ok |alright |all right )?(?:this|that|it|the focus|the project|the session) (?:is )?(?:done|finished|complete|over)(?: now)?(?: thank you| thanks)?$",
        r"^(?:okay |ok |alright |all right )?(?:i|we) (?:finished|completed) (?:this|that|it|the focus|the project|the session)(?: now)?(?: thank you| thanks)?$",
        r"^(?:okay |ok |alright |all right )?(?:let(?:'s| us)|lets) (?:end|close|finish) (?:this|that|the focus|the project|the session)(?: now)?$",
    ]
    return any(re.fullmatch(pattern, normalized) for pattern in patterns)


def _active_context() -> dict[str, Any] | None:
    try:
        payload = get_background_work_context()
    except WorkContextError:
        return None
    context = payload.get("activeContext") if isinstance(payload, dict) else None
    return context if isinstance(context, dict) else None


def _client_has_active_session(payload: dict[str, Any]) -> bool:
    client_context = payload.get("clientContext")
    if not isinstance(client_context, dict):
        return False
    memory_state = client_context.get("memoryState")
    if not isinstance(memory_state, dict):
        return False
    return isinstance(memory_state.get("activeSession"), dict)


def _clean_focus_text(value: str, max_length: int = 180) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    text = re.sub(
        r"^(?:okay|ok|alright|all right|well|so|actually|basically|maybe)\s*[,;:-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^(?:please\s+)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:please|if you can)$", "", text, flags=re.IGNORECASE)
    text = text.strip(" \t\r\n.,;:!?\"'")
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return text


def _normalize_goal(candidate: str) -> str:
    goal = _clean_focus_text(candidate)
    goal = re.sub(
        r"^(?:i|we)\s+have\s+(?:with|when)\s+",
        "",
        goal,
        flags=re.IGNORECASE,
    )
    goal = re.sub(
        r"^(?:help(?:\s+me)?)(?:\s+with)?\s+(?=(?:buy|buying|purchase|purchasing|shop|shopping|get|getting)\b)",
        "",
        goal,
        flags=re.IGNORECASE,
    ).strip()
    goal = re.sub(r"^(?:with|on|about)\s+", "", goal, flags=re.IGNORECASE)
    goal = re.sub(r"^(?:a|an|the)\s+", lambda match: match.group(0), goal)
    goal = re.sub(
        r"\s+(?:but|and)\s+(?:i|we)\s+(?:do\s+not|don't|dont)\s+know\s+"
        r"(?:where|how)\s+to\s+start.*$",
        "",
        goal,
        flags=re.IGNORECASE,
    ).strip()
    if not goal:
        return ""

    lowered_for_incident = goal.casefold()
    if re.search(
        r"\b(?:car|vehicle)\b.*\b(?:not starting|won't start|will not start|"
        r"doesn't start|does not start|starting problem|trouble starting)\b|"
        r"\b(?:problem|issue|trouble)\b.*\bstarting\b.*\b(?:car|vehicle)\b|"
        r"^starting\s+(?:my|the|our)\s+(?:car|vehicle)$",
        lowered_for_incident,
    ):
        return "Restore reliable starting and operation for the car"

    gerund_actions = {
        "finishing": "Finish",
        "completing": "Complete",
        "building": "Build",
        "creating": "Create",
        "developing": "Develop",
        "designing": "Design",
        "redesigning": "Redesign",
        "preparing": "Prepare",
        "studying": "Study",
        "researching": "Research",
        "writing": "Write",
        "planning": "Plan",
        "organizing": "Organize",
        "fixing": "Fix",
        "debugging": "Debug",
        "launching": "Launch",
        "submitting": "Submit",
        "practicing": "Practice",
        "learning": "Learn",
        "setting up": "Set up",
        "figuring out": "Figure out",
        "tackling": "Tackle",
        "working on": "Work on",
        "giving": "Give",
        "buying": "Buy",
        "purchasing": "Purchase",
        "shopping for": "Shop for",
        "ordering": "Order",
        "comparing": "Compare",
        "arranging": "Arrange",
        "choosing": "Choose",
        "getting": "Get",
    }
    lowered_goal = goal.casefold()
    for gerund, command in gerund_actions.items():
        if lowered_goal == gerund or lowered_goal.startswith(f"{gerund} "):
            remainder = goal[len(gerund):].lstrip()
            goal = f"{command}{f' {remainder}' if remainder else ''}"
            break
    if re.fullmatch(r"(?:this|that|it|something|stuff|things?)", goal, flags=re.IGNORECASE):
        return ""

    if re.match(r"^Get\s+", goal) and re.search(
        r"\b(?:television|tv|laptop|computer|phone|tablet|appliance|furniture|"
        r"vehicle|motorcycle|car|camera|monitor|headphones?|speaker)\b",
        goal,
        flags=re.IGNORECASE,
    ):
        goal = re.sub(r"^Get\s+", "Buy ", goal)

    if _IMPLICIT_FOCUS_ACTION_RE.match(goal):
        return goal[0].upper() + goal[1:]
    if re.search(r"\bdue\b", goal, flags=re.IGNORECASE):
        return f"Complete {goal}"
    if re.search(
        r"\b(?:project|assignment|homework|coursework|report|paper|essay|"
        r"presentation|portfolio|application|proposal|exam|test)\b",
        goal,
        flags=re.IGNORECASE,
    ):
        return f"Complete {goal}"
    return f"Make progress on {goal}"


def _focus_title(goal: str) -> str:
    if re.search(
        r"\b(?:car|vehicle)\b.*\b(?:start|starting|running)\b",
        goal,
        flags=re.IGNORECASE,
    ) and re.search(
        r"\b(?:get|fix|resolve|problem|trouble|reliably)\b",
        goal,
        flags=re.IGNORECASE,
    ):
        return "Car starting problem"

    purchase_match = re.match(
        r"^(?:buy|purchase|shop\s+for|order|get)\s+(.+)$",
        goal,
        flags=re.IGNORECASE,
    )
    if purchase_match and re.search(
        r"\b(?:television|tv|laptop|computer|phone|tablet|appliance|furniture|"
        r"vehicle|motorcycle|car|camera|monitor|headphones?|speaker)\b",
        purchase_match.group(1),
        flags=re.IGNORECASE,
    ):
        product = _clean_focus_text(purchase_match.group(1), 105)
        return f"Buying {product}" if product else "Product purchase"

    birthday_flowers = re.match(
        r"^give\s+([A-Z][a-z]+)\s+(?:some\s+)?flowers?\s+for\s+"
        r"(?:his|her|their)\s+birthday$",
        goal,
        flags=re.IGNORECASE,
    )
    if birthday_flowers:
        person = birthday_flowers.group(1)
        return f"Flowers for {person}'s birthday"

    title = re.sub(
        r"^(?:complete|finish|prepare|plan|build|create|develop|design|redesign|"
        r"study|research|write|organize|fix|debug|launch|submit|apply for|"
        r"practice|learn|set up|figure out|tackle|work on|give|buy|arrange|"
        r"choose|get|make progress on)\s+",
        "",
        goal,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"^(?:a|an|the|for)\s+", "", title, flags=re.IGNORECASE)
    title = _clean_focus_text(title, 120) or _clean_focus_text(goal, 120)
    return title[0].upper() + title[1:] if title else "Current project"


def _infer_focus_mode(goal: str) -> str:
    if re.search(
        r"\b(?:problem|issue|trouble|troubleshoot|diagnose|repair|not working|"
        r"won't start|will not start|doesn't start|does not start|starting problem)\b",
        goal,
        flags=re.IGNORECASE,
    ):
        return "planning"
    if _IMPLICIT_FOCUS_CODING_RE.search(goal):
        return "coding"
    if _IMPLICIT_FOCUS_MEETING_RE.search(goal):
        return "meeting"
    if _IMPLICIT_FOCUS_RESEARCH_RE.search(goal):
        return "research"
    if re.search(
        r"\b(?:buy|buying|purchase|purchasing|shop|shopping|order|ordering|"
        r"compare|comparing)\b",
        goal,
        flags=re.IGNORECASE,
    ) or (
        re.search(r"\b(?:get|getting)\b", goal, flags=re.IGNORECASE)
        and re.search(
            r"\b(?:television|tv|laptop|computer|phone|tablet|appliance|"
            r"furniture|vehicle|motorcycle|car|camera|monitor|headphones?|speaker)\b",
            goal,
            flags=re.IGNORECASE,
        )
    ):
        return "planning"
    if _IMPLICIT_FOCUS_PERSONAL_RE.search(goal):
        return "personal"
    if _IMPLICIT_FOCUS_PLANNING_RE.search(goal) or _IMPLICIT_FOCUS_DEADLINE_RE.search(goal):
        return "planning"
    return "general"


def _implicit_focus_candidate(message: str) -> tuple[str, int] | None:
    text = _clean_focus_text(message, 420)
    if not text or len(text.split()) < 4:
        return None
    if _IMPLICIT_FOCUS_EXCLUSION_RE.search(text):
        return None
    if re.search(
        r"\b(?:not\s+trying\s+to|not\s+working\s+on|do\s+not\s+want\s+to|"
        r"don't\s+want\s+to|dont\s+want\s+to|do\s+not\s+need\s+to|"
        r"don't\s+need\s+to|dont\s+need\s+to)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return None
    if re.search(r"\b(?:focus|focus session|focusing)\b", text, flags=re.IGNORECASE):
        # The existing structured focus router handles explicit focus wording.
        return None

    patterns: list[tuple[str, int]] = [
        (
            r"^(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?help\s+(?:me|us)|"
            r"(?:i|we)\s+need\s+help)\s+(?:(?:with|on)\s+)?"
            r"(?:the\s+)?(?:problem|issue|trouble)\s+(.+)$",
            7,
        ),
        (
            r"^(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?help\s+(?:me|us)|"
            r"(?:i|we)\s+need\s+help)\s+(?:(?:with|on)\s+)?"
            r"(.+\b(?:won't|will not|doesn't|does not|isn't|is not)\s+"
            r"(?:start|starting|work|working).*)$",
            7,
        ),
        (
            r"^(?:i(?:'d| would)?\s+like|i\s+like|i\s+want|i\s+need)\s+"
            r"(?:some\s+)?help\s+(?:(?:with|in|on)\s+)?"
            r"((?:buying|purchasing|shopping\s+for|getting|choosing|comparing)\s+.+)$",
            6,
        ),
        (
            r"^(?:can|could|would|will)\s+you\s+(?:please\s+)?help\s+(?:me|us)\s+"
            r"(?:(?:with|in|on)\s+)?"
            r"((?:buying|purchasing|shopping\s+for|getting|choosing|comparing)\s+.+)$",
            6,
        ),
        (
            r"^(?:my|our)\s+(?:current\s+)?(?:project|assignment|goal|priority|"
            r"main task|big task|next project)\s+(?:is|is to|involves|will be)\s+(.+)$",
            4,
        ),
        (
            r"^(?:i(?:'m| am)|we(?:'re| are))\s+(?:starting(?: to)?|beginning(?: to)?|trying to|"
            r"planning to|getting ready to|preparing to)\s+(.+)$",
            3,
        ),
        (
            r"^(?:i(?:'ve| have)|we(?:'ve| have))\s+got\s+to\s+(.+)$",
            2,
        ),
        (
            r"^(?:i(?:'m| am)|we(?:'re| are))\s+supposed\s+to\s+(.+)$",
            2,
        ),
        (
            r"^(?:i|we)\s+need\s+help\s+(?:with|on)\s+(.+)$",
            2,
        ),
        (
            r"^(?:the\s+)?thing\s+(?:i|we)\s+need\s+to\s+get\s+done\s+is\s+(.+)$",
            3,
        ),
        (
            r"^(?:this\s+is\s+)?(?:what\s+)?(?:i(?:'m| am)|we(?:'re| are))\s+working\s+on\s*[:\-]?\s*(.+)$",
            4,
        ),
        (
            r"^(?:i|we)\s+(?:need|have|want|would like|really need)\s+to\s+(.+)$",
            2,
        ),
        (
            r"^(?:i(?:'ve| have)|we(?:'ve| have))\s+got\s+((?:a|an|the|my|our)\s+.+(?:due|coming up|"
            r"to finish|to complete).*)$",
            3,
        ),
        (
            r"^(?:i|we)\s+have\s+((?:a|an|the|my|our)\s+.+(?:due|coming up|"
            r"to finish|to complete).*)$",
            3,
        ),
        (
            r"^(?:(?:can|could|would|will)\s+you\s+)?help\s+(?:me|us)\s+"
            r"((?:with\s+)?(?:plan|finish|complete|build|create|develop|design|"
            r"redesign|prepare|study|research|write|organize|fix|debug|launch|"
            r"submit|practice|learn|set up|figure out|tackle|work on)?.+)$",
            2,
        ),
        (
            r"^(?:(?:can|could)\s+we|let(?:'s| us)|lets)\s+(?:work on|tackle|"
            r"figure out|plan|finish|complete|build|create|prepare|organize|"
            r"start)\s+(.+)$",
            2,
        ),
    ]

    for pattern, base_score in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw_candidate = _clean_focus_text(match.group(1))
        if not raw_candidate:
            continue

        score = base_score
        if _IMPLICIT_FOCUS_DURABLE_RE.search(text):
            score += 2
        if _IMPLICIT_FOCUS_DEADLINE_RE.search(text):
            score += 2
        if _IMPLICIT_FOCUS_ACTION_RE.search(text):
            score += 1
        if len(text.split()) >= 7:
            score += 1

        return raw_candidate, score

    return None


def _is_contextual_followup_fragment(message: str) -> bool:
    """Return True for answers that should not become a new standalone focus.

    These phrases usually answer a question from the immediately preceding chat turn.
    Starting a focus from them loses the original object, as in "this would be for
    machine learning tasks" after asking for help buying a laptop.
    """

    text = _clean_focus_text(message, 420)
    if not text:
        return False
    return bool(
        re.fullmatch(
            r"(?:this|that|it)\s+(?:would|will|should|could|is|was)\s+"
            r"(?:be\s+)?(?:for|about|used\s+for|mainly\s+for)\s+.+|"
            r"(?:mainly|mostly|primarily|especially)\s+(?:for|to)\s+.+",
            text,
            flags=re.IGNORECASE,
        )
    )


def _contextual_followup_response(message: str) -> JSONResponse | None:
    if not _is_contextual_followup_fragment(message):
        return None
    return JSONResponse(
        {
            "intent": "chat",
            "action": "none",
            "confidence": 0.995,
            "frontendCommand": "",
            "payload": {},
            "reason": (
                "This message is a contextual answer fragment, not a complete new "
                "focus. Keep it in chat so the original subject is not discarded."
            ),
        }
    )


def _implicit_focus_start_response(
    message: str,
    request_payload: dict[str, Any],
) -> JSONResponse | None:
    if _active_context() is not None or _client_has_active_session(request_payload):
        return None

    candidate = _implicit_focus_candidate(message)
    if candidate is None:
        return None
    raw_goal, score = candidate
    if score < 5:
        return None

    goal = _normalize_goal(raw_goal)
    if not goal:
        return None
    title = _focus_title(goal)
    mode = _infer_focus_mode(goal)
    canonical_command = (
        f"start a {mode} focus session for {title} with goal to {goal}"
    )

    return JSONResponse(
        {
            "intent": "command",
            "action": "start_focus_session",
            "confidence": min(0.99, 0.88 + (score * 0.015)),
            "frontendCommand": canonical_command,
            "payload": {
                "title": title,
                "mode": mode,
                "goal": goal,
            },
            "reason": (
                "Background work context recognized a durable project, assignment, "
                "deadline, preparation goal, or multi-step personal objective and "
                "started a focus without requiring the word focus."
            ),
        }
    )



def _explicit_focus_payload(message: str) -> str:
    text = _clean_focus_text(message, 420)
    patterns = [
        r"^(?:please\s+)?(?:can|could|would|will)\s+you\s+(?:please\s+)?"
        r"(?:start|begin|create|open)\s+(?:me\s+)?(?:a\s+)?(?:new\s+)?"
        r"focus(?:\s+session)?\s+(?:for|on|about)\s+(.+)$",
        r"^(?:please\s+)?(?:start|begin|create|open)\s+(?:me\s+)?(?:a\s+)?"
        r"(?:new\s+)?focus(?:\s+session)?\s+(?:for|on|about)\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_focus_text(match.group(1), 260)
    return ""


def _is_vague_focus_payload(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    if not normalized:
        return True
    tokens = normalized.split()
    vague_tokens = {
        "get", "getting", "do", "doing", "work", "working", "help",
        "something", "stuff", "things", "thing", "it", "that", "this",
        "project", "task", "goal", "focus", "session",
    }
    return len(tokens) <= 3 and all(token in vague_tokens for token in tokens)


def _vague_explicit_focus_response(message: str) -> JSONResponse | None:
    payload = _explicit_focus_payload(message)
    if not payload or not _is_vague_focus_payload(payload):
        return None
    return JSONResponse(
        {
            "intent": "chat",
            "action": "none",
            "confidence": 0.99,
            "frontendCommand": "",
            "payload": {},
            "reason": (
                "The requested focus title was too vague to create a useful "
                "background context. Keep the turn in chat so QMeet can resolve "
                "the subject from the conversation or ask one clarifying question."
            ),
        }
    )


def _focus_correction_response(message: str) -> JSONResponse | None:
    text = _clean_focus_text(message, 420)
    patterns = [
        r"^(?:no|actually|wait|sorry|correction)[, ]+(?:i|we)\s+"
        r"(?:want|need|would\s+like)\s+(?:to\s+)?(?:do|start|begin|create|have|make)\s+"
        r"(?:a\s+)?focus(?:\s+session)?\s+(?:on|for|about)\s+(.+)$",
        r"^(?:no|actually|wait|sorry|correction)[, ]+(?:i|we)\s+"
        r"(?:want|need|would\s+like)\s+to\s+focus\s+(?:on|about)\s+(.+)$",
    ]
    raw_candidate = ""
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if match:
            raw_candidate = _clean_focus_text(match.group(1), 260)
            break
    if not raw_candidate:
        return None

    raw_candidate = re.sub(
        r"\s+(?:that\s+|which\s+)?(?:i|we)\s+(?:mentioned|talked\s+about|"
        r"discussed|said)\s+(?:before|earlier|already).*$",
        "",
        raw_candidate,
        flags=re.IGNORECASE,
    ).strip()
    raw_candidate = re.sub(
        r"\s+(?:from|like)\s+(?:before|earlier)$",
        "",
        raw_candidate,
        flags=re.IGNORECASE,
    ).strip()
    if not raw_candidate or _is_vague_focus_payload(raw_candidate):
        return None

    goal = _normalize_goal(raw_candidate)
    if re.match(r"^Get\s+", goal) and re.search(
        r"\b(?:television|tv|laptop|computer|phone|tablet|appliance|furniture|"
        r"vehicle|motorcycle|car|camera|monitor|headphones?|speaker)\b",
        goal,
        flags=re.IGNORECASE,
    ):
        goal = re.sub(r"^Get\s+", "Buy ", goal)
    title = _focus_title(goal)
    mode = _infer_focus_mode(goal)
    canonical_command = f"start a {mode} focus session for {title} with goal to {goal}"
    return JSONResponse(
        {
            "intent": "command",
            "action": "start_focus_session",
            "confidence": 0.995,
            "frontendCommand": canonical_command,
            "payload": {"title": title, "mode": mode, "goal": goal},
            "reason": (
                "The user corrected or expanded an incomplete focus. Start a new "
                "session with the complete subject instead of preserving the vague title."
            ),
        }
    )


def _purchase_focus_repair_response(
    message: str,
    request_payload: dict[str, Any],
) -> JSONResponse | None:
    """Repair an active focus after an ASR or phrasing correction.

    A correction such as "the voice did not pick me up; I meant getting a laptop
    that can do ML well" must replace a wrongly scoped session instead of merely
    adding a fact to it.
    """

    if _active_context() is None and not _client_has_active_session(request_payload):
        return None

    text = _clean_focus_text(message, 520)
    if not text:
        return None

    patterns = [
        r"^(?:no|actually|wait|sorry|correction)[, ]+.*?"
        r"(?:i\s+meant|what\s+i\s+meant\s+was|i\s+was\s+trying\s+to\s+say)\s+(.+)$",
        r"^(?:no|actually|wait|sorry|correction)[, ]+(?:the\s+)?"
        r"(?:focus|project|goal)\s+(?:is|should\s+be|was\s+supposed\s+to\s+be)\s+(.+)$",
        r"^(?:no|actually|wait|sorry|correction)[, ]+(?:this|that|it)\s+"
        r"(?:is|was)\s+(?:really\s+)?(?:about|for)\s+(.+)$",
    ]
    raw_candidate = ""
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.IGNORECASE)
        if match:
            raw_candidate = _clean_focus_text(match.group(1), 300)
            break
    if not raw_candidate:
        return None

    raw_candidate = re.sub(
        r"^(?:help(?:ing)?\s+(?:me|us)\s+(?:with|to)\s+)",
        "",
        raw_candidate,
        flags=re.IGNORECASE,
    ).strip()
    raw_candidate = re.sub(
        r"^(?:getting|buying|purchasing)\s+(?:a\s+)?laptop\s+that\s+can\s+"
        r"(?:do|handle|run)\s+(?:ml|machine\s+learning)(?:\s+tasks?)?(?:\s+well)?$",
        "buying a laptop for machine learning",
        raw_candidate,
        flags=re.IGNORECASE,
    ).strip()
    if not raw_candidate or _is_vague_focus_payload(raw_candidate):
        return None

    goal = _normalize_goal(raw_candidate)
    if not goal:
        return None
    title = _focus_title(goal)
    mode = _infer_focus_mode(goal)
    canonical_command = f"start a {mode} focus session for {title} with goal to {goal}"
    return JSONResponse(
        {
            "intent": "command",
            "action": "start_focus_session",
            "confidence": 0.997,
            "frontendCommand": canonical_command,
            "payload": {"title": title, "mode": mode, "goal": goal},
            "reason": (
                "The user corrected a transcription or scope error. Replace the "
                "mis-scoped active focus with the complete intended objective."
            ),
        }
    )


def _focus_completion_response(context: dict[str, Any]) -> JSONResponse:
    title = str(context.get("title") or "the current focus").strip()
    return JSONResponse(
        {
            "intent": "command",
            "action": "end_focus_with_summary",
            "confidence": 0.995,
            "frontendCommand": "end and summarize focus",
            "payload": {},
            "reason": (
                "Background work context routed natural completion of "
                f"{title} to a normal focus summary. Meeting follow-up tasks are only "
                "created for an explicit meeting wrap-up request."
            ),
        }
    )


def _purchase_search_response(handoff: dict[str, str]) -> JSONResponse:
    query = str(handoff.get("query") or "").strip()
    handoff_action = str(handoff.get("action") or "run_search").strip().casefold()
    if handoff_action == "open_existing":
        return JSONResponse(
            {
                "intent": "command",
                "action": "open_search",
                "confidence": 0.995,
                "frontendCommand": "open search",
                "payload": {"query": query, "reuseExisting": True},
                "reason": handoff.get("reason") or (
                    "The relevant live Search already completed, so QMeet reopened "
                    "the existing Search results instead of running it again."
                ),
            }
        )

    return JSONResponse(
        {
            "intent": "command",
            "action": "run_search",
            "confidence": 0.995,
            "frontendCommand": f"search for {query}",
            "payload": {"query": query},
            "reason": handoff.get("reason") or (
                "Background purchase context routed the user's confirmation to "
                "QMeet's live Search action."
            ),
        }
    )


def _normal_focus_end_response(message: str) -> JSONResponse | None:
    """Route ordinary focus-closing language to the real summary-and-end action.

    A normal close preserves the work as a summary. Explicit phrases such as
    "end focus without a summary" are intentionally left to the existing force-end
    command route.
    """

    context = _active_context()
    if context is None:
        return None

    normalized = re.sub(r"[?!.,;:]+", " ", message.casefold())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return None

    force_end_markers = (
        "anyway",
        "without summary",
        "without a summary",
        "without note",
        "without a note",
        "without saving",
        "do not save",
        "don't save",
        "dont save",
        "skip the summary",
        "discard the summary",
    )
    if any(marker in normalized for marker in force_end_markers):
        return None

    voice_summary_patterns = (
        r"^(?:endless|and with|end with|end the) (?:a )?summary$",
        r"^(?:end|close|finish) (?:it|this|that) with (?:a )?summary$",
    )
    normal_end_patterns = (
        r"^(?:please )?(?:(?:can|could|would|will) you (?:please )?)?"
        r"(?:end|close|finish|stop|wrap up) "
        r"(?:(?:the|my|our|this|that|current|active) )?"
        r"(?:focus|focus session|active session|session)"
        r"(?: (?:now|for me))?$",
        r"^(?:please )?(?:end|close|finish|stop|wrap up) focus$",
    )
    if not any(
        re.fullmatch(pattern, normalized)
        for pattern in (*voice_summary_patterns, *normal_end_patterns)
    ):
        return None

    return _focus_completion_response(context)


def _is_research_context(context: dict[str, Any] | None) -> bool:
    if not isinstance(context, dict):
        return False
    mode = str(context.get("mode") or "").strip().casefold()
    focus_type = str(context.get("focusType") or "").strip().casefold()
    if mode == "research" or focus_type in {
        "research",
        "document",
        "review",
        "presentation",
    }:
        return True
    haystack = " ".join(
        str(context.get(key) or "")
        for key in ("title", "objective", "subject")
    ).casefold()
    return bool(
        re.search(
            r"\b(?:essay|paper|report|research|review|article|sources?|"
            r"literature|history|school assignment)\b",
            haystack,
        )
    )


def _is_research_source_search_request(
    message: str,
    context: dict[str, Any] | None,
) -> bool:
    if not _is_research_context(context):
        return False
    visible = _clean_focus_text(message, 900)
    if not visible:
        return False
    lowered = visible.casefold()
    has_search_action = bool(
        re.search(
            r"\b(?:search(?:es|ing)?|find|look up|lookup|gather|locate|"
            r"pull up|give me|show me)\b",
            lowered,
        )
    )
    has_source_target = bool(
        re.search(
            r"\b(?:sources?|articles?|papers?|studies|citations?|references?|"
            r"links?|peer[ -]?reviewed|academic|scholarly|evidence|websites?)\b",
            lowered,
        )
    )
    explicit_search_phrase = bool(
        re.search(
            r"\b(?:do|run|perform) (?:some |a )?(?:general |web |online )?search",
            lowered,
        )
    )
    return (has_search_action and has_source_target) or (
        explicit_search_phrase and has_source_target
    )


def _build_research_search_query(
    message: str,
    context: dict[str, Any],
) -> str:
    visible = _clean_focus_text(message, 700)
    title = _clean_focus_text(str(context.get("title") or ""), 180)
    objective = _clean_focus_text(str(context.get("objective") or ""), 260)
    subject = _clean_focus_text(str(context.get("subject") or ""), 220)

    focus_parts: list[str] = []
    if subject:
        focus_parts.append(f"subject: {subject}")
    elif title:
        focus_parts.append(f"focus: {title}")
    if objective and objective.casefold() not in {
        title.casefold(),
        subject.casefold(),
    }:
        focus_parts.append(f"objective: {objective}")

    requirements = [
        "Return verifiable sources with exact titles, publishers or authors, dates when available, and direct source links.",
        "Do not invent citations, links, publication details, or claims.",
    ]
    lowered = visible.casefold()
    if re.search(
        r"\b(?:general|not necessarily academic|not academic|nonacademic|web)\b",
        lowered,
    ):
        requirements.append(
            "Include reputable general sources and clearly identify the source type."
        )
    elif re.search(
        r"\b(?:peer[ -]?(?:reviewed|research)|academic|scholarly|journal)\b",
        lowered,
    ):
        requirements.append(
            "Prioritize genuinely peer-reviewed or scholarly sources and clearly label any source that is not peer-reviewed."
        )

    parts = [visible]
    if focus_parts:
        parts.append("Active research context: " + "; ".join(focus_parts) + ".")
    parts.extend(requirements)
    return " ".join(part for part in parts if part).strip()


def _research_search_response(
    message: str,
    context: dict[str, Any],
) -> JSONResponse:
    query = _build_research_search_query(message, context)
    return JSONResponse(
        {
            "intent": "command",
            "action": "run_search",
            "confidence": 0.997,
            "frontendCommand": f"search for {query}",
            "payload": {"query": query},
            "reason": (
                "The user explicitly requested research sources. Route the request "
                "to QMeet's real Search action instead of answering with generic "
                "source suggestions or fabricated citations."
            ),
        }
    )


class BackgroundWorkContextMiddleware:
    """Observe user text before routing and protect natural focus conversation.

    In addition to growing the active context, this boundary can begin a focus from
    durable project language even when the user never says "focus." It remains
    conservative so one-off searches and small requests continue through their
    normal routes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if method not in {"POST", "PUT", "PATCH"} or path not in _OBSERVED_PATHS:
            await self.app(scope, receive, send)
            return

        buffered_messages: list[Message] = []
        body_parts: list[bytes] = []
        body_size = 0

        while True:
            message = await receive()
            buffered_messages.append(message)
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                if isinstance(chunk, bytes):
                    body_size += len(chunk)
                    if body_size <= _MAX_OBSERVED_BODY_BYTES:
                        body_parts.append(chunk)
                if not message.get("more_body", False):
                    break
            elif message.get("type") == "http.disconnect":
                break

        replay_index = 0

        async def replay_receive() -> Message:
            nonlocal replay_index
            if replay_index < len(buffered_messages):
                replay_message = buffered_messages[replay_index]
                replay_index += 1
                return replay_message
            return await receive()

        body = b"".join(body_parts) if body_size <= _MAX_OBSERVED_BODY_BYTES else b""
        content_type = _header_value(scope, b"content-type")
        request_payload = _extract_payload(body, content_type)
        user_message = _extract_message(path, request_payload)

        if path == "/api/command/interpret" and user_message:
            # Scope-changing turns must be handled before observation so a correction
            # does not contaminate the old, mis-scoped context.
            repair = _purchase_focus_repair_response(user_message, request_payload)
            if repair is not None:
                await repair(scope, replay_receive, send)
                return

            correction = _focus_correction_response(user_message)
            if correction is not None:
                await correction(scope, replay_receive, send)
                return

            vague_focus = _vague_explicit_focus_response(user_message)
            if vague_focus is not None:
                await vague_focus(scope, replay_receive, send)
                return

            if _active_context() is None and not _client_has_active_session(request_payload):
                followup_fragment = _contextual_followup_response(user_message)
                if followup_fragment is not None:
                    await followup_fragment(scope, replay_receive, send)
                    return

            implicit_start = _implicit_focus_start_response(
                user_message,
                request_payload,
            )
            if implicit_start is not None:
                await implicit_start(scope, replay_receive, send)
                return

            normal_focus_end = _normal_focus_end_response(user_message)
            if normal_focus_end is not None:
                await normal_focus_end(scope, replay_receive, send)
                return

        if user_message:
            try:
                observe_background_user_message(user_message, source=path)
            except WorkContextError:
                # Background observation must never make the primary request fail.
                pass

        if path == "/api/command/interpret" and user_message:
            # Natural completion of a personal, coding, research, planning, or general
            # focus should archive the focus with a summary. It must not fall through
            # to the meeting wrap-up command, which creates follow-up tasks.
            if _is_natural_focus_completion(user_message):
                context = _active_context()
                if context is not None:
                    response = _focus_completion_response(context)
                    await response(scope, replay_receive, send)
                    return

            context = _active_context()
            if _is_research_source_search_request(user_message, context):
                response = _research_search_response(user_message, context or {})
                await response(scope, replay_receive, send)
                return

            try:
                search_handoff = get_purchase_search_handoff(
                    user_message,
                    consume=True,
                )
            except WorkContextError:
                search_handoff = None
            if search_handoff is not None:
                response = _purchase_search_response(search_handoff)
                await response(scope, replay_receive, send)
                return

            try:
                keep_in_chat = should_keep_focus_message_in_chat(user_message)
            except WorkContextError:
                keep_in_chat = False

            if keep_in_chat:
                response = JSONResponse(
                    {
                        "intent": "chat",
                        "action": "none",
                        "confidence": 1.0,
                        "frontendCommand": "",
                        "payload": {},
                        "reason": (
                            "Active-focus conversation guard kept this natural help or "
                            "progress message in normal chat."
                        ),
                    }
                )
                await response(scope, replay_receive, send)
                return

        await self.app(scope, replay_receive, send)
