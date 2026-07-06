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
  | 'close-notes'
  | 'clear-notes'
  | 'open-calendar'
  | 'show-today'
  | 'show-tomorrow'
  | 'close-calendar'
  | 'open-search'
  | 'close-search'
  | 'voice-output-on'
  | 'voice-output-off'
  | 'voice-output-toggle'
  | 'voice-slower'
  | 'voice-faster'
  | 'voice-normal'
  | 'stop-speaking'
  | 'clear-chat'
  | 'end-chat'
  | 'close-generic';

export type ActivePanel = 'none' | 'menu' | 'settings' | 'status' | 'notes' | 'calendar' | 'search';

interface CommandMatch {
  command: LocalCommand;
  confirmation: string;
}

const HELP_MESSAGE =
  "I'm QMeet, your local AI orb interface. I can control the local QMeet interface by voice or text. I can open Menu, Settings, Status/System Dashboard, Notes, Calendar, and Search. Try saying \"open menu,\" \"show settings,\" \"show status,\" \"system status,\" \"open notes,\" \"open calendar,\" or \"open search.\" I can show calendar views with \"today\" or \"tomorrow,\" and I can open the search/browser panel with \"search the web\" or \"open browser.\" I can close panels with \"close menu,\" \"close status,\" \"close calendar,\" \"close panel,\" or \"go home.\" I can also control spoken responses with \"mute voice,\" \"unmute voice,\" \"speak slower,\" \"speak faster,\" or \"normal voice.\" For notes, say \"new note,\" \"clear notes,\" or \"close notes.\"";

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
  'close-notes': 'Closed notes.',
  'clear-notes': 'Cleared notes.',
  'open-calendar': 'Opening calendar.',
  'show-today': 'Showing today.',
  'show-tomorrow': 'Showing tomorrow.',
  'close-calendar': 'Closed calendar.',
  'open-search': 'Opening search.',
  'close-search': 'Closed search.',
  'voice-output-on': 'Voice output enabled.',
  'voice-output-off': 'Voice output muted.',
  'voice-output-toggle': 'Toggling voice output.',
  'voice-slower': 'Speaking slower.',
  'voice-faster': 'Speaking faster.',
  'voice-normal': 'Voice speed reset to normal.',
  'stop-speaking': 'Speech stopped.',
  'clear-chat': 'Chat cleared.',
  'end-chat': 'Ending conversation.',
  'close-generic': 'Closed.',
};

const REQUEST_PREFIX =
  '(?:(?:please\\s+)?(?:can|could|would|will)\\s+you\\s+|please\\s+|i\\s+(?:want|need)\\s+you\\s+to\\s+)?';
