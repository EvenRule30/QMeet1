import type { ActivePanel, ActiveSession, MemorySessionMode, MemoryTask } from '../types';
import type { CommandMatch, FocusSessionCommandPayload } from '../commands';
import {
  clearActiveSession,
  replaceActiveSession,
  updateActiveSession,
} from '../api';

export type MemoryCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
};

type ActiveSessionStateEventDetail = {
  activeSession: ActiveSession | null;
};

type NormalizedFocusPayload = {
  title?: string;
  mode?: MemorySessionMode;
  goal?: string;
};

const ACTIVE_SESSION_STORAGE_KEY = 'qmeet-active-session';
const ACTIVE_SESSION_SESSION_STORAGE_KEY = 'qmeet-active-session-live';
const ACTIVE_SESSION_STATE_EVENT = 'qmeet-active-session-state';
const ACTIVE_SESSION_COMMAND_HANDLER_MARKER = 'phase12c-v3-state-event-is-source-of-truth';

function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isMemorySessionMode(value: string | undefined): value is MemorySessionMode {
  return (
    value === 'general' ||
    value === 'coding' ||
    value === 'meeting' ||
    value === 'planning' ||
    value === 'research' ||
    value === 'personal'
  );
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function normalizeActiveSession(value: unknown): ActiveSession | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<ActiveSession>;
  if (typeof candidate.title !== 'string' || !candidate.title.trim()) {
    return null;
  }

  const now = new Date().toISOString();

  return {
    id:
      typeof candidate.id === 'string' && candidate.id.trim()
        ? candidate.id
        : createId('session'),
    title: candidate.title.trim(),
    mode: isMemorySessionMode(candidate.mode) ? candidate.mode : 'general',
    goal: typeof candidate.goal === 'string' ? candidate.goal : '',
    startedAt:
      typeof candidate.startedAt === 'string' ? candidate.startedAt : now,
    updatedAt:
      typeof candidate.updatedAt === 'string' ? candidate.updatedAt : now,
    pinnedNoteIds: readStringArray(candidate.pinnedNoteIds),
    linkedTaskIds: readStringArray(candidate.linkedTaskIds),
    ...(typeof candidate.summary === 'string'
      ? { summary: candidate.summary }
      : candidate.summary === null
        ? { summary: null }
        : {}),
  };
}

function readStoredActiveSession(): ActiveSession | null {
  if (typeof window === 'undefined') return null;

  const storageKeys = [ACTIVE_SESSION_STORAGE_KEY, ACTIVE_SESSION_SESSION_STORAGE_KEY];

  for (const storageKey of storageKeys) {
    try {
      const storage =
        storageKey === ACTIVE_SESSION_SESSION_STORAGE_KEY
          ? window.sessionStorage
          : window.localStorage;
      const rawSession = storage.getItem(storageKey);
      if (!rawSession) continue;
      const activeSession = normalizeActiveSession(JSON.parse(rawSession));
      if (activeSession) return activeSession;
    } catch {
      // Try the next fallback store.
    }
  }

  return null;
}

function writeStoredActiveSession(activeSession: ActiveSession | null) {
  if (typeof window === 'undefined') return;

  try {
    if (activeSession) {
      const serializedSession = JSON.stringify(activeSession);
      window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, serializedSession);
      window.sessionStorage.setItem(
        ACTIVE_SESSION_SESSION_STORAGE_KEY,
        serializedSession,
      );
    } else {
      window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
      window.sessionStorage.removeItem(ACTIVE_SESSION_SESSION_STORAGE_KEY);
    }
  } catch (error) {
    console.error('Failed to write active session fallback:', error);
  }
}

function dispatchActiveSessionState(activeSession: ActiveSession | null) {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent<ActiveSessionStateEventDetail>(ACTIVE_SESSION_STATE_EVENT, {
      detail: { activeSession },
    }),
  );
}

function persistActiveSessionToBackend(activeSession: ActiveSession | null) {
  if (activeSession) {
    replaceActiveSession({ activeSession }).catch((error) => {
      console.warn('Active session backend save failed:', error);
    });
    return;
  }

  clearActiveSession().catch((error) => {
    console.warn('Active session backend clear failed:', error);
  });
}

