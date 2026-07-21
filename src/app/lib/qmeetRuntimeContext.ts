export type QMeetRuntimeContext = {
  uiState: {
    activePanel: string | null;
    chatOpen: boolean;
    cameraOpen: boolean;
    menuOpen: boolean;
    promptFocused: boolean;
    visibleHints: string[];
  };
  memoryState: {
    activeSession: unknown | null;
    recentFocusSessionCount: number;
    openTaskCount: number;
    completedTaskCount: number;
    noteCount: number;
    lastVisualObservation: unknown | null;
    visualObservationCount: number;
  };
};

const ACTIVE_SESSION_KEYS = ['qmeet-active-session-live', 'qmeet-active-session'];
const TASKS_KEY = 'qmeet-memory-tasks';
const NOTES_KEY = 'qmeet-notes';
const RECENT_FOCUS_SESSIONS_KEY = 'qmeet-recent-focus-sessions';
const VISUAL_CONTEXT_KEY = 'qmeet-visual-context';

function safeReadJson<T>(storage: Storage | undefined, key: string, fallback: T): T {
  if (!storage) return fallback;
  try {
    const raw = storage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function readActiveSession(): unknown | null {
  if (typeof window === 'undefined') return null;
  for (const key of ACTIVE_SESSION_KEYS) {
    const storage = key.endsWith('-live') ? window.sessionStorage : window.localStorage;
    const value = safeReadJson<unknown | null>(storage, key, null);
    if (value && typeof value === 'object') return value;
  }
  return null;
}

function getBodyText(): string {
  if (typeof document === 'undefined') return '';
  return document.body?.innerText ?? '';
}

function isVisible(element: Element | null): boolean {
  if (!(element instanceof HTMLElement)) return false;
  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  return (
    rect.width > 1 &&
    rect.height > 1 &&
    style.visibility !== 'hidden' &&
    style.display !== 'none' &&
    Number(style.opacity || '1') > 0.01
  );
}

function hasVisibleText(pattern: RegExp): boolean {
  return pattern.test(getBodyText());
}

function detectPanel(): string | null {
  if (typeof document === 'undefined') return null;

  const panelContent = Array.from(document.querySelectorAll('.panel-content')).find(isVisible);
  const panelText = panelContent?.textContent ?? '';

  if (isVisible(document.querySelector('.qmeet-camera-overlay, [data-qmeet-camera-overlay="true"]'))) return 'camera';
  if (/Choose a QMeet tool by touch|Notes\s+Memory\s+Calendar/i.test(panelText)) return 'menu';
  if (/Current Focus|Backend Memory|Recent Focus Sessions|Visual Context|Memory Controls/i.test(panelText)) return 'memory';
  if (/Saved Notes|New Note|Write and review local notes/i.test(panelText)) return 'notes';
  if (/Google Calendar|Calendar Events|Today|Tomorrow/i.test(panelText) && /calendar/i.test(panelText)) return 'calendar';
  if (/Search the web|Search Results|Web Search/i.test(panelText)) return 'search';
  if (/Settings|Voice Output|Speech Rate/i.test(panelText)) return 'settings';
  if (/System Status|Interpreter|Last heard|Backend/i.test(panelText)) return 'status';

  if (hasVisibleText(/Choose a QMeet tool by touch/i)) return 'menu';
  if (hasVisibleText(/Current Focus|Backend Memory|Recent Focus Sessions|Visual Context/i)) return 'memory';
  if (hasVisibleText(/Saved Notes|New Note|Write and review local notes/i)) return 'notes';
  if (hasVisibleText(/Google Calendar|Calendar Events|Today|Tomorrow/i) && hasVisibleText(/calendar/i)) return 'calendar';
  if (hasVisibleText(/Search the web|Search Results|Web Search/i)) return 'search';
  if (hasVisibleText(/Settings|Voice Output|Speech Rate/i)) return 'settings';
  if (hasVisibleText(/System Status|Interpreter|Last heard|Backend/i)) return 'status';

  const chatArea = document.querySelector('.chat-area');
  if (
    isVisible(chatArea) &&
    (chatArea?.classList.contains('chat-area-visible') ||
      (chatArea instanceof HTMLElement && chatArea.getBoundingClientRect().width > 80))
  ) {
    return 'chat';
  }

  return null;
}

function collectVisibleHints(): string[] {
  if (typeof document === 'undefined') return [];
  const text = getBodyText();
  const hints: string[] = [];
  const checks: Array<[string, RegExp]> = [
    ['current focus card', /Current Focus/i],
    ['focus goal shown', /Goal:/i],
    ['focus action buttons', /Create tasks|Save note|End with summary/i],
    ['focus nudges', /Focus Nudges/i],
    ['recent focus sessions', /Recent Focus Sessions/i],
    ['visual context', /Visual Context/i],
    ['memory controls', /Memory Controls|Clear All|Reset Context/i],
    ['calendar auth', /Google Calendar/i],
    ['search results', /Search Results/i],
    ['notes editor', /Saved Notes|New Note/i],
    ['main menu cards', /Choose a QMeet tool by touch/i],
  ];
  for (const [label, pattern] of checks) {
    if (pattern.test(text)) hints.push(label);
  }
  return hints.slice(0, 10);
}

export function collectQMeetRuntimeContext(): QMeetRuntimeContext {
  if (typeof window === 'undefined') {
    return {
      uiState: {
        activePanel: null,
        chatOpen: false,
        cameraOpen: false,
        menuOpen: false,
        promptFocused: false,
        visibleHints: [],
      },
      memoryState: {
        activeSession: null,
        recentFocusSessionCount: 0,
        openTaskCount: 0,
        completedTaskCount: 0,
        noteCount: 0,
        lastVisualObservation: null,
        visualObservationCount: 0,
      },
    };
  }

  const tasks = safeReadJson<Array<{ completedAt?: string | null }>>(window.localStorage, TASKS_KEY, []);
  const notes = safeReadJson<unknown[]>(window.localStorage, NOTES_KEY, []);
  const recentFocusSessions = safeReadJson<unknown[]>(window.localStorage, RECENT_FOCUS_SESSIONS_KEY, []);
  const visualContext = safeReadJson<{
    lastObservation?: unknown | null;
    recentObservations?: unknown[];
  }>(window.localStorage, VISUAL_CONTEXT_KEY, {});

  const activePanel = detectPanel();
  const chatArea = document.querySelector('.chat-area');
  const chatOpen = Boolean(
    chatArea &&
      isVisible(chatArea) &&
      (chatArea.classList.contains('active') ||
        chatArea.classList.contains('chat-area-visible') ||
        chatArea.getBoundingClientRect().width > 80),
  );

  return {
    uiState: {
      activePanel,
      chatOpen,
      cameraOpen: activePanel === 'camera',
      menuOpen: activePanel === 'menu',
      promptFocused: document.activeElement instanceof HTMLElement
        ? /input|textarea/i.test(document.activeElement.tagName)
        : false,
      visibleHints: collectVisibleHints(),
    },
    memoryState: {
      activeSession: readActiveSession(),
      recentFocusSessionCount: Array.isArray(recentFocusSessions) ? recentFocusSessions.length : 0,
      openTaskCount: Array.isArray(tasks) ? tasks.filter((task) => !task?.completedAt).length : 0,
      completedTaskCount: Array.isArray(tasks) ? tasks.filter((task) => task?.completedAt).length : 0,
      noteCount: Array.isArray(notes) ? notes.length : 0,
      lastVisualObservation: visualContext?.lastObservation ?? null,
      visualObservationCount: Array.isArray(visualContext?.recentObservations)
        ? visualContext.recentObservations.length
        : 0,
    },
  };
}
