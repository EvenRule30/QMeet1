import { useState, useCallback, useEffect, useRef } from 'react';
import { Orb } from './components/Orb';
import { TopStatusBar } from './components/TopStatusBar';
import { ChatPanel } from './components/ChatPanel';
import { PromptBar } from './components/PromptBar';
import { NotesPanel } from './components/NotesPanel';
import { CalendarPanel } from './components/CalendarPanel';
import { SearchPanel } from './components/SearchPanel';
import { Message, OrbState, BackendStatus, ActivePanel, Note, CalendarEvent, CalendarBackendStatus, CalendarBackendView } from './types';
import { streamChatMessage, getBackendStatus, resetConversation, interpretCommandIntent, getCalendarStatus, getCalendarEvents, createCalendarEvent, startCalendarAuth, resetCalendarAuth } from "./api";
import { getSpeechRecognition, isSpeechRecognitionSupported } from './speechRecognition';
import { speakText, stopSpeaking } from './speechSynthesis';
import { parseCommand, normalizeSpokenQMeet } from './commands';
import './App.css';


function getPanelLabel(panel: ActivePanel): string {
  switch (panel) {
    case 'menu':
      return 'Menu';
    case 'settings':
      return 'Settings';
    case 'status':
      return 'Status';
    case 'notes':
      return 'Notes';
    case 'calendar':
      return 'Calendar';
    case 'search':
      return 'Search';
    default:
      return 'Home';
  }
}


type CalendarView = 'today' | 'tomorrow';

function getLocalDateKey(offsetDays = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');

  return `${year}-${month}-${day}`;
}

function getDateKeyForCalendarView(view: CalendarView): string {
  return view === 'tomorrow' ? getLocalDateKey(1) : getLocalDateKey(0);
}

function getLegacyUtcDateKeyForCalendarView(view: CalendarView): string {
  const date = new Date();

  if (view === 'tomorrow') {
    date.setDate(date.getDate() + 1);
  }

  return date.toISOString().slice(0, 10);
}

function getAcceptedDateKeysForCalendarView(view: CalendarView): Set<string> {
  return new Set([
    getDateKeyForCalendarView(view),
    getLegacyUtcDateKeyForCalendarView(view),
  ]);
}

function isEventForCalendarView(event: CalendarEvent, view: CalendarView): boolean {
  return getAcceptedDateKeysForCalendarView(view).has(event.dateKey);
}

function getCalendarViewLabel(view: CalendarView): string {
  return view === 'tomorrow' ? 'tomorrow' : 'today';
}

const VOICE_OUTPUT_STORAGE_KEY = 'qmeet-voice-output-enabled';
const SPEECH_RATE_STORAGE_KEY = 'qmeet-speech-rate';
const CALENDAR_EVENTS_STORAGE_KEY = 'qmeet-calendar-events';
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
  'delete last event',
  'clear calendar',
]);

const DESTRUCTIVE_LOCAL_COMMANDS = new Set([
  'clear-chat',
  'end-chat',
  'delete-last-note',
  'clear-notes',
  'delete-last-event',
  'clear-calendar',
]);

