from __future__ import annotations

import json
import re
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.work_context import (
    WorkContextError,
    get_background_work_context,
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
    r"renovation|move|moving|job search|certification"
    r")\b",
    flags=re.IGNORECASE,
)
_IMPLICIT_FOCUS_ACTION_RE = re.compile(
    r"\b(?:finish(?:ing)?|complet(?:e|ing)|build(?:ing)?|creat(?:e|ing)|"
    r"develop(?:ing)?|design(?:ing)?|redesign(?:ing)?|prepar(?:e|ing)|"
    r"stud(?:y|ying)|research(?:ing)?|writ(?:e|ing)|plan(?:ning)?|"
    r"organiz(?:e|ing)|fix(?:ing)?|debug(?:ging)?|launch(?:ing)?|"
    r"submit(?:ting)?|apply(?:ing)?|practic(?:e|ing)|learn(?:ing)?|"
    r"set(?:ting)? up|figur(?:e|ing) out|tackl(?:e|ing)|work(?:ing)? on|"
    r"giv(?:e|ing)|buy(?:ing)?|arrang(?:e|ing)|choos(?:e|ing)|get(?:ting)?|"
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
    r"event|party|presentation|proposal|launch|deadline|milestone|prepare)\b",
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
    goal = re.sub(r"^(?:with|on|about)\s+", "", goal, flags=re.IGNORECASE)
    goal = re.sub(r"^(?:a|an|the)\s+", lambda match: match.group(0), goal)
    if not goal:
        return ""

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
    if _IMPLICIT_FOCUS_CODING_RE.search(goal):
        return "coding"
    if _IMPLICIT_FOCUS_MEETING_RE.search(goal):
        return "meeting"
    if _IMPLICIT_FOCUS_RESEARCH_RE.search(goal):
        return "research"
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
    if re.search(r"\b(?:do not|don't|dont|not trying to|not working on)\b", text, flags=re.IGNORECASE):
        return None
    if re.search(r"\b(?:focus|focus session|focusing)\b", text, flags=re.IGNORECASE):
        # The existing structured focus router handles explicit focus wording.
        return None

    patterns: list[tuple[str, int]] = [
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

        if user_message:
            try:
                observe_background_user_message(user_message, source=path)
            except WorkContextError:
                # Background observation must never make the primary request fail.
                pass

        if path == "/api/command/interpret" and user_message:
            implicit_start = _implicit_focus_start_response(
                user_message,
                request_payload,
            )
            if implicit_start is not None:
                await implicit_start(scope, replay_receive, send)
                return

            # Natural completion of a personal, coding, research, planning, or general
            # focus should archive the focus with a summary. It must not fall through
            # to the meeting wrap-up command, which creates follow-up tasks.
            if _is_natural_focus_completion(user_message):
                context = _active_context()
                if context is not None:
                    response = _focus_completion_response(context)
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
