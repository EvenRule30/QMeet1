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


ACTION_VOCABULARY_VERSION = "canonical-local-command-v1"

CANONICAL_TOOL_ACTIONS_BY_OWNER: dict[str, tuple[str, ...]] = {
    "focus": (
        "start-focus-session",
        "update-focus-session",
        "read-focus-session",
        "end-focus-session",
        "focus-to-tasks",
        "summarize-focus-session",
        "save-focus-summary",
        "end-focus-with-summary",
        "read-last-focus-session",
        "read-focus-history",
        "resume-last-focus-session",
        "recap-focus-activity",
        "enhanced-focus-recap",
        "prepare-calendar-focus",
        "create-meeting-follow-up-tasks",
        "wrap-up-meeting-focus",
        "link-visual-to-focus",
        "read-focus-visuals",
    ),
    "calendar": (
        "open-calendar",
        "add-calendar-event",
        "read-calendar",
        "refresh-calendar",
        "edit-last-event",
        "delete-calendar-event",
        "delete-last-event",
        "clear-calendar",
        "show-today",
        "show-tomorrow",
        "close-calendar",
    ),
    "search": ("open-search", "run-search", "clear-search", "close-search"),
    "memory": ("open-memory", "close-memory", "read-memory"),
    "tasks": (
        "remember-task",
        "mark-task-done",
        "delete-last-task",
        "clear-done-tasks",
        "read-memory",
    ),
    "notes": (
        "open-notes",
        "new-note",
        "save-note",
        "read-notes",
        "delete-last-note",
        "close-notes",
        "clear-notes",
    ),
    "device_ui": (
        "help",
        "identity",
        "open-menu",
        "close-menu",
        "open-settings",
        "close-settings",
        "go-home",
        "show-status",
        "close-status",
        "hide-status",
        "voice-output-on",
        "voice-output-off",
        "voice-output-toggle",
        "voice-slower",
        "voice-faster",
        "voice-normal",
        "stop-speaking",
        "what-did-you-hear",
        "cancel-action",
        "clear-chat",
        "end-chat",
        "close-generic",
    ),
    "visual": (
        "create-visual-observation",
        "read-visual-context",
        "read-last-visual-observation",
        "read-visual-history",
        "summarize-visual-context",
        "link-visual-to-focus",
        "read-focus-visuals",
        "clear-visual-context",
        "delete-last-visual-observation",
    ),
}

CANONICAL_TOOL_ACTIONS = {
    action
    for actions in CANONICAL_TOOL_ACTIONS_BY_OWNER.values()
    for action in actions
}

