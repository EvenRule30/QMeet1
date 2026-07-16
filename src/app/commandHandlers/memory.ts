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
const SAVE_FOCUS_SUMMARY_NOTE_EVENT = 'qmeet-save-focus-summary-note';
const MEMORY_TASKS_STORAGE_KEY = 'qmeet-memory-tasks';
const RECENT_ACTIONS_STORAGE_KEY = 'qmeet-recent-actions';
const ACTIVE_SESSION_COMMAND_HANDLER_MARKER = 'phase12e-v4-focus-summary-notes-panel';

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


function readStoredMemoryTasks(): MemoryTask[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawTasks = window.localStorage.getItem(MEMORY_TASKS_STORAGE_KEY);
    if (!rawTasks) return [];
    const parsedTasks = JSON.parse(rawTasks);
    if (!Array.isArray(parsedTasks)) return [];

    return parsedTasks
      .filter((task) => task && typeof task.title === 'string')
      .map((task) => ({
        id: typeof task.id === 'string' ? task.id : createId('task'),
        title: task.title,
        createdAt:
          typeof task.createdAt === 'string'
            ? task.createdAt
            : new Date().toISOString(),
        ...(typeof task.completedAt === 'string'
          ? { completedAt: task.completedAt }
          : {}),
      }));
  } catch {
    return [];
  }
}

type StoredRecentAction = {
  id: string;
  label: string;
  detail: string;
  createdAt: string;
};

function readStoredRecentActions(): StoredRecentAction[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawActions = window.localStorage.getItem(RECENT_ACTIONS_STORAGE_KEY);
    if (!rawActions) return [];
    const parsedActions = JSON.parse(rawActions);
    if (!Array.isArray(parsedActions)) return [];

    return parsedActions
      .filter((action) => action && typeof action.label === 'string')
      .map((action) => ({
        id: typeof action.id === 'string' ? action.id : createId('action'),
        label: action.label,
        detail: typeof action.detail === 'string' ? action.detail : '',
        createdAt:
          typeof action.createdAt === 'string'
            ? action.createdAt
            : new Date().toISOString(),
      }));
  } catch {
    return [];
  }
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