const LOCAL_COMMAND_TO_FRONTEND_COMMAND: Record<string, string> = {
  'clear-chat': 'clear chat',
  'end-chat': 'end chat',
  'delete-last-note': 'delete last note',
  'clear-notes': 'clear notes',
  'delete-last-event': 'delete last event',
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
  return DESTRUCTIVE_FRONTEND_COMMANDS.has(normalizePendingDecisionText(frontendCommand));
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

export default function App() {
  const [chatActive, setChatActive] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [messages, setMessages] = useState<Message[]>([]);
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null);
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


  // Fetch and poll backend status
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const status = await getBackendStatus();
        setBackendStatus(status);
      } catch (error) {
        setBackendStatus(null);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);


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

  const deleteCalendarEvent = useCallback((eventId: string) => {
    setCalendarEvents((prev) => prev.filter((event) => event.id !== eventId));
  }, []);

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

  const deleteLastCalendarEvent = useCallback((): CalendarEvent | null => {
    if (calendarEvents.length === 0) return null;

    const deletedEvent = calendarEvents[0];
    setCalendarEvents((prev) => prev.slice(1));
    return deletedEvent;
  }, [calendarEvents]);

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
        .map((event, index) => `${index + 1}. ${event.time}: ${event.title}${event.location ? ` at ${event.location}` : ''}`)
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
    setChatActive(false);
    setMessages([]);

    try {
      await resetConversation();
    } catch (error) {
      console.error('Reset conversation error:', error);
    }
  }, [cancelActiveResponse, finishListening, stopCurrentSpeech]);

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

      if (commandRoute !== 'confirmed' && isDestructiveLocalCommand(commandMatch.command)) {
        const frontendCommand = getFrontendCommandForLocalCommand(commandMatch.command);
        const confirmationPrompt = `I understood that as: ${frontendCommand}. This changes or deletes local data. Say "confirm" to run it, or "cancel" to stop.`;

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
      } else if (commandMatch.command === 'open-calendar') {
        setCalendarView('today');
        setActivePanel('calendar');
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
      } else if (commandMatch.command === 'delete-last-event') {
        const deletedEvent = deleteLastCalendarEvent();
        setActivePanel('calendar');
        confirmationContent = deletedEvent
          ? `Deleted the last event: ${deletedEvent.time}: ${deletedEvent.title}.`
          : 'No calendar events to delete.';
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
        setSearchQuery(preparedSearchQuery);
        setActivePanel('search');
        confirmationContent = preparedSearchQuery
          ? commandMatch.confirmation
          : 'Opening search.';
      } else if (commandMatch.command === 'clear-search') {
        setSearchQuery('');
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
      
      const confirmationMsg: Message = {
        id: `a-${now}`,
        role: 'assistant',
        content: confirmationContent,
        timestamp: new Date(),
      };
      
      if (replaceMessages) {
        setMessages([userMsg, confirmationMsg]);
      } else {
        setMessages((prev) => [...prev, userMsg, confirmationMsg]);
      }

      speakAssistantText(confirmationContent, {
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
  }, [chatActive, activePanel, calendarView, calendarEvents, voiceOutputEnabled, speechRate, lastHeardTranscript, lastNormalizedTranscript, lastLocalCommand, pendingInterpreterCommand, handleEndChat, finishListening, closePanel, goHome, stopCurrentSpeech, cancelActiveResponse, speakAssistantText, setVoiceOutput, adjustSpeechRate, saveNote, getNotesReadout, deleteLastNote, clearNotes, saveCalendarEvent, getCalendarReadout, deleteLastCalendarEvent, clearCalendarEvents, refreshGoogleCalendar, googleCalendarStatus?.connected, googleCalendarStatus?.writeEnabled, googleCalendarEvents]);

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
    const statusTodayEventsCount = calendarEvents.filter((event) => event.dateKey === getDateKeyForCalendarView('today')).length;
    const statusTomorrowEventsCount = calendarEvents.filter((event) => event.dateKey === getDateKeyForCalendarView('tomorrow')).length;
    const statusGoogleEventsCount = googleCalendarEvents.length;
    const statusGoogleCalendarLabel = googleCalendarStatus?.connected
      ? googleCalendarStatus?.writeEnabled ? 'Connected · Write' : 'Connected · Read only'
      : googleCalendarStatus?.configured
        ? 'Needs auth'
        : 'Not configured';
    const trimmedSearchQuery = searchQuery.trim();
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

  return (
    <div className="agent-screen">
      <TopStatusBar orbState={orbState} chatActive={chatActive} onEnd={handleEndChat} backendStatus={backendStatus} />

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
          <Orb state={orbState} active={chatActive} />

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
          />
          <PromptBar onSend={handleSend} disabled={false} />
        </div>
      </div>

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
                  Try "what can you do", "note that buy milk", "search for kiosk mode", "add event tomorrow at 3 called meeting", "what's on my calendar", "what did you hear", "cancel", "go home", or "mute voice".
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
                  <div className="status-card-value">{trimmedSearchQuery ? 'Prepared' : 'Empty'}</div>
                  <div className="status-card-meta">{trimmedSearchQuery || 'No local query'}</div>
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
                  Say “show status,” “system status,” “diagnostics,” “what did you hear,” “read my notes,” “what's on my calendar,” “close status,” or “go home.” This panel also shows whether the last input used the exact parser, fuzzy command interpreter, or normal chat.
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
          onQueryChange={setSearchQuery}
          onClose={closePanel}
        />
      )}
    </div>
  );
}
