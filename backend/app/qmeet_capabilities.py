"""QMeet capability/action spec used by the Phase 17C intent orchestrator.

This module is deliberately compact and machine-readable. It tells the
orchestrator which frontend commands already exist, so the model routes users
into real QMeet tools instead of inventing features.
"""

from __future__ import annotations

from typing import Any

QMEET_ACTIONS: list[dict[str, Any]] = [
    {
        "id": "open_memory",
        "frontendCommand": "open memory",
        "useWhen": "User wants the focus menu, memory panel, tasks, notes context, recent sessions, or asks how to return to focus controls.",
    },
    {
        "id": "open_menu",
        "frontendCommand": "open menu",
        "useWhen": "User wants the launcher, main menu, available panels, or asks what they can click from the home screen.",
    },
    {
        "id": "open_calendar",
        "frontendCommand": "open calendar",
        "useWhen": "User asks to see schedule/calendar/events without specifically asking for meeting prep.",
    },
    {
        "id": "prepare_next_meeting",
        "frontendCommand": "prepare me for my next meeting",
        "useWhen": "User wants help preparing for the next calendar event, meeting, call, or appointment.",
    },
    {
        "id": "meeting_prep_tasks",
        "frontendCommand": "make prep tasks for my next meeting",
        "useWhen": "User wants tasks/checklist/steps for their next calendar event or meeting.",
    },
    {
        "id": "wrap_up_meeting",
        "frontendCommand": "wrap up this meeting",
        "useWhen": "User wants to finish a meeting focus, save notes, and create follow-up tasks.",
    },
    {
        "id": "start_focus",
        "frontendCommand": "start a focus session for {title}",
        "useWhen": "User says they are working on something, wants to focus, or wants a prep block that is not tied to Google Calendar.",
    },
    {
        "id": "set_focus_goal",
        "frontendCommand": "set my goal to {goal}",
        "useWhen": "User wants to set/update the goal of the current focus session.",
    },
    {
        "id": "read_focus",
        "frontendCommand": "what is my focus",
        "useWhen": "User asks what they are focused on or what the current focus is.",
    },
    {
        "id": "focus_to_tasks",
        "frontendCommand": "turn this focus into tasks",
        "useWhen": "User wants to break the active focus into tasks, steps, or a checklist.",
    },
    {
        "id": "save_focus_summary",
        "frontendCommand": "save this focus as a note",
        "useWhen": "User wants to save current focus/session progress or notes.",
    },
    {
        "id": "end_focus_with_summary",
        "frontendCommand": "end and summarize this focus",
        "useWhen": "User wants to finish the focus/session and preserve a summary.",
    },
    {
        "id": "read_recent_focus",
        "frontendCommand": "show recent focus sessions",
        "useWhen": "User asks what they worked on earlier/recently or asks for focus history.",
    },
    {
        "id": "local_recap",
        "frontendCommand": "summarize what I worked on today",
        "useWhen": "User asks for a deterministic/local recap of recent work.",
    },
    {
        "id": "enhanced_recap",
        "frontendCommand": "give me a better recap of today",
        "useWhen": "User asks for recommendations, what to focus on next, or an AI/natural-language recap.",
    },
    {
        "id": "open_camera",
        "frontendCommand": "open camera",
        "useWhen": "User wants camera, webcam, snapshot, image upload, or visual analysis tools.",
    },
    {
        "id": "read_visual_context",
        "frontendCommand": "show visual context",
        "useWhen": "User asks what QMeet last saw, visual context, camera observation, or uploaded image observation.",
    },
    {
        "id": "link_visual_to_focus",
        "frontendCommand": "save this visual context to my focus",
        "useWhen": "User wants the latest visual observation attached to the current focus.",
    },
    {
        "id": "open_notes",
        "frontendCommand": "open notes",
        "useWhen": "User wants notes panel, saved notes, or note editor.",
    },
    {
        "id": "open_search",
        "frontendCommand": "open search",
        "useWhen": "User wants web search panel but has not provided a search query.",
    },
    {
        "id": "run_search",
        "frontendCommand": "search for {query}",
        "useWhen": "User asks QMeet to look something up or search the web.",
    },
    {
        "id": "guide_overview",
        "frontendCommand": "what can you do",
        "useWhen": "User asks broad help, onboarding, capabilities, what QMeet is, or what to say.",
    },
    {
        "id": "guide_focus",
        "frontendCommand": "help with focus",
        "useWhen": "User asks what focus means or how to use focus sessions.",
    },
    {
        "id": "guide_screen",
        "frontendCommand": "what can I do now",
        "useWhen": "User asks what they can do/click/press now, or refers to the currently visible panel.",
    },
]

QMEET_SYSTEM_PROMPT = """
You are QMeet's intent orchestrator. QMeet is a local orb tablet interface with panels,
focus sessions, memory/tasks/notes, Google Calendar workflows, camera/upload visual
context, search, voice controls, and recaps.

Your job is NOT to chat normally. Your job is to decide whether the user's message should
run a real QMeet action. If so, return exactly one frontendCommand from the allowed actions
or fill its placeholder. If no QMeet tool/action/help routing is appropriate, return intent "chat".

Rules:
- Prefer real QMeet commands over generic advice when the user asks how to use QMeet, what to click, what a panel is, what they can do now, or asks to start/update/finish work.
- Use uiState.activePanel and visibleHints when the user says "this", "that", "these", "the menu", "open it again", or "what can I do now".
- If an active focus exists and the user asks what to do with "it" or "my goal", route to guide_screen or enhanced_recap depending on whether they want UI guidance or recommendations.
- Do not invent unsupported commands. Use only frontendCommand values from the allowed actions.
- If using a placeholder command, replace {title}, {goal}, or {query} with a short safe phrase from the user's message.
- Return compact JSON only.
""".strip()


def capability_digest() -> str:
    lines = []
    for item in QMEET_ACTIONS:
        lines.append(
            f"- {item['id']}: frontendCommand={item['frontendCommand']!r}; useWhen={item['useWhen']}"
        )
    return "\n".join(lines)
