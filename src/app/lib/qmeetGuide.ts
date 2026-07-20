export type QMeetGuideTopic =
  | 'overview'
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
  ['ui', /\b(?:ui|interface|menu|panel|settings|status|chat log|chatbox|orb|button|home)\b/i],
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

const TOPIC_RESPONSES: Record<QMeetGuideTopic, string> = {
  overview:
    'I am QMeet, the local orb interface for this tablet. I can help with focus sessions, memory/tasks/notes, calendar and meeting prep, camera/visual context, search, voice controls, and recaps. Try: "start a focus session for UI cleanup", "prepare me for my next meeting", "open camera", or "open memory". Ask "help with focus", "help with calendar", or "help with camera" for a smaller guide.',
  focus:
    'Focus sessions track what you are working on. Try: "start a coding focus for Phase 17", "set my goal to clean up the UI", "what is my focus", "turn this focus into tasks", or "save this focus as a note". You can also say things naturally, like "I have an appointment at 6 today I need to prepare for."',
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
    'UI commands open panels without needing ChatGPT. Try: "open memory", "open notes", "open calendar", "open search", "open settings", or "go home". The small chat-log button opens the chat without starting voice input.',
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

export function getQMeetGuideTopic(input: string): QMeetGuideTopic | null {
  const normalized = normalizeQMeetGuideText(input);
  if (!normalized) return null;

  const hasHelpIntent = HELP_INTENT_PATTERNS.some((pattern) => pattern.test(normalized));
  if (!hasHelpIntent) return null;

  for (const [topic, pattern] of TOPIC_KEYWORDS) {
    if (pattern.test(normalized)) return topic;
  }

  return 'overview';
}

export function getQMeetGuideResponse(topic: QMeetGuideTopic | null | undefined = 'overview'): string {
  return TOPIC_RESPONSES[topic ?? 'overview'] ?? TOPIC_RESPONSES.overview;
}
