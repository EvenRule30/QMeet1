import {
  type ChangeEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

import {
  ActiveSession,
  CalendarEvent,
  MemorySessionMode,
  MemoryTask,
  Note,
  RecentAction,
  RecentFocusSession,
  SearchResponse,
  VisualContext,
  VisualObservation,
} from '../types';
import {
  clearAllMemoryContext,
  exportMemoryContext,
  getMemoryContext,
  importMemoryContext,
  replaceMemoryContext,
} from '../api';
import { getMemoryInitialization } from '../lib/memoryInitializationApi';
import { normalizeMemoryLookup } from '../lib/memoryUtils';
import { ResultToast } from '../lib/toastUtils';

export type MemorySyncState = 'local' | 'syncing' | 'synced' | 'error';

type ResultToastInput = Omit<ResultToast, 'id' | 'createdAt'> | null;

type UseMemoryContextArgs = {
  pushResultToast: (toastInput: ResultToastInput) => void;
  calendarEvents: CalendarEvent[];
  googleCalendarEvents: CalendarEvent[];
  searchQuery: string;
  searchResult: SearchResponse | null;
};

type ActiveSessionDraft = {
  title: string;
  mode?: MemorySessionMode;
  goal?: string;
  pinnedNoteIds?: string[];
  linkedTaskIds?: string[];
  summary?: string | null;
};

type ActiveSessionUpdate = Partial<
  Pick<
    ActiveSession,
    'title' | 'mode' | 'goal' | 'pinnedNoteIds' | 'linkedTaskIds' | 'summary'
  >
>;

type VisualContextStateEventDetail = {
  visualContext: VisualContext;
};

type MemoryTasksStateEventDetail = {
  tasks: MemoryTask[];
};

const MEMORY_TASKS_STORAGE_KEY = 'qmeet-memory-tasks';
const RECENT_ACTIONS_STORAGE_KEY = 'qmeet-recent-actions';
const RECENT_FOCUS_SESSIONS_STORAGE_KEY = 'qmeet-recent-focus-sessions';
const NOTES_STORAGE_KEY = 'qmeet-notes';
const ACTIVE_SESSION_STORAGE_KEY = 'qmeet-active-session';
const VISUAL_CONTEXT_STORAGE_KEY = 'qmeet-visual-context';
const MEMORY_TASKS_STATE_EVENT = 'qmeet-memory-tasks-state';
const VISUAL_CONTEXT_STATE_EVENT = 'qmeet-visual-context-state';

function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isMemorySessionMode(value: unknown): value is MemorySessionMode {
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

function normalizeActiveSession(session: unknown): ActiveSession | null {
  if (!session || typeof session !== 'object') return null;

  const candidate = session as Partial<ActiveSession>;
  if (typeof candidate.title !== 'string' || !candidate.title.trim()) {
    return null;
  }

  const now = new Date().toISOString();

  return {
    id: typeof candidate.id === 'string' ? candidate.id : createId('session'),
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


function normalizeRecentFocusSession(session: unknown): RecentFocusSession | null {
  if (!session || typeof session !== 'object') return null;

  const candidate = session as Partial<RecentFocusSession>;
  if (typeof candidate.title !== 'string' || !candidate.title.trim()) {
    return null;
  }

  const now = new Date().toISOString();

  return {
    id: typeof candidate.id === 'string' ? candidate.id : createId('session'),
    title: candidate.title.trim(),
    mode: isMemorySessionMode(candidate.mode) ? candidate.mode : 'general',
    goal: typeof candidate.goal === 'string' ? candidate.goal : '',
    startedAt:
      typeof candidate.startedAt === 'string' ? candidate.startedAt : now,
    endedAt: typeof candidate.endedAt === 'string' ? candidate.endedAt : now,
    pinnedNoteIds: readStringArray(candidate.pinnedNoteIds),
    linkedTaskIds: readStringArray(candidate.linkedTaskIds),
    ...(typeof candidate.summary === 'string'
      ? { summary: candidate.summary }
      : candidate.summary === null
        ? { summary: null }
        : {}),
    ...(typeof candidate.summaryNoteId === 'string'
      ? { summaryNoteId: candidate.summaryNoteId }
      : candidate.summaryNoteId === null
        ? { summaryNoteId: null }
        : {}),
  };
}

function normalizeRecentFocusSessions(value: unknown): RecentFocusSession[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((session) => normalizeRecentFocusSession(session))
    .filter((session): session is RecentFocusSession => Boolean(session));
}


function recentFocusSessionsAreSame(
  first: RecentFocusSession[],
  second: RecentFocusSession[],
): boolean {
  return JSON.stringify(first) === JSON.stringify(second);
}


function createEmptyVisualContext(): VisualContext {
  return {
    enabled: false,
    lastObservation: null,
    recentObservations: [],
  };
}

function isVisualContextSource(value: unknown): value is VisualObservation['source'] {
  return value === 'camera' || value === 'screen' || value === 'manual';
}

function normalizeVisualObservation(value: unknown): VisualObservation | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<VisualObservation>;
  if (typeof candidate.summary !== 'string' || !candidate.summary.trim()) {
    return null;
  }

  const confidence =
    typeof candidate.confidence === 'number' && Number.isFinite(candidate.confidence)
      ? Math.max(0, Math.min(1, candidate.confidence))
      : null;

  return {
    id:
      typeof candidate.id === 'string' && candidate.id.trim()
        ? candidate.id
        : createId('visual'),
    source: isVisualContextSource(candidate.source) ? candidate.source : 'manual',
    summary: candidate.summary.trim(),
    capturedAt:
      typeof candidate.capturedAt === 'string'
        ? candidate.capturedAt
        : new Date().toISOString(),
    ...(confidence === null ? {} : { confidence }),
    ...(typeof candidate.relatedFocusId === 'string'
      ? { relatedFocusId: candidate.relatedFocusId }
      : {}),
  };
}

function normalizeVisualContext(value: unknown): VisualContext {
  if (!value || typeof value !== 'object') {
    return createEmptyVisualContext();
  }

  const candidate = value as Partial<VisualContext>;
  const recentObservations = Array.isArray(candidate.recentObservations)
    ? candidate.recentObservations
        .map((observation) => normalizeVisualObservation(observation))
        .filter((observation): observation is VisualObservation =>
          Boolean(observation),
        )
    : [];
  const lastObservation = normalizeVisualObservation(candidate.lastObservation);

  return {
    enabled: candidate.enabled === true,
    lastObservation: lastObservation ?? recentObservations[0] ?? null,
    recentObservations,
  };
}

function visualContextsAreSame(first: VisualContext, second: VisualContext): boolean {
  return JSON.stringify(first) === JSON.stringify(second);
}

function readStoredNotes(): Note[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawNotes = window.localStorage.getItem(NOTES_STORAGE_KEY);
    if (!rawNotes) return [];

    const parsedNotes = JSON.parse(rawNotes);
    if (!Array.isArray(parsedNotes)) return [];

    return parsedNotes
      .filter((note) => note && typeof note.content === 'string')
      .map((note) => ({
        id: typeof note.id === 'string' ? note.id : createId('note'),
        content: note.content,
        createdAt:
          typeof note.createdAt === 'string'
            ? note.createdAt
            : new Date().toISOString(),
      }));
  } catch {
    return [];
  }
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

function readStoredRecentActions(): RecentAction[] {
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


function readStoredRecentFocusSessions(): RecentFocusSession[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawSessions = window.localStorage.getItem(
      RECENT_FOCUS_SESSIONS_STORAGE_KEY,
    );
    if (!rawSessions) return [];

    return normalizeRecentFocusSessions(JSON.parse(rawSessions));
  } catch {
    return [];
  }
}

function readStoredActiveSession(): ActiveSession | null {
  if (typeof window === 'undefined') return null;

  try {
    const rawSession = window.localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
    if (!rawSession) return null;
    return normalizeActiveSession(JSON.parse(rawSession));
  } catch {
    return null;
  }
}


function readStoredVisualContext(): VisualContext {
  if (typeof window === 'undefined') return createEmptyVisualContext();

  try {
    const rawVisualContext = window.localStorage.getItem(VISUAL_CONTEXT_STORAGE_KEY);
    if (!rawVisualContext) return createEmptyVisualContext();
    return normalizeVisualContext(JSON.parse(rawVisualContext));
  } catch {
    return createEmptyVisualContext();
  }
}

function downloadJsonFile(payload: object, filename: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function useMemoryContext({
  pushResultToast,
  calendarEvents,
  googleCalendarEvents,
  searchQuery,
  searchResult,
}: UseMemoryContextArgs) {
  const [notes, setNotes] = useState(readStoredNotes);
  const [memoryTasks, setMemoryTasks] = useState(readStoredMemoryTasks);
  const [memoryTaskDraft, setMemoryTaskDraft] = useState('');
  const [memorySyncState, setMemorySyncState] =
    useState<MemorySyncState>('local');
  const [memorySyncMessage, setMemorySyncMessage] = useState(
    'Using browser fallback until backend memory, notes, and active context load.',
  );
  const [recentActions, setRecentActions] = useState(readStoredRecentActions);
  const [recentFocusSessions, setRecentFocusSessions] = useState(
    readStoredRecentFocusSessions,
  );
  const [activeSession, setActiveSession] = useState(readStoredActiveSession);
  const [visualContext, setVisualContext] = useState(readStoredVisualContext);

  const initialMemoryTasksRef = useRef(memoryTasks);
  const initialRecentActionsRef = useRef(recentActions);
  const initialRecentFocusSessionsRef = useRef(recentFocusSessions);
  const initialNotesRef = useRef(notes);
  const initialActiveSessionRef = useRef(activeSession);
  const initialVisualContextRef = useRef(visualContext);
  const memoryContextHydratedRef = useRef(false);
  const memoryImportInputRef = useRef<HTMLInputElement | null>(null);
  const memoryWriteQueueRef = useRef<Promise<void | unknown>>(Promise.resolve());
  const latestMemoryWriteIdRef = useRef(0);

  const enqueueMemoryWrite = useCallback(function enqueueMemoryWrite<T>(
    operation: () => Promise<T>,
  ): Promise<T> {
    const queuedWrite = memoryWriteQueueRef.current
      .catch(() => undefined)
      .then(operation);

    memoryWriteQueueRef.current = queuedWrite.then(
      () => undefined,
      () => undefined,
    );

    return queuedWrite;
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(NOTES_STORAGE_KEY, JSON.stringify(notes));
    } catch (error) {
      console.error('Failed to save notes:', error);
    }
  }, [notes]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        MEMORY_TASKS_STORAGE_KEY,
        JSON.stringify(memoryTasks),
      );
    } catch (error) {
      console.error('Failed to save memory tasks:', error);
    }
  }, [memoryTasks]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        RECENT_ACTIONS_STORAGE_KEY,
        JSON.stringify(recentActions),
      );
    } catch (error) {
      console.error('Failed to save recent actions:', error);
    }
  }, [recentActions]);


  useEffect(() => {
    try {
      window.localStorage.setItem(
        RECENT_FOCUS_SESSIONS_STORAGE_KEY,
        JSON.stringify(recentFocusSessions),
      );
    } catch (error) {
      console.error('Failed to save recent focus sessions:', error);
    }
  }, [recentFocusSessions]);

  useEffect(() => {
    try {
      if (activeSession) {
        window.localStorage.setItem(
          ACTIVE_SESSION_STORAGE_KEY,
          JSON.stringify(activeSession),
        );
      } else {
        window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
      }
    } catch (error) {
      console.error('Failed to save active session:', error);
    }
  }, [activeSession]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        VISUAL_CONTEXT_STORAGE_KEY,
        JSON.stringify(visualContext),
      );
    } catch (error) {
      console.error('Failed to save visual context:', error);
    }
  }, [visualContext]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleMemoryTasksState = (event: Event) => {
      const detail = (event as CustomEvent<MemoryTasksStateEventDetail>).detail;
      if (!Array.isArray(detail?.tasks)) return;
      setMemoryTasks(detail.tasks);
    };

    const handleVisualContextState = (event: Event) => {
      const detail = (event as CustomEvent<VisualContextStateEventDetail>).detail;
      if (!detail?.visualContext) return;
      setVisualContext((prev) => {
        const nextVisualContext = normalizeVisualContext(detail.visualContext);
        return visualContextsAreSame(prev, nextVisualContext) ? prev : nextVisualContext;
      });
    };

    const handleStorage = (event: StorageEvent) => {
      if (event.key === MEMORY_TASKS_STORAGE_KEY) {
        setMemoryTasks(readStoredMemoryTasks());
        return;
      }

      if (event.key !== VISUAL_CONTEXT_STORAGE_KEY) return;
      setVisualContext((prev) => {
        const nextVisualContext = readStoredVisualContext();
        return visualContextsAreSame(prev, nextVisualContext) ? prev : nextVisualContext;
      });
    };

    window.addEventListener(MEMORY_TASKS_STATE_EVENT, handleMemoryTasksState);
    window.addEventListener(VISUAL_CONTEXT_STATE_EVENT, handleVisualContextState);
    window.addEventListener('storage', handleStorage);

    return () => {
      window.removeEventListener(MEMORY_TASKS_STATE_EVENT, handleMemoryTasksState);
      window.removeEventListener(VISUAL_CONTEXT_STATE_EVENT, handleVisualContextState);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  const persistMemoryContextToBackend = useCallback(
    async (
      tasksToSave: MemoryTask[],
      actionsToSave: RecentAction[],
      notesToSave: Note[],
      activeSessionToSave: ActiveSession | null,
      recentFocusSessionsToSave: RecentFocusSession[],
      visualContextToSave: VisualContext,
    ) => {
      const writeId = ++latestMemoryWriteIdRef.current;
      setMemorySyncState('syncing');

      try {
        const response = await enqueueMemoryWrite(() =>
          replaceMemoryContext({
            tasks: tasksToSave,
            recentActions: actionsToSave,
            notes: notesToSave,
            activeSession: activeSessionToSave,
            recentFocusSessions: recentFocusSessionsToSave,
            visualContext: visualContextToSave,
          }),
        );

        if (writeId !== latestMemoryWriteIdRef.current) {
          return false;
        }

        setRecentFocusSessions((prev) => {
          const nextSessions =
            response.recentFocusSessions ?? recentFocusSessionsToSave;
          return recentFocusSessionsAreSame(prev, nextSessions)
            ? prev
            : nextSessions;
        });
        if (response.visualContext) {
          const nextVisualContext = normalizeVisualContext(response.visualContext);
          setVisualContext((prev) =>
            visualContextsAreSame(prev, nextVisualContext) ? prev : nextVisualContext,
          );
        }
        setMemorySyncState('synced');
        setMemorySyncMessage(
          response.message ||
            'Memory, notes, work context, active session, and visual context synced to backend.',
        );
        return true;
      } catch (error) {
        if (writeId !== latestMemoryWriteIdRef.current) {
          return false;
        }

        const message =
          error instanceof Error ? error.message : 'Backend memory sync failed.';
        setMemorySyncState('error');
        setMemorySyncMessage(`${message} Browser fallback is still active.`);
        return false;
      }
    },
    [enqueueMemoryWrite],
  );

  const loadMemoryContextFromBackend = useCallback(async () => {
    setMemorySyncState('syncing');

    try {
      const [response, initialization] = await Promise.all([
        getMemoryContext(),
        getMemoryInitialization(),
      ]);

      const backendTasks = response.tasks ?? [];
      const backendActions = response.recentActions ?? [];
      const backendNotes = response.notes ?? [];
      const backendRecentFocusSessions = normalizeRecentFocusSessions(
        response.recentFocusSessions ?? [],
      );
      const backendActiveSession = normalizeActiveSession(
        response.activeSession ?? null,
      );
      const backendVisualContext = normalizeVisualContext(response.visualContext);
      const browserTasks = initialMemoryTasksRef.current;
      const browserActions = initialRecentActionsRef.current;
      const browserNotes = initialNotesRef.current;
      const browserRecentFocusSessions = initialRecentFocusSessionsRef.current;
      const browserActiveSession = initialActiveSessionRef.current;
      const browserVisualContext = initialVisualContextRef.current;
      const backendInitialized = initialization.initialized;
      const mayMigrateBrowserFallback = !backendInitialized;

      const nextTasks =
        mayMigrateBrowserFallback &&
        backendTasks.length === 0 &&
        browserTasks.length > 0
          ? browserTasks
          : backendTasks;
      const nextActions =
        mayMigrateBrowserFallback &&
        backendActions.length === 0 &&
        browserActions.length > 0
          ? browserActions
          : backendActions;
      const nextNotes =
        mayMigrateBrowserFallback &&
        backendNotes.length === 0 &&
        browserNotes.length > 0
          ? browserNotes
          : backendNotes;
      const nextRecentFocusSessions =
        mayMigrateBrowserFallback &&
        backendRecentFocusSessions.length === 0 &&
        browserRecentFocusSessions.length > 0
          ? browserRecentFocusSessions
          : backendRecentFocusSessions;
      const nextActiveSession =
        mayMigrateBrowserFallback && !backendActiveSession && browserActiveSession
          ? browserActiveSession
          : backendActiveSession;
      const backendHasVisualContext =
        backendVisualContext.enabled ||
        backendVisualContext.lastObservation !== null ||
        backendVisualContext.recentObservations.length > 0;
      const browserHasVisualContext =
        browserVisualContext.enabled ||
        browserVisualContext.lastObservation !== null ||
        browserVisualContext.recentObservations.length > 0;
      const nextVisualContext =
        mayMigrateBrowserFallback && !backendHasVisualContext && browserHasVisualContext
          ? browserVisualContext
          : backendVisualContext;

      const copiedBrowserTasks =
        mayMigrateBrowserFallback &&
        backendTasks.length === 0 &&
        browserTasks.length > 0;
      const copiedBrowserActions =
        mayMigrateBrowserFallback &&
        backendActions.length === 0 &&
        browserActions.length > 0;
      const copiedBrowserNotes =
        mayMigrateBrowserFallback &&
        backendNotes.length === 0 &&
        browserNotes.length > 0;
      const copiedBrowserRecentFocusSessions =
        mayMigrateBrowserFallback &&
        backendRecentFocusSessions.length === 0 &&
        browserRecentFocusSessions.length > 0;
      const copiedBrowserActiveSession =
        mayMigrateBrowserFallback && !backendActiveSession && !!browserActiveSession;
      const copiedBrowserVisualContext =
        mayMigrateBrowserFallback && !backendHasVisualContext && browserHasVisualContext;

      setMemoryTasks(nextTasks);
      setRecentActions(nextActions);
      setRecentFocusSessions((prev) =>
        recentFocusSessionsAreSame(prev, nextRecentFocusSessions)
          ? prev
          : nextRecentFocusSessions,
      );
      setNotes(nextNotes);
      setActiveSession(nextActiveSession);
      setVisualContext((prev) =>
        visualContextsAreSame(prev, nextVisualContext) ? prev : nextVisualContext,
      );
      memoryContextHydratedRef.current = true;

      if (
        copiedBrowserTasks ||
        copiedBrowserActions ||
        copiedBrowserNotes ||
        copiedBrowserRecentFocusSessions ||
        copiedBrowserActiveSession ||
        copiedBrowserVisualContext
      ) {
        const migrationSaved = await persistMemoryContextToBackend(
          nextTasks,
          nextActions,
          nextNotes,
          nextActiveSession,
          nextRecentFocusSessions,
          nextVisualContext,
        );

        if (migrationSaved) {
          setMemorySyncMessage(
            'First-run browser memory, notes, work context, active session, and visual context were copied into the backend.',
          );
        }
        return;
      }

      setMemorySyncState('synced');
      setMemorySyncMessage(
        backendInitialized &&
          backendTasks.length === 0 &&
          backendActions.length === 0 &&
          backendNotes.length === 0 &&
          backendRecentFocusSessions.length === 0 &&
          !backendActiveSession &&
          !backendHasVisualContext
          ? 'Backend memory is intentionally empty.'
          : response.message || 'Memory context loaded from backend.',
      );
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Backend memory unavailable.';
      memoryContextHydratedRef.current = true;
      setMemorySyncState('error');
      setMemorySyncMessage(`${message} Using browser fallback.`);
    }
  }, [persistMemoryContextToBackend]);

  useEffect(() => {
    loadMemoryContextFromBackend();
  }, [loadMemoryContextFromBackend]);

  useEffect(() => {
    if (!memoryContextHydratedRef.current) return;

    const timeoutId = window.setTimeout(() => {
      persistMemoryContextToBackend(
        memoryTasks,
        recentActions,
        notes,
        activeSession,
        recentFocusSessions,
        visualContext,
      );
    }, 250);

    return () => window.clearTimeout(timeoutId);
  }, [
    activeSession,
    memoryTasks,
    notes,
    persistMemoryContextToBackend,
    recentActions,
    recentFocusSessions,
    visualContext,
  ]);

  const saveNote = useCallback((content: string): Note | null => {
    const trimmedContent = content.trim();
    if (!trimmedContent) {
      return null;
    }

    const note: Note = {
      id: createId('note'),
      content: trimmedContent,
      createdAt: new Date().toISOString(),
    };

    setNotes((prev) => [note, ...prev]);
    return note;
  }, []);

  const deleteNote = useCallback((noteId: string) => {
    setNotes((prev) => prev.filter((note) => note.id !== noteId));
    setActiveSession((prev) =>
      prev
        ? {
            ...prev,
            pinnedNoteIds: prev.pinnedNoteIds.filter((id) => id !== noteId),
            updatedAt: new Date().toISOString(),
          }
        : prev,
    );
  }, []);

  const clearNotes = useCallback(() => {
    setNotes([]);
    setActiveSession((prev) =>
      prev
        ? {
            ...prev,
            pinnedNoteIds: [],
            updatedAt: new Date().toISOString(),
          }
        : prev,
    );

    try {
      window.localStorage.removeItem(NOTES_STORAGE_KEY);
    } catch (error) {
      console.error('Failed to clear notes:', error);
    }
  }, []);

  const deleteLastNote = useCallback((): Note | null => {
    if (notes.length === 0) return null;

    const deletedNote = notes[0];
    setNotes((prev) => prev.slice(1));
    setActiveSession((prev) =>
      prev
        ? {
            ...prev,
            pinnedNoteIds: prev.pinnedNoteIds.filter(
              (id) => id !== deletedNote.id,
            ),
            updatedAt: new Date().toISOString(),
          }
        : prev,
    );
    return deletedNote;
  }, [notes]);

  const getNotesReadout = useCallback(() => {
    if (notes.length === 0) {
      return 'You do not have any saved notes.';
    }

    const maxToRead = 5;
    const noteLines = notes
      .slice(0, maxToRead)
      .map((note, index) => `${index + 1}. ${note.content}`);
    const remainingCount = notes.length - maxToRead;
    const suffix = remainingCount > 0 ? ` Plus ${remainingCount} more.` : '';

    return `You have ${notes.length} saved note${
      notes.length === 1 ? '' : 's'
    }: ${noteLines.join(' ')}${suffix}`;
  }, [notes]);

  const addRecentAction = useCallback((label: string, detail: string) => {
    const cleanedDetail = detail.replace(/\s+/g, ' ').trim();
    const action: RecentAction = {
      id: createId('action'),
      label,
      detail:
        cleanedDetail.length > 140
          ? `${cleanedDetail.slice(0, 137).trim()}...`
          : cleanedDetail,
      createdAt: new Date().toISOString(),
    };

    setRecentActions((prev) => [action, ...prev].slice(0, 12));
  }, []);

  const saveMemoryTask = useCallback((title: string): MemoryTask | null => {
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      return null;
    }

    const task: MemoryTask = {
      id: createId('task'),
      title: trimmedTitle,
      createdAt: new Date().toISOString(),
    };

    setMemoryTasks((prev) => [task, ...prev]);
    return task;
  }, []);

  const markMemoryTaskDone = useCallback(
    (
      lookup?: string,
      operation: 'complete' | 'delete' = 'complete',
    ): MemoryTask | null => {
      const candidateTasks =
        operation === 'delete'
          ? memoryTasks
          : memoryTasks.filter((task) => !task.completedAt);

      if (candidateTasks.length === 0) {
        return null;
      }

      const normalizedLookup = normalizeMemoryLookup(lookup ?? '');
      const targetTask = normalizedLookup
        ? candidateTasks.find((task) => {
            const normalizedTitle = normalizeMemoryLookup(task.title);
            return (
              normalizedTitle.includes(normalizedLookup) ||
              normalizedLookup.includes(normalizedTitle)
            );
          })
        : candidateTasks[0];

      if (!targetTask) {
        return null;
      }

      if (operation === 'delete') {
        setMemoryTasks((prev) =>
          prev.filter((task) => task.id !== targetTask.id),
        );
        setActiveSession((prev) =>
          prev
            ? {
                ...prev,
                linkedTaskIds: prev.linkedTaskIds.filter(
                  (id) => id !== targetTask.id,
                ),
                updatedAt: new Date().toISOString(),
              }
            : prev,
        );
        return targetTask;
      }

      const completedTask: MemoryTask = {
        ...targetTask,
        completedAt: new Date().toISOString(),
      };

      setMemoryTasks((prev) =>
        prev.map((task) => (task.id === targetTask.id ? completedTask : task)),
      );
      return completedTask;
    },
    [memoryTasks],
  );

  const markMemoryTaskDoneById = useCallback(
    (taskId: string): MemoryTask | null => {
      const targetTask = memoryTasks.find(
        (task) => task.id === taskId && !task.completedAt,
      );

      if (!targetTask) {
        return null;
      }

      const completedTask: MemoryTask = {
        ...targetTask,
        completedAt: new Date().toISOString(),
      };
      const nextTasks = memoryTasks.map((task) =>
        task.id === targetTask.id ? completedTask : task,
      );
      setMemoryTasks(nextTasks);
      return completedTask;
    },
    [memoryTasks],
  );

  const deleteMemoryTask = useCallback(
    (taskId: string): MemoryTask | null => {
      const targetTask = memoryTasks.find((task) => task.id === taskId) ?? null;

      if (!targetTask) {
        return null;
      }

      const nextTasks = memoryTasks.filter((task) => task.id !== taskId);
      setMemoryTasks(nextTasks);
      setActiveSession((prev) =>
        prev
          ? {
              ...prev,
              linkedTaskIds: prev.linkedTaskIds.filter((id) => id !== taskId),
              updatedAt: new Date().toISOString(),
            }
          : prev,
      );
      return targetTask;
    },
    [memoryTasks],
  );

  const reopenMemoryTask = useCallback(
    (taskId: string): MemoryTask | null => {
      const targetTask = memoryTasks.find(
        (task) => task.id === taskId && task.completedAt,
      );

      if (!targetTask) {
        return null;
      }

      const reopenedTask: MemoryTask = {
        id: targetTask.id,
        title: targetTask.title,
        createdAt: targetTask.createdAt,
      };
      const nextTasks = memoryTasks.map((task) =>
        task.id === targetTask.id ? reopenedTask : task,
      );
      setMemoryTasks(nextTasks);
      return reopenedTask;
    },
    [memoryTasks],
  );

  const clearCompletedTasks = useCallback((): number => {
    const completedTasks = memoryTasks.filter((task) => task.completedAt);
    const removedCount = completedTasks.length;
    if (removedCount === 0) {
      return 0;
    }

    const completedTaskTitles = completedTasks
      .map((task) => normalizeMemoryLookup(task.title))
      .filter(Boolean);
    const completedTaskIds = new Set(completedTasks.map((task) => task.id));
    const nextTasks = memoryTasks.filter((task) => !task.completedAt);
    setMemoryTasks(nextTasks);
    setActiveSession((prev) =>
      prev
        ? {
            ...prev,
            linkedTaskIds: prev.linkedTaskIds.filter(
              (id) => !completedTaskIds.has(id),
            ),
            updatedAt: new Date().toISOString(),
          }
        : prev,
    );
    setRecentActions((prev) => {
      const nextActions = prev.filter((action) => {
        const normalizedLabel = normalizeMemoryLookup(action.label);
        const normalizedDetail = normalizeMemoryLookup(action.detail);
        const actionText = `${normalizedLabel} ${normalizedDetail}`.trim();
        const matchesCompletedTaskTitle = completedTaskTitles.some((title) => {
          if (actionText.includes(title)) {
            return true;
          }

          return (
            normalizedDetail.length > 0 && title.includes(normalizedDetail)
          );
        });

        const isTaskAction =
          normalizedLabel === 'saved task' ||
          normalizedLabel === 'completed task' ||
          normalizedLabel === 'cleared completed tasks' ||
          /\btask\b/.test(actionText) ||
          matchesCompletedTaskTitle;

        return !isTaskAction;
      });

      return nextActions;
    });

    return removedCount;
  }, [memoryTasks]);

  const startActiveSession = useCallback(
    (draft: ActiveSessionDraft): ActiveSession | null => {
      const trimmedTitle = draft.title.trim();
      if (!trimmedTitle) {
        return null;
      }

      const now = new Date().toISOString();
      const session: ActiveSession = {
        id: createId('session'),
        title: trimmedTitle,
        mode: draft.mode ?? 'general',
        goal: draft.goal?.trim() ?? '',
        startedAt: now,
        updatedAt: now,
        pinnedNoteIds: draft.pinnedNoteIds ?? [],
        linkedTaskIds: draft.linkedTaskIds ?? [],
        ...(draft.summary !== undefined ? { summary: draft.summary } : {}),
      };

      setActiveSession(session);
      addRecentAction(
        'Started focus session',
        session.goal ? `${session.title}: ${session.goal}` : session.title,
      );
      return session;
    },
    [addRecentAction],
  );

  const updateActiveSessionContext = useCallback(
    (updates: ActiveSessionUpdate): ActiveSession | null => {
      if (!activeSession) {
        return null;
      }

      const updatedSession: ActiveSession = {
        ...activeSession,
        ...updates,
        title:
          typeof updates.title === 'string' && updates.title.trim()
            ? updates.title.trim()
            : activeSession.title,
        goal:
          typeof updates.goal === 'string'
            ? updates.goal.trim()
            : activeSession.goal,
        pinnedNoteIds: updates.pinnedNoteIds ?? activeSession.pinnedNoteIds,
        linkedTaskIds: updates.linkedTaskIds ?? activeSession.linkedTaskIds,
        updatedAt: new Date().toISOString(),
      };

      setActiveSession(updatedSession);
      addRecentAction(
        'Updated focus session',
        updatedSession.goal
          ? `${updatedSession.title}: ${updatedSession.goal}`
          : updatedSession.title,
      );

      return updatedSession;
    },
    [activeSession, addRecentAction],
  );

  const endActiveSession = useCallback((): ActiveSession | null => {
    if (!activeSession) {
      return null;
    }

    setActiveSession(null);
    addRecentAction('Ended focus session', activeSession.title);
    return activeSession;
  }, [activeSession, addRecentAction]);

  const getActiveSessionReadout = useCallback(() => {
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
  }, [activeSession]);

  const handleSaveMemoryTaskDraft = useCallback(() => {
    const savedTask = saveMemoryTask(memoryTaskDraft);
    if (!savedTask) {
      return;
    }

    setMemoryTaskDraft('');
    addRecentAction('Saved task', savedTask.title);
    pushResultToast({
      kind: 'success',
      title: 'Task saved',
      detail: savedTask.title,
    });
  }, [addRecentAction, memoryTaskDraft, pushResultToast, saveMemoryTask]);

  const handleExportMemory = useCallback(async () => {
    try {
      await memoryWriteQueueRef.current;
      const exportPayload = await exportMemoryContext();
      const payload = {
        version: exportPayload.version || 7,
        exportedAt: exportPayload.exportedAt || new Date().toISOString(),
        tasks: exportPayload.tasks ?? memoryTasks,
        recentActions: exportPayload.recentActions ?? recentActions,
        notes: exportPayload.notes ?? notes,
        activeSession: exportPayload.activeSession ?? activeSession,
        recentFocusSessions:
          exportPayload.recentFocusSessions ?? recentFocusSessions,
        visualContext: exportPayload.visualContext
          ? normalizeVisualContext(exportPayload.visualContext)
          : visualContext,
      };

      downloadJsonFile(
        payload,
        `qmeet-memory-${new Date().toISOString().slice(0, 10)}.json`,
      );
      setMemorySyncState('synced');
      setMemorySyncMessage('Memory export downloaded from backend memory.');
      pushResultToast({
        kind: 'success',
        title: 'Memory exported',
        detail: 'Downloaded QMeet memory JSON.',
      });
    } catch {
      const payload = {
        version: 7,
        exportedAt: new Date().toISOString(),
        tasks: memoryTasks,
        recentActions,
        notes,
        activeSession,
        recentFocusSessions,
        visualContext,
      };

      downloadJsonFile(
        payload,
        `qmeet-memory-local-${new Date().toISOString().slice(0, 10)}.json`,
      );
      setMemorySyncState('error');
      setMemorySyncMessage(
        'Backend export failed, so QMeet exported the browser fallback memory.',
      );
      pushResultToast({
        kind: 'warning',
        title: 'Local export',
        detail: 'Backend unavailable; exported browser fallback.',
      });
    }
  }, [
    activeSession,
    memoryTasks,
    notes,
    pushResultToast,
    recentActions,
    recentFocusSessions,
    visualContext,
  ]);

  const handleImportMemoryFile = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) {
        return;
      }

      let writeId: number | null = null;

      try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        const importedTasks = Array.isArray(parsed.tasks) ? parsed.tasks : [];
        const importedActions = Array.isArray(parsed.recentActions)
          ? parsed.recentActions
          : [];
        const importedNotes = Array.isArray(parsed.notes) ? parsed.notes : [];
        const importedRecentFocusSessions = normalizeRecentFocusSessions(
          parsed.recentFocusSessions ?? [],
        );
        const importedActiveSession = Object.prototype.hasOwnProperty.call(
          parsed,
          'activeSession',
        )
          ? normalizeActiveSession(parsed.activeSession)
          : null;
        const importedVisualContext = Object.prototype.hasOwnProperty.call(
          parsed,
          'visualContext',
        )
          ? normalizeVisualContext(parsed.visualContext)
          : createEmptyVisualContext();

        writeId = ++latestMemoryWriteIdRef.current;
        setMemorySyncState('syncing');
        const response = await enqueueMemoryWrite(() =>
          importMemoryContext({
            tasks: importedTasks,
            recentActions: importedActions,
            notes: importedNotes,
            activeSession: importedActiveSession,
            recentFocusSessions: importedRecentFocusSessions,
            visualContext: importedVisualContext,
          }),
        );

        setMemoryTasks(response.tasks ?? importedTasks);
        setRecentActions(response.recentActions ?? importedActions);
        setRecentFocusSessions(
          response.recentFocusSessions ?? importedRecentFocusSessions,
        );
        setNotes(response.notes ?? importedNotes);
        setVisualContext(
          response.visualContext
            ? normalizeVisualContext(response.visualContext)
            : importedVisualContext,
        );
        setActiveSession(
          Object.prototype.hasOwnProperty.call(response, 'activeSession')
            ? normalizeActiveSession(response.activeSession)
            : importedActiveSession,
        );

        if (writeId === latestMemoryWriteIdRef.current) {
          setMemorySyncState('synced');
          setMemorySyncMessage(
            response.message || 'Imported memory JSON into backend memory.',
          );
        }

        pushResultToast({
          kind: 'success',
          title: 'Memory imported',
          detail: 'Tasks, notes, focus history, work context, active session, and visual context replaced.',
        });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Could not import memory JSON.';

        if (writeId === null || writeId === latestMemoryWriteIdRef.current) {
          setMemorySyncState('error');
          setMemorySyncMessage(`${message} Existing memory was left unchanged.`);
        }

        pushResultToast({
          kind: 'error',
          title: 'Import failed',
          detail: 'Memory JSON was not imported.',
        });
      }
    },
    [enqueueMemoryWrite, pushResultToast],
  );

  const handleClearAllMemory = useCallback(async () => {
    const confirmed = window.confirm(
      'Clear all QMeet tasks, completed tasks, notes, active focus session, visual context, and hidden recent work context? This cannot be undone unless you exported a backup.',
    );
    if (!confirmed) {
      return;
    }

    setMemoryTasks([]);
    setRecentActions([]);
    setRecentFocusSessions([]);
    setNotes([]);
    setActiveSession(null);
    setVisualContext(createEmptyVisualContext());
    setMemoryTaskDraft('');

    try {
      window.localStorage.removeItem(MEMORY_TASKS_STORAGE_KEY);
      window.localStorage.removeItem(RECENT_ACTIONS_STORAGE_KEY);
      window.localStorage.removeItem(RECENT_FOCUS_SESSIONS_STORAGE_KEY);
      window.localStorage.removeItem(NOTES_STORAGE_KEY);
      window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
      window.localStorage.removeItem(VISUAL_CONTEXT_STORAGE_KEY);
    } catch (error) {
      console.error('Failed to clear local memory fallback:', error);
    }

    let writeId: number | null = null;

    try {
      writeId = ++latestMemoryWriteIdRef.current;
      setMemorySyncState('syncing');
      const response = await enqueueMemoryWrite(() => clearAllMemoryContext());

      if (writeId === latestMemoryWriteIdRef.current) {
        setMemorySyncState('synced');
        setMemorySyncMessage(response.message || 'Cleared all backend memory.');
      }

      pushResultToast({
        kind: 'warning',
        title: 'Memory cleared',
        detail: 'Tasks, notes, active focus, visual context, and work context removed.',
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Backend memory clear failed.';

      if (writeId === null || writeId === latestMemoryWriteIdRef.current) {
        setMemorySyncState('error');
        setMemorySyncMessage(`${message} Browser fallback was cleared locally.`);
      }

      pushResultToast({
        kind: 'warning',
        title: 'Local memory cleared',
        detail: 'Backend clear failed; browser fallback was cleared.',
      });
    }
  }, [enqueueMemoryWrite, pushResultToast]);

  const handleResetTasksOnly = useCallback(() => {
    const confirmed = window.confirm(
      'Clear open and completed tasks only? Notes, active focus session, and recent work context will stay.',
    );
    if (!confirmed) {
      return;
    }

    setMemoryTasks([]);
    setActiveSession((prev) =>
      prev
        ? {
            ...prev,
            linkedTaskIds: [],
            updatedAt: new Date().toISOString(),
          }
        : prev,
    );
    pushResultToast({
      kind: 'warning',
      title: 'Tasks reset',
      detail: 'Open and completed tasks cleared.',
    });
  }, [pushResultToast]);

  const handleResetNotesOnly = useCallback(() => {
    const confirmed = window.confirm(
      'Clear notes only? Tasks, active focus session, and recent work context will stay.',
    );
    if (!confirmed) {
      return;
    }

    setNotes([]);
    setActiveSession((prev) =>
      prev
        ? {
            ...prev,
            pinnedNoteIds: [],
            updatedAt: new Date().toISOString(),
          }
        : prev,
    );

    try {
      window.localStorage.removeItem(NOTES_STORAGE_KEY);
    } catch (error) {
      console.error('Failed to clear notes fallback:', error);
    }

    pushResultToast({
      kind: 'warning',
      title: 'Notes reset',
      detail: 'Backend and browser notes cleared.',
    });
  }, [pushResultToast]);

  const handleResetRecentContextOnly = useCallback(() => {
    const confirmed = window.confirm(
      'Clear hidden recent work context only? Tasks, notes, and active focus session will stay.',
    );
    if (!confirmed) {
      return;
    }

    setRecentActions([]);

    try {
      window.localStorage.removeItem(RECENT_ACTIONS_STORAGE_KEY);
    } catch (error) {
      console.error('Failed to clear recent actions fallback:', error);
    }

    pushResultToast({
      kind: 'warning',
      title: 'Work context reset',
      detail: 'Hidden recent actions cleared.',
    });
  }, [pushResultToast]);

  const getMemoryReadout = useCallback(() => {
    const openTasks = memoryTasks.filter((task) => !task.completedAt);
    const completedTasks = memoryTasks.filter((task) => task.completedAt);
    const latestNote = notes[0]?.content;
    const latestCalendarEvent = googleCalendarEvents[0] ?? calendarEvents[0];
    const latestSearch = searchResult?.query || searchQuery.trim();
    const latestRecentFocusSession = recentFocusSessions[0];
    const latestVisualObservation = visualContext.lastObservation ?? visualContext.recentObservations[0] ?? null;
    const recentActionText = recentActions
      .slice(0, 3)
      .map((action) =>
        action.detail ? `${action.label}: ${action.detail}` : action.label,
      )
      .join('; ');

    const focusText = activeSession
      ? `Current focus: ${activeSession.title} (${activeSession.mode}).${
          activeSession.goal ? ` Goal: ${activeSession.goal}.` : ''
        }`
      : 'No active focus session.';
    const taskText =
      openTasks.length > 0
        ? `Open tasks: ${openTasks
            .slice(0, 4)
            .map((task) => task.title)
            .join('; ')}.`
        : 'No open tasks.';
    const completedText =
      completedTasks.length > 0
        ? `${completedTasks.length} completed task${
            completedTasks.length === 1 ? '' : 's'
          } saved.`
        : 'No completed tasks saved.';
    const noteText = latestNote ? `Latest note: ${latestNote}.` : 'No notes yet.';
    const calendarText = latestCalendarEvent
      ? `Latest calendar item: ${latestCalendarEvent.time}: ${latestCalendarEvent.title}.`
      : 'No calendar items loaded.';
    const searchText = latestSearch
      ? `Latest search: ${latestSearch}.`
      : 'No search yet.';
    const actionText = recentActionText
      ? `Recent actions: ${recentActionText}.`
      : 'No recent actions yet.';
    const recentFocusText = latestRecentFocusSession
      ? `Last completed focus: ${latestRecentFocusSession.title}.`
      : 'No completed focus sessions yet.';
    const visualText = latestVisualObservation
      ? `Last visual observation: ${latestVisualObservation.summary}.`
      : visualContext.enabled
        ? 'Visual context is enabled, but no observations are saved yet.'
        : 'Visual context is disabled.';

    return `${focusText} ${recentFocusText} ${visualText} ${taskText} ${completedText} ${noteText} ${calendarText} ${searchText} ${actionText}`;
  }, [
    activeSession,
    calendarEvents,
    googleCalendarEvents,
    memoryTasks,
    notes,
    recentActions,
    recentFocusSessions,
    visualContext,
    searchQuery,
    searchResult?.query,
  ]);

  return {
    notes,
    memoryTasks,
    recentActions,
    recentFocusSessions,
    activeSession,
    visualContext,
    memoryTaskDraft,
    setMemoryTaskDraft,
    memorySyncState,
    memorySyncMessage,
    memoryImportInputRef,
    saveNote,
    deleteNote,
    clearNotes,
    deleteLastNote,
    getNotesReadout,
    saveMemoryTask,
    markMemoryTaskDone,
    markMemoryTaskDoneById,
    deleteMemoryTask,
    reopenMemoryTask,
    clearCompletedTasks,
    startActiveSession,
    updateActiveSessionContext,
    endActiveSession,
    getActiveSessionReadout,
    handleSaveMemoryTaskDraft,
    handleExportMemory,
    handleImportMemoryFile,
    handleClearAllMemory,
    handleResetTasksOnly,
    handleResetNotesOnly,
    handleResetRecentContextOnly,
    addRecentAction,
    getMemoryReadout,
  };
}
