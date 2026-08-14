import { useState, useCallback, useEffect, useRef } from 'react';
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
import { parseCommand, type CommandMatch } from './commands';
import { observeExactLocalRoute } from './lib/focusTurnHeaders';
import {
  cancelActiveToolContinuation,
  continueAfterVerifiedToolUpdate,
} from './lib/toolContinuation';
import {
  cancelActiveConversationLane,
  sendConversationLaneMessage,
} from './lib/conversationLane';
import {
  observeAgentShadowTurn,
  reportAgentShadowLegacyRoute,
  resolvePromotedConversationOwnership,
  resolvePromotedSingleIntentDecision,
  resolveExplicitDeterministicRouteBeforeAgent,
  shouldGuardInferredSemanticFocusMutationWithShadow,
} from './lib/agentShadowObserver';
import {
  isPromotedCalendarCreateToolDecision,
  isPromotedCalendarDeleteToolDecision,
  isPromotedCalendarEditToolDecision,
  isPromotedTaskCreateToolDecision,
  isPromotedNoteReadToolDecision,
  isPromotedNoteSaveToolDecision,
  resolveDeferredCalendarWriteAction,
  resolvePromotedCalendarCreateToolCommand,
  resolvePromotedCalendarDeleteToolCommand,
  resolvePromotedCalendarEditToolCommand,
  resolvePromotedCalendarReadToolCommand,
  resolvePromotedSearchToolCommand,
  resolvePromotedTaskCreateToolCommand,
  resolvePromotedNoteReadToolCommand,
  resolvePromotedNoteSaveToolCommand,
  normalizePromotedCalendarCreateTitle,
  type DeferredCalendarWriteAction,
  type PromotedCalendarEditChanges,
  type PromotedCalendarEditTargetCriteria,
} from './lib/agentToolPromotion';
import {
  resolveExplicitCalendarWriteIntentBeforeAgent,
} from './lib/calendarWriteIntent';
import {
  describeTaskCompletionPreviewTargets,
  describeUnresolvedTaskCompletionRequest,
  resolveTaskCompletionPreviewTargets,
} from './lib/taskCompletionPreview';
import { resolveNaturalFocusTaskCompletionTarget } from './lib/naturalTaskCompletion';
import {
  completeConfirmedTaskTargets,
  type ConfirmedTaskTarget,
} from './lib/confirmedTaskCompletion';
import { reconcileCanonicalFocusProjection } from './lib/canonicalFocusProjection';
import { applyVerifiedFocusProjection } from './lib/nativeFocusLifecycle';
import {
  recordVerifiedFocusTaskProgress,
  type FocusTaskProgressResult,
} from './lib/focusTaskProgress';
import {
  getDirectFocusTerminalCommandMatch,
  interpretSemanticFocusLifecycle,
  shouldPreflightSemanticFocusLifecycleBeforeCommandRouting,
  shouldRouteExactFocusLifecycleThroughSemanticPreflight,
} from './lib/semanticFocusLifecycle';
import { normalizeVerifiedFocusToolReceipt } from './lib/focusToolReceipt';
import { getAssistantActivity, getPanelLabel } from './lib/activityUtils';
import { getDateKeyForCalendarView } from './lib/dateUtils';
import {
  buildCalendarDeleteFrontendCommand,
  buildCalendarEditFrontendCommand,
  describeCalendarDeletePayload,
  describeCalendarEditPayload,
} from './lib/calendarUtils';
import { resolveCalendarEventReference } from './lib/calendarEventResolver';
import {
  getBriefToolSpeech,
  getResultToastForCommand,
  hasFailureLanguage,
} from './lib/toastUtils';
import {
  getCommandActionLabel,
  shouldRecordRecentAction,
} from './lib/memoryUtils';
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
  continuationContext?: string;
};
const AGENT_FIRST_EXPLICIT_CALENDAR_WRITE_WAIT_MS = 7000;

const CALENDAR_WRITE_COMMANDS = new Set<DeferredCalendarWriteAction>([
  'add-calendar-event',
  'edit-last-event',
  'delete-calendar-event',
  'delete-last-event',
  'clear-calendar',
]);

function parseVerifiedCalendarWriteAction(
  frontendCommand: string,
): DeferredCalendarWriteAction | null {
  const parsed = parseCommand(frontendCommand);
  if (!parsed) return null;
  const command = parsed.command as DeferredCalendarWriteAction;
  return CALENDAR_WRITE_COMMANDS.has(command) ? command : null;
}

