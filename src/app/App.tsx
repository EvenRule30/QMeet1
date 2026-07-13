import { useState, useCallback, useEffect, useRef } from 'react';
import { Orb } from './components/Orb';
import { TopStatusBar } from './components/TopStatusBar';
import { ChatPanel } from './components/ChatPanel';
import { PromptBar } from './components/PromptBar';
import { NotesPanel } from './components/NotesPanel';
import { CalendarPanel } from './components/CalendarPanel';
import { SearchPanel } from './components/SearchPanel';
import { Message, OrbState, ActivePanel, Note, CalendarEvent, CalendarBackendStatus, CalendarBackendView, SearchResponse, MemoryTask, RecentAction } from './types';
import { streamChatMessage, resetConversation, interpretCommandIntent, getCalendarStatus, getCalendarEvents, createCalendarEvent, deleteGoogleCalendarEvent, updateGoogleCalendarEvent, startCalendarAuth, resetCalendarAuth, searchWeb, getMemoryContext, replaceMemoryContext, exportMemoryContext, importMemoryContext, clearAllMemoryContext } from "./api";
import { getSpeechRecognition, isSpeechRecognitionSupported } from './speechRecognition';
import { speakText, stopSpeaking } from './speechSynthesis';
import { parseCommand, normalizeSpokenQMeet } from './commands';
import { getAssistantActivity, getPanelLabel } from './lib/activityUtils';
import {
  getCalendarViewLabel,
  getDateKeyForCalendarView,
  isEventForCalendarView,
  type CalendarView,
} from './lib/dateUtils';
import {
  buildCalendarDeleteFrontendCommand,
  buildCalendarEditFrontendCommand,
  calendarEventMatchesDeleteCriteria,
  describeCalendarDeletePayload,
  describeCalendarEditPayload,
  type CalendarDeleteCriteria,
} from './lib/calendarUtils';
import {
  getBriefToolSpeech,
  getResultToastForCommand,
} from './lib/toastUtils';
import {
  formatMemoryTime,
  getCommandActionLabel,
  normalizeMemoryLookup,
} from './lib/memoryUtils';
import { useBackendStatus } from './hooks/useBackendStatus';
import { useResultToasts } from './hooks/useResultToasts';
import './App.css';


type MemorySyncState = 'local' | 'syncing' | 'synced' | 'error';

const VOICE_OUTPUT_STORAGE_KEY = 'qmeet-voice-output-enabled';
const SPEECH_RATE_STORAGE_KEY = 'qmeet-speech-rate';
const CALENDAR_EVENTS_STORAGE_KEY = 'qmeet-calendar-events';
const MEMORY_TASKS_STORAGE_KEY = 'qmeet-memory-tasks';
const RECENT_ACTIONS_STORAGE_KEY = 'qmeet-recent-actions';
const LEGACY_CALENDAR_EVENTS_STORAGE_KEYS = [
  'qmeet-calendar',
  'qmeet-events',
  'calendar-events',
];

const COMMAND_INTERPRETER_EXECUTE_THRESHOLD = 0.8;
const COMMAND_INTERPRETER_CLARIFY_THRESHOLD = 0.5;

type PendingInterpreterCommand = {
  originalText: string;
  frontendCommand: string;
  action: string;
  confidence: number;
  reason: string;
};

const DESTRUCTIVE_FRONTEND_COMMANDS = new Set([
  'clear chat',
  'end chat',
  'delete last note',
  'clear notes',
  'mark task done',
  'clear completed tasks',
  'delete last event',
  'delete event',
  'edit last event',
  'clear calendar',
]);

const DESTRUCTIVE_LOCAL_COMMANDS = new Set([
  'clear-chat',
  'end-chat',
  'delete-last-note',
  'clear-notes',
  'mark-task-done',
  'clear-done-tasks',
  'delete-last-event',
  'delete-calendar-event',
  'edit-last-event',
  'clear-calendar',
]);

const LOCAL_COMMAND_TO_FRONTEND_COMMAND: Record<string, string> = {
  'clear-chat': 'clear chat',
  'end-chat': 'end chat',
  'delete-last-note': 'delete last note',
  'clear-notes': 'clear notes',
  'mark-task-done': 'mark task done',
  'clear-done-tasks': 'clear completed tasks',
  'delete-last-event': 'delete last event',
  'delete-calendar-event': 'delete event',
  'edit-last-event': 'edit last event',
  'clear-calendar': 'clear calendar',
};

function normalizePendingDecisionText(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[?!.,;:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function isDestructiveInterpreterCommand(frontendCommand: string): boolean {
  const normalizedCommand = normalizePendingDecisionText(frontendCommand);
  return DESTRUCTIVE_FRONTEND_COMMANDS.has(normalizedCommand) || /^delete event/.test(normalizedCommand);
}

function isDestructiveLocalCommand(command: string): boolean {
  return DESTRUCTIVE_LOCAL_COMMANDS.has(command);
}

function getFrontendCommandForLocalCommand(command: string): string {
  return LOCAL_COMMAND_TO_FRONTEND_COMMAND[command] ?? command.replace(/-/g, ' ');
}

function isConfirmingPendingCommand(text: string): boolean {
  return /^(?:yes|yeah|yep|correct|confirm|confirmed|do it|run it|execute it|go ahead|proceed|that is right|that's right)$/i.test(
    normalizePendingDecisionText(text)
  );
}

function isRejectingPendingCommand(text: string): boolean {
  return /^(?:no|nope|cancel|cancel it|cancel that|stop|nevermind|never mind|do not|don't|dont|abort|forget it|forget that)$/i.test(
    normalizePendingDecisionText(text)
  );
}

function clampSpeechRate(rate: number): number {
  return Math.min(1.35, Math.max(0.75, rate));
}

function readStoredVoiceOutputEnabled(): boolean {
  if (typeof window === 'undefined') return true;

  try {
    const storedValue = window.localStorage.getItem(VOICE_OUTPUT_STORAGE_KEY);

    if (storedValue === 'false') return false;
    if (storedValue === 'true') return true;

    return true;
  } catch {
    return true;
  }
}

function readStoredSpeechRate(): number {
  if (typeof window === 'undefined') return 1;

  try {
    const storedValue = window.localStorage.getItem(SPEECH_RATE_STORAGE_KEY);
    if (!storedValue) return 1;

    const parsedRate = Number(storedValue);
    return Number.isFinite(parsedRate) ? clampSpeechRate(parsedRate) : 1;
  } catch {
    return 1;
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
        id: typeof task.id === 'string' ? task.id : `task-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        title: task.title,
        createdAt: typeof task.createdAt === 'string' ? task.createdAt : new Date().toISOString(),
        ...(typeof task.completedAt === 'string' ? { completedAt: task.completedAt } : {}),
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
        id: typeof action.id === 'string' ? action.id : `action-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        label: action.label,
        detail: typeof action.detail === 'string' ? action.detail : '',
        createdAt: typeof action.createdAt === 'string' ? action.createdAt : new Date().toISOString(),
      }));
  } catch {
    return [];
  }
}

