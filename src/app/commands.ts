import { getQMeetGuideResponse, getQMeetGuideTopic } from './lib/qmeetGuide';

export type LocalCommand = 
  | 'help'
  | 'identity'
  | 'open-menu'
  | 'close-menu'
  | 'open-settings'
  | 'close-settings'
  | 'go-home'
  | 'show-status'
  | 'close-status'
  | 'hide-status'
  | 'open-notes'
  | 'new-note'
  | 'save-note'
  | 'read-notes'
  | 'delete-last-note'
  | 'open-memory'
  | 'close-memory'
  | 'read-memory'
  | 'start-focus-session'
  | 'update-focus-session'
  | 'read-focus-session'
  | 'end-focus-session'
  | 'focus-to-tasks'
  | 'summarize-focus-session'
  | 'save-focus-summary'
  | 'end-focus-with-summary'
  | 'read-last-focus-session'
  | 'read-focus-history'
  | 'resume-last-focus-session'
  | 'recap-focus-activity'
  | 'enhanced-focus-recap'
  | 'prepare-calendar-focus'
  | 'create-meeting-follow-up-tasks'
  | 'wrap-up-meeting-focus'
  | 'create-visual-observation'
  | 'read-visual-context'
  | 'read-last-visual-observation'
  | 'read-visual-history'
  | 'summarize-visual-context'
  | 'link-visual-to-focus'
  | 'read-focus-visuals'
  | 'clear-visual-context'
  | 'delete-last-visual-observation'
  | 'remember-task'
  | 'mark-task-done'
  | 'delete-last-task'
  | 'clear-done-tasks'
  | 'close-notes'
  | 'clear-notes'
  | 'open-calendar'
  | 'add-calendar-event'
  | 'read-calendar'
  | 'refresh-calendar'
  | 'edit-last-event'
  | 'delete-calendar-event'
  | 'delete-last-event'
  | 'clear-calendar'
  | 'show-today'
  | 'show-tomorrow'
  | 'close-calendar'
  | 'open-search'
  | 'run-search'
  | 'clear-search'
  | 'close-search'
  | 'voice-output-on'
  | 'voice-output-off'
  | 'voice-output-toggle'
  | 'voice-slower'
  | 'voice-faster'
  | 'voice-normal'
  | 'stop-speaking'
  | 'what-did-you-hear'
  | 'cancel-action'
  | 'clear-chat' 
  | 'end-chat'
  | 'close-generic';

export type ActivePanel = 'none' | 'menu' | 'settings' | 'status' | 'notes' | 'calendar' | 'search' | 'memory';

export type CalendarCommandDay =
  | 'today'
  | 'tomorrow'
  | `${number}-${number}-${number}`;

export interface CalendarCommandPayload {
  day: CalendarCommandDay;
  time: string;
  title: string;
}

export interface CalendarEditCommandPayload {
  day?: 'today' | 'tomorrow';
  time?: string;
  title?: string;
}

export interface CalendarDeleteCommandPayload {
  day?: 'today' | 'tomorrow';
  time?: string;
  title?: string;
}

export type FocusSessionMode =
  | 'general'
  | 'coding'
  | 'meeting'
  | 'planning'
  | 'research'
  | 'personal';

export interface FocusSessionCommandPayload {
  title?: string;
  mode?: FocusSessionMode;
  goal?: string;
  /** Phase 13C: bypass the end-of-focus summary guard when the user explicitly says to end anyway. */
  forceEnd?: boolean;
}

// Phase 13F-v1: local focus/work recap commands.
// Phase 13F-v2: LLM-enhanced recap commands.
// Phase 14C-v1: manual visual observation commands.
// Phase 14H-v2: visual read/history/summary commands route through read-visual-context payloads.
// Phase 15A-v1: visual-focus fusion commands link/read observations related to the active focus.
// Phase 16A-v1: calendar-focus prep routes next calendar events into active focus sessions.
// Phase 16B-v1: calendar-focus prep also creates linked meeting-prep tasks.
// Phase 16C-v1: meeting wrap-up commands save summaries and create follow-up tasks.
// Phase 17B-v2: guided onboarding catches broader capability/schedule questions and natural prep-block phrases.
// Phase 17B-v3: contextual guide catches follow-up UI questions and maps focus menu wording to Memory.
// Phase 17D-v2: active-focus work/help questions are allowed through to chat instead of being swallowed by the guide.
// Phase 17H-v2: task-completion updates are routed before focus/note parsing so "I finished the first two" marks tasks instead of saving notes.

export interface CommandMatch {
  command: LocalCommand;
  confirmation: string;
  payload?: string;
  calendarEvent?: CalendarCommandPayload;
  calendarEdit?: CalendarEditCommandPayload;
  calendarDelete?: CalendarDeleteCommandPayload;
  focusSession?: FocusSessionCommandPayload;
  calendarView?: 'today' | 'tomorrow' | 'all';
}

const HELP_MESSAGE = getQMeetGuideResponse('overview');

const CONFIRMATIONS: Record<LocalCommand, string> = {
  help: HELP_MESSAGE,
  identity: "I'm QMeet, your local AI orb interface. I can help with focus, memory, calendar, meetings, camera/visual context, search, and recaps. Ask 'what can you do' or 'help with focus' for quick examples.",
  'open-menu': 'Opening menu.',
  'close-menu': 'Closing menu.',
  'open-settings': 'Opening settings.',
  'close-settings': 'Closing settings.',
  'go-home': 'Going home.',
  'show-status': 'Showing status.',
  'close-status': 'Closing status.',
  'hide-status': 'Hiding status.',
  'open-notes': 'Opening notes.',
  'new-note': 'Opening a new note.',
  'save-note': 'Saved note.',
  'read-notes': 'Reading notes.',
  'delete-last-note': 'Deleted the last note.',
  'close-notes': 'Closed notes.',
  'clear-notes': 'Cleared notes.',
  'open-memory': 'Opening memory.',
  'close-memory': 'Closed memory.',
  'read-memory': 'Reading memory.',
  'start-focus-session': 'Started focus session.',
  'update-focus-session': 'Updated focus session.',
  'read-focus-session': 'Reading focus session.',
  'end-focus-session': 'Ended focus session.',
  'focus-to-tasks': 'Turning focus into tasks.',
  'summarize-focus-session': 'Summarizing focus session.',
  'save-focus-summary': 'Saving focus summary.',
  'end-focus-with-summary': 'Ending focus session with summary.',
  'read-last-focus-session': 'Reading last focus session.',
  'read-focus-history': 'Reading recent focus sessions.',
  'resume-last-focus-session': 'Resuming last focus session.',
  'recap-focus-activity': 'Recapping recent focus activity.',
  'enhanced-focus-recap': 'Preparing enhanced focus recap.',
  'prepare-calendar-focus': 'Preparing focus and tasks from your next calendar event.',
  'create-meeting-follow-up-tasks': 'Creating meeting follow-up tasks.',
  'wrap-up-meeting-focus': 'Wrapping up meeting focus.',
  'create-visual-observation': 'Saved visual observation.',
  'read-visual-context': 'Reading visual context.',
  'read-last-visual-observation': 'Reading last visual observation.',
  'read-visual-history': 'Reading recent visual observations.',
  'summarize-visual-context': 'Summarizing visual context.',
  'link-visual-to-focus': 'Linking visual context to focus.',
  'read-focus-visuals': 'Reading focus visual context.',
  'clear-visual-context': 'Clearing visual context.',
  'delete-last-visual-observation': 'Deleted last visual observation.',
  'remember-task': 'Saved task.',
  'mark-task-done': 'Marked task done.',
  'delete-last-task': 'Deleted the last task.',
  'clear-done-tasks': 'Cleared completed tasks.',
  'open-calendar': 'Opening calendar.',
  'add-calendar-event': 'Added event.',
  'read-calendar': 'Reading calendar.',
  'refresh-calendar': 'Refreshing calendar.',
  'edit-last-event': 'Updated the last event.',
  'delete-calendar-event': 'Deleted event.',
  'delete-last-event': 'Deleted the last event.',
  'clear-calendar': 'Cleared calendar.',
  'show-today': 'Showing today.',
  'show-tomorrow': 'Showing tomorrow.',
  'close-calendar': 'Closed calendar.',
  'open-search': 'Opening search.',
  'run-search': 'Searching the web.',
  'clear-search': 'Search cleared.',
  'close-search': 'Closed search.',
  'voice-output-on': 'Voice output enabled.',
  'voice-output-off': 'Voice output muted.',
  'voice-output-toggle': 'Toggling voice output.',
  'voice-slower': 'Speaking slower.',
  'voice-faster': 'Speaking faster.',
  'voice-normal': 'Voice speed reset to normal.',
  'stop-speaking': 'Speech stopped.',
  'what-did-you-hear': 'Checking the last heard transcript.',
  'cancel-action': 'Cancelled.',
  'clear-chat': 'Chat cleared.',
  'end-chat': 'Ending conversation.',
  'close-generic': 'Closed.',
};

const REQUEST_PREFIX =
  '(?:(?:please\\s+)?(?:can|could|would|will)\\s+you\\s+|please\\s+|i\\s+(?:want|need)\\s+you\\s+to\\s+)?';
const OPEN_VERB = '(?:open|show|display|bring\\s+up|pull\\s+up|launch)';
const CLOSE_VERB = '(?:close|hide|dismiss|remove|get\\s+rid\\s+of)';
const QMEET_ALIAS =
  '(?:q\\s*meet|queue\\s+meet|cue\\s+meet|cute\\s+meet|q\\s*meat|queue\\s+meat|cue\\s+meat|cute\\s+meat|key\\s+meet|key\\s+meat|q\\s*me|queue\\s+me|cue\\s+me|computer|cube\\s+meet)';

const CALENDAR_ALIAS = '(?:calendar|calender|calander|schedule|agenda)';

function rx(pattern: string): RegExp {
  return new RegExp(pattern, 'i');
}