const FOCUS_COMMANDS_THAT_PRESERVE_ACTIVE_PANEL = new Set<string>([
  'start-focus-session',
  'update-focus-session',
  'resume-last-focus-session',
  'end-focus-session',
  'end-focus-with-summary',
  'wrap-up-meeting-focus',
  'save-focus-summary',
  'focus-to-tasks',
  'create-meeting-follow-up-tasks',
  'prepare-calendar-focus',
  'read-focus-session',
  'summarize-focus-session',
]);
function shouldSuppressLegacyFocusMemoryOpen(
  command: string,
  panel: ActivePanel,
): boolean {
  return (
    panel === 'memory' &&
    FOCUS_COMMANDS_THAT_PRESERVE_ACTIVE_PANEL.has(command)
  );
}
export default function App() {
  const [chatActive, setChatActive] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [conversationResponseActive, setConversationResponseActive] = useState(false);
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
    updateCalendarEvent,
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
    getCalendarEventsForDeleteCriteria,
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
    recentFocusSessions,
    activeSession,
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
  const reconcileFocusProjection = useCallback(async () => {
    try {
      return await reconcileCanonicalFocusProjection(
        activeSession,
        recentFocusSessions,
      );
    } catch (error) {
      console.warn(
        'Canonical Focus projection reconciliation failed; preserving the current projection.',
        error,
      );
      return activeSession;
    }
  }, [activeSession, recentFocusSessions]);
  useEffect(() => {
    void reconcileFocusProjection();
  }, [reconcileFocusProjection]);
  const [lastHeardTranscript, setLastHeardTranscript] = useState('');
  const [lastNormalizedTranscript, setLastNormalizedTranscript] = useState('');
  const [lastLocalCommand, setLastLocalCommand] = useState('None');
  const [lastInputRoute, setLastInputRoute] = useState('None');
  const [lastInterpreterAction, setLastInterpreterAction] = useState('Not used');
  const [lastInterpreterFrontendCommand, setLastInterpreterFrontendCommand] = useState('None');
  const [lastInterpreterConfidence, setLastInterpreterConfidence] = useState<number | null>(null);
  const [lastInterpreterReason, setLastInterpreterReason] = useState('No interpreter request has run yet.');
  const [pendingInterpreterCommand, setPendingInterpreterCommand] = useState<PendingInterpreterCommand | null>(null);
  const pendingTaskCompletionTargetsRef = useRef<ConfirmedTaskTarget[]>([]);
  const pendingCalendarDeleteTargetIdRef = useRef<string | null>(null);
  const pendingCalendarEditTargetIdRef = useRef<string | null>(null);
  const pendingCalendarEditChangesRef = useRef<PromotedCalendarEditChanges | null>(null);
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
    cancelActiveToolContinuation();
    cancelActiveConversationLane();
    setConversationResponseActive(false);
    finishListening();
    setShowThinkingBubble(false);
    setActivePanel('none');
    setPendingInterpreterCommand(null);
    pendingTaskCompletionTargetsRef.current = [];
    pendingCalendarDeleteTargetIdRef.current = null;
    pendingCalendarEditTargetIdRef.current = null;
    pendingCalendarEditChangesRef.current = null;
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
    cancelActiveToolContinuation();
    cancelActiveConversationLane();
    setConversationResponseActive(false);
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
  const sendNormalChat = useCallback(async (
    messageText: string,
    visibleUserText: string,
    shadowTurn: ReturnType<typeof observeAgentShadowTurn> | null = null,
    activeFocusId: string | null = activeSession?.id ?? null,
  ) => {
    const ownershipHint = await resolvePromotedConversationOwnership({
      shadowTurn,
      activeFocusId,
    });
    await sendConversationLaneMessage({
      userMessage: messageText,
      visibleUserText,
      recentMessages: messages,
      activePanel,
      ownershipHint,
      voiceOutputEnabled,
      setMessages,
      setShowThinkingBubble,
      setOrbState,
      setChatActive,
      setConversationResponseActive,
      speakAssistantText,
    });
  }, [activePanel, activeSession?.id, messages, speakAssistantText, voiceOutputEnabled]);
  const handleSend = useCallback(async (text: string, displayText?: string, commandRoute: CommandRoute = 'exact', forcedCommandMatch?: CommandMatch, confirmedTaskTargets: ConfirmedTaskTarget[] = [], continuationUserText?: string, confirmedCalendarDeleteTargetId: string | null = null, confirmedCalendarEditTargetId: string | null = null, promotedCalendarEditTargetCriteria: PromotedCalendarEditTargetCriteria | null = null) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const visibleUserText = (displayText ?? trimmed).trim() || trimmed;
    const continuationUserTextForTool =
      (continuationUserText ?? visibleUserText).trim() || visibleUserText;
    const shadowTurn = commandRoute === 'exact' && !forcedCommandMatch
      ? observeAgentShadowTurn({
          userMessage: visibleUserText,
          recentMessages: messages,
          activePanel,
          chatActive,
          calendarView,
          googleCalendarConnected: Boolean(googleCalendarStatus?.connected),
          googleCalendarWriteEnabled: Boolean(googleCalendarStatus?.writeEnabled),
          pendingCommand: pendingInterpreterCommand
            ? {
                originalText: pendingInterpreterCommand.originalText,
                action: pendingInterpreterCommand.action,
                frontendCommand: pendingInterpreterCommand.frontendCommand,
              }
            : null,
          frontendFocusProjection: activeSession
            ? {
                id: activeSession.id,
                title: activeSession.title,
                goal: activeSession.goal,
                mode: activeSession.mode,
              }
            : null,
        })
      : null;
    let shadowRouteSequence = 0;
    const setTrackedInputRoute = (
      route: string,
      action = '',
      frontendCommand = '',
      owner?: 'general_chat' | 'calendar' | 'search' | 'memory' | 'tasks' | 'notes' | 'focus' | 'device_ui' | 'visual' | 'other',
      disposition?: 'conversation' | 'tool' | 'clarify',
    ) => {
      setLastInputRoute(route);
      if (!shadowTurn) return;
      shadowRouteSequence += 1;
      void reportAgentShadowLegacyRoute(shadowTurn, {
        route,
        owner,
        action,
        frontendCommand,
        disposition,
        sequence: shadowRouteSequence,
      });
    };
    // Any new input supersedes the response currently being generated.
    // Local commands can return without reaching the conversation lane, so
    // any existing response must be cancelled before command routing begins.
    stopCurrentSpeech();
    cancelActiveResponse();
    cancelActiveToolContinuation();
    cancelActiveConversationLane();
    setConversationResponseActive(false);
    setOrbState('thinking');
    if (pendingInterpreterCommand) {
          if (isConfirmingPendingCommand(trimmed)) {
            const commandToRun = pendingInterpreterCommand;
            const resolvedTaskTargets = pendingTaskCompletionTargetsRef.current;
            const resolvedCalendarDeleteTargetId =
              commandToRun.action === 'delete-calendar-event'
                ? pendingCalendarDeleteTargetIdRef.current
                : null;
            const resolvedCalendarEditTargetId =
              commandToRun.action === 'edit-last-event'
                ? pendingCalendarEditTargetIdRef.current
                : null;
            const resolvedCalendarEditChanges =
              commandToRun.action === 'edit-last-event'
                ? pendingCalendarEditChangesRef.current
                : null;
            setPendingInterpreterCommand(null);
            pendingTaskCompletionTargetsRef.current = [];
            pendingCalendarDeleteTargetIdRef.current = null;
            pendingCalendarEditTargetIdRef.current = null;
            pendingCalendarEditChangesRef.current = null;
            if (
              commandToRun.action === 'delete-calendar-event' &&
              !resolvedCalendarDeleteTargetId
            ) {
              finishListening();
              setShowThinkingBubble(false);
              setTrackedInputRoute(
                'Confirmed Calendar delete target missing',
                commandToRun.action,
                commandToRun.frontendCommand,
              );
              setLastLocalCommand('Calendar delete not executed');
              setLastInterpreterReason(
                'The confirmed targeted delete no longer had one verified event identity, so QMeet refused to re-resolve a different event.',
              );
              if (!chatActive) setChatActive(true);
              const now = Date.now();
              const userMsg = createUserMessage(now, visibleUserText);
              const assistantMsg = createAssistantMessage(
                now,
                'I could not verify the exact calendar event that was previously selected, so I did not delete anything. Please ask me to delete it again.',
              );
              setMessages((prev) => [...prev, userMsg, assistantMsg]);
              pushResultToast({
                kind: 'warning',
                title: 'Calendar unchanged',
                detail: assistantMsg.content,
              });
              speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
              return;
            }
            if (
              commandToRun.action === 'edit-last-event' &&
              (!resolvedCalendarEditTargetId || !resolvedCalendarEditChanges)
            ) {
              finishListening();
              setShowThinkingBubble(false);
              setTrackedInputRoute(
                'Confirmed Calendar edit target missing',
                commandToRun.action,
                commandToRun.frontendCommand,
              );
              setLastLocalCommand('Calendar edit not executed');
              setLastInterpreterReason(
                'The confirmed targeted edit no longer had both one verified event identity and the validated requested change, so QMeet refused to re-resolve or reinterpret anything.',
              );
              if (!chatActive) setChatActive(true);
              const now = Date.now();
              const userMsg = createUserMessage(now, visibleUserText);
              const assistantMsg = createAssistantMessage(
                now,
                'I could not verify the exact calendar event that was previously selected, so I did not update anything. Please ask me to edit it again.',
              );
              setMessages((prev) => [...prev, userMsg, assistantMsg]);
              pushResultToast({
                kind: 'warning',
                title: 'Calendar unchanged',
                detail: assistantMsg.content,
              });
              speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
              return;
            }
            setTrackedInputRoute(
              'Confirmed fuzzy interpreter command',
              commandToRun.action,
              commandToRun.frontendCommand,
            );
            setLastInterpreterAction(commandToRun.action);
            setLastInterpreterFrontendCommand(commandToRun.frontendCommand);
            setLastInterpreterConfidence(commandToRun.confidence);
            setLastInterpreterReason(commandToRun.reason || 'User confirmed a pending destructive command.');
            const confirmedTaskCommandMatch: CommandMatch | undefined =
              commandToRun.action === 'mark-task-done' &&
              resolvedTaskTargets.length > 0
                ? {
                    command: 'mark-task-done',
                    confirmation: 'Marked task done.',
                    payload: resolvedTaskTargets
                      .map((task) => task.title)
                      .join('; '),
                  }
                : undefined;
            const confirmedCalendarEditCommandMatch: CommandMatch | undefined =
              commandToRun.action === 'edit-last-event' &&
              resolvedCalendarEditChanges
                ? {
                    command: 'edit-last-event',
                    confirmation: 'Updated the last event.',
                    calendarEdit: { ...resolvedCalendarEditChanges },
                  }
                : undefined;
            if (confirmedCalendarEditCommandMatch) {
              return handleSend(
                commandToRun.frontendCommand,
                visibleUserText,
                'confirmed',
                confirmedCalendarEditCommandMatch,
                resolvedTaskTargets,
                commandToRun.originalText,
                resolvedCalendarDeleteTargetId,
                resolvedCalendarEditTargetId,
              );
            }
            return handleSend(
              commandToRun.frontendCommand,
              visibleUserText,
              'confirmed',
              confirmedTaskCommandMatch,
              resolvedTaskTargets,
              commandToRun.originalText,
              resolvedCalendarDeleteTargetId,
              resolvedCalendarEditTargetId,
            );
          }
          if (isRejectingPendingCommand(trimmed)) {
            finishListening();
            setShowThinkingBubble(false);
            setPendingInterpreterCommand(null);
            pendingTaskCompletionTargetsRef.current = [];
            pendingCalendarDeleteTargetIdRef.current = null;
            pendingCalendarEditTargetIdRef.current = null;
            pendingCalendarEditChangesRef.current = null;
            setTrackedInputRoute(
              'Cancelled pending command',
              pendingInterpreterCommand.action,
              pendingInterpreterCommand.frontendCommand,
            );
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
          pendingTaskCompletionTargetsRef.current = [];
          pendingCalendarDeleteTargetIdRef.current = null;
          pendingCalendarEditTargetIdRef.current = null;
          pendingCalendarEditChangesRef.current = null;
        }
    const routingActiveSession =
      !forcedCommandMatch && commandRoute === 'exact'
        ? await reconcileFocusProjection()
        : activeSession;
    const directFocusTerminalCommandMatch =
      !forcedCommandMatch && commandRoute === 'exact'
        ? getDirectFocusTerminalCommandMatch(trimmed)
        : null;
    if (directFocusTerminalCommandMatch) {
      setTrackedInputRoute('Direct Focus terminal safety gate');
      setLastInterpreterAction('focus_terminal_transition');
      setLastInterpreterFrontendCommand('apply verified focus terminal transition');
      setLastInterpreterConfidence(1);
      setLastInterpreterReason(
        'Unambiguous Focus-terminal language was routed before task and fuzzy command parsing.',
      );
      return handleSend(
        'apply verified focus terminal transition',
        visibleUserText,
        'interpreter',
        directFocusTerminalCommandMatch,
      );
    }
    const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);
    const explicitCalendarWriteIntent =
      !forcedCommandMatch && commandRoute === 'exact'
        ? resolveExplicitCalendarWriteIntentBeforeAgent({
            userMessage: trimmed,
            parsedCommand: parsedCommandMatch,
          })
        : null;
    const explicitDeterministicRoute =
      !forcedCommandMatch && commandRoute === 'exact'
        ? resolveExplicitDeterministicRouteBeforeAgent({
            userMessage: trimmed,
            parsedCommand: parsedCommandMatch?.command ?? null,
          })
        : null;
    const promotedSingleIntent =
      !forcedCommandMatch &&
      commandRoute === 'exact' &&
      !explicitDeterministicRoute
        ? await resolvePromotedSingleIntentDecision({
            shadowTurn,
            activeFocusId: routingActiveSession?.id ?? null,
            timeoutMs: explicitCalendarWriteIntent
              ? AGENT_FIRST_EXPLICIT_CALENDAR_WRITE_WAIT_MS
              : undefined,
          })
        : null;
    const promotedConversationAllowed =
      promotedSingleIntent?.disposition === 'conversation' &&
      !explicitCalendarWriteIntent;
    if (promotedSingleIntent?.disposition === 'conversation') {
      if (promotedConversationAllowed) {
        setPendingInterpreterCommand(null);
        setLastInputRoute('Agent-first single-intent conversation');
        setLastLocalCommand('No local command');
        setLastInterpreterAction(promotedSingleIntent.proposedAction);
        setLastInterpreterFrontendCommand('None');
        setLastInterpreterConfidence(promotedSingleIntent.confidence);
        setLastInterpreterReason(
          `Agent-first owner=${promotedSingleIntent.turnOwner}: ${promotedSingleIntent.proposedAction}.`,
        );
        await sendNormalChat(
          trimmed,
          visibleUserText,
          shadowTurn,
          routingActiveSession?.id ?? null,
        );
        return;
      }
    }
    const promotedSearchTool = resolvePromotedSearchToolCommand(
      promotedSingleIntent,
    );
    if (promotedSearchTool) {
      setPendingInterpreterCommand(null);
      setTrackedInputRoute(
        'Agent-promoted Search tool',
        promotedSearchTool.commandMatch.command,
        promotedSearchTool.query,
        'search',
        'tool',
      );
      setLastLocalCommand('Agent-promoted Search');
      setLastInterpreterAction(promotedSearchTool.commandMatch.command);
      setLastInterpreterFrontendCommand(`search: ${promotedSearchTool.query}`);
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed one canonical Search action and its query passed deterministic frontend validation.',
      );
      return handleSend(
        promotedSearchTool.query,
        visibleUserText,
        'agent',
        promotedSearchTool.commandMatch,
        [],
        visibleUserText,
      );
    }
    const promotedTaskCreateCandidate =
      isPromotedTaskCreateToolDecision(promotedSingleIntent);
    const promotedTaskCreateTool =
      resolvePromotedTaskCreateToolCommand(promotedSingleIntent);
    if (promotedTaskCreateCandidate && !promotedTaskCreateTool) {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      pendingTaskCompletionTargetsRef.current = [];
      setTrackedInputRoute(
        'Agent-promoted task create rejected',
        'remember-task',
        undefined,
        'tasks',
        'tool',
      );
      setLastLocalCommand('Task not saved');
      setLastInterpreterAction('remember-task');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed one task creation, but its typed title failed deterministic frontend validation.',
      );
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        'I understood this as creating a task, but I could not safely validate one task title. No task was added.',
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      pushResultToast({
        kind: 'warning',
        title: 'Task unchanged',
        detail: assistantMsg.content,
      });
      speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
      return;
    }
    if (promotedTaskCreateTool) {
      setPendingInterpreterCommand(null);
      setTrackedInputRoute(
        'Agent-promoted task create',
        promotedTaskCreateTool.commandMatch.command,
        `task create: ${promotedTaskCreateTool.title}`,
        'tasks',
        'tool',
      );
      setLastLocalCommand('Agent-promoted task create');
      setLastInterpreterAction(promotedTaskCreateTool.commandMatch.command);
      setLastInterpreterFrontendCommand(`task create: ${promotedTaskCreateTool.title}`);
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed one canonical task-create action and its title passed deterministic frontend validation; the existing Memory task handler remains the writer.',
      );
      return handleSend(
        visibleUserText,
        visibleUserText,
        'agent',
        promotedTaskCreateTool.commandMatch,
        [],
        visibleUserText,
      );
    }
    const promotedNoteSaveCandidate =
      isPromotedNoteSaveToolDecision(promotedSingleIntent);
    const promotedNoteSaveTool =
      resolvePromotedNoteSaveToolCommand(promotedSingleIntent);
    if (promotedNoteSaveCandidate && !promotedNoteSaveTool) {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      pendingTaskCompletionTargetsRef.current = [];
      setTrackedInputRoute(
        'Agent-promoted note save rejected',
        'save-note',
        undefined,
        'notes',
        'tool',
      );
      setLastLocalCommand('Note not saved');
      setLastInterpreterAction('save-note');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed one note save, but its typed content failed deterministic frontend validation.',
      );
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        'I understood this as saving a note, but I could not safely validate one note body. No note was added.',
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      pushResultToast({
        kind: 'warning',
        title: 'Notes unchanged',
        detail: assistantMsg.content,
      });
      speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
      return;
    }
    if (promotedNoteSaveTool) {
      setPendingInterpreterCommand(null);
      setTrackedInputRoute(
        'Agent-promoted note save',
        promotedNoteSaveTool.commandMatch.command,
        'validated note content',
        'notes',
        'tool',
      );
      setLastLocalCommand('Agent-promoted note save');
      setLastInterpreterAction(promotedNoteSaveTool.commandMatch.command);
      setLastInterpreterFrontendCommand('Validated Notes save proposal');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed one canonical note-save action and its content passed deterministic frontend validation; the existing Notes handler remains the writer.',
      );
      return handleSend(
        visibleUserText,
        visibleUserText,
        'agent',
        promotedNoteSaveTool.commandMatch,
        [],
        visibleUserText,
      );
    }
    const promotedNoteReadCandidate =
      isPromotedNoteReadToolDecision(promotedSingleIntent);
    const promotedNoteReadTool =
      resolvePromotedNoteReadToolCommand(promotedSingleIntent);
    if (promotedNoteReadCandidate && !promotedNoteReadTool) {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      pendingTaskCompletionTargetsRef.current = [];
      setTrackedInputRoute(
        'Agent-promoted note read rejected',
        'read-notes',
        undefined,
        'notes',
        'tool',
      );
      setLastLocalCommand('Notes not read');
      setLastInterpreterAction('read-notes');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed an authoritative Notes read, but its argument shape failed deterministic frontend validation.',
      );
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        'I understood this as reading your saved notes, but I could not safely validate the Notes read request.',
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
      return;
    }
    if (promotedNoteReadTool) {
      setPendingInterpreterCommand(null);
      setTrackedInputRoute(
        'Agent-promoted note read',
        promotedNoteReadTool.commandMatch.command,
        'notes read',
        'notes',
        'tool',
      );
      setLastLocalCommand('Agent-promoted note read');
      setLastInterpreterAction(promotedNoteReadTool.commandMatch.command);
      setLastInterpreterFrontendCommand('notes read');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed the canonical read-notes action; authoritative saved Notes state remains owned by the existing Notes handler.',
      );
      return handleSend(
        visibleUserText,
        visibleUserText,
        'agent',
        promotedNoteReadTool.commandMatch,
        [],
        visibleUserText,
      );
    }
    const promotedCalendarCreateCandidate =
      isPromotedCalendarCreateToolDecision(promotedSingleIntent);
    const promotedCalendarCreateTool =
      resolvePromotedCalendarCreateToolCommand(promotedSingleIntent);
    if (promotedCalendarCreateCandidate && !promotedCalendarCreateTool) {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      pendingTaskCompletionTargetsRef.current = [];
      setTrackedInputRoute(
        'Agent-promoted Calendar create rejected',
        'add-calendar-event',
        undefined,
        'calendar',
        'tool',
      );
      setLastLocalCommand('Calendar write not executed');
      setLastInterpreterAction('add-calendar-event');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed Calendar creation, but its typed arguments failed deterministic validation.',
      );
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        'I understood this as creating a Calendar event, but I could not safely validate one event title, day, and time. No calendar change was made.',
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      pushResultToast({
        kind: 'warning',
        title: 'Calendar unchanged',
        detail: assistantMsg.content,
      });
      speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
      return;
    }
    if (promotedCalendarCreateTool) {
      setPendingInterpreterCommand(null);
      setTrackedInputRoute(
        'Agent-promoted Calendar create',
        promotedCalendarCreateTool.commandMatch.command,
        `calendar create: ${promotedCalendarCreateTool.day} / ${promotedCalendarCreateTool.time ?? 'all day'} / ${promotedCalendarCreateTool.title}`,
        'calendar',
        'tool',
      );
      setLastLocalCommand('Agent-promoted Calendar create');
      setLastInterpreterAction(promotedCalendarCreateTool.commandMatch.command);
      setLastInterpreterFrontendCommand('Validated Calendar create proposal');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed one canonical Calendar create action and its title/day/time arguments passed deterministic frontend validation; execution still requires the existing Calendar confirmation path.',
      );
      return handleSend(
        visibleUserText,
        visibleUserText,
        'agent',
        promotedCalendarCreateTool.commandMatch,
        [],
        visibleUserText,
      );
    }
    const promotedCalendarDeleteCandidate =
      isPromotedCalendarDeleteToolDecision(promotedSingleIntent);
    const promotedCalendarDeleteTool =
      resolvePromotedCalendarDeleteToolCommand(promotedSingleIntent);
    if (promotedCalendarDeleteCandidate && !promotedCalendarDeleteTool) {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      pendingTaskCompletionTargetsRef.current = [];
      pendingCalendarDeleteTargetIdRef.current = null;
      pendingCalendarEditTargetIdRef.current = null;
      pendingCalendarEditChangesRef.current = null;
      setTrackedInputRoute(
        'Agent-promoted Calendar delete rejected',
        'delete-calendar-event',
        undefined,
        'calendar',
        'tool',
      );
      setLastLocalCommand('Calendar delete not executed');
      setLastInterpreterAction('delete-calendar-event');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed targeted Calendar deletion, but its day/title/time criteria failed deterministic validation.',
      );
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        'I understood this as deleting a Calendar event, but I could not safely validate one target day plus a title or time. No calendar change was made.',
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      pushResultToast({
        kind: 'warning',
        title: 'Calendar unchanged',
        detail: assistantMsg.content,
      });
      speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
      return;
    }
    if (promotedCalendarDeleteTool) {
      setPendingInterpreterCommand(null);
      setTrackedInputRoute(
        'Agent-promoted Calendar delete',
        promotedCalendarDeleteTool.commandMatch.command,
        `calendar delete: ${promotedCalendarDeleteTool.day} / ${promotedCalendarDeleteTool.time ?? 'any time'} / ${promotedCalendarDeleteTool.title ?? 'no title filter'}`,
        'calendar',
        'tool',
      );
      setLastLocalCommand('Agent-promoted Calendar delete');
      setLastInterpreterAction(promotedCalendarDeleteTool.commandMatch.command);
      setLastInterpreterFrontendCommand('Validated Calendar delete criteria');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed one canonical Calendar delete action and its lookup criteria passed deterministic validation; canonical Calendar state must still resolve exactly one target before confirmation.',
      );
      return handleSend(
        visibleUserText,
        visibleUserText,
        'agent',
        promotedCalendarDeleteTool.commandMatch,
        [],
        visibleUserText,
      );
    }
    const promotedCalendarEditCandidate =
      isPromotedCalendarEditToolDecision(promotedSingleIntent);
    const promotedCalendarEditTool =
      resolvePromotedCalendarEditToolCommand(promotedSingleIntent);
    if (promotedCalendarEditCandidate && !promotedCalendarEditTool) {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      pendingTaskCompletionTargetsRef.current = [];
      pendingCalendarEditTargetIdRef.current = null;
      pendingCalendarEditChangesRef.current = null;
      setTrackedInputRoute(
        'Agent-promoted Calendar edit rejected',
        'edit-last-event',
        undefined,
        'calendar',
        'tool',
      );
      setLastLocalCommand('Calendar edit not executed');
      setLastInterpreterAction('edit-last-event');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed targeted Calendar editing, but its target criteria or requested changes failed deterministic validation.',
      );
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        'I understood this as editing a Calendar event, but I could not safely validate both one target and one requested change. No calendar change was made.',
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      pushResultToast({
        kind: 'warning',
        title: 'Calendar unchanged',
        detail: assistantMsg.content,
      });
      speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
      return;
    }
    if (promotedCalendarEditTool) {
      setPendingInterpreterCommand(null);
      setTrackedInputRoute(
        'Agent-promoted Calendar edit',
        promotedCalendarEditTool.commandMatch.command,
        `calendar edit target: ${promotedCalendarEditTool.target.day} / ${promotedCalendarEditTool.target.time ?? 'any time'} / ${promotedCalendarEditTool.target.query}`,
        'calendar',
        'tool',
      );
      setLastLocalCommand('Agent-promoted Calendar edit');
      setLastInterpreterAction(promotedCalendarEditTool.commandMatch.command);
      setLastInterpreterFrontendCommand('Validated Calendar edit criteria and changes');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed one canonical Calendar edit action; target criteria and requested changes passed deterministic validation, but canonical Calendar state must still resolve exactly one target before confirmation.',
      );
      return handleSend(
        visibleUserText,
        visibleUserText,
        'agent',
        promotedCalendarEditTool.commandMatch,
        [],
        visibleUserText,
        null,
        null,
        promotedCalendarEditTool.target,
      );
    }
    const promotedCalendarReadTool =
      resolvePromotedCalendarReadToolCommand(promotedSingleIntent);
    const deferredCalendarWriteAction =
      resolveDeferredCalendarWriteAction(promotedSingleIntent) ??
      explicitCalendarWriteIntent?.expectedAction ??
      null;
    if (promotedCalendarReadTool) {
      setPendingInterpreterCommand(null);
      setTrackedInputRoute(
        'Agent-promoted Calendar read',
        promotedCalendarReadTool.commandMatch.command,
        `calendar read: ${promotedCalendarReadTool.view}`,
        'calendar',
        'tool',
      );
      setLastLocalCommand('Agent-promoted Calendar read');
      setLastInterpreterAction(promotedCalendarReadTool.commandMatch.command);
      setLastInterpreterFrontendCommand(
        `calendar read: ${promotedCalendarReadTool.view}`,
      );
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(
        'The unified agent proposed the canonical read-only Calendar action and its view passed deterministic frontend validation.',
      );
      return handleSend(
        visibleUserText,
        visibleUserText,
        'agent',
        promotedCalendarReadTool.commandMatch,
        [],
        visibleUserText,
      );
    }
    const promotedNonFocusToolOwner =
      promotedSingleIntent?.disposition === 'tool' &&
      promotedSingleIntent.turnOwner !== 'focus'
        ? promotedSingleIntent.turnOwner
        : explicitCalendarWriteIntent
          ? 'calendar'
          : null;
    const naturalTaskCompletionEligible =
      !parsedCommandMatch || parsedCommandMatch.command === 'mark-task-done';
    const naturalTaskCompletionTarget =
      !forcedCommandMatch &&
      commandRoute === 'exact' &&
      naturalTaskCompletionEligible
        ? resolveNaturalFocusTaskCompletionTarget(
            trimmed,
            memoryTasks,
            routingActiveSession,
          )
        : null;
    const naturalTaskCompletionCommandMatch: CommandMatch | null =
      naturalTaskCompletionTarget
        ? {
            command: 'mark-task-done',
            confirmation: 'Marked task done.',
            payload: naturalTaskCompletionTarget.title,
          }
        : null;
    const deferredExactFocusLifecycleMatch =
      !forcedCommandMatch &&
      commandRoute === 'exact' &&
      !promotedNonFocusToolOwner &&
      shouldRouteExactFocusLifecycleThroughSemanticPreflight(
        parsedCommandMatch,
        trimmed,
      )
        ? parsedCommandMatch
        : null;
    const exactNonLifecycleCommandClaimed =
      !forcedCommandMatch &&
      commandRoute === 'exact' &&
      (Boolean(parsedCommandMatch) ||
        Boolean(naturalTaskCompletionCommandMatch)) &&
      !Boolean(deferredExactFocusLifecycleMatch);
    const exactResumeLifecyclePreflight =
      deferredExactFocusLifecycleMatch?.command === 'resume-last-focus-session'
        ? {
            kind: 'resume' as const,
            commandMatch: deferredExactFocusLifecycleMatch,
            confidence: 1,
            reason:
              'An exact resume command passed deterministic lifecycle preflight before the verified native resume executor.',
          }
        : null;
    const semanticLifecyclePreflightBeforeCommandRouting =
      !forcedCommandMatch &&
      commandRoute === 'exact' &&
      !promotedNonFocusToolOwner &&
      !exactNonLifecycleCommandClaimed &&
      (Boolean(deferredExactFocusLifecycleMatch) ||
        explicitDeterministicRoute?.kind === 'focus-mutation' ||
        shouldPreflightSemanticFocusLifecycleBeforeCommandRouting(trimmed))
        ? exactResumeLifecyclePreflight ??
          await interpretSemanticFocusLifecycle(trimmed)
        : null;
    const deferredSemanticFocusLifecycleMessage =
      Boolean(semanticLifecyclePreflightBeforeCommandRouting) ||
      Boolean(deferredExactFocusLifecycleMatch);
    const commandMatch = deferredSemanticFocusLifecycleMessage
      ? null
      : naturalTaskCompletionCommandMatch &&
          parsedCommandMatch?.command === 'mark-task-done'
        ? naturalTaskCompletionCommandMatch
        : parsedCommandMatch ?? naturalTaskCompletionCommandMatch;
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
      if (commandRoute !== 'confirmed') {
        pendingTaskCompletionTargetsRef.current = [];
      }
      setTrackedInputRoute(
        naturalTaskCompletionTarget && commandRoute === 'exact'
          ? 'Natural Focus task completion'
          : getLocalCommandRouteLabel(commandRoute),
        commandMatch.command,
      );
      if (commandRoute === 'exact') {
        setLastInterpreterAction('Not used');
        setLastInterpreterFrontendCommand('None');
        setLastInterpreterConfidence(null);
        setLastInterpreterReason(
          naturalTaskCompletionTarget
            ? 'Natural completed-work language matched one open task linked to the active Focus before semantic or fuzzy interpretation.'
            : 'Exact frontend parser matched before the command interpreter was needed.',
        );
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
        const targetTitle = normalizePromotedCalendarCreateTitle(
          commandMatch.calendarEvent?.title?.trim() ?? '',
        );
        if (targetTitle) {
          const isAllDay = targetTime.toLowerCase() === 'later';
          const frontendCommand = `add event ${targetView} at ${targetTime} called ${targetTitle}`;
          const confirmationPrompt = `I understood that as: create a Google Calendar event ${targetView} ${isAllDay ? 'all day' : `at ${targetTime}`}: ${targetTitle}. Say "confirm" to create it, or "cancel" to stop.`;
          pendingTaskCompletionTargetsRef.current = [];
          setPendingInterpreterCommand({
            originalText: visibleUserText,
            frontendCommand,
            action: commandMatch.command,
            confidence: commandRoute === 'exact' ? 1 : 0.9,
            reason: 'Google Calendar event creation requires confirmation before writing to the real calendar.',
          });
          setTrackedInputRoute(commandRoute === 'exact' ? 'Exact Google Calendar write needs confirmation' : 'Fuzzy Google Calendar write needs confirmation');
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
        let targetEditEvent = null as Awaited<ReturnType<typeof findCalendarEventForChange>>;
        let editResolutionKind: 'legacy' | 'exact' | 'likely' = 'legacy';

        if (promotedCalendarEditTargetCriteria) {
          const sourceEvents = await getCalendarEventsForDeleteCriteria({
            day: promotedCalendarEditTargetCriteria.day,
          });
          const resolution = resolveCalendarEventReference(sourceEvents, {
            day: promotedCalendarEditTargetCriteria.day,
            query: promotedCalendarEditTargetCriteria.query,
            time: promotedCalendarEditTargetCriteria.time,
          });

          if (resolution.kind === 'ambiguous') {
            pendingCalendarEditTargetIdRef.current = null;
            pendingCalendarEditChangesRef.current = null;
            setTrackedInputRoute(
              'Calendar edit needs deterministic target clarification',
              commandMatch.command,
            );
            setLastLocalCommand('Calendar edit needs a more specific target');
            setLastInterpreterReason(
              `Calendar reference resolver found ${resolution.candidates.length} plausible events, so QMeet refused to choose one.`,
            );
            const candidateText = resolution.candidates
              .slice(0, 5)
              .map((event) => `${event.time || 'All day'}: ${event.title}`)
              .join('; ');
            const assistantMsg = createAssistantMessage(
              now,
              `I found ${resolution.candidates.length} possible calendar events for "${promotedCalendarEditTargetCriteria.query}": ${candidateText}. Which one did you mean? No calendar change was made.`,
            );
            setMessages((prev) => [...prev, userMsg, assistantMsg]);
            speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
            return;
          }

          if (resolution.kind === 'none') {
            pendingCalendarEditTargetIdRef.current = null;
            pendingCalendarEditChangesRef.current = null;
            setTrackedInputRoute('Edit command had no target', commandMatch.command);
            setLastLocalCommand('No calendar event to edit');
            const assistantMsg = createAssistantMessage(
              now,
              `I could not find a calendar event ${promotedCalendarEditTargetCriteria.day} that confidently matches "${promotedCalendarEditTargetCriteria.query}"${promotedCalendarEditTargetCriteria.time ? ` at ${promotedCalendarEditTargetCriteria.time}` : ''}. No calendar change was made.`,
            );
            setMessages((prev) => [...prev, userMsg, assistantMsg]);
            speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
            return;
          }

          targetEditEvent = resolution.event;
          editResolutionKind = resolution.kind;
        } else {
          targetEditEvent = await findCalendarEventForChange();
        }

        if (!targetEditEvent) {
          pendingCalendarEditTargetIdRef.current = null;
          pendingCalendarEditChangesRef.current = null;
          setTrackedInputRoute('Edit command had no target', commandMatch.command);
          setLastLocalCommand('No calendar event to edit');
          const assistantMsg = createAssistantMessage(
            now,
            googleCalendarStatus?.connected
              ? 'I did not find a Google Calendar event to edit for the current view.'
              : 'I did not find a local calendar event to edit.',
          );
          setMessages((prev) => [...prev, userMsg, assistantMsg]);
          speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
          return;
        }

        const resolvedCalendarEditChanges = commandMatch.calendarEdit
          ? {
              ...commandMatch.calendarEdit,
              ...(commandMatch.calendarEdit.day &&
              !commandMatch.calendarEdit.time?.trim()
                ? { time: targetEditEvent.time || 'All day' }
                : {}),
            }
          : null;
        const editDescription = describeCalendarEditPayload(
          resolvedCalendarEditChanges ?? commandMatch.calendarEdit,
        );
        const frontendCommand = buildCalendarEditFrontendCommand(
          resolvedCalendarEditChanges ?? commandMatch.calendarEdit,
        );
        const sourceLabel = targetEditEvent.source === 'google' ? 'Google Calendar' : 'local';
        const confirmationPrompt = editResolutionKind === 'likely'
          ? `I found ${sourceLabel} event: ${targetEditEvent.time || 'All day'}: ${targetEditEvent.title}. Did you mean this event? Changes: ${editDescription}. Say "confirm" to update it, or "cancel" to stop.`
          : `I understood that as: update ${sourceLabel} event: ${targetEditEvent.time || '—'}: ${targetEditEvent.title}. Changes: ${editDescription}. Say "confirm" to update it, or "cancel" to stop.`;
        pendingTaskCompletionTargetsRef.current = [];
        pendingCalendarEditTargetIdRef.current = targetEditEvent.id;
        pendingCalendarEditChangesRef.current = resolvedCalendarEditChanges;
        if (promotedCalendarEditTargetCriteria?.day) {
          setCalendarView(promotedCalendarEditTargetCriteria.day);
        }
        setPendingInterpreterCommand({
          originalText: visibleUserText,
          frontendCommand,
          action: commandMatch.command,
          confidence: commandRoute === 'exact' ? 1 : 0.9,
          reason: 'Calendar event editing requires confirmation after one canonical event target has been resolved.',
        });
        setTrackedInputRoute(
          promotedCalendarEditTargetCriteria
            ? editResolutionKind === 'likely'
              ? 'Likely Calendar edit match needs confirmation'
              : 'Targeted Calendar edit needs confirmation'
            : commandRoute === 'exact'
              ? 'Exact Google Calendar edit needs confirmation'
              : 'Fuzzy Google Calendar edit needs confirmation',
        );
        setLastLocalCommand('Pending calendar edit');
        setLastInterpreterAction(commandRoute === 'exact' ? 'Not used' : commandMatch.command);
        setLastInterpreterFrontendCommand(frontendCommand);
        setLastInterpreterConfidence(commandRoute === 'exact' ? 1 : 0.9);
        setLastInterpreterReason(
          editResolutionKind === 'likely'
            ? 'One strong fuzzy Calendar event candidate was resolved and its identity is locked across confirmation.'
            : 'Exactly one canonical Calendar event was resolved and its identity is locked across confirmation.',
        );
        const assistantMsg = createAssistantMessage(now, confirmationPrompt);
        setMessages((prev) => [...prev, userMsg, assistantMsg]);
        speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
        return;
      }
      if (commandRoute !== 'confirmed' && isDestructiveLocalCommand(commandMatch.command)) {
        const isTaskCompletionCommand = commandMatch.command === 'mark-task-done';
        const taskCompletionTarget = isTaskCompletionCommand
          ? commandMatch.payload?.trim() ?? ''
          : '';
        const taskCompletionPreviewTargets = isTaskCompletionCommand
          ? resolveTaskCompletionPreviewTargets(
              taskCompletionTarget,
              memoryTasks,
              routingActiveSession,
            )
          : [];
        const taskCompletionPreviewDescription =
          describeTaskCompletionPreviewTargets(taskCompletionPreviewTargets);
        const frontendCommand = commandMatch.command === 'delete-calendar-event'
          ? buildCalendarDeleteFrontendCommand(commandMatch.calendarDelete)
          : commandMatch.command === 'mark-task-done' && taskCompletionTarget
            ? `mark task ${taskCompletionTarget} done`
            : getFrontendCommandForLocalCommand(commandMatch.command);
        const isCalendarDeleteCommand = commandMatch.command === 'delete-last-event' || commandMatch.command === 'delete-calendar-event';
        const targetedDeleteSourceEvents = commandMatch.command === 'delete-calendar-event'
          ? await getCalendarEventsForDeleteCriteria(commandMatch.calendarDelete)
          : [];
        const targetedDeleteResolution = commandMatch.command === 'delete-calendar-event'
          ? resolveCalendarEventReference(targetedDeleteSourceEvents, {
              day: commandMatch.calendarDelete?.day ?? calendarView,
              query: commandMatch.calendarDelete?.title ?? null,
              time: commandMatch.calendarDelete?.time ?? null,
            })
          : null;
        const ambiguousDeleteCandidates =
          targetedDeleteResolution?.kind === 'ambiguous'
            ? targetedDeleteResolution.candidates
            : [];
        const targetDeleteEvent = commandMatch.command === 'delete-last-event'
          ? await findCalendarEventForDeletion()
          : targetedDeleteResolution?.kind === 'exact' ||
              targetedDeleteResolution?.kind === 'likely'
            ? targetedDeleteResolution.event
            : null;
        const rawDeleteDescription = commandMatch.command === 'delete-calendar-event'
          ? describeCalendarDeletePayload(commandMatch.calendarDelete)
          : frontendCommand;
        const deleteDescription = rawDeleteDescription.replace(/[.?!\s]+$/g, '').trim() || rawDeleteDescription;
        const ambiguousDeletePrompt =
          commandMatch.command === 'delete-calendar-event' && ambiguousDeleteCandidates.length > 0
            ? `I found ${ambiguousDeleteCandidates.length} possible calendar events for ${deleteDescription}: ${ambiguousDeleteCandidates
                .slice(0, 5)
                .map((event, index) => `${index + 1}. ${event.time || '—'}: ${event.title}`)
                .join(' ')}${ambiguousDeleteCandidates.length > 5 ? ` Plus ${ambiguousDeleteCandidates.length - 5} more.` : ''} Which one did you mean? No calendar change was made.`
            : null;
        const confirmationPrompt = targetDeleteEvent
          ? targetedDeleteResolution?.kind === 'likely'
            ? `I found ${targetDeleteEvent.source === 'google' ? 'Google Calendar' : 'local'} event: ${targetDeleteEvent.time || 'All day'}: ${targetDeleteEvent.title}. Did you mean this event? If so, say "confirm" to delete it, or "cancel" to stop.`
            : `I understood that as: ${deleteDescription}. This will delete ${targetDeleteEvent.source === 'google' ? 'Google Calendar' : 'local'} event: ${targetDeleteEvent.time || '—'}: ${targetDeleteEvent.title}. Say "confirm" to run it, or "cancel" to stop.`
          : ambiguousDeletePrompt ?? (isCalendarDeleteCommand
            ? `I did not find a calendar event matching ${deleteDescription}.`
            : isTaskCompletionCommand && !taskCompletionPreviewDescription
              ? describeUnresolvedTaskCompletionRequest(taskCompletionTarget)
              : taskCompletionPreviewDescription
                ? `I understood that as: ${taskCompletionPreviewDescription}. This changes local task data. Say "confirm" to run it, or "cancel" to stop.`
                : `I understood that as: ${frontendCommand}. This changes or deletes local data. Say "confirm" to run it, or "cancel" to stop.`);
        if (commandMatch.command === 'delete-calendar-event' && ambiguousDeleteCandidates.length > 0) {
          pendingCalendarDeleteTargetIdRef.current = null;
          pendingCalendarEditTargetIdRef.current = null;
          pendingCalendarEditChangesRef.current = null;
          setTrackedInputRoute('Delete command had multiple plausible targets', commandMatch.command, frontendCommand);
          setLastLocalCommand('Calendar delete needs a more specific target');
          setLastInterpreterReason(
            'The shared Calendar reference resolver found multiple plausible events, so no target identity was selected and no confirmation was created.',
          );
          const assistantMsg = createAssistantMessage(now, confirmationPrompt);
          setMessages((prev) => [...prev, userMsg, assistantMsg]);
          speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
          return;
        }
        if (isCalendarDeleteCommand && !targetDeleteEvent) {
          pendingCalendarDeleteTargetIdRef.current = null;
          pendingCalendarEditTargetIdRef.current = null;
          pendingCalendarEditChangesRef.current = null;
          setTrackedInputRoute('Delete command had no credible target', commandMatch.command, frontendCommand);
          setLastLocalCommand('No matching calendar event to delete');
          const assistantMsg = createAssistantMessage(now, confirmationPrompt);
          setMessages((prev) => [...prev, userMsg, assistantMsg]);
          speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
          return;
        }
        if (isTaskCompletionCommand && !taskCompletionPreviewDescription) {
          setTrackedInputRoute('Task completion command had no target', commandMatch.command, frontendCommand);
          setLastLocalCommand('No matching open task to complete');
          setLastInterpreterReason(
            'Task completion reference did not resolve to an open task, so no confirmation was created.',
          );
          const assistantMsg = createAssistantMessage(now, confirmationPrompt);
          setMessages((prev) => [...prev, userMsg, assistantMsg]);
          speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
          return;
        }
        const destructiveConfirmationReason =
          commandMatch.command === 'delete-calendar-event' &&
          targetedDeleteResolution?.kind === 'likely'
            ? 'One strong fuzzy Calendar event candidate was resolved; its exact event identity is locked and still requires confirmation before deletion.'
            : naturalTaskCompletionTarget
              ? 'Natural completed-work language matched one open task linked to the active Focus, so QMeet paused for confirmation.'
              : commandRoute === 'exact'
                ? 'Exact frontend parser matched a destructive command, so QMeet paused for confirmation.'
                : 'Command interpreter mapped the input to a destructive command, so QMeet paused for confirmation.';
        pendingTaskCompletionTargetsRef.current = isTaskCompletionCommand
          ? taskCompletionPreviewTargets.map((task) => ({
              id: task.id,
              title: task.title,
            }))
          : [];
        if (
          commandMatch.command === 'delete-calendar-event' &&
          targetDeleteEvent &&
          commandMatch.calendarDelete?.day
        ) {
          setCalendarView(commandMatch.calendarDelete.day);
        }
        pendingCalendarDeleteTargetIdRef.current =
          commandMatch.command === 'delete-calendar-event' && targetDeleteEvent
            ? targetDeleteEvent.id
            : null;
        setPendingInterpreterCommand({
          originalText: visibleUserText,
          frontendCommand,
          action: commandMatch.command,
          confidence: commandRoute === 'exact' ? 1 : 0.9,
          reason: destructiveConfirmationReason,
        });
        setTrackedInputRoute(
          naturalTaskCompletionTarget
            ? 'Natural Focus task completion needs safety confirmation'
            : commandRoute === 'exact'
              ? 'Exact command needs safety confirmation'
              : 'Fuzzy interpreter needs safety confirmation',
        );
        setLastLocalCommand('Pending destructive command');
        setLastInterpreterAction(commandRoute === 'exact' ? 'Not used' : commandMatch.command);
        setLastInterpreterFrontendCommand(frontendCommand);
        setLastInterpreterConfidence(commandRoute === 'exact' ? 1 : 0.9);
        setLastInterpreterReason(destructiveConfirmationReason);
        const assistantMsg = createAssistantMessage(now, confirmationPrompt);
        setMessages((prev) => [...prev, userMsg, assistantMsg]);
        speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
        return;
      }
      const immutableConfirmedTaskTargets =
        commandRoute === 'confirmed' &&
        commandMatch.command === 'mark-task-done' &&
        confirmedTaskTargets.length > 0
          ? confirmedTaskTargets
              .map((target) =>
                memoryTasks.find(
                  (task) =>
                    task.id === target.id &&
                    !task.completedAt &&
                    task.title.trim() === target.title.trim(),
                ),
              )
              .filter((task): task is (typeof memoryTasks)[number] => Boolean(task))
          : [];
      if (
        commandRoute === 'confirmed' &&
        commandMatch.command === 'mark-task-done' &&
        confirmedTaskTargets.length > 0 &&
        immutableConfirmedTaskTargets.length !== confirmedTaskTargets.length
      ) {
        finishListening();
        setShowThinkingBubble(false);
        setTrackedInputRoute('Confirmed task identity changed');
        setLastLocalCommand('Confirmed task completion not executed');
        setLastInterpreterReason(
          'The task identity changed after confirmation was requested, so QMeet refused to re-resolve a different task.',
        );
        const assistantMsg = createAssistantMessage(
          now,
          'The task changed or is no longer open, so I did not complete a different task. Please ask me to complete it again.',
        );
        setMessages((prev) => [...prev, userMsg, assistantMsg]);
        speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
        return;
      }
      const confirmedFocusTaskTargets =
        commandRoute === 'confirmed' &&
        commandMatch.command === 'mark-task-done' &&
        routingActiveSession
          ? (immutableConfirmedTaskTargets.length > 0
              ? immutableConfirmedTaskTargets
              : resolveTaskCompletionPreviewTargets(
                  commandMatch.payload?.trim() ?? '',
                  memoryTasks,
                  routingActiveSession,
                )
            ).filter((task) =>
              routingActiveSession.linkedTaskIds.includes(task.id),
            )
          : [];
      let focusTaskProgressResult: FocusTaskProgressResult | null = null;
      if (routingActiveSession && confirmedFocusTaskTargets.length > 0) {
        const completedAt = new Date().toISOString();
        try {
          focusTaskProgressResult = await recordVerifiedFocusTaskProgress(
            routingActiveSession.id,
            confirmedFocusTaskTargets.map((task) => ({
              id: task.id,
              title: task.title,
              completedAt,
            })),
          );
        } catch (error) {
          console.warn(
            'Linked Focus task completion was not committed because canonical progress could not be verified.',
            error,
          );
          finishListening();
          setShowThinkingBubble(false);
          setTrackedInputRoute('Linked Focus task completion not committed');
          setLastLocalCommand('Confirmed Focus task completion not executed');
          setLastInterpreterReason(
            'Canonical Focus task progress did not verify, so the confirmed linked task was left open locally.',
          );
          const assistantMsg = createAssistantMessage(
            now,
            'I could not verify the linked Focus task completion, so no task was changed. Make sure the QMeet backend is running and try again.',
          );
          setMessages((prev) => [...prev, userMsg, assistantMsg]);
          pushResultToast({
            kind: 'warning',
            title: 'Task unchanged',
            detail: 'Canonical Focus progress could not be verified.',
          });
          speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
          return;
        }
      }
      let confirmationContent =
        commandMatch.command === 'close-generic' && activePanel === 'none'
          ? 'No panel is open.'
          : commandMatch.confirmation;
      let shouldSpeakConfirmation = voiceOutputEnabled;
      let confirmationSpeechRate = speechRate;
      let replaceMessages = false;
      let speechConfirmationContent = getBriefToolSpeech(commandMatch.command, confirmationContent);
      const verifiedCompletedAtByTaskId = new Map(
        (focusTaskProgressResult?.tasks ?? []).map((task) => [
          task.id,
          task.completedAt,
        ]),
      );
      const confirmedTaskCompletionResult =
        commandRoute === 'confirmed' &&
        commandMatch.command === 'mark-task-done' &&
        confirmedTaskTargets.length > 0
          ? completeConfirmedTaskTargets(
              memoryTasks,
              confirmedTaskTargets,
              verifiedCompletedAtByTaskId,
            )
          : null;
      const confirmedTaskCommandResult: SplitCommandResult =
        confirmedTaskCompletionResult?.ok
          ? {
              handled: true,
              confirmationContent:
                confirmedTaskCompletionResult.completedTasks.length === 1
                  ? `Marked task done:
- ${confirmedTaskCompletionResult.completedTasks[0].title}`
                  : `Marked ${confirmedTaskCompletionResult.completedTasks.length} tasks done:
${confirmedTaskCompletionResult.completedTasks
                      .map((task, index) => `${index + 1}. ${task.title}`)
                      .join('\n')}`,
              shouldSpeakConfirmation: voiceOutputEnabled,
            }
          : { handled: false };
      const notesCommandResult: SplitCommandResult = handleNotesCommand(commandMatch, {
        voiceOutputEnabled,
        setActivePanel,
        closePanel,
        saveNote,
        deleteLastNote,
        clearNotes,
        getNotesReadout,
      });
      const setPanelForMemoryCommand = (panel: ActivePanel) => {
        if (shouldSuppressLegacyFocusMemoryOpen(commandMatch.command, panel)) {
          return;
        }
        setActivePanel(panel);
      };
      const memoryCommandResult: SplitCommandResult = notesCommandResult.handled
        ? { handled: false }
        : confirmedTaskCommandResult.handled
          ? confirmedTaskCommandResult
          : await handleMemoryCommand(commandMatch, {
            voiceOutputEnabled,
            setActivePanel: setPanelForMemoryCommand,
            closePanel,
            getMemoryReadout,
            saveMemoryTask,
            markMemoryTaskDone,
            clearCompletedTasks,
            saveNote,
            deleteNote,
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
            editLastCalendarEvent:
              confirmedCalendarEditTargetId && commandMatch.command === 'edit-last-event'
                ? async (changes) => updateCalendarEvent(confirmedCalendarEditTargetId, changes)
                : editLastCalendarEvent,
            deleteCalendarEventByCriteria:
              confirmedCalendarDeleteTargetId && commandMatch.command === 'delete-calendar-event'
                ? async () => deleteCalendarEvent(confirmedCalendarDeleteTargetId)
                : deleteCalendarEventByCriteria,
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
      confirmationContent = normalizeVerifiedFocusToolReceipt(
        commandMatch,
        confirmationContent,
      );
      if (
        commandMatch.command === 'mark-task-done' &&
        focusTaskProgressResult?.verified
      ) {
        const progressDetail = focusTaskProgressResult.allLinkedTasksComplete
          ? 'Focus progress updated. All linked tasks are complete; review the Focus before completing it.'
          : focusTaskProgressResult.nextAction
            ? `Focus progress updated.\n\nNext: ${focusTaskProgressResult.nextAction}`
            : 'Focus progress updated.';
        confirmationContent = `${confirmationContent}\n\n${progressDetail}`;
      }
      speechConfirmationContent = getBriefToolSpeech(commandMatch.command, confirmationContent);
      const confirmationMsg = createAssistantMessage(now, confirmationContent, 'tool');
      if (replaceMessages) {
        setMessages([userMsg, confirmationMsg]);
      } else {
        setMessages((prev) => [...prev, userMsg, confirmationMsg]);
      }
      if (
        shouldRecordRecentAction(commandMatch.command) &&
        !hasFailureLanguage(confirmationContent)
      ) {
        addRecentAction(
          getCommandActionLabel(commandMatch.command),
          confirmationContent,
        );
      }
      pushResultToast(getResultToastForCommand(commandMatch.command, confirmationContent));
      speakAssistantText(speechConfirmationContent, {
        enabled: shouldSpeakConfirmation,
        rate: confirmationSpeechRate,
      });
      await continueAfterVerifiedToolUpdate({
        userMessage: continuationUserTextForTool,
        command: commandMatch.command,
        toolResult: confirmationContent,
        toolContext: splitCommandResult.continuationContext,
        recentMessages: messages,
        activePanel,
        voiceOutputEnabled,
        setMessages,
        setShowThinkingBubble,
        setOrbState,
        speakAssistantText,
      });
      return;
    }
    if (displayText) {
      finishListening();
      setShowThinkingBubble(false);
      setTrackedInputRoute('Interpreter command failed to execute');
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
    const semanticFocusLifecycle = promotedNonFocusToolOwner
      ? {
          kind: 'none' as const,
          confidence: promotedSingleIntent?.confidence ?? 0,
          reason: `Agent-first owner=${promotedNonFocusToolOwner}; Focus lifecycle preflight was not allowed to claim this tool turn.`,
          possibleMutation: false as const,
        }
      : semanticLifecyclePreflightBeforeCommandRouting ??
        await interpretSemanticFocusLifecycle(trimmed);
    const inferredFocusMutationGuard =
      await shouldGuardInferredSemanticFocusMutationWithShadow({
        shadowTurn,
        userMessage: trimmed,
        semanticKind: semanticFocusLifecycle.kind,
        mutationChangesTitle:
          semanticFocusLifecycle.kind === 'update' &&
          Boolean(semanticFocusLifecycle.commandMatch.focusSession?.title),
        activeFocusId: routingActiveSession?.id ?? null,
      });
    if (inferredFocusMutationGuard.guarded) {
      setPendingInterpreterCommand(null);
      setTrackedInputRoute(
        'Deterministic active-Focus mutation safety gate',
        'focus.help',
        '',
        'focus',
        'conversation',
      );
      setLastLocalCommand('No Focus mutation');
      setLastInterpreterAction('focus_help');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(null);
      setLastInterpreterReason(inferredFocusMutationGuard.reason);
      await sendNormalChat(
        trimmed,
        visibleUserText,
        shadowTurn,
        routingActiveSession?.id ?? null,
      );
      return;
    }
    if (
      semanticFocusLifecycle.kind === 'update' ||
      semanticFocusLifecycle.kind === 'start' ||
      semanticFocusLifecycle.kind === 'resume' ||
      semanticFocusLifecycle.kind === 'end' ||
      semanticFocusLifecycle.kind === 'complete'
    ) {
      const routeByKind = {
        update: {
          route: 'Semantic lifecycle Focus update',
          action: 'update_focus_session',
          frontendCommand: 'apply semantic focus update',
          reason: 'The semantic lifecycle classifier returned one typed Focus update.',
        },
        start: {
          route: 'Semantic lifecycle Focus start',
          action: 'start_focus_session',
          frontendCommand: 'apply semantic focus start',
          reason: 'The semantic lifecycle classifier returned one typed Focus start.',
        },
        resume: {
          route: 'Deterministic semantic lifecycle Focus resume',
          action: 'resume_focus_session',
          frontendCommand: 'apply verified focus resume',
          reason: 'The exact resume command passed deterministic lifecycle preflight.',
        },
        end: {
          route: 'Semantic lifecycle Focus end',
          action: 'end_focus_session',
          frontendCommand: 'apply semantic focus end',
          reason: 'The semantic lifecycle classifier returned one typed Focus end.',
        },
        complete: {
          route: 'Semantic lifecycle Focus completion',
          action: 'complete_focus_session',
          frontendCommand: 'apply semantic focus completion',
          reason: 'The semantic lifecycle classifier returned one typed Focus completion.',
        },
      } as const;
      const route = routeByKind[semanticFocusLifecycle.kind];
      setTrackedInputRoute(route.route);
      setLastInterpreterAction(route.action);
      setLastInterpreterFrontendCommand(route.frontendCommand);
      setLastInterpreterConfidence(semanticFocusLifecycle.confidence);
      setLastInterpreterReason(
        semanticFocusLifecycle.reason || route.reason,
      );
      return handleSend(
        route.frontendCommand,
        visibleUserText,
        'interpreter',
        semanticFocusLifecycle.commandMatch,
      );
    }
    if (semanticFocusLifecycle.kind === 'acknowledged') {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      setTrackedInputRoute('Semantic Focus lifecycle cancellation');
      setLastLocalCommand('Focus lifecycle change cancelled');
      setLastInterpreterAction('focus_lifecycle_cancelled');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(semanticFocusLifecycle.confidence);
      setLastInterpreterReason(semanticFocusLifecycle.reason);
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        semanticFocusLifecycle.message,
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      speakAssistantText(assistantMsg.content, {
        enabled: voiceOutputEnabled,
      });
      return;
    }
    if (
      semanticFocusLifecycle.kind === 'blocked' ||
      (semanticFocusLifecycle.kind === 'unavailable' &&
        (semanticFocusLifecycle.possibleMutation ||
          deferredSemanticFocusLifecycleMessage))
    ) {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      setTrackedInputRoute('Semantic Focus lifecycle change blocked safely');
      setLastLocalCommand('Focus lifecycle change not executed');
      setLastInterpreterAction('focus_lifecycle_change');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(semanticFocusLifecycle.confidence);
      setLastInterpreterReason(semanticFocusLifecycle.reason);
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        semanticFocusLifecycle.message,
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      pushResultToast({
        kind: 'warning',
        title: 'Focus unchanged',
        detail: semanticFocusLifecycle.message,
      });
      speakAssistantText(assistantMsg.content, {
        enabled: voiceOutputEnabled,
      });
      return;
    }
    if (deferredSemanticFocusLifecycleMessage) {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      setTrackedInputRoute('Focus lifecycle command blocked by semantic mismatch');
      setLastLocalCommand('Focus lifecycle change not executed');
      setLastInterpreterAction('focus_lifecycle_change');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(semanticFocusLifecycle.confidence);
      setLastInterpreterReason(
        semanticFocusLifecycle.reason ||
          'Focus lifecycle language was detected before command parsing, but semantic preflight did not confirm one safe lifecycle operation.',
      );
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        'I detected a possible Focus lifecycle change, but I could not safely determine one verified operation. No Focus change was made.',
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      pushResultToast({
        kind: 'warning',
        title: 'Focus unchanged',
        detail: assistantMsg.content,
      });
      speakAssistantText(assistantMsg.content, {
        enabled: voiceOutputEnabled,
      });
      return;
    }
    const stopUnverifiedCalendarWrite = (reason: string) => {
      finishListening();
      setShowThinkingBubble(false);
      setPendingInterpreterCommand(null);
      pendingTaskCompletionTargetsRef.current = [];
      setTrackedInputRoute(
        'Calendar write not safely resolved',
        deferredCalendarWriteAction ?? 'calendar-write',
      );
      setLastLocalCommand('Calendar write not executed');
      setLastInterpreterAction(deferredCalendarWriteAction ?? 'calendar-write');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(promotedSingleIntent?.confidence ?? null);
      setLastInterpreterReason(reason);
      if (!chatActive) setChatActive(true);
      const now = Date.now();
      const userMsg = createUserMessage(now, visibleUserText);
      const assistantMsg = createAssistantMessage(
        now,
        'I understood this as a Calendar change, but I could not safely map it to one existing Calendar write command. No calendar change was made.',
      );
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      pushResultToast({
        kind: 'warning',
        title: 'Calendar unchanged',
        detail: assistantMsg.content,
      });
      speakAssistantText(assistantMsg.content, { enabled: voiceOutputEnabled });
    };

    try {
      const interpretedCommand = await interpretCommandIntent(trimmed);
      const interpretedCalendarWriteAction = interpretedCommand.frontendCommand
        ? parseVerifiedCalendarWriteAction(interpretedCommand.frontendCommand)
        : null;
      if (
        deferredCalendarWriteAction &&
        interpretedCommand.intent === 'command' &&
        interpretedCommand.frontendCommand &&
        interpretedCalendarWriteAction !== deferredCalendarWriteAction
      ) {
        stopUnverifiedCalendarWrite(
          `Unified agent classified ${deferredCalendarWriteAction}, but the legacy interpreter produced ${interpretedCalendarWriteAction ?? 'a non-Calendar or unparseable command'}. No write was executed.`,
        );
        return;
      }
      if (
        interpretedCommand.intent === 'command' &&
        interpretedCommand.frontendCommand &&
        interpretedCommand.confidence >= COMMAND_INTERPRETER_EXECUTE_THRESHOLD &&
        isDestructiveInterpreterCommand(interpretedCommand.frontendCommand)
      ) {
        const parsedInterpreterDestructiveCommand = parseCommand(
          interpretedCommand.frontendCommand,
        );
        if (parsedInterpreterDestructiveCommand?.command === 'delete-calendar-event') {
          setTrackedInputRoute(
            'Fuzzy Calendar delete needs deterministic target resolution',
            interpretedCommand.action,
            interpretedCommand.frontendCommand,
          );
          setLastInterpreterAction(interpretedCommand.action);
          setLastInterpreterFrontendCommand(interpretedCommand.frontendCommand);
          setLastInterpreterConfidence(interpretedCommand.confidence);
          setLastInterpreterReason(
            interpretedCommand.reason ||
              'Interpreter mapped fuzzy input to targeted Calendar deletion; canonical Calendar state must resolve the target before confirmation.',
          );
          return handleSend(
            interpretedCommand.frontendCommand,
            visibleUserText,
            'interpreter',
          );
        }
        finishListening();
        setShowThinkingBubble(false);
        pendingTaskCompletionTargetsRef.current = [];
        setPendingInterpreterCommand({
          originalText: visibleUserText,
          frontendCommand: interpretedCommand.frontendCommand,
          action: interpretedCommand.action,
          confidence: interpretedCommand.confidence,
          reason: interpretedCommand.reason || 'Interpreter mapped fuzzy input to a destructive frontend command.',
        });
        setTrackedInputRoute(
          'Fuzzy interpreter needs safety confirmation',
          interpretedCommand.action,
          interpretedCommand.frontendCommand,
        );
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
        setTrackedInputRoute(
          'Fuzzy interpreter command',
          interpretedCommand.action,
          interpretedCommand.frontendCommand,
        );
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
        setTrackedInputRoute(
          'Interpreter needs confirmation',
          interpretedCommand.action,
          interpretedCommand.frontendCommand,
        );
        setLastLocalCommand('Interpreter clarification');
        setLastInterpreterAction(interpretedCommand.action);
        setLastInterpreterFrontendCommand(interpretedCommand.frontendCommand);
        setLastInterpreterConfidence(interpretedCommand.confidence);
        setLastInterpreterReason(interpretedCommand.reason || 'Interpreter confidence was below the automatic execution threshold.');
        const destructiveCommand = isDestructiveInterpreterCommand(interpretedCommand.frontendCommand);
        if (destructiveCommand) {
          pendingTaskCompletionTargetsRef.current = [];
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
      if (deferredCalendarWriteAction) {
        stopUnverifiedCalendarWrite(
          interpretedCommand.reason ||
            'The unified agent identified a Calendar write, but the legacy interpreter did not return one executable Calendar mutation.',
        );
        return;
      }
      setPendingInterpreterCommand(null);
      setTrackedInputRoute('Normal chat');
      setLastLocalCommand('No local command');
      setLastInterpreterAction(interpretedCommand.action || 'none');
      setLastInterpreterFrontendCommand(interpretedCommand.frontendCommand || 'None');
      setLastInterpreterConfidence(interpretedCommand.confidence);
      setLastInterpreterReason(interpretedCommand.reason || 'Interpreter classified the input as normal chat.');
    } catch (error) {
      if (deferredCalendarWriteAction) {
        console.warn('Command interpreter unavailable for Calendar write:', error);
        stopUnverifiedCalendarWrite(getInterpreterUnavailableReason(error));
        return;
      }
      console.warn('Command interpreter unavailable, falling back to chat:', error);
      setPendingInterpreterCommand(null);
      setTrackedInputRoute('Interpreter unavailable → normal chat');
      setLastLocalCommand('No local command');
      setLastInterpreterAction('Error');
      setLastInterpreterFrontendCommand('None');
      setLastInterpreterConfidence(null);
      setLastInterpreterReason(getInterpreterUnavailableReason(error));
    }
    await sendNormalChat(
      trimmed,
      visibleUserText,
      shadowTurn,
      routingActiveSession?.id ?? null,
    );
  }, [chatActive, activePanel, calendarView, calendarEvents, voiceOutputEnabled, speechRate, lastHeardTranscript, lastNormalizedTranscript, lastLocalCommand, pendingInterpreterCommand, handleEndChat, finishListening, closePanel, goHome, stopCurrentSpeech, cancelActiveResponse, speakAssistantText, setVoiceOutput, adjustSpeechRate, saveNote, getNotesReadout, deleteLastNote, clearNotes, saveMemoryTask, memoryTasks, activeSession, reconcileFocusProjection, markMemoryTaskDone, clearCompletedTasks, getMemoryReadout, saveCalendarEvent, getCalendarReadout, deleteCalendarEvent, deleteLastCalendarEvent, deleteCalendarEventByCriteria, getCalendarEventsForDeleteCriteria, findCalendarEventForDeletion, findCalendarEventForChange, getNextCalendarEventForDeletion, getNextCalendarEventForChange, updateCalendarEvent, editLastCalendarEvent, clearCalendarEvents, refreshGoogleCalendar, runWebSearch, clearSearchState, searchError, pushResultToast, addRecentAction, googleCalendarStatus?.connected, googleCalendarStatus?.writeEnabled, googleCalendarEvents, messages, sendNormalChat]);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handleLegacyFocusEndRequest = (event: Event) => {
      const detail = (event as CustomEvent<{ action?: unknown }>).detail;
      if (detail?.action !== 'end') return;
      // MemoryOverlay still clears the legacy local projection before it emits
      // this UI-intent event. Restore the verified projection captured by App
      // before routing so readVerifiedFocusProjection() cannot observe a false
      // "no active Focus" state during the native terminal guard. handleSend
      // immediately reconciles this projection against canonical /api/focus/state.
      if (activeSession) {
        applyVerifiedFocusProjection(activeSession);
      }
      setActivePanel('none');
      void handleSend('end focus anyway', 'End focus');
    };
    window.addEventListener(
      'qmeet-active-session-command',
      handleLegacyFocusEndRequest as EventListener,
    );
    return () => {
      window.removeEventListener(
        'qmeet-active-session-command',
        handleLegacyFocusEndRequest as EventListener,
      );
    };
  }, [activeSession, handleSend]);
  const handleOrbClick = useCallback(() => {
    // If QMeet is actively generating/streaming, tapping the orb should cancel
    // that response instead of starting a new listening session.
    if (responseActive || conversationResponseActive) {
      cancelActiveResponse();
      cancelActiveConversationLane();
      setConversationResponseActive(false);
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
  }, [orbState, responseActive, conversationResponseActive, handleSend, stopCurrentSpeech, cancelActiveResponse, setMessages, startListening]);
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
