import { useEffect, useRef } from 'react';

type ActiveSession = {
  id: string;
  title: string;
  mode: string;
  goal: string;
};

type ActiveSessionEventDetail = {
  activeSession?: unknown;
};

type BackgroundWorkContext = {
  sessionId: string;
  title: string;
  mode: string;
  objective: string;
  openQuestions: string[];
  stage: string;
  confidence: number;
};

type WorkContextResponse = {
  activeContext?: unknown;
};

type PromptHistory = Record<string, string>;

const ACTIVE_SESSION_STATE_EVENT = 'qmeet-active-session-state';
const FOCUS_CHAT_EVENT = 'qmeet-enhanced-focus-recap-chat';
const PROMPT_HISTORY_STORAGE_KEY = 'qmeet-focus-conversation-prompts-v1';
const RETRY_DELAYS_MS = [180, 450, 900, 1600, 2800, 4400];
const MAX_PROMPT_HISTORY = 40;

function getApiBaseUrl() {
  const configuredUrl = import.meta.env.VITE_QMEET_API_URL?.trim();
  return (configuredUrl || 'http://localhost:8000').replace(/\/+$/, '');
}

function cleanText(value: unknown, maxLength = 500) {
  if (typeof value !== 'string') return '';
  return value.replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

function cleanStringArray(value: unknown, maxItems = 4) {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => cleanText(item, 240))
    .filter(Boolean)
    .slice(0, maxItems);
}

function normalizeActiveSession(value: unknown): ActiveSession | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<ActiveSession>;
  const id = cleanText(candidate.id, 140);
  const title = cleanText(candidate.title, 160);
  if (!id || !title) return null;

  return {
    id,
    title,
    mode: cleanText(candidate.mode, 40) || 'general',
    goal: cleanText(candidate.goal, 500),
  };
}

function normalizeWorkContext(value: unknown): BackgroundWorkContext | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<BackgroundWorkContext>;
  const sessionId = cleanText(candidate.sessionId, 140);
  const title = cleanText(candidate.title, 160);
  if (!sessionId || !title) return null;

  return {
    sessionId,
    title,
    mode: cleanText(candidate.mode, 40) || 'general',
    objective: cleanText(candidate.objective, 500),
    openQuestions: cleanStringArray(candidate.openQuestions),
    stage: cleanText(candidate.stage, 40) || 'discovery',
    confidence:
      typeof candidate.confidence === 'number' &&
      Number.isFinite(candidate.confidence)
        ? Math.max(0, Math.min(1, candidate.confidence))
        : 0,
  };
}

function readPromptHistory(): PromptHistory {
  if (typeof window === 'undefined') return {};

  try {
    const rawValue = window.localStorage.getItem(PROMPT_HISTORY_STORAGE_KEY);
    if (!rawValue) return {};

    const parsedValue = JSON.parse(rawValue);
    if (
      !parsedValue ||
      typeof parsedValue !== 'object' ||
      Array.isArray(parsedValue)
    ) {
      return {};
    }

    const entries = Object.entries(parsedValue as Record<string, unknown>)
      .map(
        ([sessionId, signature]) =>
          [cleanText(sessionId, 140), cleanText(signature, 500)] as const,
      )
      .filter(([sessionId, signature]) => Boolean(sessionId && signature))
      .slice(-MAX_PROMPT_HISTORY);

    return Object.fromEntries(entries);
  } catch {
    return {};
  }
}

function writePromptHistory(history: PromptHistory) {
  if (typeof window === 'undefined') return;

  try {
    const trimmedEntries = Object.entries(history).slice(-MAX_PROMPT_HISTORY);
    window.localStorage.setItem(
      PROMPT_HISTORY_STORAGE_KEY,
      JSON.stringify(Object.fromEntries(trimmedEntries)),
    );
  } catch {
    // Focus onboarding is optional; storage failures must not affect chat.
  }
}

function hasPromptedSession(sessionId: string) {
  return Boolean(readPromptHistory()[sessionId]);
}