function dispatchFocusSummaryNote(
  activeSession: ActiveSession,
  summary: string,
  options: { endAfterSave?: boolean } = {},
) {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent(SAVE_FOCUS_SUMMARY_NOTE_EVENT, {
      detail: {
        sessionId: activeSession.id,
        summary,
        title: activeSession.title,
        endAfterSave: Boolean(options.endAfterSave),
      },
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


function compactTaskSubject(value: string, fallback: string): string {
  const cleaned = value.replace(/\s+/g, ' ').trim();
  if (!cleaned) return fallback;
  return cleaned.length > 72 ? `${cleaned.slice(0, 69).trim()}...` : cleaned;
}

function uniqueTaskTitles(titles: string[]): string[] {
  const seen = new Set<string>();
  const uniqueTitles: string[] = [];

  for (const title of titles) {
    const cleaned = title.replace(/\s+/g, ' ').trim();
    if (!cleaned) continue;
    const key = cleaned.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    uniqueTitles.push(cleaned);
  }

  return uniqueTitles.slice(0, 5);
}

function generateFocusTaskTitles(activeSession: ActiveSession): string[] {
  const title = compactTaskSubject(activeSession.title, 'current focus');
  const goal = compactTaskSubject(activeSession.goal, title);
  const target = activeSession.goal ? goal : title;

  switch (activeSession.mode) {
    case 'coding':
      return uniqueTaskTitles([
        `Define the target behavior for ${title}`,
        `Inspect the relevant code paths for ${title}`,
        `Implement the smallest working change for ${target}`,
        `Test ${title} from the UI and backend`,
        `Commit the finished ${title} changes`,
      ]);
    case 'research':
      return uniqueTaskTitles([
        `List the key questions for ${title}`,
        `Gather useful sources or examples for ${target}`,
        `Compare findings and note tradeoffs for ${title}`,
        `Decide the next action from the ${title} research`,
      ]);
    case 'meeting':
      return uniqueTaskTitles([
        `Clarify the meeting objective for ${title}`,
        `Prepare agenda points for ${target}`,
        `Capture decisions from ${title}`,
        `Save follow-up tasks after ${title}`,
      ]);
    case 'planning':
      return uniqueTaskTitles([
        `Define the desired outcome for ${title}`,
        `Break ${target} into milestones`,
        `Identify blockers and dependencies for ${title}`,
        `Choose the first next action for ${title}`,
      ]);
    case 'personal':
      return uniqueTaskTitles([
        `Clarify what success looks like for ${title}`,
        `Choose one small next step for ${target}`,
        `Set aside time for ${title}`,
        `Review progress on ${title}`,
      ]);
    default:
      return uniqueTaskTitles([
        `Clarify the outcome for ${title}`,
        `Break ${target} into smaller steps`,
        `Identify the next concrete action for ${title}`,
        `Review progress and update the focus session`,
      ]);
  }
}

function linkTasksToActiveSession(
  activeSession: ActiveSession,
  tasks: MemoryTask[],
): ActiveSession {
  const linkedTaskIds = Array.from(
    new Set([
      ...activeSession.linkedTaskIds,
      ...tasks.map((task) => task.id).filter(Boolean),
    ]),
  );

  return {
    ...activeSession,
    linkedTaskIds,
    updatedAt: new Date().toISOString(),
  };
}

function describeFocusTasks(activeSession: ActiveSession, tasks: MemoryTask[]): string {
  if (tasks.length === 0) {
    return `I could not create tasks for ${activeSession.title}.`;
  }

  const taskList = tasks
    .map((task, index) => `${index + 1}. ${task.title}`)
    .join(' ');

  return `Added ${tasks.length} task${tasks.length === 1 ? '' : 's'} for ${activeSession.title}: ${taskList}`;
}


function formatFocusSummaryTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown';

  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function sentenceList(items: string[], fallback: string): string {
  const cleanedItems = items
    .map((item) => item.replace(/\s+/g, ' ').trim())
    .filter(Boolean);

  if (cleanedItems.length === 0) return fallback;
  return cleanedItems.join('; ');
}

function buildFocusSummary(activeSession: ActiveSession): string {
  const storedTasks = readStoredMemoryTasks();
  const storedRecentActions = readStoredRecentActions();
  const linkedTaskIds = new Set(activeSession.linkedTaskIds);
  const linkedTasks = storedTasks.filter((task) => linkedTaskIds.has(task.id));
  const openLinkedTasks = linkedTasks.filter((task) => !task.completedAt);
  const completedLinkedTasks = linkedTasks.filter((task) => task.completedAt);
  const recentFocusActions = storedRecentActions
    .filter((action) => {
      const actionText = `${action.label} ${action.detail}`.toLowerCase();
      return (
        actionText.includes('focus') ||
        actionText.includes(activeSession.title.toLowerCase()) ||
        (activeSession.goal && actionText.includes(activeSession.goal.toLowerCase()))
      );
    })
    .slice(0, 5)
    .map((action) =>
      action.detail ? `${action.label}: ${action.detail}` : action.label,
    );

  const lines = [
    `Focus summary - ${activeSession.title}`,
    `Mode: ${activeSession.mode}`,
    activeSession.goal ? `Goal: ${activeSession.goal}` : 'Goal: No goal set',
    `Started: ${formatFocusSummaryTime(activeSession.startedAt)}`,
    `Last updated: ${formatFocusSummaryTime(activeSession.updatedAt)}`,
    linkedTasks.length > 0
      ? `Linked tasks: ${linkedTasks.length} total, ${openLinkedTasks.length} open, ${completedLinkedTasks.length} completed. ${sentenceList(
          linkedTasks.slice(0, 5).map((task) => task.title),
          '',
        )}`.trim()
      : 'Linked tasks: None yet',
    recentFocusActions.length > 0
      ? `Recent focus actions: ${sentenceList(recentFocusActions, 'None yet')}`
      : 'Recent focus actions: None yet',
  ];

  return lines.join('\n');
}

function describeFocusSummary(activeSession: ActiveSession): string {
  const storedTasks = readStoredMemoryTasks();
  const linkedTaskIds = new Set(activeSession.linkedTaskIds);
  const linkedTasks = storedTasks.filter((task) => linkedTaskIds.has(task.id));
  const taskText = linkedTasks.length > 0
    ? ` ${linkedTasks.length} linked task${linkedTasks.length === 1 ? '' : 's'}.`
    : '';
  const goalText = activeSession.goal ? ` Goal: ${activeSession.goal}.` : ' No goal has been set yet.';

  return `Focus summary for ${activeSession.title}. Mode: ${activeSession.mode}.${goalText}${taskText}`;
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

    case 'read-focus-session': {
      deps.setActivePanel('memory');
      const activeSession = readStoredActiveSession();

      return {
        handled: true,
        confirmationContent: describeActiveSession(activeSession),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

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
      const focusPayload = {
        ...commandMatch.focusSession,
        title,
      };

      const session = createActiveSession(
        focusPayload,
        title,
      );

      applyActiveSession(session);
      persistActiveSessionToBackend(session);
      deps.setActivePanel('memory');

      return {
        handled: true,
        confirmationContent: describeFocusStart(focusPayload),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'update-focus-session': {
      const payload = commandMatch.focusSession ?? {};

      const existingSession = readStoredActiveSession();
      const hadExistingSession = !!existingSession;
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
        confirmationContent: hadExistingSession
          ? describeFocusUpdate(payload)
          : describeFocusStart(updatedSession),
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



    case 'summarize-focus-session': {
      const activeSession = readStoredActiveSession();
      deps.setActivePanel('memory');

      if (!activeSession) {
        return {
          handled: true,
          confirmationContent:
            'No active focus session is running. Start a focus session first, then I can summarize it.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const summary = buildFocusSummary(activeSession);
      return {
        handled: true,
        confirmationContent: summary,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'save-focus-summary': {
      const activeSession = readStoredActiveSession();

      if (!activeSession) {
        deps.setActivePanel('memory');
        return {
          handled: true,
          confirmationContent:
            'No active focus session is running. Start a focus session first, then I can save a summary note.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const summary = buildFocusSummary(activeSession);
      dispatchFocusSummaryNote(activeSession, summary);
      patchActiveSessionInBackend({ summary });
      deps.setActivePanel('notes');

      return {
        handled: true,
        confirmationContent: `Saved focus summary as a note for ${activeSession.title}. ${describeFocusSummary(activeSession)}`,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'end-focus-with-summary': {
      const activeSession = readStoredActiveSession();

      if (!activeSession) {
        deps.setActivePanel('memory');
        return {
          handled: true,
          confirmationContent:
            'No active focus session is running, so there is nothing to summarize or end.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const summary = buildFocusSummary(activeSession);
      dispatchFocusSummaryNote(activeSession, summary, { endAfterSave: true });
      applyActiveSession(null);
      persistActiveSessionToBackend(null);
      deps.setActivePanel('notes');

      return {
        handled: true,
        confirmationContent: `Saved a summary note and ended focus session: ${activeSession.title}.`,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'focus-to-tasks': {
      const activeSession = readStoredActiveSession();
      deps.setActivePanel('memory');

      if (!activeSession) {
        return {
          handled: true,
          confirmationContent:
            'No active focus session is running. Start a focus session first, then I can turn it into tasks.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const createdTasks = generateFocusTaskTitles(activeSession)
        .map((title) => deps.saveMemoryTask(title))
        .filter((task): task is MemoryTask => task !== null);

      if (createdTasks.length > 0) {
        const updatedSession = linkTasksToActiveSession(activeSession, createdTasks);
        applyActiveSession(updatedSession);
        patchActiveSessionInBackend({ linkedTaskIds: updatedSession.linkedTaskIds });
      }

      return {
        handled: true,
        confirmationContent: describeFocusTasks(activeSession, createdTasks),
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
