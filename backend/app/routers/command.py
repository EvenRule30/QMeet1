import re
from typing import Any

from fastapi import APIRouter, HTTPException

from app.agent import AgentUserFacingError, interpret_command_intent
from app.schemas import CommandInterpretRequest, CommandInterpretResponse

router = APIRouter(prefix="/api/command", tags=["command"])


MODE_WORDS = r"(?:general|coding|code|development|dev|programming|meeting|meetings|planning|plan|research|personal)"
FOCUS_WORDS = r"(?:focus|focus session|active session|session|focus mode)"


def _collapse_command_text(value: str) -> str:
    """Normalize speech-recognition spacing without changing the user's intent."""
    text = re.sub(r"[?!.,;:]+", " ", value.strip())
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(?:hey\s+)?(?:qmeet|orb|assistant)\s+", "", text, flags=re.IGNORECASE)
    # Speech recognition sometimes produces repeated filler words like "the the".
    text = re.sub(r"\b(the|my|our|current|active)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
    # It also occasionally duplicates the first verb: "end end the coding focus".
    for _ in range(4):
        collapsed = re.sub(r"^(end|stop|finish|clear|close|wrap up)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
        collapsed = re.sub(
            r"^(end|stop|finish|clear|close|wrap up)\s+(?:end|stop|finish|clear|close|wrap up)\b",
            r"\1",
            collapsed,
            flags=re.IGNORECASE,
        )
        if collapsed == text:
            break
        text = collapsed.strip()
    return text.strip()


def _command_response(
    *,
    action: str,
    frontend_command: str,
    confidence: float,
    reason: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "intent": "command",
        "action": action,
        "confidence": confidence,
        "frontendCommand": frontend_command,
        "payload": payload or {},
        "reason": reason,
    }


def _first_match(patterns: list[str], text: str) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def _clean_payload(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).strip(" .,:;?!\"'")


def _mode_from_text(value: str) -> str:
    lowered = value.lower()
    if re.search(r"\b(?:code|coding|development|dev|programming)\b", lowered):
        return "coding"
    if re.search(r"\b(?:meeting|meetings|prep|standup|sync)\b", lowered):
        return "meeting"
    if re.search(r"\b(?:plan|planning|roadmap|strategy)\b", lowered):
        return "planning"
    if re.search(r"\b(?:research|search|investigation|study)\b", lowered):
        return "research"
    if re.search(r"\b(?:personal|personally|life|home|on a personal level)\b", lowered):
        return "personal"
    return "general"


def _is_focus_planning_question(value: str) -> bool:
    return bool(
        re.search(
            r"\b(?:tell\s+me\s+how|how\s+(?:should|do|can)\s+(?:i|we)|can\s+you\s+help|help\s+me\s+(?:accomplish|achieve|do|plan|figure\s+out)|give\s+me\s+(?:a\s+)?plan|make\s+me\s+(?:a\s+)?plan|steps?\s+(?:to|for)|accomplish|achieve)\b",
            value,
            flags=re.IGNORECASE,
        )
    )


def _is_explicit_focus_set_phrase(value: str) -> bool:
    return bool(
        re.search(
            r"^(?:please\s+)?(?:set|change|update|make|switch|rename|retitle|start|begin|create|open|focus|refocus|let(?:'s|\s+us)|lets|i\s+want\s+to|i\s+need\s+to|we\s+should|we\s+need\s+to|we\s+want\s+to)\b",
            value,
            flags=re.IGNORECASE,
        )
    )


def _should_leave_focus_phrase_for_chat(full_phrase: str, payload: str) -> bool:
    if not _is_focus_planning_question(payload):
        return False
    return not _is_explicit_focus_set_phrase(full_phrase)


def _default_focus_title(mode: str) -> str:
    if mode == "coding":
        return "Coding session"
    if mode == "meeting":
        return "Meeting session"
    if mode == "planning":
        return "Planning session"
    if mode == "research":
        return "Research session"
    if mode == "personal":
        return "Personal session"
    return "Focus session"


def _focus_command_intent(message: str) -> dict[str, Any] | None:
    """Catch Phase 12 focus-session commands before the general LLM interpreter.

    This route is the backend command interpreter's structured focus layer. The
    frontend still owns the final exact parse. This keeps fuzzy focus wording
    from falling through to normal chat or being misread as older commands such
    as "end chat".
    """
    text = _collapse_command_text(message)
    if not text:
        return None

    lowered = text.lower()


    focus_to_tasks_patterns = [
        r"^(?:please\s+)?(?:turn|convert|make|create)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|goal)\s+(?:into|to)\s+(?:tasks|task list|action items|next steps|steps|checklist)$",
        r"^(?:please\s+)?(?:make|create|add|generate)\s+(?:tasks|a task list|action items|next steps|steps|a checklist)\s+(?:for|from|based on)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|goal)$",
        r"^(?:please\s+)?(?:break|split)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|goal)\s+(?:into|down into)\s+(?:tasks|steps|next steps|action items)$",
        r"^(?:please\s+)?(?:add|save)\s+(?:tasks|next steps|action items)\s+(?:for|from)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|goal)$",
        r"^(?:please\s+)?(?:turn|convert)\s+(?:it|this|that)\s+(?:into|to)\s+(?:tasks|task list|action items|next steps|steps|checklist)$",
    ]
    if _first_match(focus_to_tasks_patterns, lowered):
        return _command_response(
            action="focus_to_tasks",
            frontend_command="turn focus into tasks",
            confidence=0.98,
            reason="Backend focus interpreter matched a focus-to-tasks command.",
        )

    read_patterns = [
        r"^(?:what(?:'s| is)|what is)\s+(?:the\s+|my\s+|our\s+)?(?:current\s+|active\s+)?(?:focus|focus session|active session)$",
        r"^(?:what am i focused on(?: right now)?|what are we focused on(?: right now)?|what are we focusing on(?: right now)?)$",
        r"^(?:what should i be working on|what am i supposed to be working on|what is my focus right now)$",
        r"^(?:focus status|current focus|active focus|my focus|our focus|active session|session status)$",
        r"^(?:read|show|tell me|display|summarize)\s+(?:the\s+|my\s+|our\s+)?(?:current\s+|active\s+)?(?:focus|focus session|active session)$",
    ]
    if _first_match(read_patterns, lowered):
        return _command_response(
            action="read_focus_session",
            frontend_command="what am I focused on",
            confidence=0.98,
            reason="Backend focus interpreter matched a focus readout command.",
        )

    mode_only_match = re.search(
        rf"^(?:please\s+)?({MODE_WORDS})\s+(?:focus|focus session|session|focus mode)$",
        text,
        flags=re.IGNORECASE,
    )
    if mode_only_match:
        mode = _mode_from_text(mode_only_match.group(1))
        title = _default_focus_title(mode)
        return _command_response(
            action="start_focus_session",
            frontend_command=f"start a {mode} focus session",
            confidence=0.94,
            reason="Backend focus interpreter matched a mode-only focus command.",
            payload={"title": title, "mode": mode},
        )

    end_patterns = [
        rf"^(?:please\s+)?(?:end|stop|clear|close|leave|exit|finish|wrap up)\s+(?:(?:the|my|our|current|active)\s+)*(?:{MODE_WORDS}\s+)?{FOCUS_WORDS}$",
        rf"^(?:please\s+)?(?:end|stop|clear|close|leave|exit|finish|wrap up)\s+(?:(?:the|my|our|current|active|this|that)\s+)*(?:{MODE_WORDS}\s+)?(?:{FOCUS_WORDS}|matter|topic|work|thing)$",
        rf"^(?:please\s+)?(?:i(?:'m| am)|we(?:'re| are))\s+(?:done|finished|complete|through)\s+(?:with\s+)?(?:(?:the|my|our|current|active|this|that)\s+)*(?:{MODE_WORDS}\s+)?(?:{FOCUS_WORDS}|matter|topic|work|thing)$",
        r"^(?:please\s+)?(?:we are|we're|i am|i'm)\s+(?:done|finished|complete|through)\s+(?:with\s+)?(?:this|that|the|current)\s+(?:matter|topic|work|thing)$",
        r"^(?:please\s+)?(?:that|this)\s+(?:focus|session|matter|topic|work|thing)\s+(?:is\s+)?(?:done|finished|complete|over)$",
    ]
    if _first_match(end_patterns, lowered):
        return _command_response(
            action="end_focus_session",
            frontend_command="end focus session",
            confidence=0.98,
            reason="Backend focus interpreter matched an end-focus command.",
        )

    goal_patterns = [
        r"^(?:please\s+)?(?:set|change|update)\s+(?:a\s+|the\s+|my\s+|our\s+)?(?:focus\s+)?goal\s+(?:to|as|on)\s+(.+)$",
        r"^(?:please\s+)?(?:let(?:'s| us)|lets)\s+set\s+(?:a\s+|the\s+|my\s+|our\s+)?(?:focus\s+)?goal\s+(?:to|as|on)\s+(.+)$",
        r"^(?:please\s+)?(?:my|our|the)?\s*goal\s+(?:is|should be|should be to)\s+(.+)$",
        r"^(?:please\s+)?(?:make|set)\s+(?:it|this|the focus)\s+(?:my\s+|our\s+)?goal\s+(?:to|as)\s+(.+)$",
    ]
    match = _first_match(goal_patterns, text)
    if match and match.group(1).strip():
        goal = _clean_payload(match.group(1))
        return _command_response(
            action="update_focus_session",
            frontend_command=f"set my focus goal to {goal}",
            confidence=0.97,
            reason="Backend focus interpreter matched a focus goal update.",
            payload={"goal": goal},
        )

    update_patterns = [
        r"^(?:please\s+)?(?:set|change|update|make|switch)\s+(?:a\s+|the\s+|my\s+|our\s+|current\s+|active\s+)*(?:focus|focus session|active session)\s+(?:to|on|about|around|as)\s+(.+)$",
        r"^(?:please\s+)?(?:focus|refocus)\s+(?:me\s+|us\s+)?(?:on|around|about)\s+(.+)$",
        r"^(?:please\s+)?(?:let(?:'s| us)|lets)\s+focus\s+(?:on|around|about)\s+(.+)$",
        r"^(?:please\s+)?(?:i want to|i need to|we should|we need to|we want to)\s+focus\s+(?:on|around|about)\s+(.+)$",
        r"^(?:please\s+)?(?:my|our|the|current)\s+focus\s+(?:is|should be)\s+(.+)$",
        r"^(?:please\s+)?(?:rename|retitle)\s+(?:the\s+)?(?:focus|focus session|active session)\s+(?:to|as|called|named)\s+(.+)$",
    ]
    match = _first_match(update_patterns, text)
    if match and match.group(1).strip():
        title = _clean_payload(match.group(1))
        if _should_leave_focus_phrase_for_chat(text, title):
            return None
        return _command_response(
            action="update_focus_session",
            frontend_command=f"set current focus on {title}",
            confidence=0.97,
            reason="Backend focus interpreter matched a focus update command.",
            payload={"title": title, "mode": _mode_from_text(title)},
        )

    mode_update_match = re.search(
        r"^(?:please\s+)?(?:set|change|update)\s+(?:the\s+)?(?:focus|session)\s+mode\s+(?:to|as)\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if mode_update_match and mode_update_match.group(1).strip():
        mode_text = _clean_payload(mode_update_match.group(1))
        return _command_response(
            action="update_focus_session",
            frontend_command=f"set focus mode to {mode_text}",
            confidence=0.94,
            reason="Backend focus interpreter matched a focus mode update.",
            payload={"mode": mode_text},
        )

    start_patterns = [
        rf"^(?:please\s+)?(?:start|begin|create|open)\s+(?:a\s+|the\s+)?(?:{MODE_WORDS}\s+)?(?:focus session|focus|session|focus mode)(?:\s+(?:for|on|about|around|called|named|to|with(?:\s+the)?\s+goal\s+(?:of|to))\s+(.+))?$",
        r"^(?:please\s+)?(?:start|begin|create|open)\s+(?:a\s+|the\s+)?(?:focus session|focus|session|focus mode)\s+(?:in|as)\s+.+?\s+mode(?:\s+(?:for|on|about|around|to|with(?:\s+the)?\s+goal\s+(?:of|to))\s+(.+))?$",
        r"^(?:please\s+)?(?:start|begin)\s+(?:me\s+|us\s+)?(?:focusing|working)\s+(?:on|around|about)\s+(.+)$",
        r"^(?:i(?:'m| am)|we(?:'re| are))\s+(?:currently\s+)?(?:working|focusing)\s+(?:on|about)\s+(.+)$",
        rf"^(?:please\s+)?(?:switch|change)\s+(?:me\s+)?to\s+(?:{MODE_WORDS})\s+mode$",
    ]
    if _first_match(start_patterns, text):
        if _should_leave_focus_phrase_for_chat(text, text):
            return None
        return _command_response(
            action="start_focus_session",
            frontend_command=text,
            confidence=0.96,
            reason="Backend focus interpreter matched a start-focus command.",
        )

    return None


@router.post("/interpret", response_model=CommandInterpretResponse)
async def command_interpret(req: CommandInterpretRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    focus_intent = _focus_command_intent(message)
    if focus_intent is not None:
        return CommandInterpretResponse(**focus_intent)

    try:
        intent = await interpret_command_intent(message)
        return CommandInterpretResponse(**intent)
    except AgentUserFacingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet command interpreter hit an unexpected error.",
        )
