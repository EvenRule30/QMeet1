import re
from typing import Any

from fastapi import APIRouter, HTTPException

from app.agent import AgentUserFacingError, interpret_command_intent
from app.schemas import CommandInterpretRequest, CommandInterpretResponse
from app.qmeet_orchestrator import interpret_qmeet_orchestrator

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

def _active_session_title_from_context(client_context: dict[str, Any] | None) -> str:
    if not isinstance(client_context, dict):
        return ""
    memory_state = client_context.get("memoryState")
    if not isinstance(memory_state, dict):
        return ""
    active_session = memory_state.get("activeSession")
    if not isinstance(active_session, dict):
        return ""
    title = active_session.get("title")
    return title.strip() if isinstance(title, str) else ""

def _is_active_focus_work_help(lowered: str) -> bool:
    patterns = [
        r"\bwhat\s+(?:do|should|can)\s+i\s+do\s+(?:now|next)\b",
        r"\bwhat\s+can\s+i\s+do\s+(?:with\s+(?:it|this|that)|now|next)\b",
        r"\bnow\s+what\b",
        r"\bwhat\s+more\s+do\s+you\s+need\s+to\s+know\b",
        r"\bwhat\s+do\s+you\s+need\s+(?:to\s+know|from\s+me)\b",
        r"\b(?:can|could|will|would)\s+you\s+help\s+me\s+(?:with|do|write|fix|debug|finish|complete|get|getting|build|make)",
        r"\b(?:i\s+)?(?:just\s+)?(?:want|need)\s+help\s+(?:with|doing|writing|fixing|debugging|finishing|getting|building|making)",
        r"\bi\s+(?:do\s+not|don'?t)\s+like\s+those\s+tasks\b",
        r"\bhelp\s+me\s+(?:do|write|fix|debug|finish|complete|build|make|understand)\b",
    ]
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)

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

def _ui_shortcut_intent(message: str) -> dict[str, Any] | None:
    """Catch UI wording that the general interpreter tends to misread."""
    text = _collapse_command_text(message)
    lowered = text.lower()
    if not lowered:
        return None
    focus_menu_patterns = [
        r"^(?:please\s+)?(?:show|open|bring up|pull up|display)\s+(?:the\s+|my\s+)?(?:focus|current focus|active focus|focus session)\s+(?:menu|panel|controls?|screen)$",
        r"^(?:please\s+)?(?:show|open|bring up|pull up|display)\s+(?:the\s+)?(?:focus menu|focus panel|focus controls)$",
        r"^(?:please\s+)?(?:focus menu|focus panel|focus controls)$",
    ]
    if _first_match(focus_menu_patterns, lowered):
        return _command_response(
            action="open_memory",
            frontend_command="open memory",
            confidence=0.98,
            reason="Backend UI shortcut mapped focus menu wording to the Memory panel.",
        )
    return None


def _task_completion_intent(message: str) -> dict[str, Any] | None:
    """Catch natural task completion updates before guide/focus/note routing."""
    text = _collapse_command_text(message)
    lowered = text.lower()
    if not lowered:
        return None
    ordinal_patterns = [
        r"^(?:please\s+)?(?:i|we)\s+(?:did|finished|completed|complete|finished up|got through|handled)\s+(?:the\s+)?((?:first|last|latest|most recent)\s+(?:\d+|one|two|couple|both|three|few|four|five|six|seven|eight|nine|ten)|both|all|everything|tasks?\s+\d+(?:\s*(?:,|and)\s*(?:tasks?\s*)?\d+)*)\s+(?:tasks?|steps?|items?|things?)?$",
        r"^(?:please\s+)?(?:i|we)\s+(?:am|are|'m|'re)?\s*(?:done|finished|complete|completed|through)\s+(?:with\s+)?(?:the\s+)?((?:first|last|latest|most recent)\s+(?:\d+|one|two|couple|both|three|few|four|five|six|seven|eight|nine|ten)|both|all|everything|tasks?\s+\d+(?:\s*(?:,|and)\s*(?:tasks?\s*)?\d+)*)\s+(?:tasks?|steps?|items?|things?)?$",
        r"^(?:please\s+)?(?:complete|finish|mark|set)\s+(?:the\s+)?((?:first|last|latest|most recent)\s+(?:\d+|one|two|couple|both|three|few|four|five|six|seven|eight|nine|ten)|both|all|everything|tasks?\s+\d+(?:\s*(?:,|and)\s*(?:tasks?\s*)?\d+)*)\s+(?:tasks?|steps?|items?|things?)?(?:\s+(?:as\s+)?(?:done|complete|completed|finished))?$",
        r"^(?:please\s+)?(?:tasks?|steps?|items?)\s+((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s*(?:,|and)\s*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten))*)\s+(?:are\s+)?(?:done|complete|completed|finished)$",
        r"^(?:please\s+)?(?:complete|finish|mark|set)\s+(?:tasks?|steps?|items?)\s+((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s*(?:,|and)\s*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten))*)(?:\s+(?:as\s+)?(?:done|complete|completed|finished))?$",
        r"^(?:please\s+)?(?:i|we)\s+(?:did|finished|completed|got through|handled)\s+(?:number\s+)?((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s*(?:,|and)\s*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten))*)\s+(?:tasks?|steps?|items?|things?)?$",
        r"^(?:please\s+)?(?:i|we)\s+(?:did|finished|completed|got through|handled)\s+(?:the\s+)?((?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)(?:\s*(?:,|and)\s*(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth))*)\s+(?:tasks?|steps?|items?|things?)?$",
    ]
    match = _first_match(ordinal_patterns, lowered)
    if match and match.group(1).strip():
        payload = _clean_payload(match.group(1))
        return _command_response(
            action="mark_task_done",
            frontend_command=f"complete {payload} tasks",
            confidence=0.98,
            reason="Backend task interpreter matched a natural multi-task completion update.",
            payload={"taskLookup": payload},
        )
    direct_patterns = [
        r"^(?:please\s+)?(?:mark|set|complete|finish)\s+(?:the\s+)?(?:task\s+)?(?:called|named|about)?\s*(.+?)\s+(?:as\s+)?(?:done|complete|completed|finished)$",
        r"^(?:please\s+)?(?:i|we)\s+(?:did|finished|completed|got through|handled)\s+(?:the\s+)?(?:task\s+)?(?:called|named|about)?\s*(.+)$",
    ]
    match = _first_match(direct_patterns, text)
    if match and match.group(1).strip():
        payload = _clean_payload(match.group(1))
        return _command_response(
            action="mark_task_done",
            frontend_command=f"mark task {payload} done",
            confidence=0.94,
            reason="Backend task interpreter matched a task completion update.",
            payload={"taskLookup": payload},
        )
    return None

