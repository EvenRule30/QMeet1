import {
  type ChangeEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import {
  CalendarEvent,
  MemoryTask,
  Note,
  RecentAction,
  SearchResponse,
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

export type MemorySyncState =
  | 'local'
  | 'syncing'
  | 'synced'
  | 'error';

type ResultToastInput =
  | Omit<ResultToast, 'id' | 'createdAt'>
  | null;

type UseMemoryContextArgs = {
  pushResultToast: (toastInput: ResultToastInput) => void;
  calendarEvents: CalendarEvent[];
  googleCalendarEvents: CalendarEvent[];
  searchQuery: string;
  searchResult: SearchResponse | null;
};

const MEMORY_TASKS_STORAGE_KEY = 'qmeet-memory-tasks';
const RECENT_ACTIONS_STORAGE_KEY = 'qmeet-recent-actions';
const NOTES_STORAGE_KEY = 'qmeet-notes';

function readStoredNotes(): Note[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawNotes = window.localStorage.getItem(
      NOTES_STORAGE_KEY,
    );
    if (!rawNotes) return [];

    const parsedNotes = JSON.parse(rawNotes);
    if (!Array.isArray(parsedNotes)) return [];

    return parsedNotes
      .filter(
        (note) =>
          note && typeof note.content === 'string',
      )
      .map((note) => ({
        id:
          typeof note.id === 'string'
            ? note.id
            : `note-${Date.now()}-${Math.random()
                .toString(36)
                .slice(2)}`,
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
    const rawTasks = window.localStorage.getItem(
      MEMORY_TASKS_STORAGE_KEY,
    );
    if (!rawTasks) return [];

    const parsedTasks = JSON.parse(rawTasks);
    if (!Array.isArray(parsedTasks)) return [];

    return parsedTasks
      .filter(
        (task) =>
          task && typeof task.title === 'string',
      )
      .map((task) => ({
        id:
          typeof task.id === 'string'
            ? task.id
            : `task-${Date.now()}-${Math.random()
                .toString(36)
                .slice(2)}`,
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
    const rawActions = window.localStorage.getItem(
      RECENT_ACTIONS_STORAGE_KEY,
    );
    if (!rawActions) return [];

    const parsedActions = JSON.parse(rawActions);
    if (!Array.isArray(parsedActions)) return [];

    return parsedActions
      .filter(
        (action) =>
          action && typeof action.label === 'string',
      )
      .map((action) => ({
        id:
          typeof action.id === 'string'
            ? action.id
            : `action-${Date.now()}-${Math.random()
                .toString(36)
                .slice(2)}`,
        label: action.label,
        detail:
          typeof action.detail === 'string'
            ? action.detail
            : '',
        createdAt:
          typeof action.createdAt === 'string'
            ? action.createdAt
            : new Date().toISOString(),
      }));
  } catch {
    return [];
  }
}

function downloadJsonFile(
  payload: object,
  filename: string,
) {
  const blob = new Blob(
    [JSON.stringify(payload, null, 2)],
    { type: 'application/json' },
  );
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
  const [notes, setNotes] = useState<Note[]>(
    readStoredNotes,
  );
  const [memoryTasks, setMemoryTasks] =
    useState<MemoryTask[]>(readStoredMemoryTasks);
  const [memoryTaskDraft, setMemoryTaskDraft] =
    useState('');
  const [memorySyncState, setMemorySyncState] =
    useState<MemorySyncState>('local');
  const [memorySyncMessage, setMemorySyncMessage] =
    useState(
      'Using browser fallback until backend memory and notes load.',
    );
  const [recentActions, setRecentActions] =
    useState<RecentAction[]>(readStoredRecentActions);

  const initialMemoryTasksRef =
    useRef<MemoryTask[]>(memoryTasks);
  const initialRecentActionsRef =
    useRef<RecentAction[]>(recentActions);
  const initialNotesRef = useRef<Note[]>(notes);
  const memoryContextHydratedRef = useRef(false);
  const memoryImportInputRef =
    useRef<HTMLInputElement | null>(null);
  const memoryWriteQueueRef = useRef<Promise<void>>(
    Promise.resolve(),
  );
  const latestMemoryWriteIdRef = useRef(0);

  const enqueueMemoryWrite = useCallback(
    function enqueueMemoryWrite<T>(
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
    },
    [],
  );

  useEffect(() => {
    try {
      window.localStorage.setItem(
        NOTES_STORAGE_KEY,
        JSON.stringify(notes),
      );
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
      console.error(
        'Failed to save memory tasks:',
        error,
      );
    }
  }, [memoryTasks]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        RECENT_ACTIONS_STORAGE_KEY,
        JSON.stringify(recentActions),
      );
    } catch (error) {
      console.error(
        'Failed to save recent actions:',
        error,
      );
    }
  }, [recentActions]);

  const persistMemoryContextToBackend = useCallback(
    async (
      tasksToSave: MemoryTask[],
      actionsToSave: RecentAction[],
      notesToSave: Note[],
    ) => {
      const writeId = ++latestMemoryWriteIdRef.current;
      setMemorySyncState('syncing');

      try {
        const response = await enqueueMemoryWrite(() =>
          replaceMemoryContext({
            tasks: tasksToSave,
            recentActions: actionsToSave,
            notes: notesToSave,
          }),
        );

        if (writeId !== latestMemoryWriteIdRef.current) {
          return false;
        }

        setMemorySyncState('synced');
        setMemorySyncMessage(
          response.message ||
            'Memory, notes, and work context synced to backend.',
        );
        return true;
      } catch (error) {
        if (writeId !== latestMemoryWriteIdRef.current) {
          return false;
        }

        const message =
          error instanceof Error
            ? error.message
            : 'Backend memory sync failed.';

        setMemorySyncState('error');
        setMemorySyncMessage(
          `${message} Browser fallback is still active.`,
        );
        return false;
      }
    },
    [enqueueMemoryWrite],
  );

  const loadMemoryContextFromBackend =
    useCallback(async () => {
      setMemorySyncState('syncing');

      try {
        const [response, initialization] =
          await Promise.all([
            getMemoryContext(),
            getMemoryInitialization(),
          ]);

        const backendTasks = response.tasks ?? [];
        const backendActions =
          response.recentActions ?? [];
        const backendNotes = response.notes ?? [];

        const browserTasks =
          initialMemoryTasksRef.current;
        const browserActions =
          initialRecentActionsRef.current;
        const browserNotes = initialNotesRef.current;

        const backendInitialized =
          initialization.initialized;
        const mayMigrateBrowserFallback =
          !backendInitialized;

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

        setMemoryTasks(nextTasks);
        setRecentActions(nextActions);
        setNotes(nextNotes);
        memoryContextHydratedRef.current = true;

        if (
          copiedBrowserTasks ||
          copiedBrowserActions ||
          copiedBrowserNotes
        ) {
          const migrationSaved =
            await persistMemoryContextToBackend(
              nextTasks,
              nextActions,
              nextNotes,
            );

          if (migrationSaved) {
            setMemorySyncMessage(
              'First-run browser memory, notes, and work context were copied into the backend.',
            );
          }
          return;
        }

        setMemorySyncState('synced');
        setMemorySyncMessage(
          backendInitialized &&
            backendTasks.length === 0 &&
            backendActions.length === 0 &&
            backendNotes.length === 0
            ? 'Backend memory is intentionally empty.'
            : response.message ||
                'Memory context loaded from backend.',
        );
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : 'Backend memory unavailable.';

        memoryContextHydratedRef.current = true;
        setMemorySyncState('error');
        setMemorySyncMessage(
          `${message} Using browser fallback.`,
        );
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
      );
    }, 250);

    return () => window.clearTimeout(timeoutId);
  }, [
    memoryTasks,
    notes,
    persistMemoryContextToBackend,
    recentActions,
  ]);

  const saveNote = useCallback(
    (content: string): Note | null => {
      const trimmedContent = content.trim();

      if (!trimmedContent) {
        return null;
      }

      const note: Note = {
        id: `note-${Date.now()}-${Math.random()
          .toString(36)
          .slice(2)}`,
        content: trimmedContent,
        createdAt: new Date().toISOString(),
      };

      setNotes((prev) => [note, ...prev]);
      return note;
    },
    [],
  );

  const deleteNote = useCallback((noteId: string) => {
    setNotes((prev) =>
      prev.filter((note) => note.id !== noteId),
    );
  }, []);

  const clearNotes = useCallback(() => {
    setNotes([]);

    try {
      window.localStorage.removeItem(
        NOTES_STORAGE_KEY,
      );
    } catch (error) {
      console.error('Failed to clear notes:', error);
    }
  }, []);

  const deleteLastNote = useCallback((): Note | null => {
    if (notes.length === 0) return null;

    const deletedNote = notes[0];
    setNotes((prev) => prev.slice(1));
    return deletedNote;
  }, [notes]);

  const getNotesReadout = useCallback(() => {
    if (notes.length === 0) {
      return 'You do not have any saved notes.';
    }

    const maxToRead = 5;
    const noteLines = notes
      .slice(0, maxToRead)
      .map(
        (note, index) =>
          `${index + 1}. ${note.content}`,
      );
    const remainingCount = notes.length - maxToRead;
    const suffix =
      remainingCount > 0
        ? ` Plus ${remainingCount} more.`
        : '';

    return `You have ${notes.length} saved note${
      notes.length === 1 ? '' : 's'
    }: ${noteLines.join(' ')}${suffix}`;
  }, [notes]);

  const addRecentAction = useCallback(
    (label: string, detail: string) => {
      const cleanedDetail = detail
        .replace(/\s+/g, ' ')
        .trim();

      const action: RecentAction = {
        id: `action-${Date.now()}-${Math.random()
          .toString(36)
          .slice(2)}`,
        label,
        detail:
          cleanedDetail.length > 140
            ? `${cleanedDetail
                .slice(0, 137)
                .trim()}...`
            : cleanedDetail,
        createdAt: new Date().toISOString(),
      };

      setRecentActions((prev) =>
        [action, ...prev].slice(0, 12),
      );
    },
    [],
  );

  const saveMemoryTask = useCallback(
    (title: string): MemoryTask | null => {
      const trimmedTitle = title.trim();

      if (!trimmedTitle) {
        return null;
      }

      const task: MemoryTask = {
        id: `task-${Date.now()}-${Math.random()
          .toString(36)
          .slice(2)}`,
        title: trimmedTitle,
        createdAt: new Date().toISOString(),
      };

      const nextTasks = [task, ...memoryTasks];
      setMemoryTasks(nextTasks);
      return task;
    },
    [memoryTasks],
  );

  const markMemoryTaskDone = useCallback(
    (
      lookup?: string,
      operation: 'complete' | 'delete' = 'complete',
    ): MemoryTask | null => {
      const candidateTasks =
        operation === 'delete'
          ? memoryTasks
          : memoryTasks.filter(
              (task) => !task.completedAt,
            );

      if (candidateTasks.length === 0) {
        return null;
      }

      const normalizedLookup = normalizeMemoryLookup(
        lookup ?? '',
      );
      const targetTask = normalizedLookup
        ? candidateTasks.find((task) => {
            const normalizedTitle =
              normalizeMemoryLookup(task.title);

            return (
              normalizedTitle.includes(
                normalizedLookup,
              ) ||
              normalizedLookup.includes(
                normalizedTitle,
              )
            );
          })
        : candidateTasks[0];

      if (!targetTask) {
        return null;
      }

      if (operation === 'delete') {
        setMemoryTasks((prev) =>
          prev.filter(
            (task) => task.id !== targetTask.id,
          ),
        );
        return targetTask;
      }

      const completedTask: MemoryTask = {
        ...targetTask,
        completedAt: new Date().toISOString(),
      };

      setMemoryTasks((prev) =>
        prev.map((task) =>
          task.id === targetTask.id
            ? completedTask
            : task,
        ),
      );
      return completedTask;
    },
    [memoryTasks],
  );

  const markMemoryTaskDoneById = useCallback(
    (taskId: string): MemoryTask | null => {
      const targetTask = memoryTasks.find(
        (task) =>
          task.id === taskId && !task.completedAt,
      );

      if (!targetTask) {
        return null;
      }

      const completedTask: MemoryTask = {
        ...targetTask,
        completedAt: new Date().toISOString(),
      };

      const nextTasks = memoryTasks.map((task) =>
        task.id === targetTask.id
          ? completedTask
          : task,
      );

      setMemoryTasks(nextTasks);
      return completedTask;
    },
    [memoryTasks],
  );

  const deleteMemoryTask = useCallback(
    (taskId: string): MemoryTask | null => {
      const targetTask =
        memoryTasks.find(
          (task) => task.id === taskId,
        ) ?? null;

      if (!targetTask) {
        return null;
      }

      const nextTasks = memoryTasks.filter(
        (task) => task.id !== taskId,
      );

      setMemoryTasks(nextTasks);
      return targetTask;
    },
    [memoryTasks],
  );

  const reopenMemoryTask = useCallback(
    (taskId: string): MemoryTask | null => {
      const targetTask = memoryTasks.find(
        (task) =>
          task.id === taskId && task.completedAt,
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
        task.id === targetTask.id
          ? reopenedTask
          : task,
      );

      setMemoryTasks(nextTasks);
      return reopenedTask;
    },
    [memoryTasks],
  );

  const clearCompletedTasks =
    useCallback((): number => {
      const completedTasks = memoryTasks.filter(
        (task) => task.completedAt,
      );
      const removedCount = completedTasks.length;

      if (removedCount === 0) {
        return 0;
      }

      const completedTaskTitles = completedTasks
        .map((task) =>
          normalizeMemoryLookup(task.title),
        )
        .filter(Boolean);

      const nextTasks = memoryTasks.filter(
        (task) => !task.completedAt,
      );

      setMemoryTasks(nextTasks);

      setRecentActions((prev) => {
        const nextActions = prev.filter((action) => {
          const normalizedLabel =
            normalizeMemoryLookup(action.label);
          const normalizedDetail =
            normalizeMemoryLookup(action.detail);
          const actionText =
            `${normalizedLabel} ${normalizedDetail}`.trim();

          const isTaskAction =
            normalizedLabel === 'saved task' ||
            normalizedLabel === 'completed task' ||
            normalizedLabel ===
              'cleared completed tasks' ||
            /\btask\b/.test(actionText) ||
            completedTaskTitles.some(
              (title) =>
                actionText.includes(title) ||
                title.includes(normalizedDetail),
            );

          return !isTaskAction;
        });

        return nextActions;
      });

      return removedCount;
    }, [memoryTasks]);

  const handleSaveMemoryTaskDraft =
    useCallback(() => {
      const savedTask = saveMemoryTask(
        memoryTaskDraft,
      );

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
    }, [
      addRecentAction,
      memoryTaskDraft,
      pushResultToast,
      saveMemoryTask,
    ]);

  const handleExportMemory = useCallback(async () => {
    try {
      await memoryWriteQueueRef.current;
      const exportPayload =
        await exportMemoryContext();
      const payload = {
        version: exportPayload.version || 4,
        exportedAt:
          exportPayload.exportedAt ||
          new Date().toISOString(),
        tasks: exportPayload.tasks ?? memoryTasks,
        recentActions:
          exportPayload.recentActions ??
          recentActions,
        notes: exportPayload.notes ?? notes,
      };

      downloadJsonFile(
        payload,
        `qmeet-memory-${new Date()
          .toISOString()
          .slice(0, 10)}.json`,
      );
      setMemorySyncState('synced');
      setMemorySyncMessage(
        'Memory export downloaded from backend memory.',
      );
      pushResultToast({
        kind: 'success',
        title: 'Memory exported',
        detail: 'Downloaded QMeet memory JSON.',
      });
    } catch {
      const payload = {
        version: 4,
        exportedAt: new Date().toISOString(),
        tasks: memoryTasks,
        recentActions,
        notes,
      };

      downloadJsonFile(
        payload,
        `qmeet-memory-local-${new Date()
          .toISOString()
          .slice(0, 10)}.json`,
      );
      setMemorySyncState('error');
      setMemorySyncMessage(
        'Backend export failed, so QMeet exported the browser fallback memory.',
      );
      pushResultToast({
        kind: 'warning',
        title: 'Local export',
        detail:
          'Backend unavailable; exported browser fallback.',
      });
    }
  }, [
    memoryTasks,
    notes,
    pushResultToast,
    recentActions,
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
        const importedTasks = Array.isArray(
          parsed.tasks,
        )
          ? parsed.tasks
          : [];
        const importedActions = Array.isArray(
          parsed.recentActions,
        )
          ? parsed.recentActions
          : [];
        const importedNotes = Array.isArray(
          parsed.notes,
        )
          ? parsed.notes
          : [];

        writeId = ++latestMemoryWriteIdRef.current;
        setMemorySyncState('syncing');

        const response = await enqueueMemoryWrite(() =>
          importMemoryContext({
            tasks: importedTasks,
            recentActions: importedActions,
            notes: importedNotes,
          }),
        );

        setMemoryTasks(
          response.tasks ?? importedTasks,
        );
        setRecentActions(
          response.recentActions ??
            importedActions,
        );
        setNotes(response.notes ?? importedNotes);

        if (writeId === latestMemoryWriteIdRef.current) {
          setMemorySyncState('synced');
          setMemorySyncMessage(
            response.message ||
              'Imported memory JSON into backend memory.',
          );
        }
        pushResultToast({
          kind: 'success',
          title: 'Memory imported',
          detail:
            'Tasks, notes, and work context replaced.',
        });
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : 'Could not import memory JSON.';

        if (
          writeId === null ||
          writeId === latestMemoryWriteIdRef.current
        ) {
          setMemorySyncState('error');
          setMemorySyncMessage(
            `${message} Existing memory was left unchanged.`,
          );
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

  const handleClearAllMemory =
    useCallback(async () => {
      const confirmed = window.confirm(
        'Clear all QMeet tasks, completed tasks, notes, and hidden recent work context? This cannot be undone unless you exported a backup.',
      );

      if (!confirmed) {
        return;
      }

      setMemoryTasks([]);
      setRecentActions([]);
      setNotes([]);
      setMemoryTaskDraft('');

      try {
        window.localStorage.removeItem(
          MEMORY_TASKS_STORAGE_KEY,
        );
        window.localStorage.removeItem(
          RECENT_ACTIONS_STORAGE_KEY,
        );
        window.localStorage.removeItem(
          NOTES_STORAGE_KEY,
        );
      } catch (error) {
        console.error(
          'Failed to clear local memory fallback:',
          error,
        );
      }

      let writeId: number | null = null;

      try {
        writeId = ++latestMemoryWriteIdRef.current;
        setMemorySyncState('syncing');

        const response = await enqueueMemoryWrite(() =>
          clearAllMemoryContext(),
        );

        if (writeId === latestMemoryWriteIdRef.current) {
          setMemorySyncState('synced');
          setMemorySyncMessage(
            response.message ||
              'Cleared all backend memory.',
          );
        }
        pushResultToast({
          kind: 'warning',
          title: 'Memory cleared',
          detail:
            'Tasks, notes, and work context removed.',
        });
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : 'Backend memory clear failed.';

        if (
          writeId === null ||
          writeId === latestMemoryWriteIdRef.current
        ) {
          setMemorySyncState('error');
          setMemorySyncMessage(
            `${message} Browser fallback was cleared locally.`,
          );
        }
        pushResultToast({
          kind: 'warning',
          title: 'Local memory cleared',
          detail:
            'Backend clear failed; browser fallback was cleared.',
        });
      }
    }, [enqueueMemoryWrite, pushResultToast]);

  const handleResetTasksOnly = useCallback(() => {
    const confirmed = window.confirm(
      'Clear open and completed tasks only? Notes and recent work context will stay.',
    );

    if (!confirmed) {
      return;
    }

    setMemoryTasks([]);
    pushResultToast({
      kind: 'warning',
      title: 'Tasks reset',
      detail: 'Open and completed tasks cleared.',
    });
  }, [pushResultToast]);

  const handleResetNotesOnly = useCallback(() => {
    const confirmed = window.confirm(
      'Clear notes only? Tasks and recent work context will stay.',
    );

    if (!confirmed) {
      return;
    }

    setNotes([]);

    try {
      window.localStorage.removeItem(
        NOTES_STORAGE_KEY,
      );
    } catch (error) {
      console.error(
        'Failed to clear notes fallback:',
        error,
      );
    }

    pushResultToast({
      kind: 'warning',
      title: 'Notes reset',
      detail: 'Backend and browser notes cleared.',
    });
  }, [pushResultToast]);

  const handleResetRecentContextOnly =
    useCallback(() => {
      const confirmed = window.confirm(
        'Clear hidden recent work context only? Tasks and notes will stay.',
      );

      if (!confirmed) {
        return;
      }

      setRecentActions([]);

      try {
        window.localStorage.removeItem(
          RECENT_ACTIONS_STORAGE_KEY,
        );
      } catch (error) {
        console.error(
          'Failed to clear recent actions fallback:',
          error,
        );
      }

      pushResultToast({
        kind: 'warning',
        title: 'Work context reset',
        detail: 'Hidden recent actions cleared.',
      });
    }, [pushResultToast]);

  const getMemoryReadout = useCallback(() => {
    const openTasks = memoryTasks.filter(
      (task) => !task.completedAt,
    );
    const completedTasks = memoryTasks.filter(
      (task) => task.completedAt,
    );
    const latestNote = notes[0]?.content;
    const latestCalendarEvent =
      googleCalendarEvents[0] ?? calendarEvents[0];
    const latestSearch =
      searchResult?.query || searchQuery.trim();
    const recentActionText = recentActions
      .slice(0, 3)
      .map((action) =>
        action.detail
          ? `${action.label}: ${action.detail}`
          : action.label,
      )
      .join('; ');

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

    const noteText = latestNote
      ? `Latest note: ${latestNote}.`
      : 'No notes yet.';

    const calendarText = latestCalendarEvent
      ? `Latest calendar item: ${latestCalendarEvent.time}: ${latestCalendarEvent.title}.`
      : 'No calendar items loaded.';

    const searchText = latestSearch
      ? `Latest search: ${latestSearch}.`
      : 'No search yet.';

    const actionText = recentActionText
      ? `Recent actions: ${recentActionText}.`
      : 'No recent actions yet.';

    return `${taskText} ${completedText} ${noteText} ${calendarText} ${searchText} ${actionText}`;
  }, [
    calendarEvents,
    googleCalendarEvents,
    memoryTasks,
    notes,
    recentActions,
    searchQuery,
    searchResult?.query,
  ]);

  return {
    notes,
    memoryTasks,
    recentActions,
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
