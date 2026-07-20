export type QMeetGuideTopic =
  | 'overview'
  | 'context'
  | 'screen'
  | 'focus'
  | 'memory'
  | 'tasks'
  | 'notes'
  | 'calendar'
  | 'meetings'
  | 'visual'
  | 'search'
  | 'voice'
  | 'ui'
  | 'recap';

type ActiveSessionLike = {
  id?: string;
  title: string;
  mode?: string;
  goal?: string;
  linkedTaskIds?: string[];
  pinnedNoteIds?: string[];
};

type DetectedPanel =
  | 'menu'
  | 'memory'
  | 'notes'
  | 'calendar'
  | 'search'
  | 'settings'
  | 'status'
  | 'camera'
  | 'chat'
  | null;

const ACTIVE_SESSION_STORAGE_KEY = 'qmeet-active-session';
const ACTIVE_SESSION_SESSION_STORAGE_KEY = 'qmeet-active-session-live';

const TOPIC_KEYWORDS: Array<[QMeetGuideTopic, RegExp]> = [
  ['meetings', /\b(?:meeting|meetings|meet|event prep|wrap up|follow up|follow-up)\b/i],
  ['calendar', /\b(?:calendar|schedule|agenda|event|events|google calendar|appointment|appointments|make me a schedule|build a schedule)\b/i],
  ['visual', /\b(?:camera|webcam|visual|vision|image|images|picture|pictures|photo|photos|snapshot|screenshot|upload|saw|see|looking at)\b/i],
  ['focus', /\b(?:focus|session|goal|goals|current work|working on|preparation block|prep block)\b/i],
  ['tasks', /\b(?:task|tasks|to-do|todo|checklist|steps)\b/i],
  ['notes', /\b(?:note|notes|save note|meeting notes)\b/i],
  ['recap', /\b(?:recap|summary|summarize|history|recent work|what changed|worked on)\b/i],
  ['memory', /\b(?:memory|remember|stored|context|recent actions)\b/i],
  ['search', /\b(?:search|web|look up|lookup|internet)\b/i],
  ['voice', /\b(?:voice|speech|speak|mute|unmute|listen|heard|transcript)\b/i],
  ['ui', /\b(?:ui|interface|menu|panel|settings|status|chat log|chatbox|orb|button|home|click|tap)\b/i],
];

const HELP_INTENT_PATTERNS: RegExp[] = [
  /^\s*(?:help|commands?|command list|voice commands?|show commands?|show me commands?|show help|show me help)\s*$/i,
  /\bwhat\s+can\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+do\b/i,
  /\bwhat\s+(?:are\s+you|is\s+q\s*meet|is\s+qmeet|is\s+the\s+orb)\s+(?:able\s+to\s+do|capable\s+of|for)\b/i,
  /\bwhat\s+(?:can|could|do)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+(?:help\s+me\s+with|help\s+with|do\s+for\s+me)\b/i,
  /\bhow\s+(?:are|do)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+(?:able\s+to\s+help|able\s+to\s+do|work|operate)\b/i,
  /\bwhat\s+(?:can|should)\s+i\s+say\b/i,
  /\bhow\s+do\s+i\s+use\s+(?:this|q\s*meet|qmeet|the\s+orb)\b/i,
  /\bhow\s+(?:does|do)\s+(?:the\s+)?(?:focus|calendar|camera|visual|memory|notes?|tasks?|search|voice|recap|meeting)\b/i,
  /\bwhat\s+(?:is|are)\s+(?:a\s+|the\s+)?(?:focus|focus\s+session|memory|visual\s+context|recap|meeting\s+prep)\b/i,
  /\bhow\s+do\s+i\s+use\s+(?:the\s+)?(?:focus|calendar|camera|visual|memory|notes?|tasks?|search|voice|recap|meeting|meetings)\b/i,
  /\b(?:help|guide|teach)\s+me\s+(?:with|through|on)\s+(?:the\s+)?(?:focus|calendar|camera|visual|memory|notes?|tasks?|search|voice|recap|meeting|meetings)\b/i,
  /\b(?:help|guide|examples?|commands?)\s+(?:with|for|on)\s+(?:the\s+)?(?:focus|calendar|camera|visual|memory|notes?|tasks?|search|voice|recap|meeting|meetings)\b/i,
  /\b(?:examples?|sample commands?)\s+(?:for|of)\s+(?:the\s+)?(?:focus|calendar|camera|visual|memory|notes?|tasks?|search|voice|recap|meeting|meetings)\b/i,
  /\b(?:q\s*meet|qmeet|the\s+orb)\s+(?:guide|tutorial|manual|capabilities|features)\b/i,
  /\b(?:tell|show|explain)\s+me\s+(?:what|how)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+(?:can|does|works?)\b/i,
  /\b(?:can|could|would)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+(?:make|create|build|help\s+me\s+(?:make|create|build))\s+(?:me\s+)?(?:a\s+)?(?:schedule|agenda|day\s+plan|plan)\b/i,
  /\b(?:i\s+need|help\s+me)\s+(?:a\s+)?(?:schedule|agenda|day\s+plan)\b/i,
  /\bwhat\s+(?:tools|features|capabilities)\s+(?:do|does)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+have\b/i,
  /\bwhat\s+local\s+(?:tools|commands)\s+(?:do|does)\s+(?:you|q\s*meet|qmeet|the\s+orb)\s+have\b/i,
];