export default function App() {
  const [chatActive, setChatActive] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [messages, setMessages] = useState<Message[]>([]);
  const backendStatus = useBackendStatus();
  const [activePanel, setActivePanel] = useState<ActivePanel>('none');
  const [voiceOutputEnabled, setVoiceOutputEnabled] = useState(readStoredVoiceOutputEnabled);
  const [speechRate, setSpeechRate] = useState(readStoredSpeechRate);
  const [showThinkingBubble, setShowThinkingBubble] = useState(false);
  const [notes, setNotes] = useState<Note[]>(() => {
    if (typeof window === 'undefined') return [];

    try {
      const rawNotes = window.localStorage.getItem('qmeet-notes');
      if (!rawNotes) return [];

      const parsedNotes = JSON.parse(rawNotes);
      if (!Array.isArray(parsedNotes)) return [];

      return parsedNotes
        .filter((note) => note && typeof note.content === 'string')
        .map((note) => ({
          id: typeof note.id === 'string' ? note.id : `note-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          content: note.content,
          createdAt: typeof note.createdAt === 'string' ? note.createdAt : new Date().toISOString(),
        }));
    } catch {
      return [];
    }
  });
  const [calendarView, setCalendarView] = useState<CalendarView>('today');
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>(() => {
    if (typeof window === 'undefined') return [];
  
    try {
      const rawEvents = window.localStorage.getItem(CALENDAR_EVENTS_STORAGE_KEY);
      if (!rawEvents) return [];
  
      const parsedEvents = JSON.parse(rawEvents);
      if (!Array.isArray(parsedEvents)) return [];
  
      return parsedEvents
        .filter((event) => event && typeof event.title === 'string' && typeof event.dateKey === 'string')
        .map((event) => ({
          id: typeof event.id === 'string' ? event.id : `event-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          title: event.title,
          dateKey: event.dateKey,
          time: typeof event.time === 'string' ? event.time : 'Later',
          createdAt: typeof event.createdAt === 'string' ? event.createdAt : new Date().toISOString(),
          source: 'local',
        }));
    } catch {
      return [];
    }
  });
  const [googleCalendarStatus, setGoogleCalendarStatus] = useState<CalendarBackendStatus | null>(null);
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState<CalendarEvent[]>([]);
  const [googleCalendarLoading, setGoogleCalendarLoading] = useState(false);
  const [googleCalendarError, setGoogleCalendarError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [memoryTasks, setMemoryTasks] = useState<MemoryTask[]>(readStoredMemoryTasks);
  const [memoryTaskDraft, setMemoryTaskDraft] = useState('');
  const [memorySyncState, setMemorySyncState] = useState<MemorySyncState>('local');
  const [memorySyncMessage, setMemorySyncMessage] = useState('Using browser fallback until backend memory and notes load.');
  const [recentActions, setRecentActions] = useState<RecentAction[]>(readStoredRecentActions);
  const [lastHeardTranscript, setLastHeardTranscript] = useState('');
  const [lastNormalizedTranscript, setLastNormalizedTranscript] = useState('');
  const [lastLocalCommand, setLastLocalCommand] = useState('None');
  const [lastInputRoute, setLastInputRoute] = useState('None');
  const [lastInterpreterAction, setLastInterpreterAction] = useState('Not used');
  const [lastInterpreterFrontendCommand, setLastInterpreterFrontendCommand] = useState('None');
  const [lastInterpreterConfidence, setLastInterpreterConfidence] = useState<number | null>(null);
  const [lastInterpreterReason, setLastInterpreterReason] = useState('No interpreter request has run yet.');
  const [pendingInterpreterCommand, setPendingInterpreterCommand] = useState<PendingInterpreterCommand | null>(null);
  const [listeningTranscript, setListeningTranscript] = useState('');
  const speechTokenRef = useRef(0);
  const responseTokenRef = useRef(0);
  const activeStreamAbortRef = useRef<AbortController | null>(null);
  const recognitionRef = useRef<InstanceType<ReturnType<typeof getSpeechRecognition>> | null>(null);
  const transcriptSentRef = useRef(false);
  const listeningTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const suppressNextSpeechErrorRef = useRef(false);
  const orbAreaRef = useRef<HTMLDivElement | null>(null);
  const initialMemoryTasksRef = useRef<MemoryTask[]>(memoryTasks);
  const initialRecentActionsRef = useRef<RecentAction[]>(recentActions);
  const initialNotesRef = useRef<Note[]>(notes);
  const memoryContextHydratedRef = useRef(false);
  const memoryImportInputRef = useRef<HTMLInputElement | null>(null);

  const {
    resultToasts,
    pushResultToast,
    dismissResultToast,
    clearResultToasts,
  } = useResultToasts();

  const stopCurrentSpeech = useCallback(() => {
    speechTokenRef.current += 1;
    stopSpeaking();
  }, []);

  const cancelActiveResponse = useCallback(() => {
    responseTokenRef.current += 1;

    if (activeStreamAbortRef.current) {
      activeStreamAbortRef.current.abort();
      activeStreamAbortRef.current = null;
    }

    setShowThinkingBubble(false);
    setOrbState('idle');
  }, []);

  const speakAssistantText = useCallback((text: string, options: { enabled?: boolean; rate?: number } = {}) => {
    const trimmed = text.trim();
    const shouldSpeak = options.enabled ?? voiceOutputEnabled;
    const rate = options.rate ?? speechRate;

    if (!trimmed || !shouldSpeak) {
      setOrbState('idle');
      return;
    }

    const speechToken = speechTokenRef.current + 1;
    speechTokenRef.current = speechToken;

    const didStart = speakText(trimmed, {
      rate,
      onStart: () => {
        if (speechTokenRef.current === speechToken) {
          setOrbState('speaking');
        }
      },
      onEnd: () => {
        if (speechTokenRef.current === speechToken) {
          setOrbState('idle');
        }
      },
      onError: () => {
        if (speechTokenRef.current === speechToken) {
          setOrbState('idle');
        }
      },
    });

    if (!didStart) {
      setOrbState('idle');
    }
  }, [voiceOutputEnabled, speechRate]);



  useEffect(() => {
    return () => {
      stopSpeaking();
    };
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(VOICE_OUTPUT_STORAGE_KEY, String(voiceOutputEnabled));
    } catch (error) {
      console.error('Failed to save voice output setting:', error);
    }
  }, [voiceOutputEnabled]);

  useEffect(() => {
    try {
      window.localStorage.setItem(SPEECH_RATE_STORAGE_KEY, String(speechRate));
    } catch (error) {
      console.error('Failed to save speech rate setting:', error);
    }
  }, [speechRate]);

  useEffect(() => {
    try {
      window.localStorage.setItem('qmeet-notes', JSON.stringify(notes));
    } catch (error) {
      console.error('Failed to save notes:', error);
    }
  }, [notes]);

  useEffect(() => {
    try {
      window.localStorage.setItem(CALENDAR_EVENTS_STORAGE_KEY, JSON.stringify(calendarEvents));
    } catch (error) {
      console.error('Failed to save calendar events:', error);
    }
  }, [calendarEvents]);

  useEffect(() => {
    try {
      window.localStorage.setItem(MEMORY_TASKS_STORAGE_KEY, JSON.stringify(memoryTasks));
    } catch (error) {
      console.error('Failed to save memory tasks:', error);
    }
  }, [memoryTasks]);

  useEffect(() => {
    try {
      window.localStorage.setItem(RECENT_ACTIONS_STORAGE_KEY, JSON.stringify(recentActions));
    } catch (error) {
      console.error('Failed to save recent actions:', error);
    }
  }, [recentActions]);


  const saveNote = useCallback((content: string): Note | null => {
    const trimmedContent = content.trim();

    if (!trimmedContent) {
      return null;
    }

    const note: Note = {
      id: `note-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      content: trimmedContent,
      createdAt: new Date().toISOString(),
    };

    setNotes((prev) => [note, ...prev]);
    return note;
  }, []);

  const deleteNote = useCallback((noteId: string) => {
    setNotes((prev) => prev.filter((note) => note.id !== noteId));
  }, []);

  const clearNotes = useCallback(() => {
    setNotes([]);
    try {
      window.localStorage.removeItem('qmeet-notes');
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
      .map((note, index) => `${index + 1}. ${note.content}`);

    const remainingCount = notes.length - maxToRead;
    const suffix = remainingCount > 0 ? ` Plus ${remainingCount} more.` : '';

    return `You have ${notes.length} saved note${notes.length === 1 ? '' : 's'}: ${noteLines.join(' ')}${suffix}`;
  }, [notes]);


  const persistMemoryContextToBackend = useCallback(async (tasksToSave: MemoryTask[], actionsToSave: RecentAction[], notesToSave: Note[]) => {
    setMemorySyncState('syncing');

    try {
      const response = await replaceMemoryContext({
        tasks: tasksToSave,
        recentActions: actionsToSave,
        notes: notesToSave,
      });
      setMemorySyncState('synced');
      setMemorySyncMessage(response.message || 'Memory, notes, and work context synced to backend.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Backend memory sync failed.';
      setMemorySyncState('error');
      setMemorySyncMessage(`${message} Browser fallback is still active.`);
    }
  }, []);

  const persistMemoryTasksToBackend = useCallback(async (tasksToSave: MemoryTask[]) => {
    await persistMemoryContextToBackend(tasksToSave, recentActions, notes);
  }, [notes, persistMemoryContextToBackend, recentActions]);

  const loadMemoryContextFromBackend = useCallback(async () => {
    setMemorySyncState('syncing');

    try {
      const response = await getMemoryContext();
      const backendTasks = response.tasks ?? [];
      const backendActions = response.recentActions ?? [];
      const backendNotes = response.notes ?? [];
      const browserTasks = initialMemoryTasksRef.current;
      const browserActions = initialRecentActionsRef.current;
      const browserNotes = initialNotesRef.current;
      const nextTasks = backendTasks.length > 0 || browserTasks.length === 0 ? backendTasks : browserTasks;
      const nextActions = backendActions.length > 0 || browserActions.length === 0 ? backendActions : browserActions;
      const nextNotes = backendNotes.length > 0 || browserNotes.length === 0 ? backendNotes : browserNotes;
      const copiedBrowserTasks = backendTasks.length === 0 && browserTasks.length > 0;
      const copiedBrowserActions = backendActions.length === 0 && browserActions.length > 0;
      const copiedBrowserNotes = backendNotes.length === 0 && browserNotes.length > 0;

      setMemoryTasks(nextTasks);
      setRecentActions(nextActions);
      setNotes(nextNotes);
      memoryContextHydratedRef.current = true;

      if (copiedBrowserTasks || copiedBrowserActions || copiedBrowserNotes) {
        await replaceMemoryContext({ tasks: nextTasks, recentActions: nextActions, notes: nextNotes });
        setMemorySyncState('synced');
        setMemorySyncMessage('Browser memory, notes, and work context were copied into the backend.');
        return;
      }

      setMemorySyncState('synced');
      setMemorySyncMessage(response.message || 'Memory context loaded from backend.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Backend memory unavailable.';
      memoryContextHydratedRef.current = true;
      setMemorySyncState('error');
      setMemorySyncMessage(`${message} Using browser fallback.`);
    }
  }, []);



  useEffect(() => {
    loadMemoryContextFromBackend();
  }, [loadMemoryContextFromBackend]);

  useEffect(() => {
    if (!memoryContextHydratedRef.current) return;

    const timeoutId = window.setTimeout(() => {
      persistMemoryContextToBackend(memoryTasks, recentActions, notes);
    }, 250);

    return () => window.clearTimeout(timeoutId);
  }, [memoryTasks, notes, persistMemoryContextToBackend, recentActions]);

  const addRecentAction = useCallback((label: string, detail: string) => {
    const cleanedDetail = detail.replace(/\s+/g, ' ').trim();

    const action: RecentAction = {
      id: `action-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      label,
      detail: cleanedDetail.length > 140 ? `${cleanedDetail.slice(0, 137).trim()}...` : cleanedDetail,
      createdAt: new Date().toISOString(),
    };

    setRecentActions((prev) => {
      const nextActions = [action, ...prev].slice(0, 12);
      persistMemoryContextToBackend(memoryTasks, nextActions, notes);
      return nextActions;
    });
  }, [memoryTasks, notes, persistMemoryContextToBackend]);

  const saveMemoryTask = useCallback((title: string): MemoryTask | null => {
    const trimmedTitle = title.trim();

    if (!trimmedTitle) {
      return null;
    }

    const task: MemoryTask = {
      id: `task-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      title: trimmedTitle,
      createdAt: new Date().toISOString(),
    };

    const nextTasks = [task, ...memoryTasks];
    setMemoryTasks(nextTasks);
    persistMemoryTasksToBackend(nextTasks);
    return task;
  }, [memoryTasks, persistMemoryTasksToBackend]);

  const markMemoryTaskDone = useCallback((lookup?: string): MemoryTask | null => {
    const openTasks = memoryTasks.filter((task) => !task.completedAt);

    if (openTasks.length === 0) {
      return null;
    }

    const normalizedLookup = normalizeMemoryLookup(lookup ?? '');
    const targetTask = normalizedLookup
      ? openTasks.find((task) => {
          const normalizedTitle = normalizeMemoryLookup(task.title);
          return normalizedTitle.includes(normalizedLookup) || normalizedLookup.includes(normalizedTitle);
        })
      : openTasks[0];

    if (!targetTask) {
      return null;
    }

    const completedTask: MemoryTask = {
      ...targetTask,
      completedAt: new Date().toISOString(),
    };

    const nextTasks = memoryTasks.map((task) => (task.id === targetTask.id ? completedTask : task));
    setMemoryTasks(nextTasks);
    persistMemoryTasksToBackend(nextTasks);

    return completedTask;
  }, [memoryTasks, persistMemoryTasksToBackend]);

  const markMemoryTaskDoneById = useCallback((taskId: string): MemoryTask | null => {
    const targetTask = memoryTasks.find((task) => task.id === taskId && !task.completedAt);

    if (!targetTask) {
      return null;
    }

    const completedTask: MemoryTask = {
      ...targetTask,
      completedAt: new Date().toISOString(),
    };

    const nextTasks = memoryTasks.map((task) => (task.id === targetTask.id ? completedTask : task));
    setMemoryTasks(nextTasks);
    persistMemoryTasksToBackend(nextTasks);

    return completedTask;
  }, [memoryTasks, persistMemoryTasksToBackend]);

  const deleteMemoryTask = useCallback((taskId: string): MemoryTask | null => {
    const targetTask = memoryTasks.find((task) => task.id === taskId) ?? null;

    if (!targetTask) {
      return null;
    }

    const nextTasks = memoryTasks.filter((task) => task.id !== taskId);
    setMemoryTasks(nextTasks);
    persistMemoryTasksToBackend(nextTasks);
    return targetTask;
  }, [memoryTasks, persistMemoryTasksToBackend]);

  const reopenMemoryTask = useCallback((taskId: string): MemoryTask | null => {
    const targetTask = memoryTasks.find((task) => task.id === taskId && task.completedAt);

    if (!targetTask) {
      return null;
    }

    const reopenedTask: MemoryTask = {
      id: targetTask.id,
      title: targetTask.title,
      createdAt: targetTask.createdAt,
    };

    const nextTasks = memoryTasks.map((task) => (task.id === targetTask.id ? reopenedTask : task));
    setMemoryTasks(nextTasks);
    persistMemoryTasksToBackend(nextTasks);

    return reopenedTask;
  }, [memoryTasks, persistMemoryTasksToBackend]);

  const clearCompletedTasks = useCallback((): number => {
    const completedTasks = memoryTasks.filter((task) => task.completedAt);
    const removedCount = completedTasks.length;

    if (removedCount === 0) {
      return 0;
    }

    const completedTaskTitles = completedTasks
      .map((task) => normalizeMemoryLookup(task.title))
      .filter(Boolean);

    const nextTasks = memoryTasks.filter((task) => !task.completedAt);
    setMemoryTasks(nextTasks);
    persistMemoryTasksToBackend(nextTasks);

    // Treat Clear Done as cleanup, not as another memory action.
    // Remove task-related history too so the Memory panel does not still look like
    // the completed task exists after the completed task list has been cleared.
    setRecentActions((prev) => {
      const nextActions = prev.filter((action) => {
        const normalizedLabel = normalizeMemoryLookup(action.label);
        const normalizedDetail = normalizeMemoryLookup(action.detail);
        const actionText = `${normalizedLabel} ${normalizedDetail}`.trim();

        const isTaskAction =
          normalizedLabel === 'saved task' ||
          normalizedLabel === 'completed task' ||
          normalizedLabel === 'cleared completed tasks' ||
          /\btask\b/.test(actionText) ||
          completedTaskTitles.some(
            (title) => actionText.includes(title) || title.includes(normalizedDetail)
          );

        return !isTaskAction;
      });

      persistMemoryContextToBackend(nextTasks, nextActions, notes);
      return nextActions;
    });

    return removedCount;
  }, [memoryTasks, notes, persistMemoryContextToBackend, persistMemoryTasksToBackend]);

  const handleSaveMemoryTaskDraft = useCallback(() => {
    const savedTask = saveMemoryTask(memoryTaskDraft);

    if (!savedTask) {
      return;
    }

    setMemoryTaskDraft('');
    addRecentAction('Saved task', savedTask.title);
    pushResultToast({ kind: 'success', title: 'Task saved', detail: savedTask.title });
  }, [addRecentAction, memoryTaskDraft, pushResultToast, saveMemoryTask]);


  const handleExportMemory = useCallback(async () => {
    try {
      const exportPayload = await exportMemoryContext();
      const payload = {
        version: exportPayload.version || 4,
        exportedAt: exportPayload.exportedAt || new Date().toISOString(),
        tasks: exportPayload.tasks ?? memoryTasks,
        recentActions: exportPayload.recentActions ?? recentActions,
        notes: exportPayload.notes ?? notes,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `qmeet-memory-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMemorySyncState('synced');
      setMemorySyncMessage('Memory export downloaded from backend memory.');
      pushResultToast({ kind: 'success', title: 'Memory exported', detail: 'Downloaded QMeet memory JSON.' });
    } catch (error) {
      const payload = {
        version: 4,
        exportedAt: new Date().toISOString(),
        tasks: memoryTasks,
        recentActions,
        notes,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `qmeet-memory-local-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMemorySyncState('error');
      setMemorySyncMessage('Backend export failed, so QMeet exported the browser fallback memory.');
      pushResultToast({ kind: 'warning', title: 'Local export', detail: 'Backend unavailable; exported browser fallback.' });
    }
  }, [memoryTasks, notes, pushResultToast, recentActions]);

  const handleImportMemoryFile = useCallback(async (event: any) => {
    const file = event.target.files?.[0];
    event.target.value = '';

    if (!file) {
      return;
    }

    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const importedTasks = Array.isArray(parsed.tasks) ? parsed.tasks : [];
      const importedActions = Array.isArray(parsed.recentActions) ? parsed.recentActions : [];
      const importedNotes = Array.isArray(parsed.notes) ? parsed.notes : [];

      const response = await importMemoryContext({
        tasks: importedTasks,
        recentActions: importedActions,
        notes: importedNotes,
      });

      setMemoryTasks(response.tasks ?? importedTasks);
      setRecentActions(response.recentActions ?? importedActions);
      setNotes(response.notes ?? importedNotes);
      setMemorySyncState('synced');
      setMemorySyncMessage(response.message || 'Imported memory JSON into backend memory.');
      pushResultToast({ kind: 'success', title: 'Memory imported', detail: 'Tasks, notes, and work context replaced.' });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not import memory JSON.';
      setMemorySyncState('error');
      setMemorySyncMessage(`${message} Existing memory was left unchanged.`);
      pushResultToast({ kind: 'error', title: 'Import failed', detail: 'Memory JSON was not imported.' });
    }
  }, [pushResultToast]);

  const handleClearAllMemory = useCallback(async () => {
    const confirmed = window.confirm('Clear all QMeet tasks, completed tasks, notes, and hidden recent work context? This cannot be undone unless you exported a backup.');

    if (!confirmed) {
      return;
    }

    setMemoryTasks([]);
    setRecentActions([]);
    setNotes([]);
    setMemoryTaskDraft('');

    try {
      window.localStorage.removeItem(MEMORY_TASKS_STORAGE_KEY);
      window.localStorage.removeItem(RECENT_ACTIONS_STORAGE_KEY);
      window.localStorage.removeItem('qmeet-notes');
    } catch (error) {
      console.error('Failed to clear local memory fallback:', error);
    }

    try {
      const response = await clearAllMemoryContext();
      setMemorySyncState('synced');
      setMemorySyncMessage(response.message || 'Cleared all backend memory.');
      pushResultToast({ kind: 'warning', title: 'Memory cleared', detail: 'Tasks, notes, and work context removed.' });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Backend memory clear failed.';
      setMemorySyncState('error');
      setMemorySyncMessage(`${message} Browser fallback was cleared locally.`);
      pushResultToast({ kind: 'warning', title: 'Local memory cleared', detail: 'Backend clear failed; browser fallback was cleared.' });
    }
  }, [pushResultToast]);

  const handleResetTasksOnly = useCallback(() => {
    const confirmed = window.confirm('Clear open and completed tasks only? Notes and recent work context will stay.');

    if (!confirmed) {
      return;
    }

    setMemoryTasks([]);
    persistMemoryContextToBackend([], recentActions, notes);
    pushResultToast({ kind: 'warning', title: 'Tasks reset', detail: 'Open and completed tasks cleared.' });
  }, [notes, persistMemoryContextToBackend, pushResultToast, recentActions]);

  const handleResetNotesOnly = useCallback(() => {
    const confirmed = window.confirm('Clear notes only? Tasks and recent work context will stay.');

    if (!confirmed) {
      return;
    }

    setNotes([]);
    try {
      window.localStorage.removeItem('qmeet-notes');
    } catch (error) {
      console.error('Failed to clear notes fallback:', error);
    }
    persistMemoryContextToBackend(memoryTasks, recentActions, []);
    pushResultToast({ kind: 'warning', title: 'Notes reset', detail: 'Backend and browser notes cleared.' });
  }, [memoryTasks, persistMemoryContextToBackend, pushResultToast, recentActions]);

  const handleResetRecentContextOnly = useCallback(() => {
    const confirmed = window.confirm('Clear hidden recent work context only? Tasks and notes will stay.');

    if (!confirmed) {
      return;
    }

    setRecentActions([]);
    try {
      window.localStorage.removeItem(RECENT_ACTIONS_STORAGE_KEY);
    } catch (error) {
      console.error('Failed to clear recent actions fallback:', error);
    }
    persistMemoryContextToBackend(memoryTasks, [], notes);
    pushResultToast({ kind: 'warning', title: 'Work context reset', detail: 'Hidden recent actions cleared.' });
  }, [memoryTasks, notes, persistMemoryContextToBackend, pushResultToast]);

  const getMemoryReadout = useCallback(() => {
    const openTasks = memoryTasks.filter((task) => !task.completedAt);
    const completedTasks = memoryTasks.filter((task) => task.completedAt);
    const latestNote = notes[0]?.content;
    const latestCalendarEvent = googleCalendarEvents[0] ?? calendarEvents[0];
    const latestSearch = searchResult?.query || searchQuery.trim();
    const recentActionText = recentActions
      .slice(0, 3)
      .map((action) => action.detail ? `${action.label}: ${action.detail}` : action.label)
      .join('; ');

    const taskText = openTasks.length > 0
      ? `Open tasks: ${openTasks.slice(0, 4).map((task) => task.title).join('; ')}.`
      : 'No open tasks.';

    const completedText = completedTasks.length > 0
      ? `${completedTasks.length} completed task${completedTasks.length === 1 ? '' : 's'} saved.`
      : 'No completed tasks saved.';

    const noteText = latestNote ? `Latest note: ${latestNote}.` : 'No notes yet.';
    const calendarText = latestCalendarEvent
      ? `Latest calendar item: ${latestCalendarEvent.time}: ${latestCalendarEvent.title}.`
      : 'No calendar items loaded.';
    const searchText = latestSearch ? `Latest search: ${latestSearch}.` : 'No search yet.';
    const actionText = recentActionText ? `Recent actions: ${recentActionText}.` : 'No recent actions yet.';

    return `${taskText} ${completedText} ${noteText} ${calendarText} ${searchText} ${actionText}`;
  }, [calendarEvents, googleCalendarEvents, memoryTasks, notes, recentActions, searchQuery, searchResult?.query]);


  const saveCalendarEvent = useCallback(async (eventInput?: { day?: CalendarView; time?: string; title?: string }): Promise<CalendarEvent | null> => {
    const title = eventInput?.title?.trim() ?? '';

    if (!title) {
      return null;
    }

    const view = eventInput?.day ?? 'today';
    const eventTime = eventInput?.time?.trim() || 'Later';

    if (googleCalendarStatus?.connected && googleCalendarStatus?.writeEnabled) {
      setGoogleCalendarLoading(true);
      setGoogleCalendarError('');

      try {
        const response = await createCalendarEvent({
          title,
          day: view,
          time: eventTime,
        });

        if (response.event) {
          setGoogleCalendarEvents((prev) => [
            response.event as CalendarEvent,
            ...prev.filter((event) => event.id !== response.event?.id),
          ]);
          setGoogleCalendarError(response.message || 'Google Calendar event created.');
          return response.event;
        }

        setGoogleCalendarError(response.message || 'Google Calendar did not return the created event.');
        return null;
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Could not create Google Calendar event.';
        setGoogleCalendarError(message);
        return null;
      } finally {
        setGoogleCalendarLoading(false);
      }
    }

    const event: CalendarEvent = {
      id: `event-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      title,
      dateKey: getDateKeyForCalendarView(view),
      time: eventTime,
      createdAt: new Date().toISOString(),
      source: 'local',
    };

    setCalendarEvents((prev) => [event, ...prev]);
    return event;
  }, [googleCalendarStatus?.connected, googleCalendarStatus?.writeEnabled]);

  const deleteCalendarEvent = useCallback(async (eventId: string): Promise<CalendarEvent | null> => {
    const googleEvent = googleCalendarEvents.find(
      (event) => event.id === eventId || event.googleEventId === eventId
    );

    if (googleEvent?.source === 'google') {
      const googleEventId = googleEvent.googleEventId || googleEvent.id.replace(/^google-/, '');

      if (!googleEventId) {
        setGoogleCalendarError('Could not identify the Google Calendar event to delete.');
        return null;
      }

      setGoogleCalendarLoading(true);
      setGoogleCalendarError('');

      try {
        const response = await deleteGoogleCalendarEvent(googleEventId);
        setGoogleCalendarEvents((prev) =>
          prev.filter((event) =>
            event.id !== googleEvent.id &&
            event.googleEventId !== googleEvent.googleEventId &&
            event.googleEventId !== googleEventId
          )
        );
        setGoogleCalendarError(response.message || 'Deleted Google Calendar event.');
        return googleEvent;
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Could not delete Google Calendar event.';
        setGoogleCalendarError(message);
        return null;
      } finally {
        setGoogleCalendarLoading(false);
      }
    }

    const localEvent = calendarEvents.find((event) => event.id === eventId) ?? null;
    setCalendarEvents((prev) => prev.filter((event) => event.id !== eventId));
    return localEvent;
  }, [calendarEvents, googleCalendarEvents]);

    const updateCalendarEvent = useCallback(async (eventId: string, changes?: { day?: CalendarView; time?: string; title?: string }): Promise<CalendarEvent | null> => {
      if (!changes || (!changes.day && !changes.time?.trim() && !changes.title?.trim())) {
        setGoogleCalendarError('No calendar event changes were provided.');
        return null;
      }
  
      const googleEvent = googleCalendarEvents.find(
        (event) => event.id === eventId || event.googleEventId === eventId
      );
  
      if (googleEvent?.source === 'google') {
        const googleEventId = googleEvent.googleEventId || googleEvent.id.replace(/^google-/, '');
  
        if (!googleEventId) {
          setGoogleCalendarError('Could not identify the Google Calendar event to update.');
          return null;
        }
  
        setGoogleCalendarLoading(true);
        setGoogleCalendarError('');
  
        try {
          const response = await updateGoogleCalendarEvent(googleEventId, {
            ...(changes.title?.trim() ? { title: changes.title.trim() } : {}),
            ...(changes.day ? { day: changes.day } : {}),
            ...(changes.time?.trim() ? { time: changes.time.trim() } : {}),
          });
  
          if (response.event) {
            setGoogleCalendarEvents((prev) =>
              [
                response.event as CalendarEvent,
                ...prev.filter((event) =>
                  event.id !== googleEvent.id &&
                  event.googleEventId !== googleEvent.googleEventId &&
                  event.googleEventId !== googleEventId
                ),
              ]
            );
            setGoogleCalendarError(response.message || 'Updated Google Calendar event.');
            return response.event;
          }
  
          setGoogleCalendarError(response.message || 'Google Calendar did not return the updated event.');
          return null;
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Could not update Google Calendar event.';
          setGoogleCalendarError(message);
          return null;
        } finally {
          setGoogleCalendarLoading(false);
        }
      }
  
      const localEvent = calendarEvents.find((event) => event.id === eventId) ?? null;
  
      if (!localEvent) {
        return null;
      }
  
      const updatedLocalEvent: CalendarEvent = {
        ...localEvent,
        title: changes.title?.trim() || localEvent.title,
        time: changes.time?.trim() || localEvent.time,
        dateKey: changes.day ? getDateKeyForCalendarView(changes.day) : localEvent.dateKey,
        source: localEvent.source ?? 'local',
      };
  
      setCalendarEvents((prev) =>
        prev.map((event) => (event.id === localEvent.id ? updatedLocalEvent : event))
      );
  
      return updatedLocalEvent;
    }, [calendarEvents, googleCalendarEvents]);

  const clearCalendarEvents = useCallback(() => {
    setCalendarEvents([]);

    try {
      window.localStorage.setItem(CALENDAR_EVENTS_STORAGE_KEY, '[]');

      for (const legacyKey of LEGACY_CALENDAR_EVENTS_STORAGE_KEYS) {
        window.localStorage.removeItem(legacyKey);
      }
    } catch (error) {
      console.error('Failed to clear calendar events:', error);
    }
  }, []);

  const getNextCalendarEventForDeletion = useCallback((): CalendarEvent | null => {
    if (googleCalendarStatus?.connected) {
      const visibleGoogleEvents = googleCalendarEvents.filter((event) => isEventForCalendarView(event, calendarView));
      return visibleGoogleEvents[0] ?? googleCalendarEvents[0] ?? null;
    }

    return calendarEvents[0] ?? null;
  }, [calendarEvents, calendarView, googleCalendarEvents, googleCalendarStatus?.connected]);

  const getNextCalendarEventForChange = useCallback((): CalendarEvent | null => {
    if (googleCalendarStatus?.connected) {
      const visibleGoogleEvents = googleCalendarEvents.filter((event) => isEventForCalendarView(event, calendarView));
      return visibleGoogleEvents[0] ?? googleCalendarEvents[0] ?? null;
    }

    return calendarEvents[0] ?? null;
  }, [calendarEvents, calendarView, googleCalendarEvents, googleCalendarStatus?.connected]);

  const editLastCalendarEvent = useCallback(async (changes?: { day?: CalendarView; time?: string; title?: string }): Promise<CalendarEvent | null> => {
    const targetEvent = getNextCalendarEventForChange();

    if (!targetEvent) return null;

    return updateCalendarEvent(targetEvent.id, changes);
  }, [getNextCalendarEventForChange, updateCalendarEvent]);

  const deleteLastCalendarEvent = useCallback(async (): Promise<CalendarEvent | null> => {
    const targetEvent = getNextCalendarEventForDeletion();

    if (!targetEvent) return null;

    if (targetEvent.source === 'google' || targetEvent.googleEventId) {
      return deleteCalendarEvent(targetEvent.id);
    }

    setCalendarEvents((prev) => prev.filter((event) => event.id !== targetEvent.id));
    return targetEvent;
  }, [deleteCalendarEvent, getNextCalendarEventForDeletion]);

  const getCalendarReadout = useCallback((view: CalendarView | 'all' = 'all', remoteEvents: CalendarEvent[] = googleCalendarEvents) => {
    const googleConnected = Boolean(googleCalendarStatus?.connected);
    const sourceEvents = googleConnected ? remoteEvents : calendarEvents;
    const sourceLabel = googleConnected ? 'Google Calendar' : 'local calendar';

    const getEventsForView = (targetView: CalendarView) =>
      sourceEvents.filter((event) => isEventForCalendarView(event, targetView));

    const describeEvents = (label: string, eventsForDate: CalendarEvent[]) => {
      if (eventsForDate.length === 0) {
        return `No ${sourceLabel} events saved for ${label}.`;
      }

      const eventText = eventsForDate
        .slice(0, 5)
        .map((event) => `${event.time}: ${event.title}${event.location ? ` at ${event.location}` : ''}`)
        .join(' ');

      const remainingCount = eventsForDate.length - 5;
      const suffix = remainingCount > 0 ? ` Plus ${remainingCount} more.` : '';

      return `${label.charAt(0).toUpperCase() + label.slice(1)} ${sourceLabel}: ${eventText}${suffix}`;
    };

    if (view === 'today') {
      return describeEvents('today', getEventsForView('today'));
    }

    if (view === 'tomorrow') {
      return describeEvents('tomorrow', getEventsForView('tomorrow'));
    }

    const todayEvents = getEventsForView('today');
    const tomorrowEvents = getEventsForView('tomorrow');

    if (todayEvents.length === 0 && tomorrowEvents.length === 0) {
      return googleConnected
        ? 'You do not have any Google Calendar events for today or tomorrow.'
        : 'You do not have any local calendar events saved for today or tomorrow.';
    }

    return `${describeEvents('today', todayEvents)} ${describeEvents('tomorrow', tomorrowEvents)}`;
  }, [calendarEvents, googleCalendarEvents, googleCalendarStatus?.connected]);


  // Cleanup speech recognition state
  const finishListening = useCallback(() => {
    if (listeningTimeoutRef.current) {
      clearTimeout(listeningTimeoutRef.current);
      listeningTimeoutRef.current = null;
    }

    if (recognitionRef.current) {
      try {
        suppressNextSpeechErrorRef.current = true;
        recognitionRef.current.abort();
      } catch (error) {
        console.error('Error aborting recognition:', error);
      }
      recognitionRef.current = null;
    }

    transcriptSentRef.current = false;
    setListeningTranscript('');
    setOrbState('idle');
  }, []);

  // End chat and return to idle state
  const handleEndChat = useCallback(async () => {
    stopCurrentSpeech();
    cancelActiveResponse();
    finishListening();
    setShowThinkingBubble(false);
    setActivePanel('none');
    setPendingInterpreterCommand(null);
    clearResultToasts();
    setChatActive(false);
    setMessages([]);

    try {
      await resetConversation();
    } catch (error) {
      console.error('Reset conversation error:', error);
    }
  }, [cancelActiveResponse, clearResultToasts, finishListening, stopCurrentSpeech]);

  const closePanel = useCallback(() => {
    setActivePanel('none');
  }, []);

  const goHome = useCallback(() => {
    stopCurrentSpeech();
    cancelActiveResponse();
    finishListening();
    setShowThinkingBubble(false);
    setActivePanel('none');
    setOrbState('idle');

    window.setTimeout(() => {
      orbAreaRef.current?.focus();
    }, 0);
  }, [cancelActiveResponse, finishListening, stopCurrentSpeech]);

  const openLauncherPanel = useCallback((panel: ActivePanel) => {
    if (panel === 'calendar') {
      setCalendarView('today');
    }

    if (panel === 'search') {
      setSearchQuery('');
    }

    setActivePanel(panel);
  }, []);

  const setVoiceOutput = useCallback((enabled: boolean) => {
    if (!enabled) {
      stopCurrentSpeech();
    }
    setVoiceOutputEnabled(enabled);
  }, [stopCurrentSpeech]);

  const adjustSpeechRate = useCallback((nextRate: number) => {
    const clampedRate = clampSpeechRate(nextRate);
    setSpeechRate(clampedRate);
    return clampedRate;
  }, []);
  const loadGoogleCalendarStatus = useCallback(async (): Promise<CalendarBackendStatus | null> => {
    try {
      const status = await getCalendarStatus();
      setGoogleCalendarStatus(status);
      if (status.connected) {
        setGoogleCalendarError('');
      }
      return status;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not load Google Calendar status.';
      setGoogleCalendarStatus(null);
      setGoogleCalendarError(message);
      return null;
    }
  }, []);

  const refreshGoogleCalendar = useCallback(async (viewInput: CalendarBackendView = calendarView): Promise<CalendarEvent[]> => {
    setGoogleCalendarLoading(true);
    setGoogleCalendarError('');

    try {
      const status = await getCalendarStatus();
      setGoogleCalendarStatus(status);

      if (!status.connected) {
        setGoogleCalendarEvents([]);
        setGoogleCalendarError(status.message);
        return [];
      }

      const response = await getCalendarEvents(viewInput);
      setGoogleCalendarEvents(response.events);
      setGoogleCalendarError(response.message);
      return response.events;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not read Google Calendar events.';
      setGoogleCalendarError(message);
      return [];
    } finally {
      setGoogleCalendarLoading(false);
    }
  }, [calendarView]);

  const getCalendarEventsForDeleteCriteria = useCallback(async (criteria?: CalendarDeleteCriteria): Promise<CalendarEvent[]> => {
    if (googleCalendarStatus?.connected) {
      const targetView = criteria?.day ?? calendarView;
      return refreshGoogleCalendar(targetView);
    }

    return calendarEvents;
  }, [calendarEvents, calendarView, googleCalendarStatus?.connected, refreshGoogleCalendar]);

  const findCalendarEventForDeletion = useCallback(async (criteria?: CalendarDeleteCriteria): Promise<CalendarEvent | null> => {
    const sourceEvents = await getCalendarEventsForDeleteCriteria(criteria);
    const matchingEvents = sourceEvents.filter((event) => calendarEventMatchesDeleteCriteria(event, criteria));

    if (criteria?.day || criteria?.time || criteria?.title) {
      return matchingEvents[0] ?? null;
    }

    return getNextCalendarEventForDeletion();
  }, [getCalendarEventsForDeleteCriteria, getNextCalendarEventForDeletion]);

  const deleteCalendarEventByCriteria = useCallback(async (criteria?: CalendarDeleteCriteria): Promise<CalendarEvent | null> => {
    const targetEvent = await findCalendarEventForDeletion(criteria);

    if (!targetEvent) return null;

    if (targetEvent.source === 'google' || targetEvent.googleEventId) {
      return deleteCalendarEvent(targetEvent.id);
    }

    setCalendarEvents((prev) => prev.filter((event) => event.id !== targetEvent.id));
    return targetEvent;
  }, [deleteCalendarEvent, findCalendarEventForDeletion]);

  useEffect(() => {
    loadGoogleCalendarStatus();
  }, [loadGoogleCalendarStatus]);

  useEffect(() => {
    if (activePanel === 'calendar') {
      refreshGoogleCalendar(calendarView);
    }
  }, [activePanel, calendarView, refreshGoogleCalendar]);

  const handleStartGoogleCalendarAuth = useCallback(async () => {
    setGoogleCalendarLoading(true);
    setGoogleCalendarError('');

    try {
      const response = await startCalendarAuth();

      if (response.authUrl) {
        window.open(response.authUrl, '_blank', 'noopener,noreferrer');
        setGoogleCalendarError('Google authorization opened in a new tab. After approving access, return here and press Refresh.');
      } else {
        setGoogleCalendarError(response.message || 'Google Calendar authorization did not return a URL.');
      }
    } catch (error) {
      setGoogleCalendarError(error instanceof Error ? error.message : 'Could not start Google Calendar authorization.');
    } finally {
      setGoogleCalendarLoading(false);
      loadGoogleCalendarStatus();
    }
  }, [loadGoogleCalendarStatus]);

  const handleResetGoogleCalendarAuth = useCallback(async () => {
    setGoogleCalendarLoading(true);
    setGoogleCalendarError('');

    try {
      const response = await resetCalendarAuth();
      setGoogleCalendarEvents([]);
      setGoogleCalendarError(response.message || 'Google Calendar authorization reset.');
      await loadGoogleCalendarStatus();
    } catch (error) {
      setGoogleCalendarError(error instanceof Error ? error.message : 'Could not reset Google Calendar authorization.');
    } finally {
      setGoogleCalendarLoading(false);
    }
  }, [loadGoogleCalendarStatus]);


  const clearSearchState = useCallback(() => {
    setSearchQuery('');
    setSearchResult(null);
    setSearchError('');
    setSearchLoading(false);
  }, []);

  const runWebSearch = useCallback(async (queryInput?: string): Promise<SearchResponse | null> => {
    const query = (queryInput ?? searchQuery).trim();

    setActivePanel('search');

    if (!query) {
      setSearchError('Enter a search query first.');
      setSearchResult(null);
      return null;
    }

    setSearchQuery(query);
    setSearchLoading(true);
    setSearchError('');

    try {
      const response = await searchWeb(query);
      setSearchResult(response);
      setSearchError(response.ok ? '' : response.message || 'Search failed.');
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Web search failed.';
      setSearchResult(null);
      setSearchError(message);
      return null;
    } finally {
      setSearchLoading(false);
    }
  }, [searchQuery]);


  // TODO: Backend integration
  // Replace this function body with actual FastAPI calls:
  //
  // Option 1: WebSocket streaming
  //   const ws = useRef<WebSocket | null>(null);
  //   useEffect(() => {
  //     ws.current = new WebSocket('ws://localhost:8000/ws/chat');
  //     ws.current.onmessage = (e) => {
  //       const data = JSON.parse(e.data);
  //       // Append assistant message chunks or complete message
  //     };
  //   }, []);
  //
  // Option 2: REST with polling
  //   const res = await fetch('http://localhost:8000/api/chat', {
  //     method: 'POST',
  //     headers: { 'Content-Type': 'application/json' },
  //     body: JSON.stringify({ message: text }),
  //   });
  //   const data = await res.json();
  //   // data.reply contains the assistant response
  //
  const handleSend = useCallback(async (text: string, displayText?: string, commandRoute: 'exact' | 'interpreter' | 'confirmed' = 'exact') => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const visibleUserText = (displayText ?? trimmed).trim() || trimmed;

    stopCurrentSpeech();

    if (pendingInterpreterCommand) {
          if (isConfirmingPendingCommand(trimmed)) {
            const commandToRun = pendingInterpreterCommand;
            setPendingInterpreterCommand(null);
            setLastInputRoute('Confirmed fuzzy interpreter command');
            setLastInterpreterAction(commandToRun.action);
            setLastInterpreterFrontendCommand(commandToRun.frontendCommand);
            setLastInterpreterConfidence(commandToRun.confidence);
            setLastInterpreterReason(commandToRun.reason || 'User confirmed a pending destructive command.');
            return handleSend(commandToRun.frontendCommand, visibleUserText, 'confirmed');
          }
    
          if (isRejectingPendingCommand(trimmed)) {
            finishListening();
            setShowThinkingBubble(false);
            setPendingInterpreterCommand(null);
            setLastInputRoute('Cancelled pending command');
            setLastLocalCommand('Pending command cancelled');
            setLastInterpreterReason(`User cancelled pending command: ${pendingInterpreterCommand.frontendCommand}.`);
    
            if (!chatActive) setChatActive(true);
    
            const now = Date.now();
            const userMsg: Message = {
              id: `u-${now}`,
              role: 'user',
              content: visibleUserText,
              timestamp: new Date(),
            };
            const assistantMsg: Message = {
              id: `a-${now}`,
              role: 'assistant',
              content: 'Cancelled pending command.',
              timestamp: new Date(),
            };
    
            setMessages((prev) => [...prev, userMsg, assistantMsg]);
            pushResultToast({ kind: 'warning', title: 'Cancelled', detail: 'Pending command dismissed.' });
            speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
            return;
          }
    
          setPendingInterpreterCommand(null);
        }

    const commandMatch = parseCommand(trimmed);
    
    if (commandMatch) {
      finishListening();
      setShowThinkingBubble(false);

      if (!chatActive) setChatActive(true);

      const now = Date.now();
      const previousLastHeardTranscript = lastHeardTranscript;
      const previousLastNormalizedTranscript = lastNormalizedTranscript;
      const previousLastLocalCommand = lastLocalCommand;

      setLastLocalCommand(commandMatch.command);
      setPendingInterpreterCommand(null);
      
      if (commandRoute === 'interpreter') {
        setLastInputRoute('Fuzzy interpreter command');
      } else if (commandRoute === 'confirmed') {
        setLastInputRoute('Confirmed destructive command');
      } else {
        setLastInputRoute('Exact local command');
        setLastInterpreterAction('Not used');
        setLastInterpreterFrontendCommand('None');
        setLastInterpreterConfidence(null);
        setLastInterpreterReason('Exact frontend parser matched before the command interpreter was needed.');
      }

      const userMsg: Message = {
        id: `u-${now}`,
        role: 'user',
        content: visibleUserText,
        timestamp: new Date(),
      };
      
      if (
        commandRoute !== 'confirmed' &&
        commandMatch.command === 'add-calendar-event' &&
        googleCalendarStatus?.connected &&
        googleCalendarStatus?.writeEnabled
      ) {
        const targetView = commandMatch.calendarEvent?.day ?? 'today';
        const targetTime = commandMatch.calendarEvent?.time?.trim() || 'Later';
        const targetTitle = commandMatch.calendarEvent?.title?.trim() ?? '';

        if (targetTitle) {
          const frontendCommand = `add event ${targetView} at ${targetTime} called ${targetTitle}`;
          const confirmationPrompt = `I understood that as: create a Google Calendar event ${targetView} at ${targetTime}: ${targetTitle}. Say "confirm" to create it, or "cancel" to stop.`;

          setPendingInterpreterCommand({
            originalText: visibleUserText,
            frontendCommand,
            action: commandMatch.command,
            confidence: commandRoute === 'exact' ? 1 : 0.9,
            reason: 'Google Calendar event creation requires confirmation before writing to the real calendar.',
          });
          setLastInputRoute(commandRoute === 'exact' ? 'Exact Google Calendar write needs confirmation' : 'Fuzzy Google Calendar write needs confirmation');
          setLastLocalCommand('Pending Google Calendar write');
          setLastInterpreterAction(commandRoute === 'exact' ? 'Not used' : commandMatch.command);
          setLastInterpreterFrontendCommand(frontendCommand);
          setLastInterpreterConfidence(commandRoute === 'exact' ? 1 : 0.9);
          setLastInterpreterReason('Google Calendar event creation requires confirmation before writing to the real calendar.');

          const assistantMsg: Message = {
            id: `a-${now}`,
            role: 'assistant',
            content: confirmationPrompt,
            timestamp: new Date(),
          };

          setMessages((prev) => [...prev, userMsg, assistantMsg]);
          speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
          return;
        }
      }

      if (commandRoute !== 'confirmed' && commandMatch.command === 'edit-last-event') {
              const targetEditEvent = getNextCalendarEventForChange();
              const editDescription = describeCalendarEditPayload(commandMatch.calendarEdit);
      
              if (!targetEditEvent) {
                setLastInputRoute('Edit command had no target');
                setLastLocalCommand('No calendar event to edit');
      
                const assistantMsg: Message = {
                  id: `a-${now}`,
                  role: 'assistant',
                  content: googleCalendarStatus?.connected
                    ? 'I did not find a Google Calendar event to edit for the current view.'
                    : 'I did not find a local calendar event to edit.',
                  timestamp: new Date(),
                };
      
                setMessages((prev) => [...prev, userMsg, assistantMsg]);
                speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
                return;
              }
      
              const frontendCommand = buildCalendarEditFrontendCommand(commandMatch.calendarEdit);
              const sourceLabel = targetEditEvent.source === 'google' ? 'Google Calendar' : 'local';
              const confirmationPrompt = `I understood that as: update ${sourceLabel} event: ${targetEditEvent.time || '—'}: ${targetEditEvent.title}. Changes: ${editDescription}. Say "confirm" to update it, or "cancel" to stop.`;
      
              setPendingInterpreterCommand({
                originalText: visibleUserText,
                frontendCommand,
                action: commandMatch.command,
                confidence: commandRoute === 'exact' ? 1 : 0.9,
                reason: 'Calendar event editing requires confirmation before changing the calendar.',
              });
              setLastInputRoute(commandRoute === 'exact' ? 'Exact Google Calendar edit needs confirmation' : 'Fuzzy Google Calendar edit needs confirmation');
              setLastLocalCommand('Pending calendar edit');
              setLastInterpreterAction(commandRoute === 'exact' ? 'Not used' : commandMatch.command);
              setLastInterpreterFrontendCommand(frontendCommand);
              setLastInterpreterConfidence(commandRoute === 'exact' ? 1 : 0.9);
              setLastInterpreterReason('Calendar event editing requires confirmation before changing the calendar.');
      
              const assistantMsg: Message = {
                id: `a-${now}`,
                role: 'assistant',
                content: confirmationPrompt,
                timestamp: new Date(),
              };
      
              setMessages((prev) => [...prev, userMsg, assistantMsg]);
              speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
              return;
            }

      if (commandRoute !== 'confirmed' && isDestructiveLocalCommand(commandMatch.command)) {
        const frontendCommand = commandMatch.command === 'delete-calendar-event'
          ? buildCalendarDeleteFrontendCommand(commandMatch.calendarDelete)
          : getFrontendCommandForLocalCommand(commandMatch.command);
        const isCalendarDeleteCommand = commandMatch.command === 'delete-last-event' || commandMatch.command === 'delete-calendar-event';
        const targetDeleteEvent = commandMatch.command === 'delete-last-event'
          ? getNextCalendarEventForDeletion()
          : commandMatch.command === 'delete-calendar-event'
            ? await findCalendarEventForDeletion(commandMatch.calendarDelete)
            : null;
        const rawDeleteDescription = commandMatch.command === 'delete-calendar-event'
          ? describeCalendarDeletePayload(commandMatch.calendarDelete)
          : frontendCommand;
        const deleteDescription = rawDeleteDescription.replace(/[.?!\s]+$/g, '').trim() || rawDeleteDescription;
        const confirmationPrompt = targetDeleteEvent
          ? `I understood that as: ${deleteDescription}. This will delete ${targetDeleteEvent.source === 'google' ? 'Google Calendar' : 'local'} event: ${targetDeleteEvent.time || '—'}: ${targetDeleteEvent.title}. Say "confirm" to run it, or "cancel" to stop.`
          : isCalendarDeleteCommand
            ? `I did not find a calendar event matching ${deleteDescription}.`
            : `I understood that as: ${frontendCommand}. This changes or deletes local data. Say "confirm" to run it, or "cancel" to stop.`;

        if (isCalendarDeleteCommand && !targetDeleteEvent) {
          setLastInputRoute('Delete command had no target');
          setLastLocalCommand('No matching calendar event to delete');

          const assistantMsg: Message = {
            id: `a-${now}`,
            role: 'assistant',
            content: confirmationPrompt,
            timestamp: new Date(),
          };

          setMessages((prev) => [...prev, userMsg, assistantMsg]);
          speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
          return;
        }

        setPendingInterpreterCommand({
          originalText: visibleUserText,
          frontendCommand,
          action: commandMatch.command,
          confidence: commandRoute === 'exact' ? 1 : 0.9,
          reason:
            commandRoute === 'exact'
              ? 'Exact frontend parser matched a destructive command, so QMeet paused for confirmation.'
              : 'Command interpreter mapped the input to a destructive command, so QMeet paused for confirmation.',
        });
        setLastInputRoute(commandRoute === 'exact' ? 'Exact command needs safety confirmation' : 'Fuzzy interpreter needs safety confirmation');
        setLastLocalCommand('Pending destructive command');
        setLastInterpreterAction(commandRoute === 'exact' ? 'Not used' : commandMatch.command);
        setLastInterpreterFrontendCommand(frontendCommand);
        setLastInterpreterConfidence(commandRoute === 'exact' ? 1 : 0.9);
        setLastInterpreterReason(
          commandRoute === 'exact'
            ? 'Exact frontend parser matched a destructive command, so QMeet paused for confirmation.'
            : 'Command interpreter mapped the input to a destructive command, so QMeet paused for confirmation.'
        );

        const assistantMsg: Message = {
          id: `a-${now}`,
          role: 'assistant',
          content: confirmationPrompt,
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, userMsg, assistantMsg]);
        speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
        return;
      }

      let confirmationContent =
        commandMatch.command === 'close-generic' && activePanel === 'none'
          ? 'No panel is open.'
          : commandMatch.confirmation;
      let shouldSpeakConfirmation = voiceOutputEnabled;
      let confirmationSpeechRate = speechRate;
      let replaceMessages = false;
      let speechConfirmationContent = getBriefToolSpeech(commandMatch.command, confirmationContent);
      
      if (commandMatch.command === 'open-menu') {
        setActivePanel('menu');
      } else if (commandMatch.command === 'close-menu') {
        closePanel();
      } else if (commandMatch.command === 'open-settings') {
        setActivePanel('settings');
      } else if (commandMatch.command === 'close-settings') {
        closePanel();
      } else if (commandMatch.command === 'go-home') {
        confirmationContent = activePanel === 'none' ? "You're already home." : 'Going home.';
        goHome();
      } else if (commandMatch.command === 'show-status') {
        setActivePanel('status');
      } else if (commandMatch.command === 'close-status') {
        closePanel();
      } else if (commandMatch.command === 'hide-status') {
        closePanel();
      } else if (commandMatch.command === 'open-notes') {
        setActivePanel('notes');
      } else if (commandMatch.command === 'new-note') {
        setActivePanel('notes');
      } else if (commandMatch.command === 'save-note') {
        const savedNote = saveNote(commandMatch.payload ?? '');
        setActivePanel('notes');
        confirmationContent = savedNote ? 'Saved note.' : 'I did not catch the note text.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'read-notes') {
        setActivePanel('notes');
        confirmationContent = getNotesReadout();
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'delete-last-note') {
        const deletedNote = deleteLastNote();
        setActivePanel('notes');
        confirmationContent = deletedNote ? 'Deleted the last note.' : 'No notes to delete.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'close-notes') {
        closePanel();
      } else if (commandMatch.command === 'clear-notes') {
        clearNotes();
      } else if (commandMatch.command === 'open-memory') {
        setActivePanel('memory');
      } else if (commandMatch.command === 'close-memory') {
        closePanel();
      } else if (commandMatch.command === 'read-memory') {
        setActivePanel('memory');
        confirmationContent = getMemoryReadout();
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'remember-task') {
        const savedTask = saveMemoryTask(commandMatch.payload ?? '');
        setActivePanel('memory');
        confirmationContent = savedTask ? `Saved task: ${savedTask.title}.` : 'I did not catch the task text.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'mark-task-done') {
        const completedTask = markMemoryTaskDone(commandMatch.payload);
        setActivePanel('memory');
        confirmationContent = completedTask
          ? `Marked task done: ${completedTask.title}.`
          : commandMatch.payload
            ? `I could not find an open task matching "${commandMatch.payload}".`
            : 'No open tasks to complete.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'clear-done-tasks') {
        const removedCount = clearCompletedTasks();
        setActivePanel('memory');
        confirmationContent = removedCount > 0
          ? `Cleared ${removedCount} completed task${removedCount === 1 ? '' : 's'}.`
          : 'No completed tasks to clear.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'open-calendar') {
        setCalendarView('today');
        setActivePanel('calendar');
      } else if (commandMatch.command === 'refresh-calendar') {
        const refreshedEvents = await refreshGoogleCalendar(calendarView);
        setActivePanel('calendar');
        confirmationContent = googleCalendarStatus?.connected
          ? `Refreshed Google Calendar. ${refreshedEvents.length} event${refreshedEvents.length === 1 ? '' : 's'} loaded.`
          : 'Calendar refreshed. Google Calendar is not connected, so QMeet is showing local calendar events.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'edit-last-event') {
        const updatedEvent = await editLastCalendarEvent(commandMatch.calendarEdit);
        setActivePanel('calendar');
        confirmationContent = updatedEvent
          ? `Updated ${updatedEvent.source === 'google' ? 'Google Calendar' : 'local'} event: ${updatedEvent.time}: ${updatedEvent.title}.`
          : googleCalendarStatus?.connected
            ? 'I could not update the Google Calendar event. Check the Calendar panel status.'
            : 'No local calendar events to update.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'add-calendar-event') {
        const addedEvent = await saveCalendarEvent(commandMatch.calendarEvent);
        const targetView = commandMatch.calendarEvent?.day ?? 'today';
        setCalendarView(targetView);
        setActivePanel('calendar');
        confirmationContent = addedEvent
          ? `Added ${addedEvent.source === 'google' ? 'Google Calendar' : 'local'} event ${getCalendarViewLabel(targetView)} at ${addedEvent.time}: ${addedEvent.title}.`
          : googleCalendarStatus?.connected && googleCalendarStatus?.writeEnabled
            ? 'I could not create the Google Calendar event. Check the Calendar panel status.'
            : 'I did not catch the event details.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'read-calendar') {
        const requestedCalendarView = commandMatch.calendarView ?? 'all';
        const remoteCalendarView: CalendarBackendView =
                  requestedCalendarView === 'all' ? 'week' : requestedCalendarView;
                const remoteEvents = googleCalendarStatus?.connected
                  ? await refreshGoogleCalendar(remoteCalendarView)
                  : googleCalendarEvents;
                const sourceEvents = googleCalendarStatus?.connected ? remoteEvents : calendarEvents;
                const hasTodayEvents = sourceEvents.some((event) => isEventForCalendarView(event, 'today'));
                const hasTomorrowEvents = sourceEvents.some((event) => isEventForCalendarView(event, 'tomorrow'));
        const targetView = requestedCalendarView === 'today' || requestedCalendarView === 'tomorrow'
          ? requestedCalendarView
          : hasTodayEvents
            ? 'today'
            : hasTomorrowEvents
              ? 'tomorrow'
              : calendarView;

        setCalendarView(targetView);
        setActivePanel('calendar');
        confirmationContent = getCalendarReadout(requestedCalendarView, remoteEvents);
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'delete-calendar-event') {
        const targetView = commandMatch.calendarDelete?.day ?? calendarView;
        const deletedEvent = await deleteCalendarEventByCriteria(commandMatch.calendarDelete);
        setCalendarView(targetView);
        setActivePanel('calendar');
        confirmationContent = deletedEvent
          ? `Deleted ${deletedEvent.source === 'google' ? 'Google Calendar' : 'local'} event: ${deletedEvent.time}: ${deletedEvent.title}.`
          : googleCalendarStatus?.connected
            ? `No Google Calendar event matched ${describeCalendarDeletePayload(commandMatch.calendarDelete)}.`
            : `No local calendar event matched ${describeCalendarDeletePayload(commandMatch.calendarDelete)}.`;
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'delete-last-event') {
        const deletedEvent = await deleteLastCalendarEvent();
        setActivePanel('calendar');
        confirmationContent = deletedEvent
          ? `Deleted ${deletedEvent.source === 'google' ? 'Google Calendar' : 'local'} event: ${deletedEvent.time}: ${deletedEvent.title}.`
          : googleCalendarStatus?.connected
            ? 'No Google Calendar events to delete for the current view.'
            : 'No local calendar events to delete.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'clear-calendar') {
        clearCalendarEvents();

        try {
          await resetConversation();
        } catch (error) {
          console.error('Reset conversation after clearing calendar error:', error);
        }

        setActivePanel('calendar');
        confirmationContent = 'Cleared all local calendar events.';
        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'show-today') {
        setCalendarView('today');
        setActivePanel('calendar');
      } else if (commandMatch.command === 'show-tomorrow') {
        setCalendarView('tomorrow');
        setActivePanel('calendar');
      } else if (commandMatch.command === 'close-calendar') {
        closePanel();
      } else if (commandMatch.command === 'open-search') {
        setActivePanel('search');
      } else if (commandMatch.command === 'run-search') {
        const preparedSearchQuery = commandMatch.payload?.trim() ?? '';
        setActivePanel('search');

        if (preparedSearchQuery) {
          const searchResponse = await runWebSearch(preparedSearchQuery);

          if (searchResponse?.ok) {
            const sourceCount = searchResponse.sources?.length ?? 0;
            const stepCount = searchResponse.steps?.length ?? 0;
            const sourceText = sourceCount > 0
              ? ` ${sourceCount} source${sourceCount === 1 ? '' : 's'} added.`
              : '';
            const stepText = stepCount > 0
              ? ` ${stepCount} action step${stepCount === 1 ? '' : 's'} included.`
              : '';
            confirmationContent = `Search complete. I put the full result in the Search panel.${stepText}${sourceText}`;
          } else {
            confirmationContent = searchResponse?.message || searchError || 'Web search failed.';
          }
        } else {
          confirmationContent = 'Opening search.';
        }

        shouldSpeakConfirmation = voiceOutputEnabled;
      } else if (commandMatch.command === 'clear-search') {
        clearSearchState();
        setActivePanel('search');
        confirmationContent = 'Search cleared.';
      } else if (commandMatch.command === 'close-search') {
        closePanel();
      } else if (commandMatch.command === 'close-generic') {
        if (activePanel !== 'none') {
          closePanel();
        }
      } else if (commandMatch.command === 'voice-output-on') {
        setVoiceOutput(true);
        shouldSpeakConfirmation = true;
      } else if (commandMatch.command === 'voice-output-off') {
        setVoiceOutput(false);
        shouldSpeakConfirmation = false;
      } else if (commandMatch.command === 'voice-output-toggle') {
        const nextEnabled = !voiceOutputEnabled;
        setVoiceOutput(nextEnabled);
        confirmationContent = nextEnabled ? 'Voice output enabled.' : 'Voice output muted.';
        shouldSpeakConfirmation = nextEnabled;
      } else if (commandMatch.command === 'voice-slower') {
        confirmationSpeechRate = adjustSpeechRate(speechRate - 0.15);
        confirmationContent = `Speaking slower. Voice speed is now ${confirmationSpeechRate.toFixed(2)}×.`;
      } else if (commandMatch.command === 'voice-faster') {
        confirmationSpeechRate = adjustSpeechRate(speechRate + 0.15);
        confirmationContent = `Speaking faster. Voice speed is now ${confirmationSpeechRate.toFixed(2)}×.`;
      } else if (commandMatch.command === 'voice-normal') {
        confirmationSpeechRate = adjustSpeechRate(1);
        confirmationContent = 'Voice speed reset to normal.';
      } else if (commandMatch.command === 'stop-speaking') {
        stopCurrentSpeech();
        setOrbState('idle');
        shouldSpeakConfirmation = false;
      } else if (commandMatch.command === 'cancel-action') {
        stopCurrentSpeech();
        cancelActiveResponse();
        finishListening();
        setShowThinkingBubble(false);
        setOrbState('idle');
        confirmationContent = 'Cancelled.';
        shouldSpeakConfirmation = false;
      } else if (commandMatch.command === 'what-did-you-hear') {
        if (previousLastHeardTranscript) {
          confirmationContent = `I last heard: "${previousLastHeardTranscript}". Normalized as: "${previousLastNormalizedTranscript || previousLastHeardTranscript}". Last local command: ${previousLastLocalCommand}.`;
        } else {
          confirmationContent = 'I have not heard a voice transcript yet.';
        }
      } else if (commandMatch.command === 'clear-chat') {
        replaceMessages = true;
      } else if (commandMatch.command === 'end-chat') {
        await handleEndChat();
        return;
      }

      speechConfirmationContent = getBriefToolSpeech(commandMatch.command, confirmationContent);
      
      const confirmationMsg: Message = {
        id: `a-${now}`,
        role: 'assistant',
        variant: 'tool',
        content: confirmationContent,
        timestamp: new Date(),
      };
      
      if (replaceMessages) {
        setMessages([userMsg, confirmationMsg]);
      } else {
        setMessages((prev) => [...prev, userMsg, confirmationMsg]);
      }

      if (commandMatch.command !== 'clear-done-tasks') {
        addRecentAction(getCommandActionLabel(commandMatch.command), confirmationContent);
      }
      pushResultToast(getResultToastForCommand(commandMatch.command, confirmationContent));

      speakAssistantText(speechConfirmationContent, {
        enabled: shouldSpeakConfirmation,
        rate: confirmationSpeechRate,
      });

      return;
    }

    if (displayText) {
      finishListening();
      setShowThinkingBubble(false);
      setLastInputRoute('Interpreter command failed to execute');
      setLastLocalCommand('Interpreter unmatched command');
      setLastInterpreterReason('The interpreter returned a frontend command, but the frontend parser could not execute it.');

      if (!chatActive) setChatActive(true);

      const now = Date.now();
      const userMsg: Message = {
        id: `u-${now}`,
        role: 'user',
        content: visibleUserText,
        timestamp: new Date(),
      };
      const assistantMsg: Message = {
        id: `a-${now}`,
        role: 'assistant',
        content: 'I understood that as a command, but I could not match it to a local action.',
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      speakAssistantText(assistantMsg.content);
      return;
    }

    try {
      const interpretedCommand = await interpretCommandIntent(trimmed);

      if (
        interpretedCommand.intent === 'command' &&
        interpretedCommand.frontendCommand &&
        interpretedCommand.confidence >= COMMAND_INTERPRETER_EXECUTE_THRESHOLD &&
        isDestructiveInterpreterCommand(interpretedCommand.frontendCommand)
      ) {
        finishListening();
        setShowThinkingBubble(false);
        setPendingInterpreterCommand({
          originalText: visibleUserText,
          frontendCommand: interpretedCommand.frontendCommand,
          action: interpretedCommand.action,
          confidence: interpretedCommand.confidence,
          reason: interpretedCommand.reason || 'Interpreter mapped fuzzy input to a destructive frontend command.',
        });
        setLastInputRoute('Fuzzy interpreter needs safety confirmation');
        setLastLocalCommand('Pending destructive command');
        setLastInterpreterAction(interpretedCommand.action);
        setLastInterpreterFrontendCommand(interpretedCommand.frontendCommand);
        setLastInterpreterConfidence(interpretedCommand.confidence);
        setLastInterpreterReason(interpretedCommand.reason || 'Interpreter mapped fuzzy input to a destructive frontend command.');

        if (!chatActive) setChatActive(true);

        const now = Date.now();
        const userMsg: Message = {
          id: `u-${now}`,
          role: 'user',
          content: visibleUserText,
          timestamp: new Date(),
        };
        const assistantMsg: Message = {
          id: `a-${now}`,
          role: 'assistant',
          content: `I interpreted that as: ${interpretedCommand.frontendCommand}. This changes or deletes local data. Say "confirm" to run it, or "cancel" to stop.`,
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, userMsg, assistantMsg]);
        speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
        return;
      }

      if (
        interpretedCommand.intent === 'command' &&
        interpretedCommand.frontendCommand &&
        interpretedCommand.confidence >= COMMAND_INTERPRETER_EXECUTE_THRESHOLD
      ) {
        setLastInputRoute('Fuzzy interpreter command');
        setLastInterpreterAction(interpretedCommand.action);
        setLastInterpreterFrontendCommand(interpretedCommand.frontendCommand);
        setLastInterpreterConfidence(interpretedCommand.confidence);
        setLastInterpreterReason(interpretedCommand.reason || 'Interpreter mapped fuzzy input to a frontend command.');
        return handleSend(interpretedCommand.frontendCommand, visibleUserText, 'interpreter');
      }

      if (
        interpretedCommand.intent === 'command' &&
        interpretedCommand.frontendCommand &&
        interpretedCommand.confidence >= COMMAND_INTERPRETER_CLARIFY_THRESHOLD
      ) {
        finishListening();
        setShowThinkingBubble(false);
        setLastInputRoute('Interpreter needs confirmation');
        setLastLocalCommand('Interpreter clarification');
        setLastInterpreterAction(interpretedCommand.action);
        setLastInterpreterFrontendCommand(interpretedCommand.frontendCommand);
        setLastInterpreterConfidence(interpretedCommand.confidence);
        setLastInterpreterReason(interpretedCommand.reason || 'Interpreter confidence was below the automatic execution threshold.');

        const destructiveCommand = isDestructiveInterpreterCommand(interpretedCommand.frontendCommand);
        if (destructiveCommand) {
          setPendingInterpreterCommand({
            originalText: visibleUserText,
            frontendCommand: interpretedCommand.frontendCommand,
            action: interpretedCommand.action,
            confidence: interpretedCommand.confidence,
            reason: interpretedCommand.reason || 'Interpreter confidence was below the automatic execution threshold.',
          });
        }

        if (!chatActive) setChatActive(true);

        const now = Date.now();
        const userMsg: Message = {
          id: `u-${now}`,
          role: 'user',
          content: visibleUserText,
          timestamp: new Date(),
        };
        const assistantMsg: Message = {
          id: `a-${now}`,
          role: 'assistant',
          content: destructiveCommand
            ? `I think that may mean: ${interpretedCommand.frontendCommand}. This changes or deletes local data. Say "confirm" to run it, or "cancel" to stop.`
            : `I think that may be a command, but I am not certain. Try saying: "${interpretedCommand.frontendCommand}".`,
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, userMsg, assistantMsg]);
        speakAssistantText(assistantMsg.content);
        return;
      }

      setPendingInterpreterCommand(null);
      setLastInputRoute('Normal chat');
      setLastLocalCommand('No local command');
      setLastInterpreterAction(interpretedCommand.action || 'none');
      setLastInterpreterFrontendCommand(interpretedCommand.frontendCommand || 'None');
      setLastInterpreterConfidence(interpretedCommand.confidence);
      setLastInterpreterReason(interpretedCommand.reason || 'Interpreter classified the input as normal chat.');
    } catch (error) {
      console.warn('Command interpreter unavailable, falling back to chat:', error);
      setPendingInterpreterCommand(null);
      setLastInputRoute('Interpreter unavailable → normal chat');
      setLastLocalCommand('No local command');
      setLastInterpreterAction('Error');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(null);
      setLastInterpreterReason(error instanceof Error ? error.message : 'Interpreter request failed.');
    }

    if (!chatActive) setChatActive(true);

    const now = Date.now();
    const assistantId = `a-${now}`;

    const userMsg: Message = {
      id: `u-${now}`,
      role: 'user',
      content: visibleUserText,
      timestamp: new Date(),
    };

    cancelActiveResponse();

    setMessages((prev) => [...prev, userMsg]);
    setOrbState('thinking');
    setShowThinkingBubble(true);

    const responseToken = responseTokenRef.current + 1;
    responseTokenRef.current = responseToken;
    const abortController = new AbortController();
    activeStreamAbortRef.current = abortController;

    let assistantReply = '';

    const upsertAssistantMessage = (content: string, mode: 'replace' | 'append' = 'append') => {
      setMessages((prev) => {
        const existingMessage = prev.find((msg) => msg.id === assistantId);

        if (existingMessage) {
          return prev.map((msg) =>
            msg.id === assistantId
              ? {
                  ...msg,
                  content: mode === 'replace' ? content : msg.content + content,
                }
              : msg
          );
        }

        return [
          ...prev,
          {
            id: assistantId,
            role: 'assistant',
            content,
            timestamp: new Date(),
          },
        ];
      });
    };

    try {
      await streamChatMessage(trimmed, {
        onStart: () => {
          if (responseTokenRef.current !== responseToken) return;
          setOrbState('thinking');
        },

        onChunk: (chunk) => {
          if (responseTokenRef.current !== responseToken || !chunk) return;

          setShowThinkingBubble(false);
          assistantReply += chunk;
          upsertAssistantMessage(chunk, 'append');
        },

        onDone: () => {
          if (responseTokenRef.current !== responseToken) return;
          setShowThinkingBubble(false);
          activeStreamAbortRef.current = null;
          speakAssistantText(assistantReply);
        },

        onError: (message) => {
          if (responseTokenRef.current !== responseToken) return;
          setShowThinkingBubble(false);
          activeStreamAbortRef.current = null;
          setOrbState('error');
          upsertAssistantMessage(message, 'replace');

          window.setTimeout(() => {
            if (responseTokenRef.current === responseToken) {
              setOrbState('idle');
            }
          }, 2000);
        },
      }, { signal: abortController.signal });
    } catch (error) {
      if (abortController.signal.aborted || responseTokenRef.current !== responseToken) {
        return;
      }

      console.error('QMeet streaming error:', error);

      activeStreamAbortRef.current = null;
      setShowThinkingBubble(false);
      setOrbState('error');
      upsertAssistantMessage(
        'Streaming connection failed. Make sure the QMeet backend is running on http://localhost:8000.',
        'replace'
      );

      window.setTimeout(() => {
        if (responseTokenRef.current === responseToken) {
          setOrbState('idle');
        }
      }, 2000);
    }
  }, [chatActive, activePanel, calendarView, calendarEvents, voiceOutputEnabled, speechRate, lastHeardTranscript, lastNormalizedTranscript, lastLocalCommand, pendingInterpreterCommand, handleEndChat, finishListening, closePanel, goHome, stopCurrentSpeech, cancelActiveResponse, speakAssistantText, setVoiceOutput, adjustSpeechRate, saveNote, getNotesReadout, deleteLastNote, clearNotes, saveMemoryTask, markMemoryTaskDone, clearCompletedTasks, getMemoryReadout, saveCalendarEvent, getCalendarReadout, deleteLastCalendarEvent, deleteCalendarEventByCriteria, findCalendarEventForDeletion, getNextCalendarEventForDeletion, getNextCalendarEventForChange, editLastCalendarEvent, clearCalendarEvents, refreshGoogleCalendar, runWebSearch, clearSearchState, searchError, pushResultToast, addRecentAction, googleCalendarStatus?.connected, googleCalendarStatus?.writeEnabled, googleCalendarEvents]);

  const handleOrbClick = useCallback(() => {
    // If QMeet is actively generating/streaming, tapping the orb should cancel
    // that response instead of starting a new listening session. Checking the
    // active stream ref covers the period after the first text chunk appears,
    // when the thinking bubble is hidden but the response is still in progress.
    if (activeStreamAbortRef.current || orbState === 'thinking') {
      cancelActiveResponse();
      setChatActive(true);
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          variant: 'tool',
          content: 'Cancelled.',
          timestamp: new Date(),
        },
      ]);
      return;
    }

    // If QMeet is speaking, tapping the orb should stop the speech and return
    // to idle. It should not immediately start listening from the same tap.
    if (orbState === 'speaking') {
      stopCurrentSpeech();
      setOrbState('idle');
      return;
    }

    if (orbState !== 'idle') {
      return;
    }

    if (!isSpeechRecognitionSupported()) {
      setChatActive(true);
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: 'Voice input is not supported in this browser. Please use the text input instead.',
          timestamp: new Date(),
        },
      ]);
      return;
    }

    setOrbState('listening');
    transcriptSentRef.current = false;
    setListeningTranscript('');

    const SpeechRecognitionClass = getSpeechRecognition();

    if (!SpeechRecognitionClass) {
      setOrbState('idle');
      return;
    }

    const recognition = new SpeechRecognitionClass();
    recognitionRef.current = recognition;

    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    
    recognition.onstart = () => {
      setOrbState('listening');

      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
      }

      listeningTimeoutRef.current = setTimeout(() => {
        if (recognitionRef.current) {
          recognitionRef.current.abort();
        }

        if (!transcriptSentRef.current) {
          setListeningTranscript('')
          setChatActive(true);
          setOrbState('idle');
          setMessages((prev) => [
            ...prev,
            {
              id: `a-${Date.now()}`,
              role: 'assistant',
              content: 'I did not catch that. Tap the orb and try again.',
              timestamp: new Date(),
            },
          ]);
        }
      }, 8000);
    };
    
    recognition.onresult = (event: any) => {
      let interimTranscript = '';
      let finalTranscript = '';
    
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0]?.transcript ?? '';
    
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }
    
      const previewText = (finalTranscript || interimTranscript).trim();
      if (previewText) {
        setListeningTranscript(previewText);
      }

      if (finalTranscript.trim()) {
        if (transcriptSentRef.current) return;
        transcriptSentRef.current = true;

        if (listeningTimeoutRef.current) {
          clearTimeout(listeningTimeoutRef.current);
        }

        const rawTranscript = finalTranscript.trim();
        const normalizedTranscript = normalizeSpokenQMeet(rawTranscript);

        setLastHeardTranscript(rawTranscript);
        setLastNormalizedTranscript(normalizedTranscript);

        // Speech recognition has finished capturing the user's phrase at this point.
        // Clear the visible listening preview immediately so the UI does not keep
        // showing "Heard: Listening..." while QMeet is actually parsing the command.
        setListeningTranscript('');
        setOrbState('thinking');

        handleSend(normalizedTranscript);
      }
    };
    
    recognition.onerror = (event: any) => {
      const errorCode = event.error;

      // Suppress error if we intentionally aborted speech recognition
      if (suppressNextSpeechErrorRef.current || errorCode === 'aborted') {
        suppressNextSpeechErrorRef.current = false;
        if (listeningTimeoutRef.current) {
          clearTimeout(listeningTimeoutRef.current);
        }
        setListeningTranscript('');
        return;
      }

      let errorMessage = 'Speech recognition failed. Please try again.';
    
      if (errorCode === 'no-speech') {
        errorMessage = 'No speech detected. Please speak clearly and try again.';
      } else if (errorCode === 'audio-capture') {
        errorMessage = 'Microphone not found or permission denied.';
      } else if (errorCode === 'not-allowed') {
        errorMessage = 'Microphone permission denied. Please enable it in your browser settings.';
      } else if (errorCode === 'network') {
        errorMessage = 'Network error during speech recognition.';
      }

      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
      }
    
      setListeningTranscript('');
      setChatActive(true);
      setOrbState('error');
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: errorMessage,
          timestamp: new Date(),
        },
      ]);
    
      setTimeout(() => {
        setOrbState('idle');
      }, 2000);
    };
    
    recognition.onend = () => {
      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
        listeningTimeoutRef.current = null;
      }

      if (!transcriptSentRef.current) {
        setListeningTranscript('');
        setOrbState('idle');
      } else {
        window.setTimeout(() => {
          setListeningTranscript('');
        }, 300);
      }

      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
    };
    
    try {
      recognition.start();
    } catch (error) {
      console.error('Speech recognition start error:', error);
      
      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
      }
      
      setListeningTranscript('');
      setOrbState('idle');
    }
  }, [orbState, handleSend, stopCurrentSpeech, cancelActiveResponse]);

  const statusSnapshot = new Date();
    const statusDateLabel = statusSnapshot.toLocaleDateString([], {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
    const statusTimeLabel = statusSnapshot.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });
    const statusNotesCount = notes.length;
    const statusOpenTasksCount = memoryTasks.filter((task) => !task.completedAt).length;
    const statusCompletedTasksCount = memoryTasks.filter((task) => task.completedAt).length;
    const statusTodayEventsCount = calendarEvents.filter((event) => event.dateKey === getDateKeyForCalendarView('today')).length;
    const statusTomorrowEventsCount = calendarEvents.filter((event) => event.dateKey === getDateKeyForCalendarView('tomorrow')).length;
    const statusGoogleEventsCount = googleCalendarEvents.length;
    const statusGoogleCalendarLabel = googleCalendarStatus?.connected
      ? googleCalendarStatus?.writeEnabled ? 'Connected · Write' : 'Connected · Read only'
      : googleCalendarStatus?.configured
        ? 'Needs auth'
        : 'Not configured';
    const trimmedSearchQuery = searchQuery.trim();
    const searchStatusLabel = searchLoading
      ? 'Searching'
      : searchResult
        ? 'Results'
        : trimmedSearchQuery
          ? 'Ready'
          : 'Empty';
    const searchStatusMeta = searchResult
      ? `${searchResult.sources.length} source${searchResult.sources.length === 1 ? '' : 's'} · ${searchResult.provider || 'web'}`
      : searchError || trimmedSearchQuery || 'No query';
    const voiceInputSupported = isSpeechRecognitionSupported();
    const activePanelLabel = getPanelLabel(activePanel);
    const interpreterConfidenceLabel = lastInterpreterConfidence === null
      ? '—'
      : `${Math.round(lastInterpreterConfidence * 100)}%`;
    const interpreterReasonLabel = lastInterpreterReason.length > 82
      ? `${lastInterpreterReason.slice(0, 79)}...`
      : lastInterpreterReason;
    const pendingInterpreterLabel = pendingInterpreterCommand
      ? pendingInterpreterCommand.frontendCommand
      : 'None';
    const assistantActivity = getAssistantActivity({
      orbState,
      activePanel,
      chatActive,
      searchLoading,
      googleCalendarLoading,
      pendingCommand: pendingInterpreterCommand,
      searchQuery: trimmedSearchQuery,
      hasSearchResult: Boolean(searchResult),
      notesCount: statusNotesCount,
      calendarCount: calendarEvents.length,
      taskCount: statusOpenTasksCount,
    });

  return (
    <div className="agent-screen">
      <TopStatusBar orbState={orbState} chatActive={chatActive} onEnd={handleEndChat} backendStatus={backendStatus} activity={assistantActivity} />

      <div className="agent-body">
        {/* Orb area: full width when idle, 38% when chat active */}
        <div
        ref={orbAreaRef}
          className={`orb-area${chatActive ? ' orb-area-active' : ''}`}
          onClick={handleOrbClick}
          role="button"
          tabIndex={0}
          aria-label="QMeet orb — tap to activate"
        >
          <Orb state={orbState} active={chatActive} activity={assistantActivity} />

          {!chatActive && (
            <div className="idle-hint">
              <span>{orbState === 'listening' ? 'Listening…' : 'Ask QMeet anything…'}</span>
            </div>
          )}

          {orbState === 'listening' && (
            <div className="listening-preview">
              <div className="listening-preview-label">Heard:</div>
              <div className="listening-preview-text">
                {listeningTranscript || 'Listening…'}
              </div>
            </div>
          )}
        </div>

        {/* Chat area: hidden when idle, 62% when active */}
        <div className={`chat-area ${chatActive ? 'chat-area-visible' : 'chat-area-hidden'}`}>
          <ChatPanel
            messages={messages}
            orbState={showThinkingBubble ? orbState : orbState === 'thinking' ? 'idle' : orbState}
            activity={assistantActivity}
          />
          <PromptBar onSend={handleSend} disabled={false} />
        </div>
      </div>

      {resultToasts.length > 0 && (
        <div className="result-toast-stack" aria-live="polite" aria-label="QMeet action updates">
          {resultToasts.map((toast) => (
            <div key={toast.id} className={`result-toast result-toast-${toast.kind}`}>
              <div className="result-toast-glow" />
              <div className="result-toast-icon">
                {toast.kind === 'search' ? '⌕' : toast.kind === 'calendar' ? 'Cal' : toast.kind === 'notes' ? 'Note' : toast.kind === 'error' ? '!' : toast.kind === 'warning' ? '!' : '✓'}
              </div>
              <div className="result-toast-copy">
                <div className="result-toast-title">{toast.title}</div>
                <div className="result-toast-detail">{toast.detail}</div>
              </div>
              <button
                className="result-toast-dismiss"
                type="button"
                aria-label="Dismiss update"
                onClick={() => dismissResultToast(toast.id)}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Panel Overlays */}
      {activePanel === 'menu' && (
        <div className="panel-overlay">
          <div className="panel-content panel-content-launcher">
            <div className="panel-header">Menu</div>
            <div className="panel-body">
              <div className="launcher-intro">
                <p className="panel-section-text">
                  Choose a local QMeet tool by touch, or use the same commands by voice.
                </p>
              </div>

              <div className="launcher-grid" aria-label="QMeet app launcher">
                <button className="launcher-card" onClick={() => openLauncherPanel('notes')}>
                  <span className="launcher-title">Notes</span>
                  <span className="launcher-description">Write and review local notes.</span>
                  <span className="launcher-command">Say: open notes</span>
                </button>

                <button className="launcher-card" onClick={() => openLauncherPanel('memory')}>
                  <span className="launcher-title">Memory</span>
                  <span className="launcher-description">Review tasks and recent work.</span>
                  <span className="launcher-command">Say: what was I working on</span>
                </button>

                <button className="launcher-card" onClick={() => openLauncherPanel('calendar')}>
                  <span className="launcher-title">Calendar</span>
                  <span className="launcher-description">View today or tomorrow placeholders.</span>
                  <span className="launcher-command">Say: open calendar</span>
                </button>

                <button className="launcher-card" onClick={() => openLauncherPanel('search')}>
                  <span className="launcher-title">Search</span>
                  <span className="launcher-description">Open the local search/browser shell.</span>
                  <span className="launcher-command">Say: open search</span>
                </button>

                <button className="launcher-card" onClick={() => openLauncherPanel('settings')}>
                  <span className="launcher-title">Settings</span>
                  <span className="launcher-description">Adjust voice output and interface options.</span>
                  <span className="launcher-command">Say: show settings</span>
                </button>

                <button className="launcher-card" onClick={() => openLauncherPanel('status')}>
                  <span className="launcher-title">Status</span>
                  <span className="launcher-description">Check orb, backend, and voice state.</span>
                  <span className="launcher-command">Say: show status</span>
                </button>
              </div>

              <div className="panel-section launcher-help-section">
                <div className="panel-section-title">Quick Commands</div>
                <p className="panel-section-text">
                  Try "what can you do", "note that buy milk", "remember to test the Pi as a task", "what was I working on", "search for kiosk mode", "add event tomorrow at 3 called meeting", "what's on my calendar", "what did you hear", "cancel", "go home", or "mute voice".
                </p>
              </div>

              <button className="close-panel-btn" onClick={closePanel}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {activePanel === 'settings' && (
        <div className="panel-overlay">
          <div className="panel-content">
            <div className="panel-header">Settings</div>
            <div className="panel-body">
              <div className="panel-section">
                <div className="panel-section-title">Voice Settings</div>
                <p className="panel-section-text">
                  Microphone: Enabled · Language: English (US) · Recognition: Online · Voice preferences persist across reloads
                </p>
                <div className="settings-control-row">
                  <span className="settings-control-label">Spoken responses</span>
                  <button
                    className={`panel-action-btn ${voiceOutputEnabled ? 'panel-action-btn-active' : ''}`}
                    onClick={() => {
                      const nextEnabled = !voiceOutputEnabled;
                      setVoiceOutput(nextEnabled);
                      if (nextEnabled) {
                        speakAssistantText('Voice output enabled.', { enabled: true });
                      }
                    }}
                  >
                    {voiceOutputEnabled ? 'On' : 'Muted'}
                  </button>
                </div>
                <div className="settings-control-row">
                  <span className="settings-control-label">Voice speed</span>
                  <span className="settings-control-value">{speechRate.toFixed(2)}×</span>
                </div>
                <div className="panel-action-row">
                  <button
                    className="panel-action-btn"
                    onClick={() => {
                      const nextRate = adjustSpeechRate(speechRate - 0.15);
                      speakAssistantText(`Voice speed is now ${nextRate.toFixed(2)}×.`, { rate: nextRate });
                    }}
                  >
                    Slower
                  </button>
                  <button
                    className="panel-action-btn"
                    onClick={() => {
                      const nextRate = adjustSpeechRate(1);
                      speakAssistantText('Voice speed reset to normal.', { rate: nextRate });
                    }}
                  >
                    Normal
                  </button>
                  <button
                    className="panel-action-btn"
                    onClick={() => {
                      const nextRate = adjustSpeechRate(speechRate + 0.15);
                      speakAssistantText(`Voice speed is now ${nextRate.toFixed(2)}×.`, { rate: nextRate });
                    }}
                  >
                    Faster
                  </button>
                </div>
              </div>
              <div className="panel-section">
                <div className="panel-section-title">Display</div>
                <p className="panel-section-text">
                  Theme: Dark · Resolution: 1024×600 · Interface: Optimized
                </p>
              </div>
              <div className="panel-section">
                <div className="panel-section-title">Backend</div>
                <p className="panel-section-text">
                  Status: {backendStatus?.ok ? 'Connected' : 'Disconnected'} · Provider: {backendStatus?.provider || 'Unknown'}
                </p>
              </div>
              <button className="close-panel-btn" onClick={closePanel}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
      
      {activePanel === 'status' && (
        <div className="panel-overlay">
          <div className="panel-content panel-content-status">
            <div className="panel-header">System Status</div>
            <div className="panel-body status-panel-body">
              <div className="status-hero">
                <div>
                  <div className="status-kicker">QMeet Prototype</div>
                  <div className="status-title">Local tablet assistant dashboard</div>
                </div>
                <div className={`status-health-chip ${backendStatus?.ok ? 'status-health-good' : 'status-health-warn'}`}>
                  {backendStatus?.ok ? 'Online' : 'Offline'}
                </div>
              </div>

              <div className="status-grid">
                <div className="status-card">
                  <div className="status-card-title">Orb</div>
                  <div className="status-card-value">{orbState.charAt(0).toUpperCase() + orbState.slice(1)}</div>
                  <div className="status-card-meta">Current interaction state</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Active Panel</div>
                  <div className="status-card-value">{activePanelLabel}</div>
                  <div className="status-card-meta">Current UI surface</div>
                </div>

                <div className={`status-card ${backendStatus?.ok ? 'status-card-good' : 'status-card-warn'}`}>
                  <div className="status-card-title">Backend</div>
                  <div className="status-card-value">{backendStatus?.ok ? 'Connected' : 'Disconnected'}</div>
                  <div className="status-card-meta">FastAPI agent service</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Provider</div>
                  <div className="status-card-value">{backendStatus?.provider || 'Unknown'}</div>
                  <div className="status-card-meta">Model: {backendStatus?.model || 'Unknown'}</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Voice Input</div>
                  <div className="status-card-value">{voiceInputSupported ? 'Supported' : 'Unavailable'}</div>
                  <div className="status-card-meta">Browser speech recognition</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Last Heard</div>
                  <div className="status-card-value">{lastHeardTranscript || 'None'}</div>
                  <div className="status-card-meta">{lastNormalizedTranscript ? `Normalized: ${lastNormalizedTranscript}` : 'Last voice transcript'}</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Last Command</div>
                  <div className="status-card-value">{lastLocalCommand}</div>
                  <div className="status-card-meta">Last local command matched</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Input Route</div>
                  <div className="status-card-value">{lastInputRoute}</div>
                  <div className="status-card-meta">Exact parser, interpreter, or chat</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Interpreter</div>
                  <div className="status-card-value">{lastInterpreterAction}</div>
                  <div className="status-card-meta">Confidence: {interpreterConfidenceLabel}</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Mapped Command</div>
                  <div className="status-card-value">{lastInterpreterFrontendCommand}</div>
                  <div className="status-card-meta">{interpreterReasonLabel}</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Pending Confirm</div>
                  <div className="status-card-value">{pendingInterpreterLabel}</div>
                  <div className="status-card-meta">Destructive fuzzy commands wait for confirm</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Voice Output</div>
                  <div className="status-card-value">{voiceOutputEnabled ? 'On' : 'Muted'}</div>
                  <div className="status-card-meta">Speed: {speechRate.toFixed(2)}×</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Chat</div>
                  <div className="status-card-value">{chatActive ? 'Active' : 'Idle'}</div>
                  <div className="status-card-meta">Messages: {messages.length}</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Notes</div>
                  <div className="status-card-value">{statusNotesCount}</div>
                  <div className="status-card-meta">Saved locally</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Open Tasks</div>
                  <div className="status-card-value">{statusOpenTasksCount}</div>
                  <div className="status-card-meta">{statusCompletedTasksCount} completed · {memorySyncState}</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Calendar</div>
                  <div className="status-card-value">{calendarEvents.length}</div>
                  <div className="status-card-meta">Local events total</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Today</div>
                  <div className="status-card-value">{statusTodayEventsCount}</div>
                  <div className="status-card-meta">Events saved for today</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Tomorrow</div>
                  <div className="status-card-value">{statusTomorrowEventsCount}</div>
                  <div className="status-card-meta">Events saved for tomorrow</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Google Calendar</div>
                  <div className="status-card-value">{statusGoogleCalendarLabel}</div>
                  <div className="status-card-meta">{statusGoogleEventsCount} loaded · {googleCalendarLoading ? 'Loading' : 'Idle'}</div>
                </div>

                <div className="status-card">
                  <div className="status-card-title">Search</div>
                  <div className="status-card-value">{searchStatusLabel}</div>
                  <div className="status-card-meta">{searchStatusMeta}</div>
                </div>
              </div>

              <div className="panel-section status-detail-section">
                <div className="panel-section-title">Backend Details</div>
                <div className="status-detail-list">
                  <div className="status-detail-row">
                    <span>OpenAI key</span>
                    <strong>{backendStatus?.hasOpenAIKey ? 'Configured' : 'Missing / Unknown'}</strong>
                  </div>
                  <div className="status-detail-row">
                    <span>Max output tokens</span>
                    <strong>{backendStatus?.maxOutputTokens ?? 'Unknown'}</strong>
                  </div>
                  <div className="status-detail-row">
                    <span>Status refresh</span>
                    <strong>Every 10 seconds</strong>
                  </div>
                </div>
              </div>

              <div className="panel-section status-detail-section">
                <div className="panel-section-title">Interface</div>
                <div className="status-detail-list">
                  <div className="status-detail-row">
                    <span>Date</span>
                    <strong>{statusDateLabel}</strong>
                  </div>
                  <div className="status-detail-row">
                    <span>Time snapshot</span>
                    <strong>{statusTimeLabel}</strong>
                  </div>
                  <div className="status-detail-row">
                    <span>Display target</span>
                    <strong>1024×600</strong>
                  </div>
                </div>
              </div>

              <div className="panel-section status-detail-section">
                <div className="panel-section-title">Local Storage</div>
                <div className="status-detail-list">
                  <div className="status-detail-row">
                    <span>Voice output preference</span>
                    <strong>Saved</strong>
                  </div>
                  <div className="status-detail-row">
                    <span>Voice speed preference</span>
                    <strong>Saved</strong>
                  </div>
                  <div className="status-detail-row">
                    <span>Notes and calendar events</span>
                    <strong>Saved locally</strong>
                  </div>
                </div>
              </div>

              <div className="panel-section">
                <div className="panel-section-title">Supported Status Commands</div>
                <p className="panel-section-text">
                  Say “show status,” “system status,” “diagnostics,” “what did you hear,” “read my notes,” “what was I working on,” “what's on my calendar,” “close status,” or “go home.” This panel also shows whether the last input used the exact parser, fuzzy command interpreter, or normal chat.
                </p>
              </div>

              <button className="close-panel-btn" onClick={closePanel}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}


      {activePanel === 'memory' && (
        <div className="panel-overlay">
          <div className="panel-content memory-panel">
            <div className="panel-header">Memory</div>
            <div className="panel-body memory-panel-body">
              <div className="memory-hero">
                <div>
                  <div className="memory-kicker">Backend Memory</div>
                  <div className="memory-title">Tasks, notes, and work context sync to FastAPI, with browser fallback.</div>
                </div>
                <div className={`memory-chip memory-sync-${memorySyncState}`}>
                  {memorySyncState === 'synced' ? 'Synced' : memorySyncState === 'syncing' ? 'Syncing' : 'Local'}
                </div>
              </div>

              <div className="panel-section memory-sync-section">
                <div className="panel-section-title">Sync Status</div>
                <p className="panel-section-text">{memorySyncMessage}</p>
              </div>


              <div className="panel-section">
                <div className="panel-section-title">Memory Controls</div>
                <p className="panel-section-text">
                  Export a backup, import a saved QMeet memory JSON file, or reset stored memory categories.
                </p>
                <input
                  ref={memoryImportInputRef}
                  type="file"
                  accept="application/json,.json"
                  style={{ display: 'none' }}
                  onChange={handleImportMemoryFile}
                />
                <div className="panel-action-row">
                  <button className="panel-action-btn" type="button" onClick={handleExportMemory}>
                    Export JSON
                  </button>
                  <button className="panel-action-btn" type="button" onClick={() => memoryImportInputRef.current?.click()}>
                    Import JSON
                  </button>
                  <button className="panel-action-btn panel-action-btn-danger" type="button" onClick={handleClearAllMemory}>
                    Clear All
                  </button>
                </div>
                <div className="panel-action-row">
                  <button className="panel-action-btn panel-action-btn-danger" type="button" onClick={handleResetTasksOnly}>
                    Reset Tasks
                  </button>
                  <button className="panel-action-btn panel-action-btn-danger" type="button" onClick={handleResetNotesOnly}>
                    Reset Notes
                  </button>
                  <button className="panel-action-btn panel-action-btn-danger" type="button" onClick={handleResetRecentContextOnly}>
                    Reset Context
                  </button>
                </div>
              </div>

              <div className="panel-section memory-input-section">
                <div className="panel-section-title">New Task</div>
                <div className="memory-input-row">
                  <input
                    className="memory-task-input"
                    value={memoryTaskDraft}
                    onChange={(event) => setMemoryTaskDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && memoryTaskDraft.trim()) {
                        handleSaveMemoryTaskDraft();
                      }
                    }}
                    placeholder="Add a task..."
                  />
                  <button
                    className="panel-action-btn"
                    type="button"
                    disabled={!memoryTaskDraft.trim()}
                    onClick={handleSaveMemoryTaskDraft}
                  >
                    Save
                  </button>
                </div>
              </div>

              <div className="panel-section">
                <div className="panel-section-title">Open Tasks</div>
                {memoryTasks.filter((task) => !task.completedAt).length === 0 ? (
                  <p className="panel-section-text">No open tasks. Say “remember to test the Pi as a task,” or type one above.</p>
                ) : (
                  <div className="memory-list">
                    {memoryTasks.filter((task) => !task.completedAt).map((task) => (
                      <div className="memory-task-item" key={task.id}>
                        <div className="memory-task-copy">
                          <div className="memory-task-title">{task.title}</div>
                          <div className="memory-task-meta">Saved {formatMemoryTime(task.createdAt)}</div>
                        </div>
                        <div className="memory-task-actions">
                          <button
                            className="memory-task-done-btn"
                            type="button"
                            onClick={() => {
                              const completedTask = markMemoryTaskDoneById(task.id);
                              if (completedTask) {
                                addRecentAction('Completed task', completedTask.title);
                                pushResultToast({ kind: 'success', title: 'Task complete', detail: completedTask.title });
                              }
                            }}
                          >
                            Done
                          </button>
                          <button
                            className="memory-task-delete-btn"
                            type="button"
                            onClick={() => {
                              const deletedTask = deleteMemoryTask(task.id);
                              if (deletedTask) {
                                pushResultToast({ kind: 'warning', title: 'Task deleted', detail: deletedTask.title });
                              }
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {memoryTasks.some((task) => task.completedAt) && (
                <div className="panel-section">
                  <div className="panel-section-title">Completed Tasks</div>
                  <div className="memory-list">
                    {memoryTasks.filter((task) => task.completedAt).map((task) => (
                      <div className="memory-action-item memory-completed-task" key={task.id}>
                        <div className="memory-task-copy">
                          <div className="memory-action-title">{task.title}</div>
                          <div className="memory-task-meta">Done {task.completedAt ? formatMemoryTime(task.completedAt) : 'recently'}</div>
                        </div>
                        <div className="memory-task-actions">
                          <button
                            className="memory-task-reopen-btn"
                            type="button"
                            onClick={() => {
                              const reopenedTask = reopenMemoryTask(task.id);
                              if (reopenedTask) {
                                pushResultToast({ kind: 'info', title: 'Task reopened', detail: reopenedTask.title });
                              }
                            }}
                          >
                            Reopen
                          </button>
                          <button
                            className="memory-task-delete-btn"
                            type="button"
                            onClick={() => {
                              const deletedTask = deleteMemoryTask(task.id);
                              if (deletedTask) {
                                pushResultToast({ kind: 'warning', title: 'Task deleted', detail: deletedTask.title });
                              }
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="panel-action-row">
                    <button
                      className="panel-action-btn panel-action-btn-danger"
                      type="button"
                      onClick={() => {
                        const removedCount = clearCompletedTasks();
                        pushResultToast({
                          kind: 'warning',
                          title: 'Completed tasks cleared',
                          detail: removedCount > 0 ? `${removedCount} removed.` : 'No completed tasks to clear.',
                        });
                      }}
                    >
                      Clear Done
                    </button>
                  </div>
                </div>
              )}

              <div className="panel-section">
                <div className="panel-section-title">Supported Commands</div>
                <p className="panel-section-text">
                  Say “what was I working on,” “remember to test the Pi as a task,” “mark task done,” “mark test the Pi done,” “clear completed tasks,” or use the task buttons above. Notes and recent actions sync in the background. Use Memory Controls to export, import, or reset stored memory.
                </p>
              </div>

              <button className="close-panel-btn" onClick={closePanel}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {activePanel === 'notes' && (
        <NotesPanel 
          notes={notes}
          onSaveNote={saveNote}
          onDeleteNote={deleteNote}
          onClearNotes={clearNotes}
          onClose={closePanel}
        />
      )}

      {activePanel === 'calendar' && (
        <CalendarPanel
          view={calendarView}
          events={calendarEvents}
          googleEvents={googleCalendarEvents}
          googleStatus={googleCalendarStatus}
          googleLoading={googleCalendarLoading}
          googleError={googleCalendarError}
          onViewChange={setCalendarView}
          onDeleteEvent={deleteCalendarEvent}
          onConnectGoogleCalendar={handleStartGoogleCalendarAuth}
          onRefreshGoogleCalendar={() => refreshGoogleCalendar(calendarView)}
          onResetGoogleCalendar={handleResetGoogleCalendarAuth}
          onClose={closePanel}
        />
      )}

      {activePanel === 'search' && (
        <SearchPanel
          query={searchQuery}
          result={searchResult}
          loading={searchLoading}
          error={searchError}
          onQueryChange={setSearchQuery}
          onRunSearch={runWebSearch}
          onClearSearch={clearSearchState}
          onClose={closePanel}
        />
      )}
    </div>
  );
}