function patchActiveSessionInBackend(
  updates: Partial<
    Pick<
      ActiveSession,
      'title' | 'mode' | 'goal' | 'pinnedNoteIds' | 'linkedTaskIds' | 'summary'
    >
  >,
) {
  updateActiveSession(updates).catch((error) => {
    console.warn('Active session backend update failed:', error);
  });
}

function applyActiveSession(activeSession: ActiveSession | null) {
  writeStoredActiveSession(activeSession);
  dispatchActiveSessionState(activeSession);
}

function createActiveSession(
  payload: FocusSessionCommandPayload | undefined,
  fallbackTitle?: string,
): ActiveSession {
  const now = new Date().toISOString();
  const title =
    payload?.title?.trim() || fallbackTitle?.trim() || 'Focus session';
  const mode = isMemorySessionMode(payload?.mode) ? payload.mode : 'general';
  const goal = payload?.goal?.trim() ?? '';

  return {
    id: createId('session'),
    title,
    mode,
    goal,
    startedAt: now,
    updatedAt: now,
    pinnedNoteIds: [],
    linkedTaskIds: [],
  };
}

function updateLocalActiveSession(
  payload: FocusSessionCommandPayload | undefined,
): ActiveSession {
  const existingSession = readStoredActiveSession();

  if (!existingSession) {
    return createActiveSession(
      {
        title: payload?.title?.trim() || 'Focus session',
        mode: payload?.mode,
        goal: payload?.goal,
      },
      'Focus session',
    );
  }

  return {
    ...existingSession,
    ...(payload?.title?.trim() ? { title: payload.title.trim() } : {}),
    ...(isMemorySessionMode(payload?.mode) ? { mode: payload.mode } : {}),
    ...(typeof payload?.goal === 'string'
      ? { goal: payload.goal.trim() }
      : {}),
    updatedAt: new Date().toISOString(),
  };
}

function describeActiveSession(activeSession: ActiveSession | null): string {
  if (!activeSession) {
    return 'No active focus session is running.';
  }

  const goalText = activeSession.goal
    ? ` Goal: ${activeSession.goal}.`
    : ' No goal has been set yet.';
  const linkedTaskText =
    activeSession.linkedTaskIds.length > 0
      ? ` ${activeSession.linkedTaskIds.length} linked task${
          activeSession.linkedTaskIds.length === 1 ? '' : 's'
        }.`
      : '';
  const pinnedNoteText =
    activeSession.pinnedNoteIds.length > 0
      ? ` ${activeSession.pinnedNoteIds.length} pinned note${
          activeSession.pinnedNoteIds.length === 1 ? '' : 's'
        }.`
      : '';

  return `Current focus: ${activeSession.title}. Mode: ${activeSession.mode}.${goalText}${linkedTaskText}${pinnedNoteText}`;
}

function normalizeFocusPayload(
  payload: FocusSessionCommandPayload | undefined,
): NormalizedFocusPayload {
  const title = payload?.title?.trim();
  const goal = payload?.goal?.trim();
  const mode = isMemorySessionMode(payload?.mode) ? payload.mode : undefined;

  return {
    ...(title ? { title } : {}),
    ...(mode ? { mode } : {}),
    ...(goal ? { goal } : {}),
  };
}

function describeFocusStart(payload: FocusSessionCommandPayload | undefined) {
  const title = payload?.title?.trim() || 'Focus session';
  const mode = payload?.mode ? ` ${payload.mode}` : '';
  const goal = payload?.goal?.trim();

  return `Started${mode} focus session: ${title}.${goal ? ` Goal: ${goal}.` : ''}`;
}

function describeFocusUpdate(payload: FocusSessionCommandPayload | undefined) {
  const pieces: string[] = [];

  if (payload?.title?.trim()) {
    pieces.push(`title: ${payload.title.trim()}`);
  }
  if (payload?.mode) {
    pieces.push(`mode: ${payload.mode}`);
  }
  if (payload?.goal?.trim()) {
    pieces.push(`goal: ${payload.goal.trim()}`);
  }

  return pieces.length > 0
    ? `Updated focus session ${pieces.join(', ')}.`
    : 'Focus session updated.';
}