const COMMAND_PATTERNS: Array<[LocalCommand, RegExp[]]> = [
  [
    'help',
    [
      /^(?:help|commands?|command list|voice commands?|show commands?|show me commands?|show help|show me help)$/i,
      /^(?:what can (?:you|qmeet|the orb) do)$/i,
      /^(?:what (?:are you|is qmeet|is the orb) able to do)$/i,
      /^(?:what is focus|what is a focus|what is a focus session)$/i,
      /^(?:what was that (?:menu|panel|screen)|how (?:do|to) i open (?:it|that|this) again|can i (?:click|tap|press) (?:any one of these|one of these|these|this))$/i,
      /^(?:what (?:can|should) i say)$/i,
      /^(?:how do i use (?:this|qmeet|the orb))$/i,
      /^(?:what menus can (?:you|qmeet|the orb) open)$/i,
      /^(?:tell me what (?:you|qmeet|the orb) can do)$/i,
      /^(?:local commands?|local tools?|what local tools do you have|what tools do you have)$/i,
    ],
  ],
  [
    'identity',
    [
      rx(`^(?:who\\s+are\\s+you|what\\s+are\\s+you|what(?:'s|\\s+is)\\s+your\\s+name|what\\s+are\\s+you\\s+called)$`),
      rx(`^(?:are\\s+you|is\\s+your\\s+name)\\s+${QMEET_ALIAS}$`),
      rx(`^${QMEET_ALIAS}$`),
    ],
  ],
  [
    'open-menu',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?(?:main\\s+)?menu$`),
      /^(?:menu|main menu|app launcher|launcher)$/i,
      /^(?:show|bring\\s+up|pull\\s+up)\\s+(?:the\\s+)?menu$/i,
    ],
  ],
  [
    'close-menu',
    [rx(`^${REQUEST_PREFIX}${CLOSE_VERB}\\s+(?:the\\s+)?(?:main\\s+)?menu$`)],
  ],
  [
    'open-settings',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?settings?(?:\\s+(?:panel|screen|menu))?$`),
      /^(?:settings?|settings panel|options|preferences|configuration|config)$/i,
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:the\\s+)?(?:options|preferences|config|configuration)$`),
    ],
  ],
  [
    'close-settings',
    [rx(`^${REQUEST_PREFIX}${CLOSE_VERB}\\s+(?:the\\s+)?settings?(?:\\s+(?:panel|screen|menu))?$`)],
  ],
  [
    'go-home',
    [
      rx(`^${REQUEST_PREFIX}(?:go\\s+(?:to\\s+)?home|return\\s+(?:to\\s+)?home|back\\s+(?:to\\s+)?home|go\\s+back\\s+(?:to\\s+)?home|take\\s+me\\s+home|main\\s+screen|home\\s+screen|home)$`),
      rx(`^${REQUEST_PREFIX}(?:close\\s+everything|hide\\s+everything|clear\\s+the\\s+screen|back\\s+to\\s+main|exit\\s+panel)$`),
      /^(?:home|home screen|main screen)$/i,
    ],
  ],
  [
    'show-status',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?status(?:\\s+(?:panel|screen|menu|dashboard))?$`),
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?(?:system\\s+)?(?:dashboard|diagnostics?|health|system\\s+status)$`),
      /^(?:status|status panel|system status|system dashboard|dashboard|diagnostics|health|system|system info|system information|health check|show health|show dashboard)$/i,
      rx(`^${REQUEST_PREFIX}(?:show|display)\\s+(?:the\\s+)?(?:system|dashboard|health)$`),
    ],
  ],
  [
    'close-status',
    [rx(`^${REQUEST_PREFIX}${CLOSE_VERB}\\s+(?:the\\s+)?status(?:\\s+(?:panel|screen|menu))?$`)],
  ],
  [
    'hide-status',
    [rx(`^${REQUEST_PREFIX}hide\\s+(?:the\\s+)?status(?:\\s+(?:panel|screen|menu))?$`)],
  ],
  [
    'read-notes',
    [
      rx(`^${REQUEST_PREFIX}(?:read|list|tell\\s+me|show|display)\\s+(?:me\\s+)?(?:my\\s+)?notes$`),
      /^(?:read my notes|read notes|list my notes|list notes|show my notes|display my notes|what are my notes|what notes do i have)$/i,
    ],
  ],
  [
    'delete-last-note',
    [
      rx(`^${REQUEST_PREFIX}(?:delete|remove|erase|clear)\\s+(?:the\\s+)?(?:last|latest|newest|most\\s+recent)\\s+note$`),
      /^(?:delete last note|remove last note|delete latest note|remove latest note)$/i,
    ],
  ],
  [
    'open-notes',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?notes?(?:\\s+(?:panel|screen|menu))?$`),
      /^(?:notes?|notes panel|notepad|notebook)$/i,
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:the\\s+)?(?:notepad|notebook|note\\s+taking)$`),
      rx(`^${REQUEST_PREFIX}(?:show|display)\\s+(?:my\\s+)?notes$`),
    ],
  ],
  [
    'new-note',
    [
      rx(`^${REQUEST_PREFIX}(?:new|create|start|make)\\s+(?:a\\s+)?note$`),
      rx(`^${REQUEST_PREFIX}(?:take|write)\\s+(?:a\\s+)?note$`),
    ],
  ],
  [
    'close-notes',
    [rx(`^${REQUEST_PREFIX}${CLOSE_VERB}\\s+(?:the\\s+)?notes?(?:\\s+(?:panel|screen|menu))?$`)],
  ],
  [
    'clear-notes',
    [
      rx(`^${REQUEST_PREFIX}(?:clear|delete|wipe)\\s+(?:all\\s+)?notes?$`),
    ],
  ],

  [
    'open-memory',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?(?:memory|tasks?|task\\s+list|work\\s+log)(?:\\s+(?:panel|screen|menu))?$`),
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?(?:focus|focus\\s+session|current\\s+focus|active\\s+focus)(?:\\s+(?:menu|panel|controls?|screen))?$`),
      /^(?:memory|memory panel|tasks|task list|work log)$/i,
      /^(?:show focus menu|open focus menu|focus menu|focus panel|focus controls|current focus panel|active focus panel)$/i,
    ],
  ],
  [
    'close-memory',
    [
      rx(`^${REQUEST_PREFIX}${CLOSE_VERB}\\s+(?:the\\s+)?(?:memory|tasks?|task\\s+list|work\\s+log)(?:\\s+(?:panel|screen|menu))?$`),
    ],
  ],
  [
    'read-memory',
    [
      /^(?:what was i working on|what am i working on|what were we working on|what are my tasks|read memory|show memory|memory summary|project memory|what is in memory)$/i,
      rx(`^${REQUEST_PREFIX}(?:read|show|summarize|display|tell\\s+me)\\s+(?:my\\s+)?(?:memory|tasks?|task\\s+list|work\\s+log)$`),
    ],
  ],
  [
    'read-focus-session',
    [
      /^(?:what(?:'s|\s+is)|what\s+is)\s+(?:my\s+)?(?:current\s+)?focus(?:\s+session)?$/i,
      /^(?:what\s+am\s+i\s+focused\s+on(?:\s+right\s+now)?|what\s+are\s+we\s+focused\s+on(?:\s+right\s+now)?|what\s+is\s+my\s+focus\s+right\s+now|what\s+am\s+i\s+supposed\s+to\s+be\s+working\s+on|what\s+should\s+i\s+be\s+working\s+on)$/i,
      rx(`^${REQUEST_PREFIX}(?:read|show|tell\s+me|summarize|display)\s+(?:my\s+)?(?:current\s+)?(?:focus|focus\s+session|active\s+session)$`),
      /^(?:focus status|current focus|active focus|my focus|what's my focus|active session|session status)$/i,
    ],
  ],
  [
    'end-focus-session',
    [
      rx(`^${REQUEST_PREFIX}(?:end|stop|clear|close|leave|exit|finish|wrap\s+up)\s+(?:(?:the|my|current|active)\s+)*(?:(?:general|coding|meeting|planning|research|personal)\s+)?(?:focus|focus\s+session|active\s+session|session|focus\s+mode)$`),
      rx(`^${REQUEST_PREFIX}(?:i(?:'m|\s+am)|we(?:'re|\s+are))\s+(?:done|finished)\s+(?:with\s+)?(?:(?:the|my|current|active)\s+)*(?:(?:general|coding|meeting|planning|research|personal)\s+)?(?:focus|focus\s+session|active\s+session|session|focus\s+mode)$`),
      /^(?:end focus|stop focus|clear focus|end session|stop session|exit focus mode|finish focus|wrap up focus)$/i,
    ],
  ],


  [
    'focus-to-tasks',
    [
      /^(?:turn|convert|make|create)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|goal)\s+(?:into|to)\s+(?:tasks|task\s+list|action\s+items|next\s+steps|steps|checklist)$/i,
      /^(?:make|create|add|generate)\s+(?:tasks|a\s+task\s+list|action\s+items|next\s+steps|steps|a\s+checklist)\s+(?:for|from|based\s+on)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|goal)$/i,
      /^(?:break|split)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|goal)\s+(?:into|down\s+into)\s+(?:tasks|steps|next\s+steps|action\s+items)$/i,
      /^(?:can|could|would)\s+(?:you|we)\s+(?:please\s+)?(?:break|split|turn|convert)\s+(?:it|this|that|these|the\s+work)?\s*(?:into|down\s+into|to)\s+(?:(?:a\s+)?(?:task\s+list|checklist)|tasks|steps|next\s+steps|action\s+items)$/i,
    ],
  ],

  [
    'delete-last-task',
    [
      rx(`^${REQUEST_PREFIX}(?:delete|remove|erase|clear)\\s+(?:the\\s+)?(?:last|latest|newest|most\\s+recent)\\s+task$`),
      /^(?:delete last task|remove last task|delete latest task|remove latest task)$/i,
    ],
  ],
  [
    'clear-done-tasks',
    [
      rx(`^${REQUEST_PREFIX}(?:clear|remove|delete)\\s+(?:completed|done|finished)\\s+tasks?$`),
      /^(?:clear completed tasks|clear done tasks|remove done tasks)$/i,
    ],
  ],

  [
    'read-calendar',
    [
      rx(`^${REQUEST_PREFIX}(?:what(?:'s|\\s+is)|what\\s+are)\\s+(?:on|in)\\s+(?:my\\s+)?${CALENDAR_ALIAS}(?:\\s+events?)?$`),
      rx(`^${REQUEST_PREFIX}(?:read|list|show|display)\\s+(?:my\\s+)?${CALENDAR_ALIAS}(?:\\s+events?)?$`),
      rx(`^${REQUEST_PREFIX}(?:show|read|list|display)\\s+(?:my\\s+)?(?:calendar|calender|calander|schedule|agenda)?\\s*events$`),
      rx(`^${REQUEST_PREFIX}(?:what\\s+events\\s+do\\s+i\\s+have|what\\s+is\\s+my\\s+schedule|what\\s+are\\s+my\\s+events)$`),
      /^(?:calendar events|calender events|calander events|my events|my schedule|agenda)$/i,
    ],
  ],

  [
    'refresh-calendar',
    [
      rx(`^${REQUEST_PREFIX}(?:refresh|reload|sync|update)\s+(?:my\s+)?(?:calendar|calender|calander|schedule|agenda)(?:\s+(?:events?|view|panel))?$`),
      /^(?:refresh calendar|reload calendar|sync calendar|update calendar|refresh schedule|reload schedule|sync schedule)$/i,
    ],
  ],

  [
    'edit-last-event',
    [
      rx(`^${REQUEST_PREFIX}(?:reschedule|move)\s+(?:the\s+)?(?:last|latest|next|current|this)\s+(?:calendar\s+)?(?:event|appointment|meeting)\s+(?:to|for)\s+(.+)$`),
      rx(`^${REQUEST_PREFIX}(?:rename|retitle)\s+(?:the\s+)?(?:last|latest|next|current|this)\s+(?:calendar\s+)?(?:event|appointment|meeting)\s+(?:to|as|called|named)\s+(.+)$`),
      rx(`^${REQUEST_PREFIX}(?:change|edit|update)\s+(?:the\s+)?(?:last|latest|next|current|this)\s+(?:calendar\s+)?(?:event|appointment|meeting)(?:\s+.*)?$`),
    ],
  ],
  [
    'delete-last-event',
    [
      rx(`^${REQUEST_PREFIX}(?:delete|remove|erase|clear)\\s+(?:the\\s+)?(?:last|latest|newest|most\\s+recent)\\s+(?:calendar\\s+)?(?:event|appointment|meeting)$`),
      /^(?:delete last event|remove last event|delete latest event|remove latest event)$/i,
    ],
  ],
  [
    'clear-calendar',
    [
      rx(`^${REQUEST_PREFIX}(?:clear|reset|delete|wipe|remove|erase)\\s+(?:all\\s+|my\\s+|the\\s+)?${CALENDAR_ALIAS}(?:\\s+(?:events?|appointments?|meetings?|entries))?$`),
      rx(`^${REQUEST_PREFIX}(?:clear|reset|delete|wipe|remove|erase)\\s+(?:all\\s+)?(?:events?|appointments?|meetings?|entries)\\s+(?:from|on|in)\\s+(?:my\\s+)?${CALENDAR_ALIAS}$`),
      /^(?:clear calendar|clear calender|clear calander|clear schedule|clear agenda|clear calendar events|clear calender events|clear calander events|clear my calendar|clear my schedule|clear all events|reset calendar|wipe calendar)$/i,
    ],
  ],
  [
    'open-calendar',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:my\\s+)?(?:the\\s+)?calendar(?:\\s+(?:panel|screen|menu|view))?$`),
      /^(?:calendar|calendar panel|calender|calander|schedule|agenda)$/i,
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:the\\s+)?(?:calender|calander|schedule|agenda)$`),
    ],
  ],
  [
    'show-today',
    [
      rx(`^${REQUEST_PREFIX}(?:show|open|display|pull\\s+up|bring\\s+up)\\s+(?:me\\s+)?(?:my\\s+)?(?:the\\s+)?(?:calendar\\s+)?today(?:\\s+(?:view|agenda|schedule))?$`),
      /^(?:today|today view|today agenda|today schedule|today(?:'s)? schedule)$/i,
    ],
  ],
  [
    'show-tomorrow',
    [
      rx(`^${REQUEST_PREFIX}(?:show|open|display|pull\\s+up|bring\\s+up)\\s+(?:me\\s+)?(?:my\\s+)?(?:the\\s+)?(?:calendar\\s+)?tomorrow(?:\\s+(?:view|agenda|schedule))?$`),
      /^(?:tomorrow|tomorrow view|tomorrow agenda|tomorrow schedule|tomorrow(?:'s)? schedule)$/i,
    ],
  ],
  [
    'close-calendar',
    [
      rx(`^${REQUEST_PREFIX}${CLOSE_VERB}\\s+(?:my\\s+)?(?:the\\s+)?calendar(?:\\s+(?:panel|screen|menu|view))?$`),
    ],
  ],
  [
    'open-search',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?(?:search|web\\s+search|browser)(?:\\s+(?:panel|screen|menu|view))?$`),
      /^(?:open|show|display|launch) (?:search|browser|web search|web|internet)$/i,
      /^(?:open|show|display|launch) (?:the )?(?:search|browser|web search|web|internet) (?:panel|screen|view)$/i,
      rx(`^${REQUEST_PREFIX}(?:search|browse)\\s+(?:the\\s+)?(?:web|internet)$`),
      rx(`^${REQUEST_PREFIX}(?:web|internet)\\s+(?:search|browser)$`),
      /^(?:search|search panel|browser|web search|web|internet)$/i,
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:the\\s+)?(?:web|internet)$`),
      rx(`^${REQUEST_PREFIX}(?:internet\\s+search|web\\s+browser|look\\s+(?:something\\s+)?up|look\\s+this\\s+up)$`),
    ],
  ],
  [
    'clear-search',
    [
      rx(`^${REQUEST_PREFIX}(?:clear|reset|delete|wipe)\\s+(?:the\\s+)?(?:search|search\\s+query|web\\s+search|browser\\s+query)$`),
      /^(?:clear search|reset search|clear search query|clear browser query)$/i,
    ],
  ],
  [
    'close-search',
    [
      rx(`^${REQUEST_PREFIX}${CLOSE_VERB}\\s+(?:the\\s+)?(?:search|web\\s+search|browser)(?:\\s+(?:panel|screen|menu|view))?$`),
      /^(?:close|hide|dismiss) (?:search|browser|web search)$/i,
      /^(?:close|hide|dismiss) (?:the )?(?:search|browser|web search) (?:panel|screen|view)$/i,
    ],
  ],
  [
    'voice-output-on',
    [
      rx(`^${REQUEST_PREFIX}(?:turn\\s+on|enable|unmute|activate)\\s+(?:the\\s+)?(?:voice|speech|voice\\s+output|spoken\\s+responses|speaker)$`),
      rx(`^${REQUEST_PREFIX}(?:voice|speech|speaker)\\s+on$`),
      rx(`^${REQUEST_PREFIX}(?:read|speak)\\s+(?:responses\\s+)?(?:out\\s+loud|aloud)$`),
      rx(`^${REQUEST_PREFIX}(?:talk|speak)\\s+(?:again|back\\s+on)$`),
      rx(`^${REQUEST_PREFIX}(?:voice\\s+)?back\\s+on$`),
      /^(?:talk again|speak again|voice back on|unmute)$/i,
    ],
  ],
  [
    'voice-output-off',
    [
      rx(`^${REQUEST_PREFIX}(?:turn\\s+off|disable|mute|deactivate)\\s+(?:the\\s+)?(?:voice|speech|voice\\s+output|spoken\\s+responses|speaker)$`),
      rx(`^${REQUEST_PREFIX}(?:voice|speech|speaker)\\s+off$`),
      rx(`^${REQUEST_PREFIX}(?:stop|quit)\\s+(?:reading|speaking)\\s+(?:out\\s+loud|aloud)$`),
      rx(`^${REQUEST_PREFIX}(?:silence|mute)\\s+(?:yourself|your\\s+voice|the\\s+voice)$`),
      rx(`^${REQUEST_PREFIX}(?:stop|quiet|hush)\\s+(?:your\\s+)?speaking$`),
      /^(?:mute yourself|silence voice|voice quiet)$/i,
    ],
  ],
  [
    'voice-output-toggle',
    [rx(`^${REQUEST_PREFIX}toggle\\s+(?:the\\s+)?(?:voice|speech|voice\\s+output|spoken\\s+responses|speaker)$`)],
  ],
  [
    'voice-slower',
    [
      rx(`^${REQUEST_PREFIX}(?:speak|talk|read)\\s+slower$`),
      rx(`^${REQUEST_PREFIX}(?:slow\\s+down|decrease|lower)\\s+(?:the\\s+)?(?:voice|speech|voice\\s+speed|speech\\s+rate)$`),
      rx(`^${REQUEST_PREFIX}(?:voice|speech)\\s+slower$`),
      /^(?:slower voice|voice slower)$/i,
    ],
  ],
  [
    'voice-faster',
    [
      rx(`^${REQUEST_PREFIX}(?:speak|talk|read)\\s+faster$`),
      rx(`^${REQUEST_PREFIX}(?:speed\\s+up|increase|raise)\\s+(?:the\\s+)?(?:voice|speech|voice\\s+speed|speech\\s+rate)$`),
      rx(`^${REQUEST_PREFIX}(?:voice|speech)\\s+faster$`),
      /^(?:faster voice|voice faster)$/i,
    ],
  ],
  [
    'voice-normal',
    [
      rx(`^${REQUEST_PREFIX}(?:normal|default|reset)\\s+(?:voice|speech|voice\\s+speed|speech\\s+rate)$`),
      rx(`^${REQUEST_PREFIX}(?:speak|talk|read)\\s+(?:normally|normal)$`),
      /^(?:normal speed|normal voice|voice normal)$/i,
    ],
  ],
  [
    'stop-speaking',
    [
      rx(`^${REQUEST_PREFIX}(?:stop\\s+speaking|stop\\s+talking|stop\\s+reading|be\\s+quiet|silence)$`),
      rx(`^${REQUEST_PREFIX}(?:stop|cancel)\\s+(?:your\\s+)?(?:response|responding|talking|speaking|voice)$`),
      /^(?:stop talking|stop response|stop responding|stop speaking|shut up|be quiet)$/i,
    ],
  ],
  [
    'cancel-action',
    [
      rx(`^${REQUEST_PREFIX}(?:cancel|stop|nevermind|never\\s+mind|abort|cancel\\s+that|stop\\s+that|forget\\s+(?:it|that)|stop\\s+listening|cancel\\s+listening)$`),
      rx(`^${REQUEST_PREFIX}(?:cancel|stop)\\s+(?:the\\s+)?(?:request|action)$`),
      /^(?:never mind|forget that|cancel request|enough|pause)$/i,
    ],
  ],
  [
    'what-did-you-hear',
    [
      /^(?:what did you hear|what did you hear me say|what did i say|what was the last thing you heard)$/i,
      /^(?:last transcript|show last transcript|repeat last transcript|debug transcript|voice debug)$/i,
      rx(`^${REQUEST_PREFIX}(?:show|tell\\s+me|repeat)\\s+(?:the\\s+)?(?:last\\s+)?(?:voice\\s+)?(?:transcript|thing\\s+you\\s+heard)$`),
    ],
  ],

  [
    'clear-chat',
    [
      rx(`^${REQUEST_PREFIX}(?:clear|reset|delete|wipe)\\s+(?:the\\s+)?(?:chat|conversation|messages)$`),
      /^(?:clear|reset)$/i,
    ],
  ],
  [
    'end-chat',
    [rx(`^${REQUEST_PREFIX}(?:end|exit|quit|stop)\\s+(?:the\\s+)?(?:chat|conversation)$`)],
  ],
  [
    'close-generic',
    [
      rx(`^${REQUEST_PREFIX}${CLOSE_VERB}\\s+(?:the\\s+)?(?:current\\s+panel|this\\s+panel|panel|popup|window|screen|this|it)$`),
    ],
  ],
];


function cleanCommandPayload(payload: string): string {
  return payload
    .replace(/^["']+|["']+$/g, '')
    .trim();
}

function extractNotePayload(normalized: string): string | null {
  const patterns = [
    /^(?:please\s+)?(?:note|remember)\s+that\s+(.+)$/i,
    /^(?:please\s+)?(?:save|add)\s+(?:a\s+)?note\s+(.+)$/i,
    /^(?:please\s+)?(?:take|write|create|make)\s+(?:a\s+)?note\s+(?:that\s+|saying\s+|called\s+|about\s+)?(.+)$/i,
  ];

  for (const pattern of patterns) {
    const match = normalized.match(pattern);
    const payload = match?.[1]
      ? cleanCommandPayload(match[1]).replace(/\s+as\s+(?:a\s+)?task$/i, '').trim()
      : '';
    if (payload) return payload;
  }

  return null;
}


function extractTaskPayload(normalized: string): string | null {
  const patterns = [
    /^(?:please\s+)?(?:remember|save|add)\s+(?:this\s+)?(?:as\s+)?(?:a\s+)?task\s*(?:to|that|called|named|:)?\s+(.+)$/i,
    /^(?:please\s+)?(?:remember|remind\s+me)\s+to\s+(.+)$/i,
    /^(?:please\s+)?(?:add|create|make|save)\s+(?:a\s+)?task\s+(?:to\s+|that\s+|called\s+|named\s+)?(.+)$/i,
    /^(?:please\s+)?task\s+(?:to\s+|that\s+|called\s+|named\s+)?(.+)$/i,
  ];

  for (const pattern of patterns) {
    const match = normalized.match(pattern);
    const payload = match?.[1]
      ? cleanCommandPayload(match[1]).replace(/\s+as\s+(?:a\s+)?task$/i, '').trim()
      : '';
    if (payload) return payload;
  }

  return null;
}

function extractTaskDonePayload(normalized: string): string | null {
  const commandText = normalized
    .replace(
      /^(?:(?:please\s+)?(?:can|could|would|will)\s+you\s+|please\s+|i\s+(?:want|need)\s+you\s+to\s+)/i,
      '',
    )
    .trim();

  const broadDonePatterns = [
    /^(?:please\s+)?(?:mark|set)\s+(?:the\s+)?(?:task\s+)?(?:as\s+)?(?:done|complete|completed|finished)$/i,
    /^(?:please\s+)?(?:complete|finish)\s+(?:the\s+)?(?:next|latest|last|current)?\s*task$/i,
  ];

  if (broadDonePatterns.some((pattern) => pattern.test(commandText))) {
    return '';
  }

  const ordinalTaskPatterns = [
    /^(?:please\s+)?(?:i|we)\s+(?:did|finished|completed|complete|finished up|got through|handled)\s+(?:the\s+)?((?:first|last|latest|most\s+recent)\s+(?:\d+|one|two|couple|both|three|few|four|five|six|seven|eight|nine|ten)|both|all|everything|tasks?\s+\d+(?:\s*(?:,|and)\s*(?:tasks?\s*)?\d+)*)\s+(?:tasks?|steps?|items?|things?)?$/i,
    /^(?:please\s+)?(?:i|we)\s+(?:am|are|'m|'re)?\s*(?:done|finished|complete|completed|through)\s+(?:with\s+)?(?:the\s+)?((?:first|last|latest|most\s+recent)\s+(?:\d+|one|two|couple|both|three|few|four|five|six|seven|eight|nine|ten)|both|all|everything|tasks?\s+\d+(?:\s*(?:,|and)\s*(?:tasks?\s*)?\d+)*)\s+(?:tasks?|steps?|items?|things?)?$/i,
    /^(?:please\s+)?(?:complete|finish|mark|set)\s+(?:the\s+)?((?:first|last|latest|most\s+recent)\s+(?:\d+|one|two|couple|both|three|few|four|five|six|seven|eight|nine|ten)|both|all|everything|tasks?\s+\d+(?:\s*(?:,|and)\s*(?:tasks?\s*)?\d+)*)\s+(?:tasks?|steps?|items?|things?)?(?:\s+(?:as\s+)?(?:done|complete|completed|finished))?$/i,
    /^(?:please\s+)?(?:tasks?|steps?|items?)\s+((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s*(?:,|and)\s*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten))*)\s+(?:are\s+)?(?:done|complete|completed|finished)$/i,
    /^(?:please\s+)?(?:complete|finish|mark|set)\s+(?:tasks?|steps?|items?|things?)\s+((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s*(?:,|and)\s*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten))*)(?:\s+(?:as\s+)?(?:done|complete|completed|finished))?$/i,
    /^(?:please\s+)?(?:i|we)\s+(?:did|finished|completed|got through|handled)\s+(?:number\s+)?((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s*(?:,|and)\s*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten))*)\s+(?:tasks?|steps?|items?|things?)?$/i,
    /^(?:please\s+)?(?:i|we)\s+(?:did|finished|completed|got through|handled)\s+(?:the\s+)?((?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)(?:\s*(?:,|and)\s*(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth))*)\s+(?:tasks?|steps?|items?|things?)?$/i,
  ];

  for (const pattern of ordinalTaskPatterns) {
    const match = commandText.match(pattern);
    const payload = match?.[1] ? cleanCommandPayload(match[1]) : '';
    if (payload) return payload;
  }

  const patterns = [
    /^(?:complete|finish)\s+(?:the\s+)?(.+?)\s+task$/i,
    /^(?:please\s+)?(?:mark|set|complete|finish)\s+(?:the\s+)?(?:task\s+)?(?:called|named|about)?\s*(.+?)\s+(?:as\s+)?(?:done|complete|completed|finished)$/i,
    /^(?:please\s+)?(?:mark|set)\s+(?:the\s+)?(?:task\s+)?(.+?)\s+(?:as\s+)?(?:done|complete|completed|finished)$/i,
    /^(?:please\s+)?(?:i|we)\s+(?:did|finished|completed|got through|handled)\s+(?:the\s+)?(?:task\s+)?(?:called|named|about)?\s*(.+)$/i,
  ];

  for (const pattern of patterns) {
    const match = commandText.match(pattern);
    const payload = match?.[1]
      ? cleanCommandPayload(match[1]).replace(/\s+tasks?$/i, '').trim()
      : '';
    if (payload) return payload;
  }

  return null;
}


