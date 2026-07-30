import { useState, useCallback, useRef } from 'react';
import { Orb } from './components/Orb';
import { TopStatusBar } from './components/TopStatusBar';
import { ChatPanel } from './components/ChatPanel';
import { PromptBar } from './components/PromptBar';
import { MenuOverlay } from './panels/MenuOverlay';
import { SettingsOverlay } from './panels/SettingsOverlay';
import { StatusOverlay } from './panels/StatusOverlay';
import { MemoryOverlay } from './panels/MemoryOverlay';
import { NotesOverlay } from './panels/NotesOverlay';
import { CalendarOverlay } from './panels/CalendarOverlay';
import { SearchOverlay } from './panels/SearchOverlay';
import { OrbState, ActivePanel } from './types';
import { resetConversation, interpretCommandIntent } from "./api";
import { parseCommand } from './commands';
import { observeExactLocalRoute } from './lib/focusTurnHeaders';
import { getAssistantActivity, getPanelLabel } from './lib/activityUtils';
import { getDateKeyForCalendarView } from './lib/dateUtils';
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
import { getCommandActionLabel } from './lib/memoryUtils';
import {
  buildInterpreterClarifyPrompt,
  buildInterpreterDestructivePrompt,
  createAssistantMessage,
  createUserMessage,
  getInterpreterUnavailableReason,
  getLocalCommandRouteLabel,
  type CommandRoute,
} from './lib/chatFlowUtils';
import { useBackendStatus } from './hooks/useBackendStatus';
import { useResultToasts } from './hooks/useResultToasts';
import { useMemoryContext } from './hooks/useMemoryContext';
import { useSearchController } from './hooks/useSearchController';
import { useCalendarController } from './hooks/useCalendarController';
import { useSpeechOutput } from './hooks/useSpeechOutput';
import { useChatStreamController } from './hooks/useChatStreamController';
import { useSpeechRecognitionController } from './hooks/useSpeechRecognitionController';
import { handleNotesCommand } from './commandHandlers/notes';
import { handleMemoryCommand } from './commandHandlers/memory';
import { handleSearchCommand } from './commandHandlers/search';
import { handleVoiceCommand } from './commandHandlers/voice';
import { handleCalendarCommand } from './commandHandlers/calendar';
import {
  COMMAND_INTERPRETER_CLARIFY_THRESHOLD,
  COMMAND_INTERPRETER_EXECUTE_THRESHOLD,
  getFrontendCommandForLocalCommand,
  isConfirmingPendingCommand,
  isDestructiveInterpreterCommand,
  isDestructiveLocalCommand,
  isRejectingPendingCommand,
  type PendingInterpreterCommand,
} from './lib/commandRouterUtils';
import './App.css';


type SplitCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
  confirmationSpeechRate?: number;
};





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
    findCalendarEventForChange,
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
  const orbAreaRef = useRef<HTMLDivElement | null>(null);
  const {
    listeningTranscript,
    finishListening,
    startListening,
    voiceInputSupported,
  } = useSpeechRecognitionController({
    setOrbState,
    setChatActive,
    setMessages,
  });

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


  const sendNormalChat = useCallback(async (messageText: string, visibleUserText: string) => {
    await sendStreamingChat(messageText, visibleUserText);
  }, [sendStreamingChat]);

  const handleSend = useCallback(async (text: string, displayText?: string, commandRoute: CommandRoute = 'exact') => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const visibleUserText = (displayText ?? trimmed).trim() || trimmed;

    // Any new input supersedes the response currently being generated.
    // Local commands can return without reaching sendStreamingChat, so the
    // existing stream must be cancelled before command routing begins.
    stopCurrentSpeech();
    cancelActiveResponse();
    setOrbState('thinking');

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
            const userMsg = createUserMessage(now, visibleUserText);
            const assistantMsg = createAssistantMessage(now, 'Cancelled pending command.');
    
            setMessages((prev) => [...prev, userMsg, assistantMsg]);
            pushResultToast({ kind: 'warning', title: 'Cancelled', detail: 'Pending command dismissed.' });
            speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
            return;
          }
    
          setPendingInterpreterCommand(null);
        }

    const commandMatch = parseCommand(trimmed);
    
    if (commandMatch) {
      if (commandRoute === 'exact') {
        const requiresExactConfirmation =
          isDestructiveLocalCommand(commandMatch.command) ||
          (
            commandMatch.command === 'add-calendar-event' &&
            Boolean(googleCalendarStatus?.connected) &&
            Boolean(googleCalendarStatus?.writeEnabled)
          );

        observeExactLocalRoute({
          command: commandMatch.command,
          requiresConfirmation: requiresExactConfirmation,
        });
      }

      finishListening();
      setShowThinkingBubble(false);

      if (!chatActive) setChatActive(true);

      const now = Date.now();
      const previousLastHeardTranscript = lastHeardTranscript;
      const previousLastNormalizedTranscript = lastNormalizedTranscript;
      const previousLastLocalCommand = lastLocalCommand;

      setLastLocalCommand(commandMatch.command);
      setPendingInterpreterCommand(null);
      
      setLastInputRoute(getLocalCommandRouteLabel(commandRoute));
      if (commandRoute === 'exact') {
        setLastInterpreterAction('Not used');
        setLastInterpreterFrontendCommand('None');
        setLastInterpreterConfidence(null);
        setLastInterpreterReason('Exact frontend parser matched before the command interpreter was needed.');
      }

      const userMsg = createUserMessage(now, visibleUserText);
      
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

          const assistantMsg = createAssistantMessage(now, confirmationPrompt);

          setMessages((prev) => [...prev, userMsg, assistantMsg]);
          speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
          return;
        }
      }

      if (commandRoute !== 'confirmed' && commandMatch.command === 'edit-last-event') {
              const targetEditEvent = await findCalendarEventForChange();
              const editDescription = describeCalendarEditPayload(commandMatch.calendarEdit);
      
              if (!targetEditEvent) {
                setLastInputRoute('Edit command had no target');
                setLastLocalCommand('No calendar event to edit');
      
                const assistantMsg = createAssistantMessage(
                  now,
                  googleCalendarStatus?.connected
                    ? 'I did not find a Google Calendar event to edit for the current view.'
                    : 'I did not find a local calendar event to edit.'
                );
      
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
      
              const assistantMsg = createAssistantMessage(now, confirmationPrompt);
      
              setMessages((prev) => [...prev, userMsg, assistantMsg]);
              speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
              return;
            }

      if (commandRoute !== 'confirmed' && isDestructiveLocalCommand(commandMatch.command)) {
        const taskCompletionTarget = commandMatch.command === 'mark-task-done'
          ? commandMatch.payload?.trim() ?? ''
          : '';
        const frontendCommand = commandMatch.command === 'delete-calendar-event'
          ? buildCalendarDeleteFrontendCommand(commandMatch.calendarDelete)
          : commandMatch.command === 'mark-task-done' && taskCompletionTarget
            ? `mark task ${taskCompletionTarget} done`
            : getFrontendCommandForLocalCommand(commandMatch.command);
        const isCalendarDeleteCommand = commandMatch.command === 'delete-last-event' || commandMatch.command === 'delete-calendar-event';
        const targetDeleteEvent = commandMatch.command === 'delete-last-event'
          ? await findCalendarEventForDeletion()
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

          const assistantMsg = createAssistantMessage(now, confirmationPrompt);

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

        const assistantMsg = createAssistantMessage(now, confirmationPrompt);

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
      
      const notesCommandResult: SplitCommandResult = handleNotesCommand(commandMatch, {
        voiceOutputEnabled,
        setActivePanel,
        closePanel,
        saveNote,
        deleteLastNote,
        clearNotes,
        getNotesReadout,
      });

      const memoryCommandResult: SplitCommandResult = notesCommandResult.handled
        ? { handled: false }
        : handleMemoryCommand(commandMatch, {
            voiceOutputEnabled,
            setActivePanel,
            closePanel,
            getMemoryReadout,
            saveMemoryTask,
            markMemoryTaskDone,
            clearCompletedTasks,
          });

      const searchCommandResult: SplitCommandResult = notesCommandResult.handled || memoryCommandResult.handled
        ? { handled: false }
        : await handleSearchCommand(commandMatch, {
            voiceOutputEnabled,
            searchError,
            setActivePanel,
            closePanel,
            runWebSearch,
            clearSearchState,
          });

      const voiceCommandResult: SplitCommandResult = notesCommandResult.handled || memoryCommandResult.handled || searchCommandResult.handled
        ? { handled: false }
        : handleVoiceCommand(commandMatch, {
            voiceOutputEnabled,
            speechRate,
            previousLastHeardTranscript,
            previousLastNormalizedTranscript,
            previousLastLocalCommand,
            setVoiceOutput,
            adjustSpeechRate,
            stopCurrentSpeech,
            cancelActiveResponse,
            finishListening,
            setShowThinkingBubble,
            setOrbState,
          });

      const calendarCommandResult: SplitCommandResult = notesCommandResult.handled || memoryCommandResult.handled || searchCommandResult.handled || voiceCommandResult.handled
        ? { handled: false }
        : await handleCalendarCommand(commandMatch, {
            voiceOutputEnabled,
            calendarView,
            calendarEvents,
            googleCalendarStatus,
            googleCalendarEvents,
            setCalendarView,
            setActivePanel,
            closePanel,
            saveCalendarEvent,
            editLastCalendarEvent,
            deleteCalendarEventByCriteria,
            deleteLastCalendarEvent,
            clearCalendarEvents,
            refreshGoogleCalendar,
            getCalendarReadout,
            resetConversation,
          });

      const splitCommandResult: SplitCommandResult = notesCommandResult.handled
        ? notesCommandResult
        : memoryCommandResult.handled
          ? memoryCommandResult
          : searchCommandResult.handled
            ? searchCommandResult
            : voiceCommandResult.handled
              ? voiceCommandResult
              : calendarCommandResult;

      if (splitCommandResult.handled) {
        if (splitCommandResult.confirmationContent !== undefined) {
          confirmationContent = splitCommandResult.confirmationContent;
        }

        if (splitCommandResult.shouldSpeakConfirmation !== undefined) {
          shouldSpeakConfirmation = splitCommandResult.shouldSpeakConfirmation;
        }

        if (splitCommandResult.confirmationSpeechRate !== undefined) {
          confirmationSpeechRate = splitCommandResult.confirmationSpeechRate;
        }
      } else if (commandMatch.command === 'open-menu') {
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
      } else if (commandMatch.command === 'close-generic') {
        if (activePanel !== 'none') {
          closePanel();
        }
      } else if (commandMatch.command === 'clear-chat') {
        replaceMessages = true;
        setPendingInterpreterCommand(null);

        try {
          await resetConversation();
        } catch (error) {
          console.error('Clear chat backend reset error:', error);
          confirmationContent =
            'Chat cleared locally, but the backend conversation could not be reset.';
        }
      } else if (commandMatch.command === 'end-chat') {
        await handleEndChat();
        return;
      }

      speechConfirmationContent = getBriefToolSpeech(commandMatch.command, confirmationContent);
      
      const confirmationMsg = createAssistantMessage(now, confirmationContent, 'tool');
      
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
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(now, 'I understood that as a command, but I could not match it to a local action.');

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
        const userMsg = createUserMessage(now, visibleUserText);
        const assistantMsg = createAssistantMessage(now, buildInterpreterDestructivePrompt(interpretedCommand.frontendCommand));

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
        const userMsg = createUserMessage(now, visibleUserText);
        const assistantMsg = createAssistantMessage(now, buildInterpreterClarifyPrompt(interpretedCommand.frontendCommand, destructiveCommand));

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
      setLastInterpreterReason(getInterpreterUnavailableReason(error));
    }

    await sendNormalChat(trimmed, visibleUserText);
  }, [chatActive, activePanel, calendarView, calendarEvents, voiceOutputEnabled, speechRate, lastHeardTranscript, lastNormalizedTranscript, lastLocalCommand, pendingInterpreterCommand, handleEndChat, finishListening, closePanel, goHome, stopCurrentSpeech, cancelActiveResponse, speakAssistantText, setVoiceOutput, adjustSpeechRate, saveNote, getNotesReadout, deleteLastNote, clearNotes, saveMemoryTask, markMemoryTaskDone, clearCompletedTasks, getMemoryReadout, saveCalendarEvent, getCalendarReadout, deleteLastCalendarEvent, deleteCalendarEventByCriteria, findCalendarEventForDeletion, findCalendarEventForChange, getNextCalendarEventForDeletion, getNextCalendarEventForChange, editLastCalendarEvent, clearCalendarEvents, refreshGoogleCalendar, runWebSearch, clearSearchState, searchError, pushResultToast, addRecentAction, googleCalendarStatus?.connected, googleCalendarStatus?.writeEnabled, googleCalendarEvents, sendNormalChat]);
  
  const handleOrbClick = useCallback(() => {
    // If QMeet is actively generating/streaming, tapping the orb should cancel
    // that response instead of starting a new listening session.
    if (responseActive) {
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

    startListening((rawTranscript, normalizedTranscript) => {
      setLastHeardTranscript(rawTranscript);
      setLastNormalizedTranscript(normalizedTranscript);
      handleSend(normalizedTranscript);
    });
  }, [orbState, responseActive, handleSend, stopCurrentSpeech, cancelActiveResponse, setMessages, startListening]);

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
        <MenuOverlay openLauncherPanel={openLauncherPanel} onClose={closePanel} />
      )}

      {activePanel === 'settings' && (
        <SettingsOverlay
          backendStatus={backendStatus}
          voiceOutputEnabled={voiceOutputEnabled}
          speechRate={speechRate}
          setVoiceOutput={setVoiceOutput}
          speakAssistantText={speakAssistantText}
          adjustSpeechRate={adjustSpeechRate}
          onClose={closePanel}
        />
      )}
      
      {activePanel === 'status' && (
        <StatusOverlay
          activePanelLabel={activePanelLabel}
          backendStatus={backendStatus}
          orbState={orbState}
          voiceInputSupported={voiceInputSupported}
          lastHeardTranscript={lastHeardTranscript}
          lastNormalizedTranscript={lastNormalizedTranscript}
          lastLocalCommand={lastLocalCommand}
          lastInputRoute={lastInputRoute}
          lastInterpreterAction={lastInterpreterAction}
          lastInterpreterFrontendCommand={lastInterpreterFrontendCommand}
          interpreterConfidenceLabel={interpreterConfidenceLabel}
          interpreterReasonLabel={interpreterReasonLabel}
          pendingInterpreterLabel={pendingInterpreterLabel}
          voiceOutputEnabled={voiceOutputEnabled}
          speechRate={speechRate}
          chatActive={chatActive}
          messagesCount={messages.length}
          statusNotesCount={statusNotesCount}
          statusOpenTasksCount={statusOpenTasksCount}
          statusCompletedTasksCount={statusCompletedTasksCount}
          memorySyncState={memorySyncState}
          calendarEventsCount={calendarEvents.length}
          statusTodayEventsCount={statusTodayEventsCount}
          statusTomorrowEventsCount={statusTomorrowEventsCount}
          statusGoogleCalendarLabel={statusGoogleCalendarLabel}
          statusGoogleEventsCount={statusGoogleEventsCount}
          googleCalendarLoading={googleCalendarLoading}
          searchStatusLabel={searchStatusLabel}
          searchStatusMeta={searchStatusMeta}
          statusDateLabel={statusDateLabel}
          statusTimeLabel={statusTimeLabel}
          onClose={closePanel}
        />
      )}


      {activePanel === 'memory' && (
        <MemoryOverlay
          memorySyncState={memorySyncState}
          memorySyncMessage={memorySyncMessage}
          memoryImportInputRef={memoryImportInputRef}
          memoryTaskDraft={memoryTaskDraft}
          setMemoryTaskDraft={setMemoryTaskDraft}
          memoryTasks={memoryTasks}
          onExportMemory={handleExportMemory}
          onImportMemoryFile={handleImportMemoryFile}
          onClearAllMemory={handleClearAllMemory}
          onResetTasksOnly={handleResetTasksOnly}
          onResetNotesOnly={handleResetNotesOnly}
          onResetRecentContextOnly={handleResetRecentContextOnly}
          onSaveMemoryTaskDraft={handleSaveMemoryTaskDraft}
          markMemoryTaskDoneById={markMemoryTaskDoneById}
          deleteMemoryTask={deleteMemoryTask}
          reopenMemoryTask={reopenMemoryTask}
          clearCompletedTasks={clearCompletedTasks}
          addRecentAction={addRecentAction}
          pushResultToast={pushResultToast}
          onClose={closePanel}
        />
      )}

      {activePanel === 'notes' && (
        <NotesOverlay
          notes={notes}
          onSaveNote={saveNote}
          onDeleteNote={deleteNote}
          onClearNotes={clearNotes}
          onClose={closePanel}
        />
      )}

      {activePanel === 'calendar' && (
        <CalendarOverlay
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
        <SearchOverlay
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
