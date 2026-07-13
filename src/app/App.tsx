import { useState, useCallback, useRef } from 'react';
import { Orb } from './components/Orb';
import { TopStatusBar } from './components/TopStatusBar';
import { ChatPanel } from './components/ChatPanel';
import { PromptBar } from './components/PromptBar';
import { NotesPanel } from './components/NotesPanel';
import { CalendarPanel } from './components/CalendarPanel';
import { SearchPanel } from './components/SearchPanel';
import { Message, OrbState, ActivePanel, CalendarBackendView } from './types';
import { resetConversation, interpretCommandIntent } from "./api";
import { getSpeechRecognition, isSpeechRecognitionSupported } from './speechRecognition';
import { parseCommand, normalizeSpokenQMeet } from './commands';
import { getAssistantActivity, getPanelLabel } from './lib/activityUtils';
import {
  getCalendarViewLabel,
  getDateKeyForCalendarView,
  isEventForCalendarView,
} from './lib/dateUtils';
import {
  buildCalendarDeleteFrontendCommand,
  buildCalendarEditFrontendCommand,
  describeCalendarDeletePayload,
  describeCalendarEditPayload,
} from './lib/calendarUtils';
import {
  getBriefToolSpeech,
  getResultToastForCommand,
} from './lib/toastUtils';
import {
  formatMemoryTime,
  getCommandActionLabel,
} from './lib/memoryUtils';
import { useBackendStatus } from './hooks/useBackendStatus';
import { useResultToasts } from './hooks/useResultToasts';
import { useMemoryContext } from './hooks/useMemoryContext';
import { useSearchController } from './hooks/useSearchController';
import { useCalendarController } from './hooks/useCalendarController';
import { useSpeechOutput } from './hooks/useSpeechOutput';
import { useChatStreamController } from './hooks/useChatStreamController';
import './App.css';


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



export default function App() {
  const [chatActive, setChatActive] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const backendStatus = useBackendStatus();
  const [activePanel, setActivePanel] = useState<ActivePanel>('none');
  const {
    voiceOutputEnabled,
    speechRate,
    stopCurrentSpeech,
    speakAssistantText,
    setVoiceOutput,
    adjustSpeechRate,
  } = useSpeechOutput({ setOrbState });
  const {
    messages,
    setMessages,
    showThinkingBubble,
    setShowThinkingBubble,
    responseActive,
    cancelActiveResponse,
    sendStreamingChat,
    clearMessages,
  } = useChatStreamController({
    setOrbState,
    setChatActive,
    speakAssistantText,
  });
  const {
    calendarView,
    setCalendarView,
    calendarEvents,
    googleCalendarStatus,
    googleCalendarEvents,
    googleCalendarLoading,
    googleCalendarError,
    saveCalendarEvent,
    deleteCalendarEvent,
    clearCalendarEvents,
    getNextCalendarEventForDeletion,
    getNextCalendarEventForChange,
    editLastCalendarEvent,
    deleteLastCalendarEvent,
    getCalendarReadout,
    refreshGoogleCalendar,
    findCalendarEventForDeletion,
    deleteCalendarEventByCriteria,
    handleStartGoogleCalendarAuth,
    handleResetGoogleCalendarAuth,
  } = useCalendarController({ activePanel });
  const openSearchPanel = useCallback(() => {
    setActivePanel('search');
  }, []);
  const {
    searchQuery,
    setSearchQuery,
    searchResult,
    searchLoading,
    searchError,
    runWebSearch,
    clearSearchState,
  } = useSearchController({ openSearchPanel });
  const {
    resultToasts,
    pushResultToast,
    dismissResultToast,
    clearResultToasts,
  } = useResultToasts();
  const {
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
  } = useMemoryContext({
    pushResultToast,
    calendarEvents,
    googleCalendarEvents,
    searchQuery,
    searchResult,
  });
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
  const recognitionRef = useRef<InstanceType<ReturnType<typeof getSpeechRecognition>> | null>(null);
  const transcriptSentRef = useRef(false);
  const listeningTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const suppressNextSpeechErrorRef = useRef(false);
  const orbAreaRef = useRef<HTMLDivElement | null>(null);
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
    clearMessages();

    try {
      await resetConversation();
    } catch (error) {
      console.error('Reset conversation error:', error);
    }
  }, [cancelActiveResponse, clearMessages, clearResultToasts, finishListening, stopCurrentSpeech]);

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
  }, [setCalendarView, setSearchQuery]);




  // Calendar state and Google Calendar actions live in useCalendarController.


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

    await sendStreamingChat(trimmed, visibleUserText);
  }, [chatActive, activePanel, calendarView, calendarEvents, voiceOutputEnabled, speechRate, lastHeardTranscript, lastNormalizedTranscript, lastLocalCommand, pendingInterpreterCommand, handleEndChat, finishListening, closePanel, goHome, stopCurrentSpeech, cancelActiveResponse, speakAssistantText, setVoiceOutput, adjustSpeechRate, saveNote, getNotesReadout, deleteLastNote, clearNotes, saveMemoryTask, markMemoryTaskDone, clearCompletedTasks, getMemoryReadout, saveCalendarEvent, getCalendarReadout, deleteLastCalendarEvent, deleteCalendarEventByCriteria, findCalendarEventForDeletion, getNextCalendarEventForDeletion, getNextCalendarEventForChange, editLastCalendarEvent, clearCalendarEvents, refreshGoogleCalendar, runWebSearch, clearSearchState, searchError, pushResultToast, addRecentAction, googleCalendarStatus?.connected, googleCalendarStatus?.writeEnabled, googleCalendarEvents, sendStreamingChat]);

  const handleOrbClick = useCallback(() => {
    // If QMeet is actively generating/streaming, tapping the orb should cancel
    // that response instead of starting a new listening session.
    if (responseActive || orbState === 'thinking') {
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
  }, [orbState, responseActive, handleSend, stopCurrentSpeech, cancelActiveResponse, setMessages]);

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