function normalizeFocusSessionMode(value: string | undefined): FocusSessionMode | undefined {
  const normalized = value ? cleanCommandPayload(value).toLowerCase() : '';
  if (!normalized) return undefined;

  if (/\b(?:code|coding|development|dev|programming)\b/.test(normalized)) return 'coding';
  if (/\b(?:meeting|meetings|prep|standup|sync)\b/.test(normalized)) return 'meeting';
  if (/\b(?:plan|planning|roadmap|strategy)\b/.test(normalized)) return 'planning';
  if (/\b(?:research|search|investigation|study)\b/.test(normalized)) return 'research';
  if (/\b(?:personal|life|home)\b/.test(normalized)) return 'personal';
  if (/\b(?:general|default)\b/.test(normalized)) return 'general';

  return undefined;
}

function defaultFocusSessionTitle(mode: FocusSessionMode | undefined): string {
  switch (mode) {
    case 'coding':
      return 'Coding session';
    case 'meeting':
      return 'Meeting session';
    case 'planning':
      return 'Planning session';
    case 'research':
      return 'Research session';
    case 'personal':
      return 'Personal session';
    default:
      return 'Focus session';
  }
}

type FocusSessionIntent = {
  command:
    | 'start-focus-session'
    | 'update-focus-session'
    | 'read-focus-session'
    | 'end-focus-session'
    | 'focus-to-tasks'
    | 'summarize-focus-session'
    | 'save-focus-summary'
    | 'end-focus-with-summary'
    | 'read-last-focus-session'
    | 'read-focus-history'
    | 'resume-last-focus-session'
    | 'recap-focus-activity'
    | 'enhanced-focus-recap'
    | 'create-meeting-follow-up-tasks'
    | 'wrap-up-meeting-focus';
  focusSession?: FocusSessionCommandPayload;
  payload?: string;
  confirmation?: string;
};

function makeFocusSessionIntent(
  command: FocusSessionIntent['command'],
  focusSession?: FocusSessionCommandPayload,
  confirmation?: string,
): FocusSessionIntent {
  return {
    command,
    ...(focusSession ? { focusSession } : {}),
    ...(confirmation ? { confirmation } : {}),
  };
}

function normalizeFocusCommandPhrase(value: string): string {
  let text = value
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/[?!.,;:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^(?:hey\s+)?(?:qmeet|orb|assistant)\s+/i, '')
    .trim();

  for (let index = 0; index < 4; index += 1) {
    const collapsed = text
      .replace(/\b(the|my|our|current|active)\s+\1\b/gi, '$1')
      .replace(/^(end|stop|finish|clear|close|wrap up)\s+\1\b/i, '$1')
      .replace(/^(end|stop|finish|clear|close|wrap up)\s+(?:end|stop|finish|clear|close|wrap up)\b/i, '$1');

    if (collapsed === text) break;
    text = collapsed.trim();
  }

  return text;
}

function cleanFocusTitlePayload(value: string): string {
  return cleanCommandPayload(value)
    .replace(/\s+(?:please|thanks|thank you)$/i, '')
    .trim();
}


function splitFocusTitleAndGoal(value: string): FocusSessionCommandPayload {
  const cleaned = cleanFocusTitlePayload(value);
  const goalPatterns: Array<{
    pattern: RegExp;
    readGoal: (match: RegExpMatchArray) => string;
  }> = [
    {
      pattern: /^(.+?)\s+(?:with\s+(?:the\s+)?goal\s+(?:of|to)|goal\s+(?:is|to|of)|and\s+set\s+(?:a\s+)?goal\s+(?:to|of))\s+(.+)$/i,
      readGoal: (match) => match[2],
    },
    {
      pattern: /^(.+?)\s+(?:so\s+(?:i|we)\s+can|so\s+that\s+(?:i|we)\s+can)\s+(.+)$/i,
      readGoal: (match) => match[2],
    },
    {
      pattern: /^(.+?)\s+and\s+(tell\s+me|help\s+me|explain|figure\s+out|work\s+on)\s+(.+)$/i,
      readGoal: (match) => `${match[2]} ${match[3]}`,
    },
  ];

  for (const { pattern, readGoal } of goalPatterns) {
    const match = cleaned.match(pattern);
    const title = match?.[1] ? cleanFocusTitlePayload(match[1]) : '';
    const goal = match ? cleanFocusTitlePayload(readGoal(match)) : '';
    if (title && goal) {
      return { title, goal };
    }
  }

  return { title: cleaned };
}