const OPEN_VERB = '(?:open|show|display|bring\\s+up|pull\\s+up|launch)';
const CLOSE_VERB = '(?:close|hide|dismiss|remove|get\\s+rid\\s+of)';
const QMEET_ALIAS =
  '(?:q\\s*meet|queue\\s+meet|cue\\s+meet|cute\\s+meet|q\\s*meat|queue\\s+meat|cue\\s+meat|cute\\s+meat|key\\s+meet|key\\s+meat|q\\s*me|queue\\s+me|cue\\s+me)';

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
      /^(?:menu|main menu)$/i,
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
      /^(?:settings?|settings panel)$/i,
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
      rx(`^${REQUEST_PREFIX}(?:close\\s+everything|hide\\s+everything|clear\\s+the\\s+screen|back\\s+to\\s+main)$`),
    ],
  ],
  [
    'show-status',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?status(?:\\s+(?:panel|screen|menu|dashboard))?$`),
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?(?:system\\s+)?(?:dashboard|diagnostics?|health|system\\s+status)$`),
      /^(?:status|status panel|system status|system dashboard|dashboard|diagnostics|health)$/i,
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
    'open-notes',
    [
      rx(`^${REQUEST_PREFIX}${OPEN_VERB}\\s+(?:me\\s+)?(?:the\\s+)?notes?(?:\\s+(?:panel|screen|menu))?$`),
      /^(?:notes?|notes panel)$/i,
    ],
  ],
  [
    'new-note',
    [
      rx(`^${REQUEST_PREFIX}(?:new|create|start)\\s+(?:a\\s+)?note$`),
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
      /^(?:calendar|calendar panel)$/i,
    ],
  ],
  [
    'show-today',
    [
      rx(`^${REQUEST_PREFIX}(?:show|open|display|pull\\s+up|bring\\s+up)\\s+(?:me\\s+)?(?:my\\s+)?(?:the\\s+)?(?:calendar\\s+)?today(?:\\s+(?:view|agenda|schedule))?$`),
      /^(?:today|today view|today agenda|today schedule)$/i,
    ],
  ],
  [
    'show-tomorrow',
    [
      rx(`^${REQUEST_PREFIX}(?:show|open|display|pull\\s+up|bring\\s+up)\\s+(?:me\\s+)?(?:my\\s+)?(?:the\\s+)?(?:calendar\\s+)?tomorrow(?:\\s+(?:view|agenda|schedule))?$`),
      /^(?:tomorrow|tomorrow view|tomorrow agenda|tomorrow schedule)$/i,
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
      /^(?:open|show|display|launch) (?:search|browser|web search)$/i,
      /^(?:open|show|display|launch) (?:the )?(?:search|browser|web search) (?:panel|screen|view)$/i,
      rx(`^${REQUEST_PREFIX}(?:search|browse)\\s+(?:the\\s+)?(?:web|internet)$`),
      rx(`^${REQUEST_PREFIX}(?:web|internet)\\s+(?:search|browser)$`),
      /^(?:search|search panel|browser|web search)$/i,
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
    ],
  ],
  [
    'voice-output-off',
    [
      rx(`^${REQUEST_PREFIX}(?:turn\\s+off|disable|mute|deactivate)\\s+(?:the\\s+)?(?:voice|speech|voice\\s+output|spoken\\s+responses|speaker)$`),
      rx(`^${REQUEST_PREFIX}(?:voice|speech|speaker)\\s+off$`),
      rx(`^${REQUEST_PREFIX}(?:stop|quit)\\s+(?:reading|speaking)\\s+(?:out\\s+loud|aloud)$`),
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
    ],
  ],
  [
    'voice-faster',
    [
      rx(`^${REQUEST_PREFIX}(?:speak|talk|read)\\s+faster$`),
      rx(`^${REQUEST_PREFIX}(?:speed\\s+up|increase|raise)\\s+(?:the\\s+)?(?:voice|speech|voice\\s+speed|speech\\s+rate)$`),
      rx(`^${REQUEST_PREFIX}(?:voice|speech)\\s+faster$`),
    ],
  ],
  [
    'voice-normal',
    [
      rx(`^${REQUEST_PREFIX}(?:normal|default|reset)\\s+(?:voice|speech|voice\\s+speed|speech\\s+rate)$`),
      rx(`^${REQUEST_PREFIX}(?:speak|talk|read)\\s+(?:normally|normal)$`),
    ],
  ],
  [
    'stop-speaking',
    [rx(`^${REQUEST_PREFIX}(?:stop\\s+speaking|stop\\s+talking|stop\\s+reading|be\\s+quiet|silence)$`)],
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

export function normalizeSpokenQMeet(text: string): string {
  return text.replace(
    /\b(?:q\s*meet|queue\s+meet|cue\s+meet|cute\s+meet|q\s*meat|queue\s+meat|cue\s+meat|cute\s+meat|key\s+meet|key\s+meat|q\s*me|queue\s+me|cue\s+me)\b/gi,
    'QMeet'
  );
}

function normalizeCommandText(text: string): string {
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
  const normalized = normalizeCommandText(text);
  
  for (const [command, patterns] of COMMAND_PATTERNS) {
    if (patterns.some((pattern) => pattern.test(normalized))) {
      return {
        command,
        confirmation: CONFIRMATIONS[command],
      };
    }
  }

  return null;
}