const CONTEXTUAL_GUIDE_PATTERNS: RegExp[] = [
  /\bwhat\s+can\s+i\s+do\s+(?:now|next|with\s+it|with\s+this|with\s+that)\b/i,
  /\bwhat\s+should\s+i\s+do\s+(?:now|next)\b/i,
  /\bnow\s+what\b/i,
  /\bwhat\s+are\s+my\s+options\b/i,
  /\bwhat\s+can\s+i\s+(?:click|tap|press)\b/i,
  /\bcan\s+i\s+(?:click|tap|press)\s+(?:on\s+)?(?:these|this|any\s+(?:one\s+)?of\s+these|one\s+of\s+these|the\s+buttons?)\b/i,
  /\bwhat\s+does\s+this\s+(?:screen|menu|panel|view)\s+do\b/i,
];

const SCREEN_GUIDE_PATTERNS: RegExp[] = [
  /\bwhat\s+(?:was|is)\s+that\s+(?:menu|panel|screen|thing)\b/i,
  /\bwhat\s+(?:menu|panel|screen)\s+(?:appeared|opened|showed\s+up)\b/i,
  /\bhow\s+(?:do|to)\s+i\s+open\s+(?:it|that|this)\s+again\b/i,
  /\bhow\s+(?:do|to)\s+i\s+get\s+(?:back\s+)?(?:to\s+)?(?:it|that|this)\b/i,
  /\bhow\s+(?:do|to)\s+i\s+(?:reopen|show)\s+(?:that|this|the)\s+(?:menu|panel|screen)\b/i,
  /\bwhere\s+(?:is|are)\s+(?:the\s+)?(?:focus|memory|task|note|calendar|camera)\s+(?:menu|panel|controls?)\b/i,
];

const TOPIC_RESPONSES: Record<QMeetGuideTopic, string> = {
  overview:
    'I am QMeet, the local orb interface for this tablet. I can help with focus sessions, memory/tasks/notes, calendar and meeting prep, camera/visual context, search, voice controls, and recaps. Try: "start a focus session for UI cleanup", "prepare me for my next meeting", "open camera", or "open memory". Ask "help with focus", "help with calendar", or "help with camera" for a smaller guide.',
  context:
    '',
  screen:
    '',
  focus:
    'A focus session is QMeet\'s current work context. It tells the orb what you are working on so chat, tasks, notes, visuals, and recaps can connect to it. Try: "start a coding focus for my Java class", "set my goal to finish the parser", "what is my focus", "turn this focus into tasks", or "save this focus as a note". To see the focus controls, say "open memory" or "show focus menu".',
  memory:
    'Memory keeps tasks, notes, recent actions, active focus, focus history, and visual observations. Try: "open memory", "what was I working on", "show recent focus sessions", or "summarize what I worked on today".',
  tasks:
    'Tasks are lightweight to-dos. Try: "remember to test the Pi as a task", "mark task done", "clear completed tasks", or "turn this focus into tasks". Focus, meeting-prep, and follow-up tasks can be linked to the current session.',
  notes:
    'Notes store snippets and summaries. Try: "note that the prototype needs UI polish", "read my notes", "save this focus as a note", or "save meeting notes".',
  calendar:
    'Calendar tools can show events, add events, and turn meetings into focus sessions. Try: "show today", "add event today at 6 PM called appointment", "prepare me for my next meeting", or "make prep tasks for my next meeting". For a new schedule, tell me the events/tasks and I can help turn them into calendar items, tasks, and focus blocks.',
  meetings:
    'Meeting workflows connect Calendar, Focus, Tasks, and Notes. Try: "prepare me for my next meeting", "make prep tasks for my next meeting", "save meeting notes", "create follow-up tasks from this meeting", or "wrap up this meeting".',
  visual:
    'Visual context stores text observations from manual notes, webcam snapshots, or uploaded images. Try: "open camera", "analyze snapshot", "what was the last thing you saw", "show visual observations", or "save this visual context to my focus". QMeet stores the text description, not the raw image.',
  search:
    'Search runs real web searches from QMeet. Try: "search for Raspberry Pi kiosk mode", "look up Chromium flags", or "clear search". Search results can support the current focus.',
  voice:
    'Voice controls adjust QMeet speech and listening. Try: "mute voice", "unmute voice", "speak slower", "speak faster", "normal voice", "stop speaking", or "what did you hear".',
  ui:
    'UI commands open panels without needing ChatGPT. Try: "open menu", "open memory", "open notes", "open calendar", "open search", "open settings", or "go home". Menu cards and panel buttons are clickable, and the small chat-log button opens the chat without starting voice input.',
  recap:
    'Recaps summarize what QMeet remembers. Try: "summarize what I worked on today", "what did I focus on recently", "give me a better recap of today", or "what should I focus on next". Local recaps are deterministic; enhanced recaps use ChatGPT.',
};