function maybePersonalMode(value: string): FocusSessionMode | undefined {
  return /\bpersonal(?:ly)?\b|\bon a personal level\b/i.test(value)
    ? 'personal'
    : normalizeFocusSessionMode(value);
}

function isFocusPlanningQuestionPayload(value: string): boolean {
  return /\b(?:tell\s+me\s+how|how\s+(?:should|can|do)\s+(?:i|we)|give\s+me\s+(?:a\s+)?plan|make\s+me\s+(?:a\s+)?plan|help\s+me\s+(?:to\s+)?(?:accomplish|complete|do|execute)|accomplish\s+(?:it|this|that|my\s+focus|my\s+goal|the\s+goal|the\s+focus)|doing\s+my\s+focus|do\s+my\s+focus)\b/i.test(value);
}


function cleanVisualObservationPayload(value: string): string {
  return value
    .replace(/\s+/g, ' ')
    .replace(/^(?:that\s+)?/i, '')
    .trim()
    .replace(/^["']+|["']+$/g, '')
    .replace(/[.?!,;:]+$/g, '')
    .trim();
}

function extractVisualObservationPayload(value: string): string | null {
  const normalized = normalizeSpokenQMeet(value)
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/^(?:hey\s+)?(?:qmeet|orb|assistant)\s+/i, '')
    .trim();

  const visualObservationPatterns: RegExp[] = [
    /^(?:please\s+)?(?:note|remember|save|record|store)\s+(?:visually|as\s+(?:a\s+)?visual\s+(?:note|observation)|in\s+visual\s+context)\s+(?:that\s+)?(.+)$/i,
    /^(?:please\s+)?(?:visual\s+(?:note|observation)|visual\s+memory)\s+(?:that\s+)?(.+)$/i,
    /^(?:please\s+)?(?:add|save|record|store)\s+(?:a\s+)?(?:manual\s+)?visual\s+(?:observation|note)\s+(?:that\s+)?(.+)$/i,
    /^(?:please\s+)?(?:i(?:'m|\s+am)|we(?:'re|\s+are))\s+(?:looking\s+at|seeing|viewing)\s+(.+)$/i,
    /^(?:please\s+)?(?:the\s+camera\s+should\s+remember|remember\s+from\s+the\s+camera)\s+(?:that\s+)?(.+)$/i,
  ];

  for (const pattern of visualObservationPatterns) {
    const match = normalized.match(pattern);
    const payload = match?.[1] ? cleanVisualObservationPayload(match[1]) : '';
    if (payload) return payload;
  }

  return null;
}

function extractVisualContextIntent(normalized: string): CommandMatch | null {
  const text = normalizeSpokenQMeet(normalized)
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/^(?:hey\s+)?(?:qmeet|orb|assistant)\s+/i, '')
    .trim();
  const commandText = normalizeCommandText(text);

  const linkFocusPatterns = [
    /^(?:please\s+)?(?:link|attach|pin|connect|save|add)\s+(?:the\s+|this\s+|my\s+|our\s+)?(?:last|latest|current|most\s+recent)?\s*(?:visual\s+)?(?:observation|visual\s+context|visual\s+memory|camera\s+observation|camera\s+memory|thing\s+(?:i|we)\s+saw|what\s+(?:i|we)\s+saw|what\s+you\s+saw)\s+(?:to|with|into|under|for)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$/i,
    /^(?:please\s+)?(?:save|pin|attach|link)\s+(?:what\s+)?(?:you\s+)?(?:last\s+)?(?:saw|observed|captured)\s+(?:to|with|into|under|for)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$/i,
    /^(?:please\s+)?(?:use|keep)\s+(?:the\s+|this\s+)?(?:visual\s+context|camera\s+observation|last\s+observation)\s+(?:for|with|under)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$/i,
  ];
  if (linkFocusPatterns.some((pattern) => pattern.test(commandText))) {
    return {
      command: 'link-visual-to-focus',
      confirmation: CONFIRMATIONS['link-visual-to-focus'],
    };
  }

  const focusVisualPatterns = [
    /^(?:please\s+)?(?:show|read|list|display|summarize|recap|review)\s+(?:the\s+|my\s+|our\s+)?(?:visuals|visual\s+observations|visual\s+context|camera\s+observations|camera\s+context)\s+(?:for|linked\s+to|related\s+to|under|with)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$/i,
    /^(?:please\s+)?(?:what\s+)?(?:visual\s+context|visuals|camera\s+context|things\s+(?:i|we)\s+saw)\s+(?:is|are)?\s*(?:linked\s+to|related\s+to|saved\s+for|under)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$/i,
    /^(?:please\s+)?(?:show|read|list|summarize)?\s*(?:focus\s+visuals|focus\s+visual\s+context|focus\s+camera\s+context)$/i,
    /^(?:please\s+)?(?:what\s+did\s+(?:you|qmeet)\s+see|what\s+was\s+seen)\s+(?:for|during|in)\s+(?:the\s+|my\s+|our\s+|current\s+|active\s+)?(?:focus|focus\s+session|session)$/i,
  ];
  if (focusVisualPatterns.some((pattern) => pattern.test(commandText))) {
    return {
      command: 'read-focus-visuals',
      confirmation: CONFIRMATIONS['read-focus-visuals'],
    };
  }

  const clearPatterns = [
    /^(?:please\s+)?(?:clear|reset|wipe|forget|delete)\s+(?:the\s+|my\s+|all\s+)?(?:visual\s+context|visual\s+memory|visual\s+observations|camera\s+context|camera\s+memory)$/i,
    /^(?:please\s+)?(?:clear|reset|wipe|forget|delete)\s+(?:everything\s+)?(?:i|we)\s+(?:saw|looked\s+at|were\s+looking\s+at)$/i,
  ];
  if (clearPatterns.some((pattern) => pattern.test(commandText))) {
    return {
      command: 'clear-visual-context',
      confirmation: CONFIRMATIONS['clear-visual-context'],
    };
  }

  const deleteLastPatterns = [
    /^(?:please\s+)?(?:delete|remove|forget|erase)\s+(?:the\s+)?(?:last|latest|most\s+recent)\s+(?:visual\s+)?(?:observation|visual\s+note|visual\s+memory|camera\s+observation)$/i,
    /^(?:please\s+)?(?:delete|remove|forget|erase)\s+(?:what\s+)?(?:i|we)\s+(?:just\s+)?(?:saw|looked\s+at)$/i,
  ];
  if (deleteLastPatterns.some((pattern) => pattern.test(commandText))) {
    return {
      command: 'delete-last-visual-observation',
      confirmation: CONFIRMATIONS['delete-last-visual-observation'],
    };
  }

  const summarizePatterns = [
    /^(?:please\s+)?(?:summarize|recap|review)\s+(?:the\s+|my\s+|our\s+)?(?:visual\s+context|visual\s+memory|visual\s+observations|camera\s+context|camera\s+memory)$/i,
    /^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:a\s+)?(?:visual|camera)\s+(?:summary|recap|review)$/i,
  ];
  if (summarizePatterns.some((pattern) => pattern.test(commandText))) {
    return {
      command: 'read-visual-context',
      confirmation: CONFIRMATIONS['read-visual-context'],
      payload: 'summary',
    };
  }

  const historyPatterns = [
    /^(?:please\s+)?(?:show|read|list|display|open)\s+(?:the\s+|my\s+|our\s+)?(?:recent\s+|saved\s+|all\s+)?(?:visual\s+observations|visual\s+history|camera\s+observations|camera\s+history|things\s+(?:i|we)\s+saw)$/i,
    /^(?:please\s+)?(?:what\s+(?:have|did)\s+(?:i|we)\s+(?:seen|looked\s+at|saved\s+visually))$/i,
    /^(?:visual\s+history|camera\s+history|visual\s+observations)$/i,
  ];
  if (historyPatterns.some((pattern) => pattern.test(commandText))) {
    return {
      command: 'read-visual-context',
      confirmation: CONFIRMATIONS['read-visual-context'],
      payload: 'history',
    };
  }

  const lastPatterns = [
    /^(?:please\s+)?(?:what\s+(?:was|is)|show|read|tell\s+me|display)\s+(?:the\s+|my\s+|our\s+)?(?:last|latest|most\s+recent)\s+(?:visual\s+observation|visual\s+note|visual\s+memory|camera\s+observation|camera\s+memory|thing\s+(?:i|we)\s+saw)$/i,
    /^(?:please\s+)?(?:what\s+(?:did|do)\s+(?:i|we)\s+(?:last\s+)?(?:see|look\s+at)|what\s+(?:am|are)\s+(?:i|we)\s+looking\s+at|what\s+did\s+you\s+last\s+see|what\s+was\s+the\s+last\s+thing\s+you\s+saw)$/i,
    /^(?:please\s+)?(?:last|latest)\s+(?:visual|camera)\s+(?:observation|memory|note)$/i,
  ];
  if (lastPatterns.some((pattern) => pattern.test(commandText))) {
    return {
      command: 'read-visual-context',
      confirmation: CONFIRMATIONS['read-visual-context'],
      payload: 'last',
    };
  }

  const readPatterns = [
    /^(?:please\s+)?(?:what\s+(?:was|is)|show|read|tell\s+me|display|open)\s+(?:the\s+|my\s+|our\s+)?(?:current\s+)?(?:visual\s+context|visual\s+memory|camera\s+context|camera\s+memory)$/i,
    /^(?:visual\s+context|visual\s+memory|camera\s+context)$/i,
  ];
  if (readPatterns.some((pattern) => pattern.test(commandText))) {
    return {
      command: 'read-visual-context',
      confirmation: CONFIRMATIONS['read-visual-context'],
    };
  }

  return null;
}