def _qmeet_guide_intent(message: str, client_context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Route broad QMeet help/capability questions into the local bite-sized guide."""
    text = _collapse_command_text(message)
    lowered = text.lower()
    if not lowered:
        return None

    if _active_session_title_from_context(client_context) and _is_active_focus_work_help(lowered):
        return None
    help_patterns = [
        r"\bwhat\s+can\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+do\b",
        r"\bwhat\s+(?:are\s+you|is\s+q\s*meet|is\s+qmeet|is\s+the\s+orb)\s+(?:able\s+to\s+do|capable\s+of|for)\b",
        r"\bwhat\s+(?:can|could|do)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+(?:help\s+me\s+with|help\s+with|do\s+for\s+me)\b",
        r"\bhow\s+(?:are|do)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+(?:able\s+to\s+help|able\s+to\s+do|work|operate)\b",
        r"\bwhat\s+(?:can|should)\s+i\s+say\b",
        r"\bhow\s+do\s+i\s+use\s+(?:this|q\s*meet|qmeet|the\s+orb)\b",
        r"\bwhat\s+(?:is|are)\s+(?:a\s+|the\s+)?(?:focus|focus\s+session|memory|visual\s+context|recap|meeting\s+prep)\b",
        r"\bwhat\s+can\s+i\s+do\s+(?:now|next|with\s+it|with\s+this|with\s+that)\b",
        r"\bwhat\s+should\s+i\s+do\s+(?:now|next)\b",
        r"\bnow\s+what\b",
        r"\bwhat\s+are\s+my\s+options\b",
        r"\bwhat\s+was\s+that\s+(?:menu|panel|screen|thing)\b",
        r"\bwhat\s+(?:menu|panel|screen)\s+(?:appeared|opened|showed\s+up)\b",
        r"\bhow\s+(?:do|to)\s+i\s+open\s+(?:it|that|this)\s+again\b",
        r"\bcan\s+i\s+(?:click|tap|press)\s+(?:on\s+)?(?:these|this|any\s+(?:one\s+)?of\s+these|one\s+of\s+these|the\s+buttons?)\b",
        r"\b(?:can|could|would)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+(?:make|create|build|help\s+me\s+(?:make|create|build))\s+(?:me\s+)?(?:a\s+)?(?:schedule|agenda|day\s+plan|plan)\b",
        r"\b(?:i\s+need|help\s+me)\s+(?:a\s+)?(?:schedule|agenda|day\s+plan)\b",
        r"\b(?:help|guide|teach)\s+me\s+(?:with|through|on)\s+",
        r"\b(?:examples?|sample commands?)\s+(?:for|of)\s+",
        r"\bwhat\s+(?:tools|features|capabilities)\s+(?:do|does)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+have\b",
        r"\bwhat\s+local\s+(?:tools|commands)\s+(?:do|does)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+have\b",
    ]
    if not _first_match(help_patterns, lowered):
        return None
    topic = "overview"
    if re.search(
        r"\b(?:what\s+can\s+i\s+do\s+(?:now|next|with\s+it|with\s+this|with\s+that)|what\s+should\s+i\s+do\s+(?:now|next)|now\s+what|what\s+are\s+my\s+options|can\s+i\s+(?:click|tap|press))\b",
        lowered,
        flags=re.IGNORECASE,
    ):
        topic = "context"
    elif re.search(
        r"\b(?:what\s+was\s+that\s+(?:menu|panel|screen|thing)|what\s+(?:menu|panel|screen)\s+(?:appeared|opened|showed\s+up)|how\s+(?:do|to)\s+i\s+open\s+(?:it|that|this)\s+again)\b",
        lowered,
        flags=re.IGNORECASE,
    ):
        topic = "screen"
    topic_patterns = [
        ("meetings", r"\b(?:meeting|meetings|meet|event prep|wrap up|follow up|follow-up)\b"),
        ("calendar", r"\b(?:calendar|schedule|agenda|event|events|google calendar|appointment|appointments)\b"),
        ("visual", r"\b(?:camera|webcam|visual|vision|image|images|picture|pictures|photo|photos|snapshot|screenshot|upload|saw|see|looking at)\b"),
        ("focus", r"\b(?:focus|session|goal|goals|current work|working on|preparation block|prep block)\b"),
        ("tasks", r"\b(?:task|tasks|to-do|todo|checklist|steps)\b"),
        ("notes", r"\b(?:note|notes|save note|meeting notes)\b"),
        ("recap", r"\b(?:recap|summary|summarize|history|recent work|what changed|worked on)\b"),
        ("memory", r"\b(?:memory|remember|stored|context|recent actions)\b"),
        ("search", r"\b(?:search|web|look up|lookup|internet)\b"),
        ("voice", r"\b(?:voice|speech|speak|mute|unmute|listen|heard|transcript)\b"),
        ("ui", r"\b(?:ui|interface|menu|panel|settings|status|chat log|chatbox|orb|button|home|click|tap)\b"),
    ]
    if topic == "overview":
        for candidate, pattern in topic_patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                topic = candidate
                break
    if topic == "context":
        command = "what can I do now with it"
    elif topic == "screen":
        command = "what was that menu"
    else:
        command = "what can you do" if topic == "overview" else f"help with {topic}"
    return _command_response(
        action="qmeet_guide",
        frontend_command=command,
        confidence=0.95,
        reason="Backend guide router matched a QMeet capability/help question.",
        payload={"topic": topic},
    )

def _ad_hoc_preparation_focus_intent(message: str) -> dict[str, Any] | None:
    """Create a meeting-prep focus from natural appointment-prep phrasing."""
    text = _collapse_command_text(message)
    lowered = text.lower()
    if not lowered:
        return None
    generic_patterns = [
        r"^(?:yes\s+|yeah\s+|yep\s+|sure\s+|ok(?:ay)?\s+)?(?:please\s+)?(?:start|begin|create|open)\s+(?:that\s+|the\s+|my\s+)?(?:focus\s+)?(?:preparation|prep)\s+(?:block|focus|session)$",
        r"^(?:yes\s+|yeah\s+|yep\s+|sure\s+|ok(?:ay)?\s+)?(?:you\s+can\s+)?(?:start|begin|create|open)\s+(?:that\s+|the\s+|my\s+)?(?:focus\s+)?(?:preparation|prep)\s+(?:block|focus|session)$",
    ]
    if _first_match(generic_patterns, lowered):
        return _command_response(
            action="start_ad_hoc_prep_focus",
            frontend_command="start a meeting focus session for preparation block with goal to prepare for the upcoming appointment or meeting",
            confidence=0.94,
            reason="Backend prep-focus router matched a natural focus-preparation-block request.",
        )
    has_prep = bool(
        re.search(
            r"\b(?:need|needs|want|wants|have|has|should|must)\s+to\s+(?:prepare|prep|get\s+ready)|\b(?:prepare|prep|get\s+ready)\s+(?:for|before)\b",
            lowered,
            flags=re.IGNORECASE,
        )
    )
    event_match = re.search(r"\b(appointment|meeting|event|call)\b", lowered, flags=re.IGNORECASE)
    if not has_prep or not event_match:
        return None
    time_match = re.search(r"\b(?:at|around|by|before)\s+((?:\d{1,2}:\d{2}|\d{1,2}\s+\d{2}|\d{1,2})\s*(?:a\s*\.?\s*m\.?|p\s*\.?\s*m\.?|am|pm)?)\b", text, flags=re.IGNORECASE)
    day_match = re.search(r"\b(today|tomorrow)\b", lowered, flags=re.IGNORECASE)
    event_word = event_match.group(1).lower()
    time_text = _clean_payload(time_match.group(1)) if time_match else ""
    time_text = re.sub(r"^(\d{1,2})\s+(\d{2})\b", r"\1:\2", time_text)
    time_text = re.sub(r"\bp\s*\.?\s*m\.?\b", "PM", time_text, flags=re.IGNORECASE)
    time_text = re.sub(r"\ba\s*\.?\s*m\.?\b", "AM", time_text, flags=re.IGNORECASE)
    day_text = day_match.group(1).lower() if day_match else ""
    title = _clean_payload(" ".join(part for part in [time_text, day_text, event_word] if part)) or f"{event_word} preparation"
    goal = f"prepare for the {event_word}"
    if time_text:
        goal += f" at {time_text}"
    if day_text:
        goal += f" {day_text}"
    goal += ". Review details, gather notes, prepare questions, and identify next steps."
    return _command_response(
        action="start_ad_hoc_prep_focus",
        frontend_command=f"start a meeting focus session for {title} with goal to {goal}",
        confidence=0.93,
        reason="Backend prep-focus router matched a natural appointment/meeting prep phrase.",
        payload={"title": title, "mode": "meeting", "goal": goal},
    )

def _calendar_focus_intent(message: str) -> dict[str, Any] | None:
    """Catch calendar-to-focus prep/task commands before the general interpreter."""
    text = _collapse_command_text(message)
    if not text:
        return None
    lowered = text.lower()
    patterns = [
        r"^(?:please\s+)?(?:prepare|prep)\s+(?:me\s+)?(?:for\s+)?(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$",
        r"^(?:please\s+)?(?:start|begin|create|open)\s+(?:a\s+)?(?:focus|focus\s+session|meeting\s+prep\s+focus|prep\s+session)\s+(?:for|from|based\s+on)\s+(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$",
        r"^(?:please\s+)?(?:what\s+should\s+i\s+work\s+on|what\s+should\s+i\s+prepare|what\s+do\s+i\s+need\s+to\s+prepare)\s+(?:before|for)\s+(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$",
        r"^(?:please\s+)?(?:summarize|review|check)\s+(?:my\s+)?(?:schedule|calendar|agenda)\s+and\s+(?:focus\s+)?(?:priorities|priority|prep|preparation)$",
        r"^(?:please\s+)?(?:calendar|meeting|event)\s+(?:focus|prep|preparation)$",
        r"^(?:please\s+)?(?:focus|prep|prepare)\s+(?:for\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$",
        r"^(?:please\s+)?(?:make|create|add|generate|build)\s+(?:prep|preparation|meeting\s+prep|calendar\s+prep)?\s*tasks?\s+(?:for|from|based\s+on)\s+(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$",
        r"^(?:please\s+)?(?:turn|convert|break\s+down)\s+(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)\s+(?:into|in\s+to)\s+(?:prep\s+)?tasks?$",
        r"^(?:please\s+)?(?:next|upcoming)\s+(?:meeting|event|calendar\s+event|appointment|call)\s+(?:prep\s+)?tasks?$",
    ]
    if _first_match(patterns, lowered):
        return _command_response(
            action="prepare_calendar_focus",
            frontend_command="prepare me for my next meeting",
            confidence=0.98,
            reason="Backend calendar-focus interpreter matched a next-event prep/task command.",
        )

    return None

def _meeting_wrapup_intent(message: str) -> dict[str, Any] | None:
    """Catch Phase 16C current-meeting wrap-up and follow-up commands."""
    text = _collapse_command_text(message)
    if not text:
        return None
    lowered = text.lower()
    wrap_patterns = [
        r"^(?:please\s+)?(?:wrap\s+up|close\s+out|finish|end)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|meeting\s+prep|call|appointment)(?:\s+(?:with|and\s+save|and\s+write)\s+(?:a\s+)?(?:summary|recap|note|notes))?$",
        r"^(?:please\s+)?(?:end|finish|wrap\s+up|close)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment)\s+(?:with\s+)?(?:a\s+)?(?:summary|recap|note|notes)$",
        r"^(?:please\s+)?(?:summarize|recap|save\s+(?:a\s+)?summary\s+of|save)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment)\s+(?:and\s+)?(?:end|finish|close|wrap\s+up)(?:\s+it)?$",
        r"^(?:please\s+)?(?:save\s+(?:a\s+)?meeting\s+(?:summary|recap|note|notes)\s+and\s+end|save\s+and\s+end\s+(?:the\s+)?meeting)$",
        r"^(?:please\s+)?(?:meeting|call|appointment)\s+(?:wrap\s+up|closeout|close\s+out)$",
    ]
    if _first_match(wrap_patterns, lowered):
        return _command_response(
            action="wrap_up_meeting_focus",
            frontend_command="wrap up this meeting",
            confidence=0.98,
            reason="Backend meeting wrap-up interpreter matched a summary-and-end command.",
        )
    follow_up_patterns = [
        r"^(?:please\s+)?(?:create|make|add|generate|build|capture|save)\s+(?:meeting\s+)?(?:follow\s*-?\s*up|followup|action)\s+(?:tasks|task\s+list|items|item|actions|next\s+steps|steps)\s+(?:for|from|based\s+on)?\s*(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment|focus|session)?$",
        r"^(?:please\s+)?(?:turn|convert|break\s+down)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment)\s+(?:into|in\s+to)\s+(?:follow\s*-?\s*up\s+)?(?:tasks|task\s+list|action\s+items|next\s+steps|steps|checklist)$",
        r"^(?:please\s+)?(?:meeting|call|appointment)\s+(?:follow\s*-?\s*up|followup|action)\s+(?:tasks|items|next\s+steps)$",
        r"^(?:please\s+)?(?:what\s+are|show|list|create)\s+(?:the\s+)?(?:follow\s*-?\s*ups|followups|action\s+items|next\s+steps)\s+(?:from|for)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|call|appointment)$",
    ]
    if _first_match(follow_up_patterns, lowered):
        return _command_response(
            action="create_meeting_follow_up_tasks",
            frontend_command="create follow-up tasks from this meeting",
            confidence=0.98,
            reason="Backend meeting wrap-up interpreter matched a follow-up task command.",
        )
    save_summary_patterns = [
        r"^(?:please\s+)?(?:save|store|remember|write)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|call|appointment)\s+(?:as|to|in)\s+(?:a\s+)?(?:note|notes|memory|summary)$",
        r"^(?:please\s+)?(?:save|store|remember|write)\s+(?:a\s+)?(?:meeting\s+)?(?:summary|recap|note|notes)\s+(?:of|for)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|call|appointment)?$",
        r"^(?:please\s+)?(?:save|write)\s+(?:meeting\s+)?notes$",
    ]
    if _first_match(save_summary_patterns, lowered):
        return _command_response(
            action="save_meeting_summary",
            frontend_command="save meeting notes",
            confidence=0.96,
            reason="Backend meeting wrap-up interpreter matched a save-meeting-notes command.",
        )
    summarize_patterns = [
        r"^(?:please\s+)?(?:summarize|recap|review)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment)$",
        r"^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:a\s+)?(?:meeting|call|appointment)\s+(?:summary|recap|review)$",
    ]
    if _first_match(summarize_patterns, lowered):
        return _command_response(
            action="summarize_meeting_focus",
            frontend_command="summarize this meeting",
            confidence=0.95,
            reason="Backend meeting wrap-up interpreter matched a summarize-current-meeting command.",
        )
    return None

def _visual_context_intent(message: str) -> dict[str, Any] | None:
    """Catch Phase 14 manual visual-context commands before the general interpreter."""
    text = _collapse_command_text(message)
    if not text:
        return None

    lowered = text.lower()
    link_focus_patterns = [
        r"^(?:please\s+)?(?:link|attach|pin|connect|save|add)\s+(?:the\s+|this\s+|my\s+|our\s+)?(?:last|latest|current|most\s+recent)?\s*(?:visual\s+)?(?:observation|visual\s+context|visual\s+memory|camera\s+observation|camera\s+memory|thing\s+(?:i|we)\s+saw|what\s+(?:i|we)\s+saw|what\s+you\s+saw)\s+(?:to|with|into|under|for)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$",
        r"^(?:please\s+)?(?:save|pin|attach|link)\s+(?:what\s+)?(?:you\s+)?(?:last\s+)?(?:saw|observed|captured)\s+(?:to|with|into|under|for)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$",
        r"^(?:please\s+)?(?:use|keep)\s+(?:the\s+|this\s+)?(?:visual\s+context|camera\s+observation|last\s+observation)\s+(?:for|with|under)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$",
    ]
    if _first_match(link_focus_patterns, lowered):
        return _command_response(
            action="link_visual_to_focus",
            frontend_command="save this visual context to my focus",
            confidence=0.98,
            reason="Backend visual-focus interpreter matched a link visual-to-focus command.",
        )
    focus_visual_patterns = [
        r"^(?:please\s+)?(?:show|read|list|display|summarize|recap|review)\s+(?:the\s+|my\s+|our\s+)?(?:visuals|visual\s+observations|visual\s+context|camera\s+observations|camera\s+context)\s+(?:for|linked\s+to|related\s+to|under|with)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$",
        r"^(?:please\s+)?(?:what\s+)?(?:visual\s+context|visuals|camera\s+context|things\s+(?:i|we)\s+saw)\s+(?:is|are)?\s*(?:linked\s+to|related\s+to|saved\s+for|under)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$",
        r"^(?:please\s+)?(?:show|read|list|summarize)?\s*(?:focus\s+visuals|focus\s+visual\s+context|focus\s+camera\s+context)$",
        r"^(?:please\s+)?(?:what\s+did\s+(?:you|qmeet)\s+see|what\s+was\s+seen)\s+(?:for|during|in)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$",
    ]
    if _first_match(focus_visual_patterns, lowered):
        return _command_response(
            action="read_focus_visuals",
            frontend_command="show visuals for my focus",
            confidence=0.98,
            reason="Backend visual-focus interpreter matched a read focus-linked visual command.",
        )
    clear_patterns = [
        r"^(?:please\s+)?(?:clear|reset|wipe|forget|delete)\s+(?:the\s+|my\s+|all\s+)?(?:visual\s+context|visual\s+memory|visual\s+observations|camera\s+context|camera\s+memory)$",
        r"^(?:please\s+)?(?:clear|reset|wipe|forget|delete)\s+(?:everything\s+)?(?:i|we)\s+(?:saw|looked\s+at|were\s+looking\s+at)$",
    ]
    if _first_match(clear_patterns, lowered):
        return _command_response(
            action="clear_visual_context",
            frontend_command="clear visual context",
            confidence=0.98,
            reason="Backend visual-context interpreter matched a clear command.",
        )
    delete_last_patterns = [
        r"^(?:please\s+)?(?:delete|remove|forget|erase)\s+(?:the\s+)?(?:last|latest|most\s+recent)\s+(?:visual\s+)?(?:observation|visual\s+note|visual\s+memory|camera\s+observation)$",
        r"^(?:please\s+)?(?:delete|remove|forget|erase)\s+(?:what\s+)?(?:i|we)\s+(?:just\s+)?(?:saw|looked\s+at)$",
    ]
    if _first_match(delete_last_patterns, lowered):
        return _command_response(
            action="delete_last_visual_observation",
            frontend_command="delete last visual observation",
            confidence=0.98,
            reason="Backend visual-context interpreter matched a delete-last command.",
        )
    summarize_patterns = [
        r"^(?:please\s+)?(?:summarize|recap|review)\s+(?:the\s+|my\s+|our\s+)?(?:visual\s+context|visual\s+memory|visual\s+observations|camera\s+context|camera\s+memory)$",
        r"^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:a\s+)?(?:visual|camera)\s+(?:summary|recap|review)$",
    ]
    if _first_match(summarize_patterns, lowered):
        return _command_response(
            action="summarize_visual_context",
            frontend_command="summarize visual context",
            confidence=0.98,
            reason="Backend visual-context interpreter matched a visual summary command.",
        )
    history_patterns = [
        r"^(?:please\s+)?(?:show|read|list|display|open)\s+(?:the\s+|my\s+|our\s+)?(?:recent\s+|saved\s+|all\s+)?(?:visual\s+observations|visual\s+history|camera\s+observations|camera\s+history|things\s+(?:i|we)\s+saw)$",
        r"^(?:please\s+)?(?:what\s+(?:have|did)\s+(?:i|we)\s+(?:seen|looked\s+at|saved\s+visually))$",
        r"^(?:visual\s+history|camera\s+history|visual\s+observations)$",
    ]
    if _first_match(history_patterns, lowered):
        return _command_response(
            action="read_visual_history",
            frontend_command="show visual observations",
            confidence=0.98,
            reason="Backend visual-context interpreter matched a visual history command.",
        )
    last_patterns = [
        r"^(?:please\s+)?(?:what\s+(?:was|is)|show|read|tell\s+me|display)\s+(?:the\s+|my\s+|our\s+)?(?:last|latest|most\s+recent)\s+(?:visual\s+observation|visual\s+note|visual\s+memory|camera\s+observation|camera\s+memory|thing\s+(?:i|we)\s+saw)$",
        r"^(?:please\s+)?(?:what\s+(?:did|do)\s+(?:i|we)\s+(?:last\s+)?(?:see|look\s+at)|what\s+(?:am|are)\s+(?:i|we)\s+looking\s+at|what\s+did\s+you\s+last\s+see|what\s+was\s+the\s+last\s+thing\s+you\s+saw)$",
        r"^(?:please\s+)?(?:last|latest)\s+(?:visual|camera)\s+(?:observation|memory|note)$",
    ]
    if _first_match(last_patterns, lowered):
        return _command_response(
            action="read_last_visual_observation",
            frontend_command="what was the last visual observation",
            confidence=0.98,
            reason="Backend visual-context interpreter matched a last-visual-observation command.",
        )
    read_patterns = [
        r"^(?:please\s+)?(?:what\s+(?:was|is)|show|read|tell\s+me|display|open)\s+(?:the\s+|my\s+|our\s+)?(?:current\s+)?(?:visual\s+context|visual\s+memory|camera\s+context|camera\s+memory)$",
        r"^(?:visual\s+context|visual\s+memory|camera\s+context)$",
    ]
    if _first_match(read_patterns, lowered):
        return _command_response(
            action="read_visual_context",
            frontend_command="show visual context",
            confidence=0.98,
            reason="Backend visual-context interpreter matched a read command.",
        )
    observation_patterns = [
        r"^(?:please\s+)?(?:note|remember|save|record|store)\s+(?:visually|as\s+(?:a\s+)?visual\s+(?:note|observation)|in\s+visual\s+context)\s+(?:that\s+)?(.+)$",
        r"^(?:please\s+)?(?:visual\s+(?:note|observation)|visual\s+memory)\s+(?:that\s+)?(.+)$",
        r"^(?:please\s+)?(?:add|save|record|store)\s+(?:a\s+)?(?:manual\s+)?visual\s+(?:observation|note)\s+(?:that\s+)?(.+)$",
        r"^(?:please\s+)?(?:i(?:'m|\s+am)|we(?:'re|\s+are))\s+(?:looking\s+at|seeing|viewing)\s+(.+)$",
        r"^(?:please\s+)?(?:the\s+camera\s+should\s+remember|remember\s+from\s+the\s+camera)\s+(?:that\s+)?(.+)$",
    ]
    match = _first_match(observation_patterns, text)
    if match and match.group(1).strip():
        payload = _clean_payload(match.group(1))
        return _command_response(
            action="create_visual_observation",
            frontend_command=f"note visually that {payload}",
            confidence=0.97,
            reason="Backend visual-context interpreter matched a manual visual observation command.",
            payload={"summary": payload},
        )
    return None


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
    force_end_patterns = [
        r"^(?:please\s+)?(?:end|finish|stop|close|clear|discard)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|focus mode)\s+(?:anyway|without\s+(?:saving|a\s+summary|summary|a\s+note|note))$",
        r"^(?:please\s+)?(?:end|finish|stop|close|clear|discard)\s+(?:anyway|without\s+(?:saving|a\s+summary|summary|a\s+note|note))$",
        r"^(?:please\s+)?(?:end|finish|stop|close|clear|discard)\s+(?:it|this|that)\s+(?:anyway|without\s+(?:saving|a\s+summary|summary|a\s+note|note))$",
        r"^(?:please\s+)?(?:do\s+not|don't)\s+save\s+(?:a\s+)?(?:summary|note)\s+(?:and\s+)?(?:end|finish|stop|close)\s+(?:the\s+)?(?:focus|session)?$",
        r"^(?:please\s+)?(?:skip|discard)\s+(?:the\s+)?(?:summary|note)\s+(?:and\s+)?(?:end|finish|stop|close)\s+(?:the\s+)?(?:focus|session)?$",
    ]
    if _first_match(force_end_patterns, lowered):
        return _command_response(
            action="end_focus_session",
            frontend_command="end focus anyway",
            confidence=0.99,
            reason="Backend focus interpreter matched an explicit force-end command.",
        )
    focus_to_tasks_patterns = [
        r"^(?:please\s+)?(?:turn|convert|make|create)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|goal)\s+(?:into|to)\s+(?:tasks|task list|action items|next steps|steps|checklist)$",
        r"^(?:please\s+)?(?:make|create|add|generate)\s+(?:tasks|a task list|action items|next steps|steps|a checklist)\s+(?:for|from|based on)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|goal)$",
        r"^(?:please\s+)?(?:break|split)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|goal)\s+(?:into|down into)\s+(?:tasks|steps|next steps|action items)$",
        r"^(?:can|could|would)\s+(?:you|we)\s+(?:please\s+)?(?:break|split|turn|convert)\s+(?:it|this|that|these|the work)?\s*(?:into|down into|to)\s+(?:(?:a\s+)?(?:task list|checklist)|tasks|steps|next steps|action items)$",
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

    end_with_summary_patterns = [
        r"^(?:please\s+)?(?:end|finish|wrap up|close)\s+(?:with|and\s+save|and\s+write)\s+(?:a\s+)?(?:summary|recap|note)$",
        r"^(?:please\s+)?(?:end|finish|wrap up|close)\s+(?:and\s+)?(?:summarize|recap|save\s+(?:a\s+)?summary|save)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|matter|topic|work|thing)?$",
        r"^(?:please\s+)?(?:summarize|recap|save\s+(?:a\s+)?summary\s+of|save)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session)\s+(?:and\s+)?(?:end|finish|close|wrap up)(?:\s+it)?$",
        r"^(?:please\s+)?(?:summarize|recap)\s+(?:and\s+)?(?:end|finish|close|wrap up)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session)$",
        r"^(?:please\s+)?(?:end|finish|wrap up|close)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session)\s+(?:with\s+)?(?:a\s+)?(?:summary|recap)$",
        r"^(?:please\s+)?(?:save\s+(?:a\s+)?summary\s+and\s+end|save\s+and\s+end)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session)?$",
    ]
    if _first_match(end_with_summary_patterns, lowered):
        return _command_response(
            action="end_focus_with_summary",
            frontend_command="end and summarize focus",
            confidence=0.98,
            reason="Backend focus interpreter matched an end-with-summary command.",
        )
    save_summary_patterns = [
        r"^(?:please\s+)?(?:save|store|remember|write)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session)\s+(?:as|to|in)\s+(?:a\s+)?(?:note|notes|memory|summary)$",
        r"^(?:please\s+)?(?:save|store|remember|write)\s+(?:a\s+)?(?:summary|recap)\s+(?:of|for)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session)$",
        r"^(?:please\s+)?(?:save|store|remember|write)\s+(?:the\s+)?(?:focus|session)\s+(?:summary|recap)(?:\s+(?:as|to|in)\s+(?:a\s+)?(?:note|notes|memory))?$",
        r"^(?:please\s+)?(?:save|store|remember)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:session|focus)(?:\s+to\s+memory)?$",
    ]
    if _first_match(save_summary_patterns, lowered):
        return _command_response(
            action="save_focus_summary",
            frontend_command="save focus summary as note",
            confidence=0.98,
            reason="Backend focus interpreter matched a save-focus-summary command.",
        )
    summarize_patterns = [
        r"^(?:please\s+)?(?:summarize|recap|review)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session|matter|topic|work|thing)$",
        r"^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:a\s+)?(?:focus|session)\s+(?:summary|recap|review)$",
        r"^(?:please\s+)?(?:what\s+did\s+i\s+do|what\s+did\s+we\s+do|what\s+happened|what\s+changed)\s+(?:in|during|for)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus session|active session|session)$",
        r"^(?:focus|session)\s+(?:summary|recap|review)$",
    ]
    if _first_match(summarize_patterns, lowered):
        return _command_response(
            action="summarize_focus_session",
            frontend_command="summarize this focus",
            confidence=0.98,
            reason="Backend focus interpreter matched a focus summary command.",
        )

    enhanced_focus_recap_patterns: list[tuple[str, str, str]] = [
        (
            r"^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:an?\s+)?(?:ai|smart|enhanced|better|polished|natural|intelligent)\s+(?:focus|work|activity|progress)?\s*(?:recap|summary|review)(?:\s+(?:(?:for|of)\s+)?(today|yesterday|this\s+week|recent(?:\s+work|\s+activity|\s+progress)?))?$",
            "enhanced focus recap",
            "enhanced-recent",
        ),
        (
            r"^(?:please\s+)?(?:summarize|recap|review)\s+(?:my|our)\s+(?:recent\s+)?progress(?:\s+(today|yesterday|this\s+week))?$",
            "enhanced progress recap",
            "enhanced-recent",
        ),
        (
            r"^(?:please\s+)?(?:what\s+should\s+(?:i|we)\s+focus\s+on\s+next|what\s+should\s+(?:i|we)\s+do\s+next|what\s+is\s+the\s+next\s+priority|suggest\s+(?:my|our)?\s*(?:next\s+)?priority|suggest\s+next\s+steps)$",
            "what should I focus on next",
            "next-priority",
        ),
        (
            r"^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:a\s+)?(?:daily|weekly)\s+(?:work|focus|activity|progress)\s+(?:recap|summary|review)\s+(?:with\s+)?(?:recommendations|next\s+steps|priorities)$",
            "enhanced focus recap",
            "enhanced-recent",
        ),
    ]
    for pattern, frontend_command, payload in enhanced_focus_recap_patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            explicit_window = match.group(1) if match.lastindex and match.group(1) else payload
            explicit_window = re.sub(r"\s+", "-", explicit_window.lower()).strip()
            if payload == "next-priority":
                routed_frontend_command = frontend_command
            elif explicit_window in {"today", "yesterday", "this-week"}:
                routed_frontend_command = f"enhanced focus recap {explicit_window.replace('-', ' ')}"
            else:
                routed_frontend_command = frontend_command
            return _command_response(
                action="enhanced_focus_recap",
                frontend_command=routed_frontend_command,
                confidence=0.98,
                reason="Backend focus interpreter matched an enhanced focus recap command.",
                payload={"timeframe": explicit_window},
            )
    focus_recap_patterns: list[tuple[str, str, str]] = [
        (
            r"^(?:please\s+)?(?:summarize|recap|review)\s+(?:what\s+)?(?:i|we)\s+(?:worked\s+on|focused\s+on|did|accomplished)\s+today$",
            "summarize what I worked on today",
            "today",
        ),
        (
            r"^(?:please\s+)?(?:what\s+did|what\s+have)\s+(?:i|we)\s+(?:work\s+on|focus\s+on|do|accomplish)\s+today$",
            "summarize what I worked on today",
            "today",
        ),
        (
            r"^(?:please\s+)?(?:today(?:'s)?\s+)?(?:focus|work|activity)\s+(?:recap|summary|review)$",
            "today focus recap",
            "today",
        ),
        (
            r"^(?:please\s+)?(?:summarize|recap|review)\s+(?:what\s+)?(?:i|we)\s+(?:worked\s+on|focused\s+on|did|accomplished)\s+yesterday$",
            "summarize what I worked on yesterday",
            "yesterday",
        ),
        (
            r"^(?:please\s+)?(?:what\s+did|what\s+have)\s+(?:i|we)\s+(?:work\s+on|focus\s+on|do|accomplish)\s+yesterday$",
            "summarize what I worked on yesterday",
            "yesterday",
        ),
        (
            r"^(?:please\s+)?(?:yesterday(?:'s)?\s+)?(?:focus|work|activity)\s+(?:recap|summary|review)$",
            "yesterday focus recap",
            "yesterday",
        ),
        (
            r"^(?:please\s+)?what\s+changed\s+since\s+yesterday$",
            "what changed since yesterday",
            "since-yesterday",
        ),
        (
            r"^(?:please\s+)?(?:summarize|recap|review)\s+(?:my|our)?\s*(?:recent\s+)?(?:focus|focuses|focus\s+sessions|work|activity)$",
            "recap recent focus activity",
            "recent",
        ),
        (
            r"^(?:please\s+)?what\s+did\s+(?:i|we)\s+focus\s+on\s+recently$",
            "recap recent focus activity",
            "recent",
        ),
        (
            r"^(?:please\s+)?(?:what\s+have|what\s+did)\s+(?:i|we)\s+been\s+(?:working|focusing)\s+on\s+recently$",
            "recap recent focus activity",
            "recent",
        ),
        (
            r"^(?:please\s+)?(?:daily|weekly|recent)\s+(?:focus|work|activity)\s+(?:recap|summary|review)$",
            "recap recent focus activity",
            "recent",
        ),
    ]
    for pattern, frontend_command, payload in focus_recap_patterns:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return _command_response(
                action="recap_focus_activity",
                frontend_command=frontend_command,
                confidence=0.98,
                reason="Backend focus interpreter matched a focus activity recap command.",
                payload={"timeframe": payload},
            )
    focus_history_patterns = [
        r"^(?:please\s+)?(?:show|list|read|display|open)\s+(?:my\s+|our\s+)?(?:recent\s+)?(?:focus\s+)?(?:history|sessions|focus\s+sessions)$",
        r"^(?:please\s+)?(?:show|list|read|display|open)\s+(?:my\s+|our\s+)?recent\s+(?:focuses|focus\s+sessions|sessions)$",
        r"^(?:please\s+)?(?:what\s+(?:are|were)\s+)?(?:my\s+|our\s+)?recent\s+(?:focuses|focus\s+sessions|sessions)(?:\s+again)?$",
        r"^(?:focus|session)\s+history$",
        r"^(?:recent\s+focus|recent\s+focuses|recent\s+sessions|recent\s+focus\s+sessions)$",
        r"^(?:please\s+)?what\s+(?:have|were)\s+(?:i|we)\s+been\s+working\s+on(?:\s+recently)?$",
    ]
    if _first_match(focus_history_patterns, lowered):
        return _command_response(
            action="read_focus_history",
            frontend_command="show recent focus sessions",
            confidence=0.98,
            reason="Backend focus interpreter matched a recent focus history command.",
        )
    last_focus_patterns = [
        r"^(?:please\s+)?(?:what\s+was|what\s+were|show|read|tell\s+me\s+about|display)\s+(?:my\s+|our\s+)?(?:last|latest|previous|most\s+recent)\s+(?:focus|focus\s+session|session)$",
        r"^(?:please\s+)?(?:what\s+did\s+(?:i|we)\s+focus\s+on\s+last|what\s+was\s+(?:i|we)\s+focused\s+on\s+last)$",
        r"^(?:please\s+)?(?:what\s+was\s+(?:i|we)\s+working\s+on\s+(?:earlier|before|previously|last))$",
        r"^(?:last|latest|previous|most\s+recent)\s+(?:focus|focus\s+session|session)$",
    ]
    if _first_match(last_focus_patterns, lowered):
        return _command_response(
            action="read_last_focus_session",
            frontend_command="what was my last focus",
            confidence=0.98,
            reason="Backend focus interpreter matched a last-focus recall command.",
        )
    resume_focus_patterns = [
        r"^(?:please\s+)?(?:resume|restart|continue|reopen|restore)\s+(?:my\s+|our\s+|the\s+)?(?:last|latest|previous|most\s+recent)\s+(?:(general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)?(?:focus|focus\s+session|session)$",
        r"^(?:please\s+)?(?:start|open)\s+(?:my\s+|our\s+|the\s+)?(?:last|latest|previous|most\s+recent)\s+(?:(general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)?(?:focus|focus\s+session|session)\s+(?:again|back\s+up)$",
        r"^(?:please\s+)?(?:resume|restart|continue|reopen|restore)\s+(?:(general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)(?:focus|focus\s+session|session)$",
    ]
    resume_match = _first_match(resume_focus_patterns, text)
    if resume_match:
        mode = _mode_from_text(resume_match.group(1) or "") if resume_match.lastindex else ""
        if mode:
            frontend_command = f"resume last {mode} focus"
            payload = {"mode": mode}
        else:
            frontend_command = "resume last focus"
            payload = {}
        return _command_response(
            action="resume_last_focus_session",
            frontend_command=frontend_command,
            confidence=0.98,
            reason="Backend focus interpreter matched a resume-focus command.",
            payload=payload,
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
        r"^(?:please\s+)?(?:rename|retitle)\s+(?:(?:the|my|our|current|active)\s+)?(?:focus|focus session|active session)\s+(?:to|as|called|named)\s+(.+)$",
        r"^(?:please\s+)?(?:set|change|update)\s+(?:(?:the|my|our|current|active)\s+)?(?:focus|session)\s+title\s+(?:to|as)\s+(.+)$",
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
        r"^(?:please\s+)?(?:set|change|update)\s+(?:(?:the|my|our|current|active)\s+)?(?:focus|session)\s+mode\s+(?:to|as)\s+(.+)$",
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

    ui_shortcut_intent = _ui_shortcut_intent(message)
    if ui_shortcut_intent is not None:
        return CommandInterpretResponse(**ui_shortcut_intent)
    task_completion_intent = _task_completion_intent(message)
    if task_completion_intent is not None:
        return CommandInterpretResponse(**task_completion_intent)

    qmeet_guide_intent = _qmeet_guide_intent(message, req.clientContext)
    if qmeet_guide_intent is not None:
        return CommandInterpretResponse(**qmeet_guide_intent)
    ad_hoc_prep_intent = _ad_hoc_preparation_focus_intent(message)
    if ad_hoc_prep_intent is not None:
        return CommandInterpretResponse(**ad_hoc_prep_intent)

    calendar_focus_intent = _calendar_focus_intent(message)
    if calendar_focus_intent is not None:
        return CommandInterpretResponse(**calendar_focus_intent)

    meeting_wrapup_intent = _meeting_wrapup_intent(message)
    if meeting_wrapup_intent is not None:
        return CommandInterpretResponse(**meeting_wrapup_intent)
    visual_intent = _visual_context_intent(message)
    if visual_intent is not None:
        return CommandInterpretResponse(**visual_intent)

    focus_intent = _focus_command_intent(message)
    if focus_intent is not None:
        return CommandInterpretResponse(**focus_intent)

    orchestrator_intent = await interpret_qmeet_orchestrator(
        message,
        ui_state=req.uiState,
        client_context=req.clientContext,
    )
    if orchestrator_intent is not None:
        return CommandInterpretResponse(**orchestrator_intent)
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
