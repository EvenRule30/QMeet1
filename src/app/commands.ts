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
  | 'close-notes'
  | 'clear-notes'
  | 'open-calendar'
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

export type ActivePanel = 'none' | 'menu' | 'settings' | 'status' | 'notes' | 'calendar' | 'search';

export interface CommandMatch {
  command: LocalCommand;
  confirmation: string;
  payload?: string;
}

const HELP_MESSAGE =
  "I'm QMeet, your local AI orb interface. I can control the local QMeet interface by voice or text. I can open Menu, Settings, Status/System Dashboard, Notes, Calendar, and Search. Try saying \"open menu,\" \"show settings,\" \"show status,\" \"open notes,\" \"open calendar,\" or \"open search.\" I can save notes with \"note that buy milk,\" \"remember that test the tablet UI,\" or \"save note call Dr. Fang.\" I can prepare local search queries with \"search for raspberry pi kiosk mode,\" \"look up local voice assistant,\" or \"google chromium flags.\" I can read notes with \"read my notes\" and delete the newest one with \"delete last note.\" I can close panels with \"close panel\" or \"go home.\" I can also control spoken responses with \"mute voice,\" \"unmute voice,\" \"speak slower,\" \"speak faster,\" or \"normal voice.\"";

const CONFIRMATIONS: Record<LocalCommand, string> = {
  help: HELP_MESSAGE,
  identity: "I'm QMeet, your local AI orb interface.",
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
  'open-calendar': 'Opening calendar.',
  'show-today': 'Showing today.',
  'show-tomorrow': 'Showing tomorrow.',
  'close-calendar': 'Closed calendar.',
  'open-search': 'Opening search.',
  'run-search': 'Searching locally.',
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

function rx(pattern: string): RegExp {
  return new RegExp(pattern, 'i');
}

const COMMAND_PATTERNS: Array<[LocalCommand, RegExp[]]> = [
  [
    'help',
    [
      /^(?:help|commands?|command list|voice commands?|show commands?|show me commands?|show help|show me help)$/i,
      /^(?:what can (?:you|qmeet|the orb) do)$/i,
      /^(?:what (?:can|should) i say)$/i,
      /^(?:how do i use (?:this|qmeet|the orb))$/i,
      /^(?:what menus can (?:you|qmeet|the orb) open)$/i,
      /^(?:tell me what (?:you|qmeet|the orb) can do)$/i,
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
      /^(?:read my notes|read notes|list my notes|list notes|show my notes|display my notes)$/i,
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
    'open-calendar',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:my\\s+)?(?:the\\s+)?calendar(?:\\s+(?:panel|screen|menu|view))?$`),
      /^(?:calendar|calendar panel|calender|schedule)$/i,
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:the\\s+)?(?:calender|schedule)$`),
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
      rx(`^${REQUEST_PREFIX}(?:clear|reset|delete|wipe)\s+(?:the\s+)?(?:search|search\s+query|web\s+search|browser\s+query)$`),
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
      /^(?:stop talking|stop response|stop responding|stop speaking|never mind|forget that|enough|pause)$/i,
    ],
  ],
  [
    'cancel-action',
    [
      rx(`^${REQUEST_PREFIX}(?:cancel|stop|nevermind|never\\s+mind|abort|cancel\\s+that|stop\\s+that|forget\\s+(?:it|that)|stop\\s+listening|cancel\\s+listening)$`),
      rx(`^${REQUEST_PREFIX}(?:cancel|stop)\\s+(?:the\\s+)?(?:request|action)$`),
      /^(?:never mind|forget that|cancel request)$/i,
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
    const payload = match?.[1] ? cleanCommandPayload(match[1]) : '';
    if (payload) return payload;
  }

  return null;
}

function extractSearchPayload(normalized: string): { payload: string; confirmationPrefix: string } | null {
  const patterns: Array<{ pattern: RegExp; confirmationPrefix: string; rejectPayload?: (payload: string) => boolean }> = [
    { pattern: /^(?:please\s+)?search\s+(?:the\s+)?(?:web|internet)\s+for\s+(.+)$/i, confirmationPrefix: 'Searching locally for' },
    { pattern: /^(?:please\s+)?search\s+for\s+(.+)$/i, confirmationPrefix: 'Searching locally for' },
    { pattern: /^(?:please\s+)?search\s+(.+)$/i, confirmationPrefix: 'Searching locally for' },
    { pattern: /^(?:please\s+)?(?:web|internet)\s+search\s+(.+)$/i, confirmationPrefix: 'Searching locally for' },
    { pattern: /^(?:please\s+)?look\s+(?:this\s+)?up\s+(.+)$/i, confirmationPrefix: 'Searching locally for' },
    { pattern: /^(?:please\s+)?google\s+(.+)$/i, confirmationPrefix: 'Search query prepared' },
    {
      pattern: /^(?:please\s+)?find\s+(.+)$/i,
      confirmationPrefix: 'Searching locally for',
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