export function handleMemoryCommand(
  commandMatch: CommandMatch,
  deps: {
    voiceOutputEnabled: boolean;
    setActivePanel: (panel: ActivePanel) => void;
    closePanel: () => void;
    getMemoryReadout: () => string;
    saveMemoryTask: (title: string) => MemoryTask | null;
    markMemoryTaskDone: (
      lookup?: string,
      operation?: 'complete' | 'delete',
    ) => MemoryTask | null;
    clearCompletedTasks: () => number;
  },
): MemoryCommandResult {
  switch (commandMatch.command) {
    case 'open-memory':
      deps.setActivePanel('memory');
      return { handled: true };

    case 'close-memory':
      deps.closePanel();
      return { handled: true };

    case 'read-focus-session':
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: describeActiveSession(readStoredActiveSession()),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };

    case 'read-memory': {
      deps.setActivePanel('memory');
      const activeSession = readStoredActiveSession();
      const memoryReadout = deps.getMemoryReadout();
      const focusReadout = activeSession ? describeActiveSession(activeSession) : '';
      const normalizedMemoryReadout = activeSession
        ? memoryReadout.replace(/^No active focus session\.\s*/i, '')
        : memoryReadout;

      return {
        handled: true,
        confirmationContent: focusReadout
          ? `${focusReadout} ${normalizedMemoryReadout}`.trim()
          : normalizedMemoryReadout,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'start-focus-session': {
      const detail = normalizeFocusPayload(commandMatch.focusSession);
      const title = detail.title || commandMatch.payload?.trim() || 'Focus session';
      const session = createActiveSession(
        {
          ...commandMatch.focusSession,
          title,
        },
        title,
      );

      applyActiveSession(session);
      persistActiveSessionToBackend(session);
      deps.setActivePanel('memory');

      return {
        handled: true,
        confirmationContent: describeFocusStart({
          ...commandMatch.focusSession,
          title,
        }),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'update-focus-session': {
      const payload = commandMatch.focusSession ?? {};
      const hadExistingSession = !!readStoredActiveSession();
      const updatedSession = updateLocalActiveSession(payload);

      applyActiveSession(updatedSession);

      if (hadExistingSession) {
        patchActiveSessionInBackend({
          ...(payload.title?.trim() ? { title: payload.title.trim() } : {}),
          ...(isMemorySessionMode(payload.mode) ? { mode: payload.mode } : {}),
          ...(typeof payload.goal === 'string'
            ? { goal: payload.goal.trim() }
            : {}),
        });
      } else {
        persistActiveSessionToBackend(updatedSession);
      }

      deps.setActivePanel('memory');

      return {
        handled: true,
        confirmationContent: describeFocusUpdate(payload),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'end-focus-session': {
      const existingSession = readStoredActiveSession();
      applyActiveSession(null);
      persistActiveSessionToBackend(null);
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: existingSession
          ? `Ended focus session: ${existingSession.title}.`
          : 'No active focus session was running.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'remember-task': {
      const savedTask = deps.saveMemoryTask(commandMatch.payload ?? '');
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: savedTask
          ? `Saved task: ${savedTask.title}.`
          : 'I did not catch the task text.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'mark-task-done': {
      const completedTask = deps.markMemoryTaskDone(commandMatch.payload);
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: completedTask
          ? `Marked task done: ${completedTask.title}.`
          : commandMatch.payload
            ? `I could not find an open task matching "${commandMatch.payload}".`
            : 'No open tasks to complete.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'delete-last-task': {
      const deletedTask = deps.markMemoryTaskDone(undefined, 'delete');
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: deletedTask
          ? `Deleted task: ${deletedTask.title}.`
          : 'No tasks to delete.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'clear-done-tasks': {
      const removedCount = deps.clearCompletedTasks();
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent:
          removedCount > 0
            ? `Cleared ${removedCount} completed task${
                removedCount === 1 ? '' : 's'
              }.`
            : 'No completed tasks to clear.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    default:
      return { handled: false };
  }
}