GLOBAL_CAPABILITY_CONTRACT: list[dict[str, Any]] = [
    {
        "owner": "general_chat",
        "authority": "read-only conversation",
        "conversationActions": ["conversation.respond"],
    },
    {
        "owner": "focus",
        "authority": "canonical verified Focus backend",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["focus"]),
        "conversationActions": ["focus.help"],
        "rule": "Active Focus is context, not universal ownership.",
    },
    {
        "owner": "calendar",
        "authority": "deterministic Calendar handlers / verified Google Calendar writes",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["calendar"]),
        "constraint": "Current natural event-date support is primarily today/tomorrow.",
        "promotedReadAction": "read-calendar",
        "readArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["view"],
            "properties": {
                "view": {"type": "string", "enum": ["today", "tomorrow", "all"]},
            },
        },
        "promotedCreateAction": "add-calendar-event",
        "createArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["day", "title", "time"],
            "properties": {
                "day": {"type": "string", "enum": ["today", "tomorrow"]},
                "title": {"type": "string", "minLength": 1, "maxLength": 240},
                "time": {"type": ["string", "null"]},
            },
        },
        "promotedDeleteAction": "delete-calendar-event",
        "deleteArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["day", "title", "time"],
            "properties": {
                "day": {"type": "string", "enum": ["today", "tomorrow"]},
                "title": {"type": ["string", "null"]},
                "time": {"type": ["string", "null"]},
            },
            "constraint": "At least one of title or time must be non-null; values are lookup criteria, never canonical event identity.",
        },
        "promotedEditAction": "edit-last-event",
        "editArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["targetDay", "query", "currentTime", "changeField", "changeValue"],
            "properties": {
                "targetDay": {"type": "string", "enum": ["today", "tomorrow"]},
                "query": {"type": "string", "minLength": 1, "maxLength": 240},
                "currentTime": {"type": ["string", "null"]},
                "changeField": {"type": "string", "enum": ["time", "title", "day"]},
                "changeValue": {"type": "string", "minLength": 1, "maxLength": 240},
            },
            "constraint": (
                "targetDay identifies where the event exists before the edit; it is separate from a destination day. "
                "The query is a natural lookup reference, not canonical event identity. Exactly one time/title/day change is proposed. "
                "A day-only move preserves the event's existing time. Deterministic Calendar state performs exact/fuzzy/ambiguous resolution before confirmation."
            ),
        },
        "promotionConstraint": (
            "read-calendar, add-calendar-event, targeted delete-calendar-event, and targeted edit-last-event proposals are agent-promotable. "
            "Create/delete/edit require deterministic argument validation; targeted delete/edit additionally require canonical "
            "zero/one/multiple target resolution through the shared exact/likely/ambiguous/none resolver, and writes still require the existing confirmation path. "
            "Delete-last and clears remain deferred."
        ),
    },
    {
        "owner": "search",
        "authority": "deterministic search capability",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["search"]),
        "ownershipRule": (
            "Use Search when the user asks QMeet to discover, verify, inspect, compare, or report "
            "external web evidence/opinions/current information rather than answer from model memory."
        ),
        "executableAction": "run-search",
        "argumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 500},
            },
        },
    },
    {
        "owner": "memory",
        "authority": "deterministic Memory state",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["memory"]),
    },
    {
        "owner": "tasks",
        "authority": "deterministic task handlers plus canonical Focus lineage when linked",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["tasks"]),
        "promotedCreateAction": "remember-task",
        "createArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title"],
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 240},
            },
        },
        "promotedReadAction": "read-memory",
        "readArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["scope"],
            "properties": {
                "scope": {"type": "string", "enum": ["global"]},
            },
        },
        "promotedCompleteAction": "mark-task-done",
        "completeArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["scope", "query"],
            "properties": {
                "scope": {"type": "string", "enum": ["global"]},
                "query": {"type": "string", "minLength": 1, "maxLength": 240},
            },
            "constraint": (
                "query is semantic lookup language only and never task identity. "
                "Exactly one real open task must be deterministically resolved before confirmation."
            ),
        },
        "promotionConstraint": (
            "Only single-task creation was agent-promotable in Phase 21C1; Phase 21C3 additionally promotes authoritative GLOBAL open-task reads. "
            "Phase 21C4 promotes the semantic front door for one named/referenced task completion, but Task completion remains on QMeet's existing deterministic identity/confirmation execution path. "
            "The model may provide only scope=global plus a lookup query; zero matches do nothing, multiple plausible matches require clarification, and one resolved task identity is locked across confirmation. "
            "Focus-linked task questions remain Focus-owned. Historical completion/deletion/clear safeguards remain authoritative; deletion/clear operations stay on their existing guarded paths."
        ),
    },
    {
        "owner": "notes",
        "authority": "deterministic note handlers",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["notes"]),
        "promotedSaveAction": "save-note",
        "saveArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["content"],
            "properties": {
                "content": {"type": "string", "minLength": 1, "maxLength": 6000},
            },
        },
        "promotedReadAction": "read-notes",
        "readArgumentSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {},
        },
        "promotionConstraint": (
            "Single-note save and authoritative note reads are agent-promotable. Save content is user-authored note content, not permission to invent or summarize unsupported facts. "
            "Delete/clear remain on their existing deterministic confirmation paths, and Focus-summary-to-note remains Focus-owned."
        ),
    },
    {
        "owner": "device_ui",
        "authority": "deterministic frontend/device handlers",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["device_ui"]),
    },
    {
        "owner": "visual",
        "authority": "deterministic camera/visual-context handlers",
        "actions": list(CANONICAL_TOOL_ACTIONS_BY_OWNER["visual"]),
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
- Prefer real QMeet commands when the user asks how to use QMeet, what to click, what a panel is, or asks to start/update/finish work.
- Prefer chat, not a command, when the user wants help doing the actual work inside an active focus.
- Use uiState.activePanel and visibleHints when the user says "this", "that", "these", "the menu", "open it again", or "what can I do now".
- If an active focus exists and the user asks for substantive help with the work itself (for example "what do I do now", "help me do the code", "what more do you need to know", "I don't like those tasks"), return intent "chat" so the main assistant can coach using active focus context. Do not route those to guide_screen or guide_focus.
- Use guide_screen only for UI questions like what buttons can be clicked, what panel is open, or how to reopen a menu.
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
    lines.append("Canonical executable actions by owner:")
    for owner, actions in CANONICAL_TOOL_ACTIONS_BY_OWNER.items():
        lines.append(f"- {owner}: {', '.join(actions)}")
    return "\n".join(lines)