export function normalizeQMeetGuideText(value: string): string {
  return value
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/[?!.,;:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^(?:hey\s+)?(?:q\s*meet|qmeet|orb|assistant)\s+/i, '')
    .trim();
}

function readActiveSession(): ActiveSessionLike | null {
  if (typeof window === 'undefined') return null;
  const keys = [ACTIVE_SESSION_SESSION_STORAGE_KEY, ACTIVE_SESSION_STORAGE_KEY];
  for (const key of keys) {
    try {
      const raw = window.sessionStorage.getItem(key) ?? window.localStorage.getItem(key);
      if (!raw) continue;
      const parsed = JSON.parse(raw) as Partial<ActiveSessionLike>;
      if (parsed && typeof parsed.title === 'string' && parsed.title.trim()) {
        return {
          title: parsed.title.trim(),
          id: typeof parsed.id === 'string' ? parsed.id : undefined,
          mode: typeof parsed.mode === 'string' ? parsed.mode : 'general',
          goal: typeof parsed.goal === 'string' ? parsed.goal : '',
          linkedTaskIds: Array.isArray(parsed.linkedTaskIds)
            ? parsed.linkedTaskIds.filter((item): item is string => typeof item === 'string')
            : [],
          pinnedNoteIds: Array.isArray(parsed.pinnedNoteIds)
            ? parsed.pinnedNoteIds.filter((item): item is string => typeof item === 'string')
            : [],
        };
      }
    } catch {
      // Ignore restricted storage / malformed stale values.
    }
  }
  return null;
}

function getDocumentText(): string {
  if (typeof document === 'undefined') return '';
  return document.body?.innerText ?? '';
}

function detectOpenPanel(): DetectedPanel {
  if (typeof document === 'undefined') return null;
  const bodyText = getDocumentText();

  if (document.querySelector('.qmeet-camera-overlay, [data-qmeet-camera-overlay="true"]')) return 'camera';
  if (/Choose a QMeet tool by touch/i.test(bodyText)) return 'menu';
  if (/Backend Memory/i.test(bodyText) || /Current Focus/i.test(bodyText)) return 'memory';
  if (/Write and review local notes|Notes/i.test(bodyText) && /Saved Notes|New Note|note/i.test(bodyText)) return 'notes';
  if (/Google Calendar|Calendar Events|Today|Tomorrow/i.test(bodyText) && /calendar/i.test(bodyText)) return 'calendar';
  if (/Search the web|Search Results|Web Search/i.test(bodyText)) return 'search';
  if (/Settings|Voice Output|Speech Rate/i.test(bodyText)) return 'settings';
  if (/System Status|Backend|Interpreter|Last heard/i.test(bodyText)) return 'status';
  if (document.querySelector('.chat-area-visible')) return 'chat';

  return null;
}