function rememberPrompt(sessionId: string, question: string) {
  const history = readPromptHistory();
  delete history[sessionId];
  history[sessionId] = question;
  writePromptHistory(history);
}

function wait(delayMs: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, delayMs);
  });
}

async function fetchMatchingContext(
  sessionId: string,
): Promise<BackgroundWorkContext | null> {
  const endpoint = `${getApiBaseUrl()}/api/work-context`;

  for (const delayMs of RETRY_DELAYS_MS) {
    await wait(delayMs);

    try {
      const response = await fetch(endpoint, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!response.ok) continue;

      const payload = (await response.json()) as WorkContextResponse;
      const context = normalizeWorkContext(payload.activeContext);
      if (context?.sessionId === sessionId) return context;
    } catch {
      // The backend may still be persisting the new focus. Retry quietly.
    }
  }

  return null;
}

function fallbackQuestion(session: ActiveSession) {
  const subject = session.goal || session.title;

  switch (session.mode) {
    case 'coding':
      return `What does the smallest working version of ${subject} need to do?`;
    case 'meeting':
      return 'What outcome should this meeting produce?';
    case 'research':
      return 'What exact question should this research answer?';
    case 'planning':
      return 'What result and deadline should shape this plan?';
    case 'personal':
      return 'What would make this feel successful for you?';
    default:
      return 'What result would make this focus successful?';
  }
}

function buildAssistantPrompt(
  session: ActiveSession,
  context: BackgroundWorkContext | null,
  question: string,
) {
  const objective = context?.objective || session.goal || 'Not fully defined yet';

  return [
    'QMeet automatic focus onboarding turn.',
    'This is an assistant-initiated follow-up after the user started a new background focus.',
    `Focus title: ${context?.title || session.title}`,
    `Focus mode: ${context?.mode || session.mode}`,
    `Current objective: ${objective}`,
    `Most useful unanswered question: ${question}`,
    '',
    'Respond as QMeet in a warm, natural way.',
    'Briefly acknowledge that this is now the main focus, then ask exactly one follow-up question.',
    'Ask the unanswered question above, with only light conversational rewording if needed.',
    'Do not pretend the user sent another message.',
    'Do not explain the focus feature, mention Memory, list tools, create tasks, or ask a second question.',
    'Keep the whole response to two or three short sentences.',
  ].join('\n');
}

function dispatchFocusQuestion(
  session: ActiveSession,
  context: BackgroundWorkContext | null,
  question: string,
) {
  window.dispatchEvent(
    new CustomEvent(FOCUS_CHAT_EVENT, {
      detail: {
        prompt: buildAssistantPrompt(session, context, question),
        assistantOnly: true,
      },
    }),
  );
}

export function FocusConversationBridge() {
  const pendingSessionRef = useRef<string | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleSessionState = (event: Event) => {
      const detail = (event as CustomEvent<ActiveSessionEventDetail>).detail;
      const session = normalizeActiveSession(detail?.activeSession);

      if (!session) {
        pendingSessionRef.current = null;
        return;
      }

      if (
        pendingSessionRef.current === session.id ||
        hasPromptedSession(session.id)
      ) {
        return;
      }

      pendingSessionRef.current = session.id;

      void (async () => {
        const context = await fetchMatchingContext(session.id);
        if (pendingSessionRef.current !== session.id) return;

        const question =
          context?.stage === 'complete'
            ? ''
            : context?.openQuestions[0] || fallbackQuestion(session);

        if (!question || hasPromptedSession(session.id)) {
          pendingSessionRef.current = null;
          return;
        }

        rememberPrompt(session.id, question);
        dispatchFocusQuestion(session, context, question);
        pendingSessionRef.current = null;
      })();
    };

    window.addEventListener(ACTIVE_SESSION_STATE_EVENT, handleSessionState);
    return () => {
      window.removeEventListener(ACTIVE_SESSION_STATE_EVENT, handleSessionState);
    };
  }, []);

  return null;
}
