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
  overview: `**I am QMeet.** I help you operate this tablet by voice or touch.

**Good first moves:**
- Say "open menu" to see the main panels.
- Say "start a focus for ..." to make that work my background context.
- Say "open memory" to see focus, tasks, notes, and saved context.

**Try:** "start a focus for my Java class", "prepare me for my next meeting", or "what can I do from here?".`,
  context: '',
  screen: '',
  focus: `**Focus is my background work context.** When you tell me what you are working on, I keep that as the main focus until you end it.

**While focus is active, ask naturally:**
- "what should I do next?"
- "help me write the code"
- "what do you need to know?"

**To manage it:** say "open memory", "set my goal to ...", or "end and summarize this focus".`,
  memory: `**Memory is where I show the context I am using.**

**Inside Memory you can see:**
- Current focus and goal.
- Open tasks and completed tasks.
- Recent focus sessions.
- Visual context and saved notes.

**Try:** "open memory", "show recent focus sessions", or "clear context".`,
  tasks: `**Tasks are lightweight to-dos I can track for you.**

**Try saying:**
- "remember to test the Pi as a task"
- "mark task done"
- "turn this focus into tasks"

Tasks can also link to your current focus or meeting prep.`,
  notes: `**Notes store snippets, summaries, and meeting/focus captures.**

**Try saying:** "note that the prototype needs UI polish", "read my notes", "save this focus as a note", or "save meeting notes".`,
  calendar: `**Calendar helps me connect your schedule to your work.** I can show events, add events, and turn meetings into focus sessions.

**Try saying:**
- "show today"
- "add event today at 6 PM called appointment"
- "prepare me for my next meeting"
- "make prep tasks for my next meeting"`,
  meetings: `**Meeting mode connects Calendar, Focus, Tasks, and Notes.**

**Before:** "prepare me for my next meeting" or "make prep tasks for my next meeting".
**After:** "save meeting notes", "create follow-up tasks from this meeting", or "wrap up this meeting".`,
  visual: `**Visual context lets me use camera snapshots, uploaded images, or manual visual notes.** I store the text observation, not the raw image.

**Try saying:** "open camera", "analyze snapshot", "what was the last thing you saw", or "save this visual context to my focus".`,
  search: `**Search lets me look things up from the web.**

**Try saying:** "search for Raspberry Pi kiosk mode", "look up Chromium flags", or "clear search". Search can support your current focus.`,
  voice: `**Voice controls adjust how I speak and listen.**

**Try saying:** "mute voice", "unmute voice", "speak slower", "speak faster", "normal voice", "stop speaking", or "what did you hear".`,
  ui: `**You can use voice or touch.**

**Main panels:**
- "open menu" shows the launcher.
- "open memory" shows focus, tasks, notes, and context.
- "open calendar", "open notes", "open camera", or "open search" open those tools directly.

Buttons and cards are clickable. If you ask "what can I click?", I will use the screen I can detect.`,
  recap: `**Recaps summarize what I remember from your work.**

**Try saying:** "summarize what I worked on today", "what did I focus on recently", "give me a better recap of today", or "what should I focus on next".`,
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


function isActiveFocusWorkQuestion(normalized: string): boolean {
  return (
    /\bwhat\s+(?:do|should|can)\s+i\s+do\s+(?:now|next)\b/i.test(normalized) ||
    /\bwhat\s+can\s+i\s+do\s+(?:with\s+(?:it|this|that)|now|next)\b/i.test(normalized) ||
    /\bnow\s+what\b/i.test(normalized) ||
    /\bwhat\s+more\s+do\s+you\s+need\s+to\s+know\b/i.test(normalized) ||
    /\bwhat\s+do\s+you\s+need\s+(?:to\s+know|from\s+me)\b/i.test(normalized) ||
    /\b(?:can|could|will|would)\s+you\s+help\s+me\s+(?:with|do|write|fix|debug|finish|complete|get|getting|build|make)\b/i.test(normalized) ||
    /\b(?:i\s+)?(?:just\s+)?(?:want|need)\s+help\s+(?:with|doing|writing|fixing|debugging|finishing|getting|building|making)\b/i.test(normalized) ||
    /\b(?:i\s+)?do\s+not\s+like\s+those\s+tasks\b/i.test(normalized) ||
    /\bi\s+don'?t\s+like\s+those\s+tasks\b/i.test(normalized) ||
    /\bhelp\s+me\s+(?:do|write|fix|debug|finish|complete|build|make|understand)\b/i.test(normalized) ||
    /\b(?:help|assist)\s+me\s+with\s+(?:my\s+)?(?:current\s+)?focus\b/i.test(normalized)
  );
}

function getScreenGuideResponse(): string {
  const panel = detectOpenPanel();
  const activeSession = readActiveSession();

  if (panel === 'menu') {
    return `**This is the main Menu.**

Yes, the cards are clickable.

**Try:**
- Tap Memory for focus, tasks, and context.
- Tap Calendar for events.
- Tap Notes, Search, Settings, or Status.

You can also say "open memory" or "go home".`;
  }

  if (panel === 'memory') {
    return activeSession
      ? `**This is Memory.** It is where I show your active focus, tasks, focus history, and visual context.

**For "${activeSession.title}":**
- Ask "what should I do next?" for direct help.
- Use the buttons to create tasks, save a note, or end with summary.
- Use Clear Context if you want to wipe the focus/context state.`
      : '**This is Memory.** It shows tasks, recent focus sessions, visual context, and memory sync. Start a focus with "start a focus session for ...", or add a task with "remember to ... as a task".';
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
    return `Yes. The Menu cards are clickable.

**Useful cards:**
- Memory: focus, tasks, and context.
- Calendar: events and meeting prep.
- Notes: saved notes.
- Search: web lookup.
- Settings and Status: controls and diagnostics.

You can tap a card or say it out loud.`;
  }

  if (panel === 'memory') {
    return activeSession
      ? `You are in Memory, and your current focus is "${activeSession.title}".

**Useful from here:**
- Ask me "what should I do next?" for direct help with the work.
- Tap Create tasks, Save note, or End with summary if you want to manage the focus.
- Use Clear Context when you want to remove focus/context state.`
      : 'You are in Memory. You can add tasks, review focus history, inspect visual context, import/export memory, or start work by saying "start a focus session for ...".';
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
      ? `Goal: ${activeSession.goal.trim()}.`
      : 'No goal is set yet.';
    const linkedTaskCount = activeSession.linkedTaskIds?.length ?? 0;
    const linkedText = linkedTaskCount > 0
      ? `${linkedTaskCount} linked task${linkedTaskCount === 1 ? '' : 's'} exist.`
      : 'No linked tasks yet.';
    return `**Current focus:** ${activeSession.title}

- ${goalText}
- ${linkedText}

**Useful controls:** say "open memory" to see buttons, "turn this focus into tasks" to create tasks, or ask me naturally for help with the work itself.`;
  }

  return 'A good first step is to set context. Try: "start a focus session for ...", "open memory", "show today", "open camera", or "what can you do with calendar".';
}

export function getQMeetGuideTopic(input: string): QMeetGuideTopic | null {
  const normalized = normalizeQMeetGuideText(input);
  if (!normalized) return null;

  const activeSession = readActiveSession();
  if (activeSession && isActiveFocusWorkQuestion(normalized)) {
    return null;
  }

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