function getScreenGuideResponse(): string {
  const panel = detectOpenPanel();
  const activeSession = readActiveSession();

  if (panel === 'menu') {
    return 'You are looking at the main Menu. Yes, the cards are clickable: Notes, Memory, Calendar, Search, Settings, and Status all open their panels. You can also say the same actions out loud, like "open memory" or "open calendar". Say "go home" to close panels.';
  }

  if (panel === 'memory') {
    return activeSession
      ? `You are looking at Memory. This is also the focus menu: it shows your current focus, focus action buttons, nudges, tasks, recent focus sessions, and visual context. For your current focus, try "turn this focus into tasks", "save this focus as a note", or "what should I do next".`
      : 'You are looking at Memory. It shows tasks, saved focus sessions, visual context, and memory sync status. Start a focus with "start a focus session for ...", or add a task with "remember to ... as a task".';
  }

  if (panel === 'calendar') {
    return 'You are looking at Calendar. You can click/tap calendar controls, or say "show today", "show tomorrow", "prepare me for my next meeting", or "make prep tasks for my next meeting".';
  }

  if (panel === 'notes') {
    return 'You are looking at Notes. You can type a note, save it, or use voice commands like "note that ...", "read my notes", and "save meeting notes".';
  }

  if (panel === 'search') {
    return 'You are looking at Search. Type or say a search query like "search for Raspberry Pi kiosk mode". Results appear in this panel.';
  }

  if (panel === 'camera') {
    return 'You are looking at the Camera overlay. You can use the camera preview, take a snapshot, upload an image, analyze it, and save the returned text as visual context. QMeet stores the text observation, not the raw image.';
  }

  if (activeSession) {
    return `The focus controls live in Memory. Your current focus is "${activeSession.title}". Say "open memory" or "show focus menu" to bring that panel back. From there you can create tasks, save a note, end with summary, or link visual context.`;
  }

  return 'If you mean the main launcher, say "open menu". If you mean focus controls, say "open memory" or "show focus menu". Most panels can also be opened directly: "open notes", "open calendar", "open camera", or "open search".';
}

function getContextGuideResponse(): string {
  const panel = detectOpenPanel();
  const activeSession = readActiveSession();

  if (panel === 'menu') {
    return 'Yes. The Menu cards are clickable. Tap Memory for focus/tasks, Notes for notes, Calendar for events, Search for web search, Settings for voice/interface settings, or Status for system diagnostics. You can also say those names out loud.';
  }

  if (panel === 'memory') {
    return activeSession
      ? `With this focus, you can click the Memory action buttons or say: "set my goal to ...", "turn this focus into tasks", "save this focus as a note", "what should I do next", or "end and summarize this focus".`
      : 'In Memory, you can add tasks, review recent focus sessions, inspect visual context, import/export memory, or start a focus by saying "start a focus session for ...".';
  }

  if (panel === 'calendar') {
    return 'From Calendar, useful next actions are: "prepare me for my next meeting", "make prep tasks for my next meeting", "show tomorrow", or "add event today at 6 PM called appointment".';
  }

  if (panel === 'notes') {
    return 'From Notes, you can write a note, save it, or ask QMeet to read notes. If you are in a focus session, try "save this focus as a note" to capture the current work.';
  }

  if (panel === 'camera') {
    return 'From Camera, you can take a snapshot, upload an image, analyze it, then ask "what did you last see" or "save this visual context to my focus".';
  }

  if (activeSession) {
    const goalText = activeSession.goal?.trim()
      ? ` Your goal is: ${activeSession.goal.trim()}.`
      : ' You have not set a goal yet.';
    const linkedTaskCount = activeSession.linkedTaskIds?.length ?? 0;
    const linkedText = linkedTaskCount > 0
      ? ` You already have ${linkedTaskCount} linked task${linkedTaskCount === 1 ? '' : 's'}.`
      : ' You can turn this focus into tasks.';
    return `You are focused on "${activeSession.title}".${goalText}${linkedText} Try: "set my goal to ...", "turn this focus into tasks", "what should I do next", "save this focus as a note", or "open memory" to see the controls.`;
  }

  return 'A good first step is to set context. Try: "start a focus session for ...", "open memory", "show today", "open camera", or "what can you do with calendar".';
}

export function getQMeetGuideTopic(input: string): QMeetGuideTopic | null {
  const normalized = normalizeQMeetGuideText(input);
  if (!normalized) return null;

  if (CONTEXTUAL_GUIDE_PATTERNS.some((pattern) => pattern.test(normalized))) {
    return 'context';
  }

  if (SCREEN_GUIDE_PATTERNS.some((pattern) => pattern.test(normalized))) {
    return 'screen';
  }

  const hasHelpIntent = HELP_INTENT_PATTERNS.some((pattern) => pattern.test(normalized));
  if (!hasHelpIntent) return null;

  for (const [topic, pattern] of TOPIC_KEYWORDS) {
    if (pattern.test(normalized)) return topic;
  }

  return 'overview';
}

export function getQMeetGuideResponse(topic: QMeetGuideTopic | null | undefined = 'overview'): string {
  if (topic === 'context') return getContextGuideResponse();
  if (topic === 'screen') return getScreenGuideResponse();
  return TOPIC_RESPONSES[topic ?? 'overview'] ?? TOPIC_RESPONSES.overview;
}