function normalizePrepTimeText(value: string): string {
  return value
    .replace(/^(\d{1,2})\s+(\d{2})\b/, '$1:$2')
    .replace(/\bp\s*\.?\s*m\.?\b/gi, 'PM')
    .replace(/\ba\s*\.?\s*m\.?\b/gi, 'AM')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractAdHocPreparationFocusIntent(normalized: string): CommandMatch | null {
  const text = normalizeFocusCommandPhrase(normalized);
  const lowered = text.toLowerCase();

  const genericPrepPatterns = [
    /^(?:yes\s+|yeah\s+|yep\s+|sure\s+|ok(?:ay)?\s+)?(?:please\s+)?(?:start|begin|create|open)\s+(?:that\s+|the\s+|my\s+)?(?:focus\s+)?(?:preparation|prep)\s+(?:block|focus|session)$/i,
    /^(?:yes\s+|yeah\s+|yep\s+|sure\s+|ok(?:ay)?\s+)?(?:please\s+)?(?:start|begin|create|open)\s+(?:that\s+|the\s+|my\s+)?(?:focus\s+block|prep\s+block|prep\s+session)$/i,
    /^(?:yes\s+|yeah\s+|yep\s+|sure\s+|ok(?:ay)?\s+)?(?:you\s+can\s+)?(?:start|begin|create|open)\s+(?:that\s+|the\s+|my\s+)?(?:focus\s+)?(?:preparation|prep)\s+(?:block|focus|session)$/i,
  ];
  if (genericPrepPatterns.some((pattern) => pattern.test(text))) {
    return {
      command: 'start-focus-session',
      confirmation: 'Started meeting prep focus session: Preparation block.',
      focusSession: {
        title: 'Preparation block',
        mode: 'meeting',
        goal: 'Prepare for the upcoming appointment, meeting, or event. Review details, gather notes, prepare questions, and identify next steps.',
      },
    };
  }

  const hasPrepIntent = /\b(?:need|needs|want|wants|have|has|should|must)\s+to\s+(?:prepare|prep|get\s+ready)|\b(?:prepare|prep|get\s+ready)\s+(?:for|before)\b/i.test(text);
  const eventWordMatch = text.match(/\b(appointment|meeting|event|call)\b/i);
  if (!hasPrepIntent || !eventWordMatch) return null;

  const timeMatch = text.match(/\b(?:at|around|by|before)\s+((?:\d{1,2}:\d{2}|\d{1,2}\s+\d{2}|\d{1,2})\s*(?:a\s*\.?\s*m\.?|p\s*\.?\s*m\.?|am|pm)?)\b/i);
  const dayMatch = text.match(/\b(today|tomorrow)\b/i);
  const eventWord = eventWordMatch[1].toLowerCase();
  const timeText = timeMatch?.[1] ? normalizePrepTimeText(timeMatch[1]) : '';
  const dayText = dayMatch?.[1] ? dayMatch[1].toLowerCase() : '';
  const titleParts = [timeText, dayText, eventWord].filter(Boolean);
  const title = titleParts.length ? titleParts.join(' ') : `${eventWord} preparation`;
  const goalParts = [`Prepare for the ${eventWord}`];
  if (timeText) goalParts.push(`at ${timeText}`);
  if (dayText) goalParts.push(dayText);
  const goal = `${goalParts.join(' ')}. Review details, gather notes, prepare questions, and identify next steps.`;

  return {
    command: 'start-focus-session',
    confirmation: `Started meeting prep focus session: ${title}.`,
    focusSession: {
      title,
      mode: 'meeting',
      goal,
    },
  };
}

function extractCalendarFocusIntent(normalized: string): CommandMatch | null {
  const text = normalizeFocusCommandPhrase(normalized);

  const preparePatterns = [
    /^(?:please\s+)?(?:prepare|prep)\s+(?:me\s+)?(?:for\s+)?(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$/i,
    /^(?:please\s+)?(?:start|begin|create|open)\s+(?:a\s+)?(?:focus|focus\s+session|meeting\s+prep\s+focus|prep\s+session)\s+(?:for|from|based\s+on)\s+(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$/i,
    /^(?:please\s+)?(?:start|begin|create|open)\s+(?:a\s+)?(?:focus|focus\s+session|meeting\s+prep\s+focus|prep\s+session)\s+(?:for|from|based\s+on)\s+(?:the\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)\s+(?:on|in)\s+(?:my\s+)?(?:calendar|schedule|agenda)$/i,
    /^(?:please\s+)?(?:what\s+should\s+i\s+work\s+on|what\s+should\s+i\s+prepare|what\s+do\s+i\s+need\s+to\s+prepare)\s+(?:before|for)\s+(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$/i,
    /^(?:please\s+)?(?:summarize|review|check)\s+(?:my\s+)?(?:schedule|calendar|agenda)\s+and\s+(?:focus\s+)?(?:priorities|priority|prep|preparation)$/i,
    /^(?:please\s+)?(?:calendar|meeting|event)\s+(?:focus|prep|preparation)$/i,
    /^(?:please\s+)?(?:focus|prep|prepare)\s+(?:for\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$/i,
    /^(?:please\s+)?(?:make|create|add|generate|build)\s+(?:prep|preparation|meeting\s+prep|calendar\s+prep)?\s*tasks?\s+(?:for|from|based\s+on)\s+(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)$/i,
    /^(?:please\s+)?(?:turn|convert|break\s+down)\s+(?:my\s+)?(?:next|upcoming)\s+(?:calendar\s+)?(?:event|meeting|appointment|call)\s+(?:into|in\s+to)\s+(?:prep\s+)?tasks?$/i,
    /^(?:please\s+)?(?:next|upcoming)\s+(?:meeting|event|calendar\s+event|appointment|call)\s+(?:prep\s+)?tasks?$/i,
  ];

  if (preparePatterns.some((pattern) => pattern.test(text))) {
    return {
      command: 'prepare-calendar-focus',
      confirmation: CONFIRMATIONS['prepare-calendar-focus'],
      focusSession: { mode: 'meeting' },
    };
  }

  return null;
}

function extractFocusSessionIntent(normalized: string): FocusSessionIntent | null {
  const focusText = normalizeFocusCommandPhrase(normalized);


  const meetingWrapPatterns = [
    /^(?:please\s+)?(?:wrap\s+up|close\s+out|finish|end)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|meeting\s+prep|call|appointment)(?:\s+(?:with|and\s+save|and\s+write)\s+(?:a\s+)?(?:summary|recap|note|notes))?$/i,
    /^(?:please\s+)?(?:end|finish|wrap\s+up|close)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment)\s+(?:with\s+)?(?:a\s+)?(?:summary|recap|note|notes)$/i,
    /^(?:please\s+)?(?:summarize|recap|save\s+(?:a\s+)?summary\s+of|save)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment)\s+(?:and\s+)?(?:end|finish|close|wrap\s+up)(?:\s+it)?$/i,
    /^(?:please\s+)?(?:save\s+(?:a\s+)?meeting\s+(?:summary|recap|note|notes)\s+and\s+end|save\s+and\s+end\s+(?:the\s+)?meeting)$/i,
    /^(?:please\s+)?(?:meeting|call|appointment)\s+(?:wrap\s+up|closeout|close\s+out)$/i,
  ];
  if (meetingWrapPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'wrap-up-meeting-focus',
      undefined,
      'Wrapping up meeting focus with summary and follow-up tasks.',
    );
  }

  const meetingFollowUpPatterns = [
    /^(?:please\s+)?(?:create|make|add|generate|build|capture|save)\s+(?:meeting\s+)?(?:follow\s*-?\s*up|followup|action)\s+(?:tasks|task\s+list|items|item|actions|next\s+steps|steps)\s+(?:for|from|based\s+on)?\s*(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment|focus|session)?$/i,
    /^(?:please\s+)?(?:turn|convert|break\s+down)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment)\s+(?:into|in\s+to)\s+(?:follow\s*-?\s*up\s+)?(?:tasks|task\s+list|action\s+items|next\s+steps|steps|checklist)$/i,
    /^(?:please\s+)?(?:meeting|call|appointment)\s+(?:follow\s*-?\s*up|followup|action)\s+(?:tasks|items|next\s+steps)$/i,
    /^(?:please\s+)?(?:what\s+are|show|list|create)\s+(?:the\s+)?(?:follow\s*-?\s*ups|followups|action\s+items|next\s+steps)\s+(?:from|for)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|call|appointment)$/i,
  ];
  if (meetingFollowUpPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'create-meeting-follow-up-tasks',
      undefined,
      'Creating meeting follow-up tasks.',
    );
  }

  const saveMeetingSummaryPatterns = [
    /^(?:please\s+)?(?:save|store|remember|write)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|call|appointment)\s+(?:as|to|in)\s+(?:a\s+)?(?:note|notes|memory|summary)$/i,
    /^(?:please\s+)?(?:save|store|remember|write)\s+(?:a\s+)?(?:meeting\s+)?(?:summary|recap|note|notes)\s+(?:of|for)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|call|appointment)?$/i,
    /^(?:please\s+)?(?:save|store|remember|write)\s+(?:the\s+)?(?:meeting|call|appointment)\s+(?:summary|recap|notes?)(?:\s+(?:as|to|in)\s+(?:a\s+)?(?:note|notes|memory))?$/i,
    /^(?:please\s+)?(?:save|write)\s+(?:meeting\s+)?notes$/i,
  ];
  if (saveMeetingSummaryPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'save-focus-summary',
      undefined,
      'Saving meeting summary note.',
    );
  }

  const summarizeMeetingPatterns = [
    /^(?:please\s+)?(?:summarize|recap|review)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|meeting\s+focus|meeting\s+session|call|appointment)$/i,
    /^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:a\s+)?(?:meeting|call|appointment)\s+(?:summary|recap|review)$/i,
    /^(?:please\s+)?(?:what\s+happened|what\s+changed|what\s+did\s+(?:i|we)\s+do)\s+(?:in|during|for)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:meeting|call|appointment)$/i,
  ];
  if (summarizeMeetingPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'summarize-focus-session',
      undefined,
      'Summarizing meeting focus.',
    );
  }

  const forceEndPatterns = [
    /^(?:please\s+)?(?:end|finish|stop|close|clear|discard)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|focus\s+mode)\s+(?:anyway|without\s+(?:saving|a\s+summary|summary|a\s+note|note))$/i,
    /^(?:please\s+)?(?:end|finish|stop|close|clear|discard)\s+(?:anyway|without\s+(?:saving|a\s+summary|summary|a\s+note|note))$/i,
    /^(?:please\s+)?(?:end|finish|stop|close|clear|discard)\s+(?:it|this|that)\s+(?:anyway|without\s+(?:saving|a\s+summary|summary|a\s+note|note))$/i,
    /^(?:please\s+)?(?:do\s+not|don't)\s+save\s+(?:a\s+)?(?:summary|note)\s+(?:and\s+)?(?:end|finish|stop|close)\s+(?:the\s+)?(?:focus|session)?$/i,
    /^(?:please\s+)?(?:skip|discard)\s+(?:the\s+)?(?:summary|note)\s+(?:and\s+)?(?:end|finish|stop|close)\s+(?:the\s+)?(?:focus|session)?$/i,
  ];
  if (forceEndPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'end-focus-session',
      { forceEnd: true },
      'Ending focus session without saving a summary.',
    );
  }

  const endPatterns = [
    /^(?:please\s+)?(?:end|stop|clear|close|leave|exit|finish|wrap\s+up)\s+(?:(?:the|my|our|current|active)\s+)*(?:(?:general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)?(?:focus|focus\s+session|active\s+session|session|focus\s+mode)$/i,
    /^(?:please\s+)?(?:end|stop|clear|close|leave|exit|finish|wrap\s+up)\s+(?:(?:the|my|our|current|active|this|that)\s+)*(?:(?:general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)?(?:focus|focus\s+session|active\s+session|session|focus\s+mode|matter|topic|work|thing)$/i,
    /^(?:please\s+)?(?:i(?:'m|\s+am)|we(?:'re|\s+are))\s+(?:done|finished|complete|through)\s+(?:with\s+)?(?:(?:the|my|our|current|active|this|that)\s+)*(?:(?:general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)?(?:focus|focus\s+session|active\s+session|session|focus\s+mode|matter|topic|work|thing)$/i,
    /^(?:please\s+)?(?:we\s+are|we're|i\s+am|i'm)\s+(?:done|finished|complete|through)\s+(?:with\s+)?(?:this|that|the|current)\s+(?:matter|topic|work|thing)$/i,
    /^(?:please\s+)?(?:that|this)\s+(?:focus|session|matter|topic|work|thing)\s+(?:is\s+)?(?:done|finished|complete|over)$/i,
  ];
  if (endPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent('end-focus-session');
  }


  const endWithSummaryPatterns = [
    /^(?:please\s+)?(?:end|finish|wrap\s+up|close)\s+(?:with|and\s+save|and\s+write)\s+(?:a\s+)?(?:summary|recap|note)$/i,
    /^(?:please\s+)?(?:end|finish|wrap\s+up|close)\s+(?:and\s+)?(?:summarize|recap|save\s+(?:a\s+)?summary|save)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|matter|topic|work|thing)?$/i,
    /^(?:please\s+)?(?:summarize|recap|save\s+(?:a\s+)?summary\s+of|save)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session)\s+(?:and\s+)?(?:end|finish|close|wrap\s+up)(?:\s+it)?$/i,
    /^(?:please\s+)?(?:summarize|recap)\s+(?:and\s+)?(?:end|finish|close|wrap\s+up)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session)$/i,
    /^(?:please\s+)?(?:end|finish|wrap\s+up|close)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session)\s+(?:with\s+)?(?:a\s+)?(?:summary|recap)$/i,
    /^(?:please\s+)?(?:save\s+(?:a\s+)?summary\s+and\s+end|save\s+and\s+end)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session)?$/i,
  ];
  if (endWithSummaryPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'end-focus-with-summary',
      undefined,
      'Ending focus session with summary.',
    );
  }

  const saveSummaryPatterns = [
    /^(?:please\s+)?(?:save|store|remember|write)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session)\s+(?:as|to|in)\s+(?:a\s+)?(?:note|notes|memory|summary)$/i,
    /^(?:please\s+)?(?:save|store|remember|write)\s+(?:a\s+)?(?:summary|recap)\s+(?:of|for)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session)$/i,
    /^(?:please\s+)?(?:save|store|remember|write)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|session)\s+(?:summary|recap)(?:\s+(?:as|to|in)\s+(?:a\s+)?(?:note|notes|memory))?$/i,
    /^(?:please\s+)?(?:save|store|remember)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:session|focus)(?:\s+to\s+memory)?$/i,
  ];
  if (saveSummaryPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'save-focus-summary',
      undefined,
      'Saving focus summary.',
    );
  }

  const summarizePatterns = [
    /^(?:please\s+)?(?:summarize|recap|review)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|matter|topic|work|thing)$/i,
    /^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:a\s+)?(?:focus|session)\s+(?:summary|recap|review)$/i,
    /^(?:please\s+)?(?:what\s+did\s+i\s+do|what\s+did\s+we\s+do|what\s+happened|what\s+changed)\s+(?:in|during|for)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session)$/i,
    /^(?:focus|session)\s+(?:summary|recap|review)$/i,
  ];
  if (summarizePatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'summarize-focus-session',
      undefined,
      'Summarizing focus session.',
    );
  }



  const enhancedFocusRecapPatterns: Array<{ pattern: RegExp; payload: string; confirmation: string }> = [
    {
      pattern: /^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:an?\s+)?(?:ai|smart|enhanced|better|polished|natural|intelligent)\s+(?:focus|work|activity|progress)?\s*(?:recap|summary|review)(?:\s+(?:(?:for|of)\s+)?(today|yesterday|this\s+week|recent(?:\s+work|\s+activity|\s+progress)?))?$/i,
      payload: 'enhanced-recent',
      confirmation: 'Preparing enhanced focus recap.',
    },
    {
      pattern: /^(?:please\s+)?(?:summarize|recap|review)\s+(?:my|our)\s+(?:recent\s+)?progress(?:\s+(today|yesterday|this\s+week))?$/i,
      payload: 'enhanced-recent',
      confirmation: 'Preparing enhanced progress recap.',
    },
    {
      pattern: /^(?:please\s+)?(?:what\s+should\s+(?:i|we)\s+focus\s+on\s+next|what\s+should\s+(?:i|we)\s+do\s+next|what\s+is\s+the\s+next\s+priority|suggest\s+(?:my|our)?\s*(?:next\s+)?priority|suggest\s+next\s+steps)$/i,
      payload: 'next-priority',
      confirmation: 'Preparing focus recommendations.',
    },
    {
      pattern: /^(?:please\s+)?(?:give\s+me\s+|make\s+me\s+|create\s+)?(?:a\s+)?(?:daily|weekly)\s+(?:work|focus|activity|progress)\s+(?:recap|summary|review)\s+(?:with\s+)?(?:recommendations|next\s+steps|priorities)$/i,
      payload: 'enhanced-recent',
      confirmation: 'Preparing enhanced focus recap.',
    },
  ];
  for (const { pattern, payload, confirmation } of enhancedFocusRecapPatterns) {
    const match = focusText.match(pattern);
    if (match) {
      const explicitWindow = match[1]
        ? match[1].replace(/\s+/g, '-').toLowerCase()
        : payload;
      return {
        command: 'enhanced-focus-recap',
        payload: explicitWindow,
        confirmation,
      };
    }
  }

  const focusRecapPatterns: Array<{ pattern: RegExp; payload: string; confirmation: string }> = [
    {
      pattern: /^(?:please\s+)?(?:summarize|recap|review)\s+(?:what\s+)?(?:i|we)\s+(?:worked\s+on|focused\s+on|did|accomplished)\s+today$/i,
      payload: 'today',
      confirmation: "Recapping today\'s focus activity.",
    },
    {
      pattern: /^(?:please\s+)?(?:what\s+did|what\s+have)\s+(?:i|we)\s+(?:work\s+on|focus\s+on|do|accomplish)\s+today$/i,
      payload: 'today',
      confirmation: "Recapping today\'s focus activity.",
    },
    {
      pattern: /^(?:please\s+)?(?:today(?:'s)?\s+)?(?:focus|work|activity)\s+(?:recap|summary|review)$/i,
      payload: 'today',
      confirmation: "Recapping today\'s focus activity.",
    },
    {
      pattern: /^(?:please\s+)?(?:summarize|recap|review)\s+(?:what\s+)?(?:i|we)\s+(?:worked\s+on|focused\s+on|did|accomplished)\s+yesterday$/i,
      payload: 'yesterday',
      confirmation: "Recapping yesterday\'s focus activity.",
    },
    {
      pattern: /^(?:please\s+)?(?:what\s+did|what\s+have)\s+(?:i|we)\s+(?:work\s+on|focus\s+on|do|accomplish)\s+yesterday$/i,
      payload: 'yesterday',
      confirmation: "Recapping yesterday\'s focus activity.",
    },
    {
      pattern: /^(?:please\s+)?(?:yesterday(?:'s)?\s+)?(?:focus|work|activity)\s+(?:recap|summary|review)$/i,
      payload: 'yesterday',
      confirmation: "Recapping yesterday\'s focus activity.",
    },
    {
      pattern: /^(?:please\s+)?what\s+changed\s+since\s+yesterday$/i,
      payload: 'since-yesterday',
      confirmation: 'Recapping what changed since yesterday.',
    },
    {
      pattern: /^(?:please\s+)?(?:summarize|recap|review)\s+(?:my|our)?\s*(?:recent\s+)?(?:focus|focuses|focus\s+sessions|work|activity)$/i,
      payload: 'recent',
      confirmation: 'Recapping recent focus activity.',
    },
    {
      pattern: /^(?:please\s+)?what\s+did\s+(?:i|we)\s+focus\s+on\s+recently$/i,
      payload: 'recent',
      confirmation: 'Recapping recent focus activity.',
    },
    {
      pattern: /^(?:please\s+)?(?:what\s+have|what\s+did)\s+(?:i|we)\s+been\s+(?:working|focusing)\s+on\s+recently$/i,
      payload: 'recent',
      confirmation: 'Recapping recent focus activity.',
    },
    {
      pattern: /^(?:please\s+)?(?:daily|weekly|recent)\s+(?:focus|work|activity)\s+(?:recap|summary|review)$/i,
      payload: 'recent',
      confirmation: 'Recapping recent focus activity.',
    },
  ];
  for (const { pattern, payload, confirmation } of focusRecapPatterns) {
    if (pattern.test(focusText)) {
      return {
        command: 'recap-focus-activity',
        payload,
        confirmation,
      };
    }
  }

  const focusHistoryPatterns = [
    /^(?:please\s+)?(?:show|list|read|display|open)\s+(?:my\s+|our\s+)?(?:recent\s+)?(?:focus\s+)?(?:history|sessions|focus\s+sessions)$/i,
    /^(?:please\s+)?(?:show|list|read|display|open)\s+(?:my\s+|our\s+)?recent\s+(?:focuses|focus\s+sessions|sessions)$/i,
    /^(?:please\s+)?(?:what\s+(?:are|were)\s+)?(?:my\s+|our\s+)?recent\s+(?:focuses|focus\s+sessions|sessions)(?:\s+again)?$/i,
    /^(?:focus|session)\s+history$/i,
    /^(?:recent\s+focus|recent\s+focuses|recent\s+sessions|recent\s+focus\s+sessions)$/i,
    /^(?:please\s+)?what\s+(?:have|were)\s+(?:i|we)\s+been\s+working\s+on(?:\s+recently)?$/i,
  ];
  if (focusHistoryPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'read-focus-history',
      undefined,
      'Reading recent focus sessions.',
    );
  }

  const lastFocusPatterns = [
    /^(?:please\s+)?(?:what\s+was|what\s+were|show|read|tell\s+me\s+about|display)\s+(?:my\s+|our\s+)?(?:last|latest|previous|most\s+recent)\s+(?:focus|focus\s+session|session)$/i,
    /^(?:please\s+)?(?:what\s+did\s+(?:i|we)\s+focus\s+on\s+last|what\s+was\s+(?:i|we)\s+focused\s+on\s+last)$/i,
    /^(?:please\s+)?(?:what\s+was\s+(?:i|we)\s+working\s+on\s+(?:earlier|before|previously|last))$/i,
    /^(?:last|latest|previous|most\s+recent)\s+(?:focus|focus\s+session|session)$/i,
  ];
  if (lastFocusPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'read-last-focus-session',
      undefined,
      'Reading last focus session.',
    );
  }

  const resumeFocusPatterns: Array<{
    pattern: RegExp;
    read: (match: RegExpMatchArray) => FocusSessionCommandPayload | undefined;
  }> = [
    {
      pattern: /^(?:please\s+)?(?:resume|restart|continue|reopen|restore)\s+(?:my\s+|our\s+|the\s+)?(?:last|latest|previous|most\s+recent)\s+(?:(general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)?(?:focus|focus\s+session|session)$/i,
      read: (match) => {
        const mode = normalizeFocusSessionMode(match[1]);
        return mode ? { mode } : undefined;
      },
    },
    {
      pattern: /^(?:please\s+)?(?:start|open)\s+(?:my\s+|our\s+|the\s+)?(?:last|latest|previous|most\s+recent)\s+(?:(general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)?(?:focus|focus\s+session|session)\s+(?:again|back\s+up)$/i,
      read: (match) => {
        const mode = normalizeFocusSessionMode(match[1]);
        return mode ? { mode } : undefined;
      },
    },
    {
      pattern: /^(?:please\s+)?(?:resume|restart|continue|reopen|restore)\s+(?:(general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)(?:focus|focus\s+session|session)$/i,
      read: (match) => {
        const mode = normalizeFocusSessionMode(match[1]);
        return mode ? { mode } : undefined;
      },
    },
  ];
  for (const { pattern, read } of resumeFocusPatterns) {
    const match = focusText.match(pattern);
    if (match) {
      const payload = read(match);
      const modeText = payload?.mode ? `${payload.mode} ` : '';
      return makeFocusSessionIntent(
        'resume-last-focus-session',
        payload,
        `Resuming last ${modeText}focus session.`,
      );
    }
  }

  const readPatterns = [
    /^(?:what(?:'s|\s+is)|what\s+is)\s+(?:the\s+|my\s+|our\s+)?(?:current\s+|active\s+)?focus(?:\s+session)?$/i,
    /^(?:what\s+am\s+i\s+focused\s+on(?:\s+right\s+now)?|what\s+are\s+we\s+focused\s+on(?:\s+right\s+now)?|what\s+are\s+we\s+focusing\s+on(?:\s+right\s+now)?|what\s+is\s+my\s+focus\s+right\s+now|what\s+am\s+i\s+supposed\s+to\s+be\s+working\s+on|what\s+should\s+i\s+be\s+working\s+on)$/i,
    /^(?:please\s+)?(?:read|show|tell\s+me|summarize|display)\s+(?:the\s+|my\s+|our\s+)?(?:current\s+|active\s+)?(?:focus|focus\s+session|active\s+session)$/i,
    /^(?:focus status|current focus|active focus|my focus|our focus|what's my focus|what's our focus|active session|session status)$/i,
  ];
  if (readPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent('read-focus-session');
  }


  const focusToTasksPatterns = [
    /^(?:please\s+)?(?:turn|convert|make|create)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|goal)\s+(?:into|to)\s+(?:tasks|task\s+list|action\s+items|next\s+steps|steps|checklist)$/i,
    /^(?:please\s+)?(?:make|create|add|generate)\s+(?:tasks|a\s+task\s+list|action\s+items|next\s+steps|steps|a\s+checklist)\s+(?:for|from|based\s+on)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|goal)$/i,
    /^(?:please\s+)?(?:break|split)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|goal)\s+(?:into|down\s+into)\s+(?:tasks|steps|next\s+steps|action\s+items)$/i,
    /^(?:can|could|would)\s+(?:you|we)\s+(?:please\s+)?(?:break|split|turn|convert)\s+(?:it|this|that|these|the\s+work)?\s*(?:into|down\s+into|to)\s+(?:(?:a\s+)?(?:task\s+list|checklist)|tasks|steps|next\s+steps|action\s+items)$/i,
    /^(?:please\s+)?(?:add|save)\s+(?:tasks|next\s+steps|action\s+items)\s+(?:for|from)\s+(?:(?:this|the|my|our|current|active)\s+)*(?:focus|focus\s+session|active\s+session|session|goal)$/i,
    /^(?:please\s+)?(?:turn|convert)\s+(?:it|this|that)\s+(?:into|to)\s+(?:tasks|task\s+list|action\s+items|next\s+steps|steps|checklist)$/i,
  ];
  if (focusToTasksPatterns.some((pattern) => pattern.test(focusText))) {
    return makeFocusSessionIntent(
      'focus-to-tasks',
      undefined,
      'Turning focus into tasks.',
    );
  }

  const modeShortcutMatch = focusText.match(
    /^(general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+(?:focus|focus\s+session|session|mode)$/i,
  );
  if (modeShortcutMatch) {
    const mode = normalizeFocusSessionMode(modeShortcutMatch[1]);
    if (mode) {
      const title = defaultFocusSessionTitle(mode);
      return makeFocusSessionIntent(
        'start-focus-session',
        { title, mode },
        `Started ${mode} focus session: ${title}`,
      );
    }
  }

  const goalPatterns = [
    /^(?:please\s+)?(?:set|change|update)\s+(?:a\s+|the\s+|my\s+|our\s+)?(?:focus\s+)?goal\s+(?:to|as|on)\s+(.+)$/i,
    /^(?:please\s+)?(?:let(?:'s|\s+us)|lets)\s+set\s+(?:a\s+|the\s+|my\s+|our\s+)?(?:focus\s+)?goal\s+(?:to|as|on)\s+(.+)$/i,
    /^(?:please\s+)?(?:my|our|the)?\s*goal\s+(?:is|should\s+be|should\s+be\s+to)\s+(.+)$/i,
    /^(?:please\s+)?(?:make|set)\s+(?:it|this|the\s+focus)\s+(?:my\s+|our\s+)?goal\s+(?:to|as)\s+(.+)$/i,
  ];
  for (const pattern of goalPatterns) {
    const match = focusText.match(pattern);
    const goal = match?.[1] ? cleanFocusTitlePayload(match[1]) : '';
    if (goal) {
      return makeFocusSessionIntent(
        'update-focus-session',
        { goal },
        `Updated focus goal: ${goal}`,
      );
    }
  }

  const titleUpdatePatterns = [
    /^(?:please\s+)?(?:rename|retitle)\s+(?:the\s+)?(?:focus|focus\s+session|active\s+session)\s+(?:to|as|called|named)\s+(.+)$/i,
    /^(?:please\s+)?(?:set|change|update|make|switch)\s+(?:a\s+|the\s+|my\s+|our\s+|current\s+|active\s+)*(?:focus|focus\s+session|active\s+session)\s+(?:to|on|about|around|as)\s+(.+)$/i,
    /^(?:please\s+)?(?:set|change|update)\s+(?:the\s+)?(?:focus|session)\s+title\s+(?:to|as)\s+(.+)$/i,
    /^(?:please\s+)?(?:focus|refocus)\s+(?:me\s+|us\s+)?(?:on|around|about)\s+(.+)$/i,
    /^(?:please\s+)?(?:let(?:'s|\s+us)|lets)\s+focus\s+(?:on|around|about)\s+(.+)$/i,
    /^(?:please\s+)?(?:i\s+want\s+to|i\s+need\s+to|we\s+should|we\s+need\s+to|we\s+want\s+to)\s+focus\s+(?:on|around|about)\s+(.+)$/i,
    /^(?:please\s+)?(?:my|our|the|current)\s+focus\s+(?:is|should\s+be)\s+(.+)$/i,
  ];
  for (const pattern of titleUpdatePatterns) {
    const match = focusText.match(pattern);
    const title = match?.[1] ? cleanFocusTitlePayload(match[1]) : '';
    if (title && !isFocusPlanningQuestionPayload(title)) {
      const splitPayload = splitFocusTitleAndGoal(title);
      const mode = maybePersonalMode(splitPayload.title ?? '') ?? maybePersonalMode(splitPayload.goal ?? '');
      return makeFocusSessionIntent(
        'update-focus-session',
        { ...splitPayload, ...(mode ? { mode } : {}) },
        `Updated focus: ${splitPayload.title ?? title}`,
      );
    }
  }

  const modeUpdatePatterns = [
    /^(?:please\s+)?(?:set|change|update)\s+(?:the\s+)?(?:focus|session)\s+mode\s+(?:to|as)\s+(.+)$/i,
  ];
  for (const pattern of modeUpdatePatterns) {
    const match = focusText.match(pattern);
    const mode = normalizeFocusSessionMode(match?.[1]);
    if (mode) {
      return makeFocusSessionIntent(
        'update-focus-session',
        { mode },
        `Updated focus mode: ${mode}`,
      );
    }
  }

  const startPatterns: Array<{
    pattern: RegExp;
    read: (match: RegExpMatchArray) => FocusSessionCommandPayload | null;
  }> = [
    {
      pattern: /^(?:please\s+)?(?:start|begin|create|open)\s+(?:a\s+|the\s+)?(?:(general|coding|code|development|dev|programming|meeting|planning|research|personal)\s+)?(?:focus\s+session|focus|session|focus\s+mode)(?:\s+(?:for|on|about|around|called|named|to|with(?:\s+the)?\s+goal\s+(?:of|to))\s+(.+))?$/i,
      read: (match) => {
        const mode = normalizeFocusSessionMode(match[1]);
        const title = match[2] ? cleanFocusTitlePayload(match[2]) : defaultFocusSessionTitle(mode);
        const splitPayload = splitFocusTitleAndGoal(title);
        const titleMode = maybePersonalMode(splitPayload.title ?? '') ?? maybePersonalMode(splitPayload.goal ?? '');
        return splitPayload.title
          ? { ...splitPayload, ...(mode || titleMode ? { mode: mode ?? titleMode } : {}) }
          : null;
      },
    },
    {
      pattern: /^(?:please\s+)?(?:start|begin|create|open)\s+(?:a\s+|the\s+)?(?:focus\s+session|focus|session|focus\s+mode)\s+(?:in|as)\s+(.+?)\s+mode(?:\s+(?:for|on|about|around|to|with(?:\s+the)?\s+goal\s+(?:of|to))\s+(.+))?$/i,
      read: (match) => {
        const mode = normalizeFocusSessionMode(match[1]);
        if (!mode) return null;
        const title = match[2] ? cleanFocusTitlePayload(match[2]) : defaultFocusSessionTitle(mode);
        return { ...splitFocusTitleAndGoal(title), mode };
      },
    },
    {
      pattern: /^(?:please\s+)?(?:start|begin)\s+(?:me\s+|us\s+)?(?:focusing|working)\s+(?:on|around|about)\s+(.+)$/i,
      read: (match) => {
        const title = match[1] ? cleanFocusTitlePayload(match[1]) : '';
        if (!title) return null;
        const splitPayload = splitFocusTitleAndGoal(title);
        return splitPayload.title
          ? { ...splitPayload, mode: maybePersonalMode(splitPayload.title) ?? maybePersonalMode(splitPayload.goal ?? '') ?? 'general' }
          : null;
      },
    },
    {
      pattern: /^(?:please\s+)?(?:switch|change)\s+(?:me\s+)?to\s+(.+?)\s+mode$/i,
      read: (match) => {
        const title = cleanFocusTitlePayload(match[1]);
        const mode = normalizeFocusSessionMode(title);
        if (!mode) return null;
        return { title: title || defaultFocusSessionTitle(mode), mode };
      },
    },
    {
      pattern: /^(?:i(?:'m|\s+am)|we(?:'re|\s+are))\s+(?:currently\s+)?(?:working|focusing)\s+(?:on|about)\s+(.+)$/i,
      read: (match) => {
        const title = match[1] ? cleanFocusTitlePayload(match[1]) : '';
        return title ? { title, mode: maybePersonalMode(title) ?? 'general' } : null;
      },
    },
  ];

  for (const { pattern, read } of startPatterns) {
    const match = focusText.match(pattern);
    const focusSession = match ? read(match) : null;
    if (focusSession?.title) {
      const modeText = focusSession.mode ? `${focusSession.mode} ` : '';
      return makeFocusSessionIntent(
        'start-focus-session',
        focusSession,
        `Started ${modeText}focus session: ${focusSession.title}`,
      );
    }
  }

  return null;
}

function extractSearchPayload(normalized: string): { payload: string; confirmationPrefix: string } | null {
  const patterns: Array<{ pattern: RegExp; confirmationPrefix: string; rejectPayload?: (payload: string) => boolean }> = [
    { pattern: /^(?:please\s+)?search\s+(?:the\s+)?(?:web|internet)\s+for\s+(.+)$/i, confirmationPrefix: 'Searching the web for' },
    { pattern: /^(?:please\s+)?search\s+for\s+(.+)$/i, confirmationPrefix: 'Searching the web for' },
    { pattern: /^(?:please\s+)?search\s+(.+)$/i, confirmationPrefix: 'Searching the web for' },
    { pattern: /^(?:please\s+)?(?:web|internet)\s+search\s+(.+)$/i, confirmationPrefix: 'Searching the web for' },
    { pattern: /^(?:please\s+)?look\s+(?:this\s+)?up\s+(.+)$/i, confirmationPrefix: 'Searching the web for' },
    { pattern: /^(?:please\s+)?google\s+(.+)$/i, confirmationPrefix: 'Searching the web for' },
    {
      pattern: /^(?:please\s+)?find\s+(.+)$/i,
      confirmationPrefix: 'Searching the web for',
      rejectPayload: (payload) => /^(?:out|me|a\s+solution|a\s+way)\b/i.test(payload),
    },
  ];

  for (const { pattern, confirmationPrefix, rejectPayload } of patterns) {
    const match = normalized.match(pattern);
    const payload = match?.[1] ? cleanCommandPayload(match[1]) : '';

    if (!payload || rejectPayload?.(payload)) continue;

    return { payload, confirmationPrefix };
  }

  return null;
}


function splitCalendarTitleAndTrailingTime(rawTitle: string): { title: string; time: string } {
  const titleWithSpeechFixes = cleanCommandPayload(rawTitle)
    // Chrome speech recognition sometimes inserts "to at" / "two at" before a time.
    // Example: "called QMeet test to at 5:00" should become title "QMeet test", time "5:00".
    .replace(/\b(?:to|too|two)\s+at\s+/gi, 'at ')
    .replace(/\s+/g, ' ')
    .trim();

  const trailingTimePatterns = [
    /\s+(?:at|by)\s+((?:\d{1,2})(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|am|pm)?|noon|midnight)\s*$/i,
    /\s+(?:around|for)\s+((?:\d{1,2})(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|am|pm)?|noon|midnight)\s*$/i,
  ];

  for (const pattern of trailingTimePatterns) {
    const match = titleWithSpeechFixes.match(pattern);

    if (match?.[1]) {
      return {
        title: cleanCommandPayload(titleWithSpeechFixes.replace(pattern, '')),
        time: cleanCommandPayload(match[1]),
      };
    }
  }

  return {
    title: titleWithSpeechFixes,
    time: '',
  };
}

function normalizeCalendarTimeCandidate(rawTime: string | undefined): string {
  const cleanedTime = rawTime ? cleanCommandPayload(rawTime) : '';

  // Guard against a regex backtracking case where the parser reads the day word
  // as the time. Example: "add event today called QMeet test at 5" can
  // otherwise become time="today" and title="QMeet test".
  if (/^(?:today|tomorrow)$/i.test(cleanedTime)) {
    return '';
  }

  return cleanedTime;
}

function isAbsoluteCalendarCommandDay(value: string): value is `${number}-${number}-${number}` {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function makeCalendarCommandPayload(
  rawDay: string | undefined,
  rawTime: string | undefined,
  rawTitle: string | undefined
): CalendarCommandPayload | null {
  const dayCandidate = rawDay?.trim().toLowerCase() ?? '';
  const day: CalendarCommandDay =
    dayCandidate === 'tomorrow'
      ? 'tomorrow'
      : dayCandidate === 'today'
        ? 'today'
        : isAbsoluteCalendarCommandDay(dayCandidate)
          ? dayCandidate
          : 'today';
  const explicitTime = normalizeCalendarTimeCandidate(rawTime);
  const titleParts = splitCalendarTitleAndTrailingTime(rawTitle ?? '');
  const title = titleParts.title;
  const time = explicitTime || titleParts.time || 'Later';

  if (!title) return null;

  return {
    day,
    time,
    title,
  };
}

function extractCalendarEventPayload(normalized: string): CalendarCommandPayload | null {
  const patterns: Array<{
    pattern: RegExp;
    read: (match: RegExpMatchArray) => CalendarCommandPayload | null;
  }> = [
    // Phase 21F3 confirmation round-trip for one already-resolved absolute date.
    // Natural date language is resolved by the agent/date interpreter before this
    // parser; this only preserves the canonical YYYY-MM-DD identity across confirm.
    {
      pattern: /^(?:please\s+)?(?:add|create|schedule|make)\s+(?:an?\s+)?(?:(?:calendar|calender|calander)\s+)?(?:event|appointment|reminder|meeting)\s+(\d{4}-\d{2}-\d{2})\s+at\s+(.+?)\s+(?:called|named|titled|for|about)\s+(.+)$/i,
      read: (match) => makeCalendarCommandPayload(match[1], match[2], match[3]),
    },
    // "add event today called meeting at 5" / "add event today called meeting to at 5"
    // This must run before the broad "day/time called title" pattern below.
    {
      pattern: /^(?:please\s+)?(?:add|create|schedule|make)\s+(?:an?\s+)?(?:(?:calendar|calender|calander)\s+)?(?:event|appointment|reminder|meeting)\s+(today|tomorrow)\s+(?:called|named|titled|for|about)\s+(.+)$/i,
      read: (match) => makeCalendarCommandPayload(match[1], undefined, match[2]),
    },

    // "add event today at 3 called meeting" / "add event at 3 called meeting"
    {
      pattern: /^(?:please\s+)?(?:add|create|schedule|make)\s+(?:an?\s+)?(?:(?:calendar|calender|calander)\s+)?(?:event|appointment|reminder|meeting)\s+(?:(today|tomorrow)\s+)?at\s+(.+?)\s+(?:called|named|titled|for|about)\s+(.+)$/i,
      read: (match) => makeCalendarCommandPayload(match[1], match[2], match[3]),
    },

    // "add event called meeting today at 5"
    {
      pattern: /^(?:please\s+)?(?:add|create|schedule|make)\s+(?:an?\s+)?(?:(?:calendar|calender|calander)\s+)?(?:event|appointment|reminder|meeting)\s+(?:called|named|titled|for|about)\s+(.+?)\s+(today|tomorrow)(?:\s+(?:at|by)\s+(.+))?$/i,
      read: (match) => makeCalendarCommandPayload(match[2], match[3], match[1]),
    },

    // "add event called meeting at 5" defaults to today.
    {
      pattern: /^(?:please\s+)?(?:add|create|schedule|make)\s+(?:an?\s+)?(?:(?:calendar|calender|calander)\s+)?(?:event|appointment|reminder|meeting)\s+(?:called|named|titled|for|about)\s+(.+)$/i,
      read: (match) => makeCalendarCommandPayload('today', undefined, match[1]),
    },

    // "put meeting on my calendar tomorrow at 3"
    {
      pattern: /^(?:please\s+)?(?:put|add)\s+(.+?)\s+(?:on|to)\s+(?:my\s+)?(?:calendar|calender|calander|schedule|agenda)\s+(?:(today|tomorrow)\s+)?(?:at\s+)?(.+)$/i,
      read: (match) => makeCalendarCommandPayload(match[2], match[3], match[1]),
    },

    // "schedule meeting tomorrow at 3"
    {
      pattern: /^(?:please\s+)?schedule\s+(.+?)\s+(today|tomorrow)\s+(?:at\s+)?(.+)$/i,
      read: (match) => makeCalendarCommandPayload(match[2], match[3], match[1]),
    },

    // "remind me tomorrow at 3 to call Bob"
    {
      pattern: /^(?:please\s+)?remind\s+me\s+(today|tomorrow)\s+(?:at\s+)?(.+?)\s+to\s+(.+)$/i,
      read: (match) => makeCalendarCommandPayload(match[1], match[2], match[3]),
    },
  ];

  for (const { pattern, read } of patterns) {
    const match = normalized.match(pattern);
    const payload = match ? read(match) : null;

    if (payload) return payload;
  }

  return null;
}



function normalizeCalendarDeleteTime(rawTime: string | undefined): string {
  return rawTime
    ? cleanCommandPayload(rawTime)
        .replace(/\b([ap])\.\s*m\.?\b/gi, '$1m')
        .replace(/\b([ap])\s+m\b/gi, '$1m')
        .replace(/\s+/g, ' ')
        .trim()
    : '';
}

function makeCalendarDeletePayload(
  rawDay?: string,
  rawTime?: string,
  rawTitle?: string
): CalendarDeleteCommandPayload | null {
  const dayCandidate = rawDay?.toLowerCase();
  const day = isCalendarDay(dayCandidate) ? dayCandidate : undefined;
  const time = normalizeCalendarDeleteTime(rawTime);
  const title = rawTitle ? cleanCommandPayload(rawTitle) : '';

  if (!day && !time && !title) return null;

  return {
    ...(day ? { day } : {}),
    ...(time ? { time } : {}),
    ...(title ? { title } : {}),
  };
}

function extractCalendarDeletePayload(normalized: string): CalendarDeleteCommandPayload | null {
  const timeToken = String.raw`(?:\d{1,2})(?::\d{2})?\s*(?:a\.?\s*m\.?|p\.?\s*m\.?|am|pm)?|noon|midnight`;
  const calendarWord = String.raw`(?:calendar|calender|calander)`;
  const eventWord = String.raw`(?:(?:${calendarWord})\s+)?(?:event|appointment|meeting)`;
  const deleteVerb = String.raw`(?:delete|remove|erase|cancel)`;

  const patterns: Array<{
    pattern: RegExp;
    read: (match: RegExpMatchArray) => CalendarDeleteCommandPayload | null;
  }> = [
    // "delete the 1:00 p.m. calendar event Test Meeting"
    // Also accepts an optional title marker:
    // "delete the 1 PM calendar event called Test Meeting"
    {
      pattern: new RegExp(
        String.raw`^(?:please\s+)?${deleteVerb}\s+(?:the\s+)?(${timeToken})\s+${eventWord}(?:\s+(today|tomorrow))?\s+(?:(?:called|named|titled|for|about)\s+)?(.+)$`,
        'i',
      ),
      read: (match) =>
        makeCalendarDeletePayload(
          match[2],
          match[1],
          match[3],
        ),
    },

    // "delete the 12:00 p.m. event tomorrow"
    {
      pattern: new RegExp(String.raw`^(?:please\s+)?${deleteVerb}\s+(?:the\s+)?(${timeToken})\s+${eventWord}(?:\s+(today|tomorrow))?$`, 'i'),
      read: (match) => makeCalendarDeletePayload(match[2], match[1]),
    },

    // "delete the event tomorrow at 12:00 p.m."
    // "delete the calendar event at 1 pm"
    {
      pattern: new RegExp(String.raw`^(?:please\s+)?${deleteVerb}\s+(?:the\s+)?${eventWord}(?:\s+(today|tomorrow))?\s+(?:at\s+)?(${timeToken})(?:\s+(?:called|named|titled|for|about)\s+(.+))?$`, 'i'),
      read: (match) => makeCalendarDeletePayload(match[1], match[2], match[3]),
    },

    // "delete the event at 12:00 p.m. tomorrow"
    {
      pattern: new RegExp(String.raw`^(?:please\s+)?${deleteVerb}\s+(?:the\s+)?${eventWord}\s+(?:at\s+)?(${timeToken})\s+(today|tomorrow)(?:\s+(?:called|named|titled|for|about)\s+(.+))?$`, 'i'),
      read: (match) => makeCalendarDeletePayload(match[2], match[1], match[3]),
    },

    // "delete tomorrow's 12 pm event"
    {
      pattern: new RegExp(String.raw`^(?:please\s+)?${deleteVerb}\s+(?:the\s+)?(?:today(?:'s)?|tomorrow(?:'s)?)\s+(${timeToken})\s+${eventWord}$`, 'i'),
      read: (match) => {
        const dayMatch = normalized.match(/\b(tomorrow|today)(?:'s)?\b/i);
        return makeCalendarDeletePayload(dayMatch?.[1], match[1]);
      },
    },

    // "delete the calendar event tomorrow called dentist"
    {
      pattern: new RegExp(String.raw`^(?:please\s+)?${deleteVerb}\s+(?:the\s+)?${eventWord}\s+(today|tomorrow)\s+(?:called|named|titled|for|about)\s+(.+)$`, 'i'),
      read: (match) => makeCalendarDeletePayload(match[1], undefined, match[2]),
    },

    // Natural speech can place the title before the final event noun:
    // "delete the 7 PM check my sock drawer for socks calendar event"
    // "delete the 7 PM check my sock drawer for socks the calendar event"
    //
    // Keep this after the standard title-after-event and no-title patterns so
    // phrases such as "delete the 1 PM calendar event called Test Meeting"
    // continue to use their more specific parser first.
    {
      pattern: new RegExp(
        String.raw`^(?:please\s+)?${deleteVerb}\s+(?:the\s+)?(${timeToken})\s+(.+?)\s+(?:(?:the\s+)?${calendarWord}\s+(?:event|appointment|meeting)|(?:the\s+)?(?:event|appointment))(?:\s+(today|tomorrow))?$`,
        'i',
      ),
      read: (match) =>
        makeCalendarDeletePayload(
          match[3],
          match[1],
          match[2],
        ),
    },
  ];

  for (const { pattern, read } of patterns) {
    const match = normalized.match(pattern);
    const payload = match ? read(match) : null;

    if (payload) return payload;
  }

  return null;
}

function normalizeCalendarEditTail(tail: string): string {
  return tail
    .replace(/\b(?:two|too|to)\s+at\b/gi, 'at')
    .replace(/\b(?:for)\s+at\b/gi, 'at')
    .replace(/\s+/g, ' ')
    .trim();
}

function isCalendarDay(value: string | undefined): value is 'today' | 'tomorrow' {
  return value === 'today' || value === 'tomorrow';
}

function extractCalendarEditPayload(normalized: string): CalendarEditCommandPayload | null {
  const base = String.raw`(?:the\s+)?(?:last|latest|next|current|this)\s+(?:calendar\s+)?(?:event|appointment|meeting)`;

  const titleOnlyPatterns = [
    new RegExp(String.raw`^(?:please\s+)?(?:rename|retitle)\s+${base}\s+(?:to|as|called|named)\s+(.+)$`, 'i'),
    new RegExp(String.raw`^(?:please\s+)?(?:change|edit|update)\s+${base}\s+(?:title|name)\s+(?:to|as|called|named)\s+(.+)$`, 'i'),
  ];

  for (const pattern of titleOnlyPatterns) {
    const match = normalized.match(pattern);
    const title = match?.[1] ? cleanCommandPayload(match[1]) : '';
    if (title) return { title };
  }

  const timeOnlyPatterns = [
    new RegExp(String.raw`^(?:please\s+)?(?:change|edit|update)\s+${base}\s+(?:time\s+)?(?:to|for)\s+(?:at\s+)?(.+)$`, 'i'),
    new RegExp(String.raw`^(?:please\s+)?(?:reschedule|move)\s+${base}\s+(?:to|for)\s+(?:at\s+)?(.+)$`, 'i'),
  ];

  for (const pattern of timeOnlyPatterns) {
    const match = normalized.match(pattern);
    const rawTail = match?.[1] ? normalizeCalendarEditTail(cleanCommandPayload(match[1])) : '';
    if (!rawTail) continue;

    const withDayAndTitle = rawTail.match(/^(today|tomorrow)\s+(?:at\s+)?(.+?)\s+(?:called|named|titled|as)\s+(.+)$/i);
    if (withDayAndTitle) {
      const day = withDayAndTitle[1].toLowerCase();
      const time = cleanCommandPayload(withDayAndTitle[2]);
      const title = cleanCommandPayload(withDayAndTitle[3]);
      if (isCalendarDay(day) && time) return { day, time, ...(title ? { title } : {}) };
    }

    const withDay = rawTail.match(/^(today|tomorrow)\s+(?:at\s+)?(.+)$/i);
    if (withDay) {
      const day = withDay[1].toLowerCase();
      const time = cleanCommandPayload(withDay[2]);
      if (isCalendarDay(day) && time) return { day, time };
    }

    const withTitle = rawTail.match(/^(.+?)\s+(?:called|named|titled|as)\s+(.+)$/i);
    if (withTitle) {
      const time = cleanCommandPayload(withTitle[1]);
      const title = cleanCommandPayload(withTitle[2]);
      if (time || title) return { ...(time ? { time } : {}), ...(title ? { title } : {}) };
    }

    return { time: rawTail };
  }

  const combinedPatterns = [
    new RegExp(String.raw`^(?:please\s+)?(?:change|edit|update)\s+${base}\s+(?:to\s+)?(?:(today|tomorrow)\s+)?(?:at\s+)?(.+?)\s+(?:called|named|titled|as)\s+(.+)$`, 'i'),
    new RegExp(String.raw`^(?:please\s+)?(?:change|edit|update)\s+${base}\s+(?:to\s+)?(today|tomorrow)\s+(?:at\s+)?(.+)$`, 'i'),
  ];

  for (const pattern of combinedPatterns) {
    const match = normalized.match(pattern);
    if (!match) continue;

    const dayCandidate = match[1]?.toLowerCase();
    const day = isCalendarDay(dayCandidate) ? dayCandidate : undefined;
    const time = match[2] ? cleanCommandPayload(normalizeCalendarEditTail(match[2])) : '';
    const title = match[3] ? cleanCommandPayload(match[3]) : '';

    if (day || time || title) {
      return {
        ...(day ? { day } : {}),
        ...(time ? { time } : {}),
        ...(title ? { title } : {}),
      };
    }
  }

  return null;
}

function extractCalendarReadPayload(normalized: string): 'today' | 'tomorrow' | 'all' | null {
  const todayPatterns = [
    /^(?:please\s+)?(?:show|read|list|display|open|pull\s+up|bring\s+up)\s+(?:my\s+)?(?:(?:calendar|calender|calander|schedule|agenda)\s+)?today(?:'s)?\s+(?:events|agenda|schedule|calendar)$/i,
    /^(?:please\s+)?(?:show|read|list|display|open|pull\s+up|bring\s+up)\s+(?:my\s+)?today(?:'s)?\s+(?:events|agenda|schedule|calendar)$/i,
    /^(?:please\s+)?what(?:'s|\s+is)\s+on\s+(?:my\s+)?(?:calendar|calender|calander|schedule|agenda)\s+today$/i,
    /^(?:please\s+)?what\s+do\s+i\s+have\s+(?:today|on\s+today)$/i,
  ];

  const tomorrowPatterns = [
    /^(?:please\s+)?(?:show|read|list|display|open|pull\s+up|bring\s+up)\s+(?:my\s+)?(?:(?:calendar|calender|calander|schedule|agenda)\s+)?tomorrow(?:'s)?\s+(?:events|agenda|schedule|calendar)$/i,
    /^(?:please\s+)?(?:show|read|list|display|open|pull\s+up|bring\s+up)\s+(?:my\s+)?tomorrow(?:'s)?\s+(?:events|agenda|schedule|calendar)$/i,
    /^(?:please\s+)?what(?:'s|\s+is)\s+on\s+(?:my\s+)?(?:calendar|calender|calander|schedule|agenda)\s+tomorrow$/i,
    /^(?:please\s+)?what\s+do\s+i\s+have\s+(?:tomorrow|on\s+tomorrow)$/i,
  ];

  const allPatterns = [
    /^(?:please\s+)?what(?:'s|\s+is)\s+on\s+(?:my\s+)?(?:calendar|calender|calander|schedule|agenda)$/i,
    /^(?:please\s+)?what\s+are\s+(?:my\s+)?(?:calendar|calender|calander|schedule|agenda)\s+events$/i,
    /^(?:please\s+)?(?:read|list|show|display)\s+(?:my\s+)?(?:calendar|calender|calander|schedule|agenda)$/i,
    /^(?:please\s+)?(?:read|list|show|display)\s+(?:my\s+)?(?:calendar|calender|calander|schedule|agenda)?\s*events$/i,
    /^(?:please\s+)?what\s+do\s+i\s+have\s+scheduled$/i,
    /^(?:please\s+)?what\s+are\s+my\s+events$/i,
  ];

  if (todayPatterns.some((pattern) => pattern.test(normalized))) return 'today';
  if (tomorrowPatterns.some((pattern) => pattern.test(normalized))) return 'tomorrow';
  if (allPatterns.some((pattern) => pattern.test(normalized))) return 'all';

  return null;
}

export function normalizeSpokenQMeet(text: string): string {
  return text.replace(
    /\b(?:q\s*meet|queue\s+meet|cue\s+meet|cute\s+meet|q\s*meat|queue\s+meat|cue\s+meat|cute\s+meat|key\s+meet|key\s+meat|q\s*me|queue\s+me|cue\s+me)\b/gi,
    'QMeet'
  );
}

export function normalizeCommandText(text: string): string {
  return normalizeSpokenQMeet(text)
    .trim()
    .toLowerCase()
    .replace(/[""]/g, '"')
    .replace(/['']/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/[?!.,;:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^(?:hey\s+)?(?:qmeet|orb|assistant)\s+/, '')
    .trim();
}

export function parseCommand(text: string): CommandMatch | null {
  return debugCommandParse(text).match;
}

export function debugCommandParse(text: string): {
    rawText: string;
    normalizedText: string;
    match: CommandMatch | null;
  } {
  const normalized = normalizeCommandText(text);
  const payloadSource = normalizeSpokenQMeet(text)
      .trim()
      .replace(/[?!.,;:]+$/g, '')
      .replace(/\s+/g, ' ')
      .replace(/^(?:hey\s+)?(?:qmeet|orb|assistant)\s+/i, '')
      .trim();

    const qmeetGuideTopic = getQMeetGuideTopic(payloadSource);
    if (qmeetGuideTopic) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: 'help',
          confirmation: getQMeetGuideResponse(qmeetGuideTopic),
          payload: qmeetGuideTopic,
        },
      };
    }
  
    const adHocPrepFocusIntent = extractAdHocPreparationFocusIntent(payloadSource);
    if (adHocPrepFocusIntent) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: adHocPrepFocusIntent,
      };
    }

    const visualContextIntent = extractVisualContextIntent(payloadSource);
    if (visualContextIntent) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: visualContextIntent,
      };
    }

    const visualObservationPayload = extractVisualObservationPayload(payloadSource);
    if (visualObservationPayload) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: 'create-visual-observation',
          confirmation: `Saved visual observation: ${visualObservationPayload}.`,
          payload: visualObservationPayload,
        },
      };
    }

    const taskDonePayload = extractTaskDonePayload(payloadSource);
    if (taskDonePayload !== null) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: 'mark-task-done',
          confirmation: CONFIRMATIONS['mark-task-done'],
          payload: taskDonePayload,
        },
      };
    }

    const calendarFocusIntent = extractCalendarFocusIntent(payloadSource);
    if (calendarFocusIntent) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: calendarFocusIntent,
      };
    }

    const focusSessionIntent = extractFocusSessionIntent(payloadSource);
    if (focusSessionIntent) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: focusSessionIntent.command,
          confirmation: focusSessionIntent.confirmation ?? CONFIRMATIONS[focusSessionIntent.command],
          ...(focusSessionIntent.focusSession
            ? { focusSession: focusSessionIntent.focusSession }
            : {}),
          ...(focusSessionIntent.payload ? { payload: focusSessionIntent.payload } : {}),
        },
      };
    }

    const taskPayload = extractTaskPayload(payloadSource);
    if (taskPayload) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: 'remember-task',
          confirmation: CONFIRMATIONS['remember-task'],
          payload: taskPayload,
        },
      };
    }

    // Do not save likely task-completion/progress updates as notes. If no task matched, leave it for chat.
    if (/\b(?:finished|completed|done|did|got through|handled)\b/i.test(payloadSource) && /\b(?:first|second|third|fourth|fifth|task|tasks|step|steps|item|items|thing|things|\d+)\b/i.test(payloadSource)) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: null,
      };
    }

    const notePayload = extractNotePayload(payloadSource);
    if (notePayload) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: 'save-note',
          confirmation: CONFIRMATIONS['save-note'],
          payload: notePayload,
        },
      };
    }

    const calendarDelete = extractCalendarDeletePayload(payloadSource);
    if (calendarDelete) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: 'delete-calendar-event',
          confirmation: CONFIRMATIONS['delete-calendar-event'],
          calendarDelete,
        },
      };
    }

    const calendarEdit = extractCalendarEditPayload(payloadSource);
    if (calendarEdit) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: 'edit-last-event',
          confirmation: CONFIRMATIONS['edit-last-event'],
          calendarEdit,
        },
      };
    }

    const calendarEvent = extractCalendarEventPayload(payloadSource);
    if (calendarEvent) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: 'add-calendar-event',
          confirmation: CONFIRMATIONS['add-calendar-event'],
          calendarEvent,
        },
      };
    }

    const calendarView = extractCalendarReadPayload(payloadSource);
    if (calendarView) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
          command: 'read-calendar',
          confirmation: CONFIRMATIONS['read-calendar'],
          calendarView,
        },
      };
    }
  
    const searchPayload = extractSearchPayload(payloadSource);
  if (searchPayload) {
    return {
      rawText: text,
      normalizedText: normalized,
      match: {
        command: 'run-search',
        confirmation: `${searchPayload.confirmationPrefix}: ${searchPayload.payload}`,
        payload: searchPayload.payload,
      },
    };
  }
  
  for (const [command, patterns] of COMMAND_PATTERNS) {
    if (patterns.some((pattern) => pattern.test(normalized))) {
      return {
        rawText: text,
        normalizedText: normalized,
        match: {
        command,
        confirmation: CONFIRMATIONS[command],
        },
      };
    }
  }

  return {
    rawText: text,
    normalizedText: normalized,
    match: null,
  };
}
