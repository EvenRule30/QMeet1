import {
  type ChangeEvent,
  type RefObject,
  useCallback,
  useEffect,
  useState,
} from 'react';
import type {
  ActiveSession,
  MemoryTask,
  RecentFocusSession,
  VisualContext,
  VisualObservation,
} from '../types';
import type { ResultToast } from '../lib/toastUtils';
import { formatMemoryTime } from '../lib/memoryUtils';
import {
  getRecentFocusSessions,
  clearVisualContext,
  deleteVisualObservationById,
  getVisualContext,
} from '../api';

type MemorySyncState = 'local' | 'syncing' | 'synced' | 'error';
type ToastInput = Omit<ResultToast, 'id' | 'createdAt'> | null;

type ActiveSessionCommandEventDetail = {
  action: 'start' | 'update' | 'end';
  title?: string;
  mode?: ActiveSession['mode'];
  goal?: string;
};

type ActiveSessionStateEventDetail = {
  activeSession: ActiveSession | null;
};

type PromptCommandEventDetail = {
  command: string;
};

type VisualContextStateEventDetail = {
  visualContext: VisualContext;
};

type MemoryOverlayProps = {
  memorySyncState: MemorySyncState;
  memorySyncMessage: string;
  memoryImportInputRef: RefObject<HTMLInputElement>;
  memoryTaskDraft: string;
  setMemoryTaskDraft: (value: string) => void;
  memoryTasks: MemoryTask[];
  onExportMemory: () => void;
  onImportMemoryFile: (event: ChangeEvent<HTMLInputElement>) => void;
  // Retained in the component contract while App/useMemoryContext are cleaned up
  // separately. Phase 20U intentionally does not expose these legacy broad-reset
  // callbacks in the UI because they can imply canonical Focus deletion.
  onClearAllMemory: () => void;
  onResetTasksOnly: () => void;
  onResetNotesOnly: () => void;
  onResetRecentContextOnly: () => void;
  onSaveMemoryTaskDraft: () => void;
  markMemoryTaskDoneById: (taskId: string) => MemoryTask | null;
  deleteMemoryTask: (taskId: string) => MemoryTask | null;
  reopenMemoryTask: (taskId: string) => MemoryTask | null;
  clearCompletedTasks: () => number;
  addRecentAction: (label: string, detail: string) => void;
  pushResultToast: (toastInput: ToastInput) => void;
  onClose: () => void;
};

const ACTIVE_SESSION_STORAGE_KEY = 'qmeet-active-session';
const ACTIVE_SESSION_SESSION_STORAGE_KEY = 'qmeet-active-session-live';
const VISUAL_CONTEXT_STORAGE_KEY = 'qmeet-visual-context';
const ACTIVE_SESSION_COMMAND_EVENT = 'qmeet-active-session-command';
const ACTIVE_SESSION_STATE_EVENT = 'qmeet-active-session-state';
const QMEET_PROMPT_COMMAND_EVENT = 'qmeet-prompt-command';
const VISUAL_CONTEXT_STATE_EVENT = 'qmeet-visual-context-state';

function normalizeActiveSession(value: unknown): ActiveSession | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<ActiveSession>;
  if (typeof candidate.title !== 'string' || !candidate.title.trim()) {
    return null;
  }

  const now = new Date().toISOString();
  const mode =
    candidate.mode === 'coding' ||
    candidate.mode === 'meeting' ||
    candidate.mode === 'planning' ||
    candidate.mode === 'research' ||
    candidate.mode === 'personal' ||
    candidate.mode === 'general'
      ? candidate.mode
      : 'general';

  return {
    id:
      typeof candidate.id === 'string' && candidate.id
        ? candidate.id
        : `session-${Date.now()}`,
    title: candidate.title.trim(),
    mode,
    goal: typeof candidate.goal === 'string' ? candidate.goal : '',
    startedAt:
      typeof candidate.startedAt === 'string' ? candidate.startedAt : now,
    updatedAt:
      typeof candidate.updatedAt === 'string' ? candidate.updatedAt : now,
    pinnedNoteIds: Array.isArray(candidate.pinnedNoteIds)
      ? candidate.pinnedNoteIds.filter(
          (item): item is string => typeof item === 'string',
        )
      : [],
    linkedTaskIds: Array.isArray(candidate.linkedTaskIds)
      ? candidate.linkedTaskIds.filter(
          (item): item is string => typeof item === 'string',
        )
      : [],
    ...(typeof candidate.summary === 'string'
      ? { summary: candidate.summary }
      : candidate.summary === null
        ? { summary: null }
        : {}),
  };
}

function normalizeRecentFocusSession(value: unknown): RecentFocusSession | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<RecentFocusSession>;
  if (typeof candidate.title !== 'string' || !candidate.title.trim()) {
    return null;
  }

  const now = new Date().toISOString();
  const mode =
    candidate.mode === 'coding' ||
    candidate.mode === 'meeting' ||
    candidate.mode === 'planning' ||
    candidate.mode === 'research' ||
    candidate.mode === 'personal' ||
    candidate.mode === 'general'
      ? candidate.mode
      : 'general';

  return {
    id:
      typeof candidate.id === 'string' && candidate.id
        ? candidate.id
        : `session-${Date.now()}`,
    title: candidate.title.trim(),
    mode,
    goal: typeof candidate.goal === 'string' ? candidate.goal : '',
    startedAt:
      typeof candidate.startedAt === 'string' ? candidate.startedAt : now,
    endedAt: typeof candidate.endedAt === 'string' ? candidate.endedAt : now,
    pinnedNoteIds: Array.isArray(candidate.pinnedNoteIds)
      ? candidate.pinnedNoteIds.filter(
          (item): item is string => typeof item === 'string',
        )
      : [],
    linkedTaskIds: Array.isArray(candidate.linkedTaskIds)
      ? candidate.linkedTaskIds.filter(
          (item): item is string => typeof item === 'string',
        )
      : [],
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

function createEmptyVisualContext(): VisualContext {
  return {
    enabled: false,
    lastObservation: null,
    recentObservations: [],
  };
}

function isVisualContextSource(
  value: unknown,
): value is VisualObservation['source'] {
  return value === 'camera' || value === 'screen' || value === 'manual';
}

function normalizeVisualObservation(value: unknown): VisualObservation | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<VisualObservation>;
  if (typeof candidate.summary !== 'string' || !candidate.summary.trim()) {
    return null;
  }

  return {
    id:
      typeof candidate.id === 'string' && candidate.id.trim()
        ? candidate.id
        : `visual-${Date.now()}`,
    source: isVisualContextSource(candidate.source) ? candidate.source : 'manual',
    summary: candidate.summary.trim(),
    capturedAt:
      typeof candidate.capturedAt === 'string'
        ? candidate.capturedAt
        : new Date().toISOString(),
    ...(typeof candidate.confidence === 'number' &&
    Number.isFinite(candidate.confidence)
      ? { confidence: Math.max(0, Math.min(1, candidate.confidence)) }
      : {}),
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

function formatVisualSource(source: VisualObservation['source']) {
  return source.charAt(0).toUpperCase() + source.slice(1);
}

function getVisualObservationMeta(observation: VisualObservation) {
  const pieces = [
    formatVisualSource(observation.source),
    formatMemoryTime(observation.capturedAt),
  ];

  if (typeof observation.confidence === 'number') {
    pieces.push(`${Math.round(observation.confidence * 100)}% confidence`);
  }
  if (observation.relatedFocusId) {
    pieces.push('linked to focus');
  }

  return pieces.join(' · ');
}

function getFocusLinkedVisualObservations(
  activeSession: ActiveSession | null,
  visualContext: VisualContext,
) {
  if (!activeSession) return [];
  return visualContext.recentObservations.filter(
    (observation) => observation.relatedFocusId === activeSession.id,
  );
}

function readStoredActiveSession(): ActiveSession | null {
  if (typeof window === 'undefined') return null;

  try {
    const rawSession =
      window.localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY) ??
      window.sessionStorage.getItem(ACTIVE_SESSION_SESSION_STORAGE_KEY);
    if (!rawSession) return null;
    return normalizeActiveSession(JSON.parse(rawSession));
  } catch {
    return null;
  }
}

function clearStoredActiveSession() {
  if (typeof window === 'undefined') return;

  try {
    window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
    window.sessionStorage.removeItem(ACTIVE_SESSION_SESSION_STORAGE_KEY);
  } catch {
    // Local/session storage can fail in restricted browser modes.
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

function dispatchVisualContextState(visualContext: VisualContext) {
  if (typeof window === 'undefined') return;

  try {
    window.localStorage.setItem(
      VISUAL_CONTEXT_STORAGE_KEY,
      JSON.stringify(visualContext),
    );
  } catch (error) {
    console.error('Failed to write visual context fallback:', error);
  }

  window.dispatchEvent(
    new CustomEvent<VisualContextStateEventDetail>(VISUAL_CONTEXT_STATE_EVENT, {
      detail: { visualContext },
    }),
  );
}

function dispatchActiveSessionCommand(detail: ActiveSessionCommandEventDetail) {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent<ActiveSessionCommandEventDetail>(
      ACTIVE_SESSION_COMMAND_EVENT,
      { detail },
    ),
  );
}

function formatSessionMode(mode: ActiveSession['mode']) {
  return mode.charAt(0).toUpperCase() + mode.slice(1);
}

function getFocusAgeLabel(activeSession: ActiveSession | null) {
  if (!activeSession) return 'No focus';

  const startedAt = new Date(activeSession.startedAt).getTime();
  if (!Number.isFinite(startedAt)) return 'Active';

  const minutes = Math.max(0, Math.round((Date.now() - startedAt) / 60000));
  if (minutes < 1) return 'Just started';
  if (minutes < 60) return `${minutes}m active`;

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0
    ? `${hours}h ${remainingMinutes}m active`
    : `${hours}h active`;
}

function MemoryOverlayStyles() {
  return (
    <style>{`
      .memory-panel-body {
        gap: 0.75rem;
      }

      .memory-hero {
        align-items: flex-start;
        gap: 0.75rem;
      }

      .memory-title {
        line-height: 1.35;
      }

      .memory-overview-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.55rem;
      }

      .memory-stat-card {
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 0.82rem;
        background: rgba(8, 20, 32, 0.42);
        padding: 0.58rem 0.62rem;
      }

      .memory-stat-label {
        color: rgba(148, 163, 184, 0.82);
        font-size: 0.63rem;
        font-weight: 700;
        letter-spacing: 0.11em;
        text-transform: uppercase;
      }

      .memory-stat-value {
        margin-top: 0.22rem;
        color: rgba(236, 253, 245, 0.96);
        font-size: 0.86rem;
        font-weight: 760;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .memory-focus-card {
        border-color: rgba(45, 212, 191, 0.26);
        background: linear-gradient(135deg, rgba(20, 184, 166, 0.12), rgba(8, 20, 32, 0.4));
      }

      .memory-focus-goal {
        border-left: 2px solid rgba(45, 212, 191, 0.52);
        padding-left: 0.6rem;
        margin: 0.55rem 0;
      }

      .memory-control-note {
        border: 1px solid rgba(251, 191, 36, 0.18);
        border-radius: 0.74rem;
        background: rgba(120, 53, 15, 0.12);
        color: rgba(254, 243, 199, 0.82);
        padding: 0.52rem 0.62rem;
        font-size: 0.78rem;
        line-height: 1.4;
      }

      .memory-action-item,
      .memory-task-copy {
        min-width: 0;
      }

      @media (max-width: 820px) {
        .memory-overview-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }
      }
    `}</style>
  );
}

function formatSessionRange(session: RecentFocusSession) {
  return `${formatMemoryTime(session.startedAt)} → ${formatMemoryTime(
    session.endedAt,
  )}`;
}

function getRecentFocusSessionMeta(session: RecentFocusSession) {
  const linkedTaskCount = session.linkedTaskIds.length;
  const pinnedNoteCount = session.pinnedNoteIds.length;
  const pieces = [
    `${formatSessionMode(session.mode)} mode`,
    `Ended ${formatMemoryTime(session.endedAt)}`,
  ];

  if (linkedTaskCount > 0) {
    pieces.push(
      `${linkedTaskCount} linked task${linkedTaskCount === 1 ? '' : 's'}`,
    );
  }
  if (pinnedNoteCount > 0 || session.summaryNoteId) {
    pieces.push('summary saved');
  }

  return pieces.join(' · ');
}

type FocusNudge = {
  id: string;
  title: string;
  detail: string;
  command: string;
  actionLabel: string;
};

function findLinkedTasks(
  activeSession: ActiveSession | null,
  memoryTasks: MemoryTask[],
) {
  if (!activeSession || activeSession.linkedTaskIds.length === 0) return [];
  const linkedIds = new Set(activeSession.linkedTaskIds);
  return memoryTasks.filter((task) => linkedIds.has(task.id));
}

function getFocusAgeMinutes(activeSession: ActiveSession | null) {
  if (!activeSession) return 0;
  const startedAt = new Date(activeSession.startedAt).getTime();
  if (!Number.isFinite(startedAt)) return 0;
  return Math.max(0, Math.round((Date.now() - startedAt) / 60000));
}

function buildFocusNudges(
  activeSession: ActiveSession | null,
  memoryTasks: MemoryTask[],
): FocusNudge[] {
  if (!activeSession) {
    return [
      {
        id: 'start-focus',
        title: 'Start with a focus session',
        detail:
          'Set the current work context so QMeet can connect chat, tasks, and notes.',
        command: 'start a focus session for …',
        actionLabel: 'Start focus',
      },
    ];
  }

  const nudges: FocusNudge[] = [];
  const linkedTasks = findLinkedTasks(activeSession, memoryTasks);
  const openLinkedTasks = linkedTasks.filter((task) => !task.completedAt);
  const completedLinkedTasks = linkedTasks.filter((task) => task.completedAt);
  const focusAgeMinutes = getFocusAgeMinutes(activeSession);

  if (!activeSession.goal.trim()) {
    nudges.push({
      id: 'set-goal',
      title: 'Add a goal',
      detail:
        'A goal makes focus-aware chat, summaries, and next steps more useful.',
      command: 'set my goal to …',
      actionLabel: 'Set goal',
    });
  }

  if (activeSession.goal.trim() && linkedTasks.length === 0) {
    nudges.push({
      id: 'make-tasks',
      title: 'Turn this focus into tasks',
      detail: 'Create a short checklist from the current focus and goal.',
      command: 'turn this focus into tasks',
      actionLabel: 'Create tasks',
    });
  }

  if (openLinkedTasks.length > 0) {
    nudges.push({
      id: 'next-linked-task',
      title: 'Next linked task',
      detail: openLinkedTasks[0].title,
      command: 'what should I do next for this focus',
      actionLabel: 'Ask next step',
    });
  }

  if (linkedTasks.length > 0 && openLinkedTasks.length === 0) {
    nudges.push({
      id: 'summarize-completed-focus',
      title: 'All linked tasks are done',
      detail: `You completed ${completedLinkedTasks.length} linked task${
        completedLinkedTasks.length === 1 ? '' : 's'
      }. Capture the outcome before ending the focus.`,
      command: 'save this focus as a note',
      actionLabel: 'Save note',
    });
  }

  if (
    activeSession.goal.trim() &&
    activeSession.pinnedNoteIds.length === 0 &&
    focusAgeMinutes >= 30
  ) {
    nudges.push({
      id: 'save-progress-note',
      title: 'Save a progress note',
      detail:
        'This focus has been active for a while and has not pinned a summary note yet.',
      command: 'save this focus as a note',
      actionLabel: 'Save note',
    });
  }

  if (nudges.length === 0) {
    nudges.push({
      id: 'keep-going',
      title: 'Keep momentum',
      detail:
        'Your focus has a goal and linked context. Ask QMeet for the next step when you are ready.',
      command: 'what should I do next for this focus',
      actionLabel: 'Ask QMeet',
    });
  }

  return nudges.slice(0, 3);
}

function promptForNudgeValue(nudge: FocusNudge): string | null {
  if (typeof window === 'undefined') return null;

  if (nudge.id === 'start-focus') {
    const title = window.prompt('What should this focus session be called?');
    const trimmedTitle = title?.trim();
    return trimmedTitle ? `start a focus session for ${trimmedTitle}` : null;
  }

  if (nudge.id === 'set-goal') {
    const goal = window.prompt('What goal should QMeet track for this focus?');
    const trimmedGoal = goal?.trim();
    return trimmedGoal ? `set my goal to ${trimmedGoal}` : null;
  }

  return null;
}

function resolveNudgeCommand(nudge: FocusNudge): string | null {
  if (nudge.command.includes('…')) {
    return promptForNudgeValue(nudge);
  }
  return nudge.command;
}

function dispatchPromptCommand(command: string) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent<PromptCommandEventDetail>(QMEET_PROMPT_COMMAND_EVENT, {
      detail: { command },
    }),
  );
}

function runFocusNudge(
  nudge: FocusNudge,
  pushResultToast: (toastInput: ToastInput) => void,
) {
  const command = resolveNudgeCommand(nudge);
  if (!command) return;

  dispatchPromptCommand(command);
  pushResultToast({
    kind: 'info',
    title: 'Nudge action',
    detail: command,
  });
}

function runFocusQuickAction(
  command: string,
  label: string,
  pushResultToast: (toastInput: ToastInput) => void,
) {
  dispatchPromptCommand(command);
  pushResultToast({
    kind: 'info',
    title: label,
    detail: command,
  });
}

export function MemoryOverlay({
  memorySyncState,
  memorySyncMessage,
  memoryImportInputRef,
  memoryTaskDraft,
  setMemoryTaskDraft,
  memoryTasks,
  onExportMemory,
  onImportMemoryFile,
  onResetTasksOnly,
  onResetNotesOnly,
  onSaveMemoryTaskDraft,
  markMemoryTaskDoneById,
  deleteMemoryTask,
  reopenMemoryTask,
  clearCompletedTasks,
  addRecentAction,
  pushResultToast,
  onClose,
}: MemoryOverlayProps) {
  const [activeSession, setActiveSession] = useState(readStoredActiveSession);
  const [recentFocusSessions, setRecentFocusSessions] = useState<
    RecentFocusSession[]
  >([]);
  const [recentFocusSessionMessage, setRecentFocusSessionMessage] = useState(
    'Loading recent focus sessions...',
  );
  const [visualContext, setVisualContext] = useState<VisualContext>(
    createEmptyVisualContext,
  );
  const [visualContextMessage, setVisualContextMessage] = useState(
    'Loading visual context...',
  );

  const openTasks = memoryTasks.filter((task) => !task.completedAt);
  const completedTasks = memoryTasks.filter((task) => task.completedAt);
  const focusNudges = buildFocusNudges(activeSession, memoryTasks);
  const focusLinkedVisualObservations = getFocusLinkedVisualObservations(
    activeSession,
    visualContext,
  );

  const loadRecentFocusSessions = useCallback(async () => {
    try {
      const response = await getRecentFocusSessions();
      setRecentFocusSessions(
        normalizeRecentFocusSessions(response.recentFocusSessions),
      );
      setRecentFocusSessionMessage(
        response.message || 'Recent focus sessions loaded.',
      );
    } catch (error) {
      setRecentFocusSessionMessage(
        error instanceof Error
          ? error.message
          : 'Recent focus sessions unavailable.',
      );
    }
  }, []);

  const loadVisualContext = useCallback(async () => {
    try {
      const response = await getVisualContext();
      setVisualContext(normalizeVisualContext(response.visualContext));
      setVisualContextMessage(response.message || 'Visual context loaded.');
    } catch (error) {
      setVisualContextMessage(
        error instanceof Error ? error.message : 'Visual context unavailable.',
      );
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const refreshStoredSession = () => {
      setActiveSession(readStoredActiveSession());
    };
    const handleActiveSessionState = (event: Event) => {
      const detail = (event as CustomEvent<ActiveSessionStateEventDetail>)
        .detail;
      setActiveSession(normalizeActiveSession(detail?.activeSession ?? null));
    };
    const handleStorage = (event: StorageEvent) => {
      if (event.key === ACTIVE_SESSION_STORAGE_KEY) {
        refreshStoredSession();
      }
    };

    window.addEventListener(ACTIVE_SESSION_STATE_EVENT, handleActiveSessionState);
    window.addEventListener('storage', handleStorage);
    const intervalId = window.setInterval(refreshStoredSession, 750);

    return () => {
      window.removeEventListener(
        ACTIVE_SESSION_STATE_EVENT,
        handleActiveSessionState,
      );
      window.removeEventListener('storage', handleStorage);
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    loadRecentFocusSessions();
  }, [loadRecentFocusSessions, activeSession?.id]);

  useEffect(() => {
    loadVisualContext();
  }, [loadVisualContext]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleVisualContextState = (event: Event) => {
      const detail = (event as CustomEvent<VisualContextStateEventDetail>)
        .detail;
      setVisualContext(normalizeVisualContext(detail?.visualContext));
      setVisualContextMessage('Visual context updated.');
    };

    window.addEventListener(VISUAL_CONTEXT_STATE_EVENT, handleVisualContextState);
    return () => {
      window.removeEventListener(
        VISUAL_CONTEXT_STATE_EVENT,
        handleVisualContextState,
      );
    };
  }, []);

  const handleDeleteVisualObservation = async (observationId: string) => {
    try {
      const response = await deleteVisualObservationById(observationId);
      const nextVisualContext = normalizeVisualContext(response.visualContext);
      setVisualContext(nextVisualContext);
      dispatchVisualContextState(nextVisualContext);
      pushResultToast({
        kind: 'warning',
        title: 'Observation removed',
        detail: 'Removed one visual observation.',
      });
    } catch (error) {
      pushResultToast({
        kind: 'error',
        title: 'Visual delete failed',
        detail:
          error instanceof Error ? error.message : 'Could not remove observation.',
      });
    }
  };

  const handleClearVisualContext = async () => {
    const confirmed = window.confirm('Clear saved visual context observations?');
    if (!confirmed) return;

    try {
      const response = await clearVisualContext();
      const nextVisualContext = normalizeVisualContext(response.visualContext);
      setVisualContext(nextVisualContext);
      dispatchVisualContextState(nextVisualContext);
      setVisualContextMessage(response.message || 'Visual context cleared.');
      const removedCount =
        response.removedVisualObservationCount ?? response.removedCount ?? 0;
      pushResultToast({
        kind: 'warning',
        title: 'Visual context cleared',
        detail:
          removedCount > 0
            ? `${removedCount} observation${removedCount === 1 ? '' : 's'} removed.`
            : 'No visual observations to clear.',
      });
    } catch (error) {
      pushResultToast({
        kind: 'error',
        title: 'Visual clear failed',
        detail:
          error instanceof Error ? error.message : 'Could not clear visual context.',
      });
    }
  };

  return (
    <div className="panel-overlay">
      <MemoryOverlayStyles />
      <div className="panel-content memory-panel">
        <div className="panel-header">Memory</div>
        <div className="panel-body memory-panel-body">
          <div className="memory-hero">
            <div>
              <div className="memory-kicker">Backend Memory</div>
              <div className="memory-title">
                Focus, tasks, notes, visuals, and recent work context sync to
                FastAPI with browser fallback.
              </div>
            </div>
            <div className={`memory-chip memory-sync-${memorySyncState}`}>
              {memorySyncState === 'synced'
                ? 'Synced'
                : memorySyncState === 'syncing'
                  ? 'Syncing'
                  : 'Local'}
            </div>
          </div>

          <div className="memory-overview-grid" aria-label="Memory overview">
            <div className="memory-stat-card memory-focus-card">
              <div className="memory-stat-label">Focus</div>
              <div className="memory-stat-value">
                {activeSession ? activeSession.title : 'None'}
              </div>
            </div>
            <div className="memory-stat-card">
              <div className="memory-stat-label">Tasks</div>
              <div className="memory-stat-value">
                {openTasks.length} open · {completedTasks.length} done
              </div>
            </div>
            <div className="memory-stat-card">
              <div className="memory-stat-label">Sessions</div>
              <div className="memory-stat-value">
                {recentFocusSessions.length} recent
              </div>
            </div>
            <div className="memory-stat-card">
              <div className="memory-stat-label">Visuals</div>
              <div className="memory-stat-value">
                {visualContext.recentObservations.length} saved
              </div>
            </div>
          </div>

          <div className="panel-section memory-sync-section">
            <div className="panel-section-title">Current Focus</div>
            {activeSession ? (
              <div className="memory-list">
                <div className="memory-action-item memory-focus-card">
                  <div className="memory-task-copy">
                    <div className="memory-action-title">
                      {activeSession.title}
                    </div>
                    <div className="memory-task-meta">
                      {formatSessionMode(activeSession.mode)} mode ·{' '}
                      {getFocusAgeLabel(activeSession)} · Started{' '}
                      {formatMemoryTime(activeSession.startedAt)}
                    </div>
                    <p className="panel-section-text memory-focus-goal">
                      {activeSession.goal
                        ? `Goal: ${activeSession.goal}`
                        : 'No goal set yet. Say “set my goal to …” to add one.'}
                    </p>
                    <div className="panel-action-row">
                      <button
                        className="panel-action-btn"
                        type="button"
                        onClick={() =>
                          runFocusQuickAction(
                            'turn this focus into tasks',
                            'Focus tasks',
                            pushResultToast,
                          )
                        }
                      >
                        Create tasks
                      </button>
                      <button
                        className="panel-action-btn"
                        type="button"
                        onClick={() =>
                          runFocusQuickAction(
                            'save this focus as a note',
                            'Focus note',
                            pushResultToast,
                          )
                        }
                      >
                        Save note
                      </button>
                      <button
                        className="panel-action-btn"
                        type="button"
                        disabled={!visualContext.lastObservation}
                        onClick={() =>
                          runFocusQuickAction(
                            'save this visual context to my focus',
                            'Link visual',
                            pushResultToast,
                          )
                        }
                      >
                        Link visual
                      </button>
                      <button
                        className="panel-action-btn"
                        type="button"
                        onClick={() =>
                          runFocusQuickAction(
                            'end and summarize this focus',
                            'End with summary',
                            pushResultToast,
                          )
                        }
                      >
                        End with summary
                      </button>
                    </div>

                    {focusLinkedVisualObservations.length > 0 && (
                      <div className="memory-list">
                        {focusLinkedVisualObservations
                          .slice(0, 3)
                          .map((observation) => (
                            <div
                              className="memory-action-item"
                              key={observation.id}
                            >
                              <div className="memory-task-copy">
                                <div className="memory-action-title">
                                  Linked {formatVisualSource(observation.source)}{' '}
                                  visual
                                </div>
                                <div className="memory-task-meta">
                                  {getVisualObservationMeta(observation)}
                                </div>
                                <p className="panel-section-text">
                                  {observation.summary}
                                </p>
                              </div>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>

                  <div className="memory-task-actions">
                    <button
                      className="memory-task-delete-btn"
                      type="button"
                      onClick={() => {
                        clearStoredActiveSession();
                        setActiveSession(null);
                        dispatchActiveSessionState(null);
                        dispatchActiveSessionCommand({ action: 'end' });
                      }}
                    >
                      End
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <p className="panel-section-text">
                No active focus. Say “start a focus for my Java class” or “I am
                working on the UI cleanup” and I will use it as background
                context.
              </p>
            )}
          </div>

          <div className="panel-section memory-sync-section">
            <div className="panel-section-title">Recent Focus Sessions</div>
            <div className="memory-control-note">
              Focus history is read-only in Memory. End or complete the current
              Focus through the verified Focus lifecycle; historical sessions
              are retained for recall, resume, and audit continuity.
            </div>
            {recentFocusSessions.length === 0 ? (
              <p className="panel-section-text">
                {recentFocusSessionMessage ||
                  'Ended focus sessions will appear here.'}
              </p>
            ) : (
              <div className="memory-list">
                {recentFocusSessions.slice(0, 5).map((session) => (
                  <div className="memory-action-item" key={session.id}>
                    <div className="memory-task-copy">
                      <div className="memory-action-title">{session.title}</div>
                      <div className="memory-task-meta">
                        {getRecentFocusSessionMeta(session)}
                      </div>
                      <p className="panel-section-text">
                        {session.goal
                          ? `Goal: ${session.goal}`
                          : 'No goal was saved for this focus.'}
                      </p>
                      <div className="memory-task-meta">
                        {formatSessionRange(session)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="panel-section memory-sync-section">
            <div className="panel-section-title">Visual Context</div>
            <p className="panel-section-text">
              {visualContext.enabled
                ? 'Visual context is enabled for future camera or screen observations.'
                : 'Visual context is ready but disabled until a camera, screen, or manual observation source is connected.'}
            </p>
            {visualContext.lastObservation ? (
              <div className="memory-list">
                <div className="memory-action-item">
                  <div className="memory-task-copy">
                    <div className="memory-action-title">Last observation</div>
                    <div className="memory-task-meta">
                      {getVisualObservationMeta(visualContext.lastObservation)}
                    </div>
                    <p className="panel-section-text">
                      {visualContext.lastObservation.summary}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <p className="panel-section-text">
                {visualContextMessage ||
                  'No visual observations saved yet. Open Camera or upload an image to create one.'}
              </p>
            )}

            {visualContext.recentObservations.length > 0 && (
              <div className="memory-list">
                {visualContext.recentObservations
                  .slice(0, 4)
                  .map((observation) => (
                    <div className="memory-action-item" key={observation.id}>
                      <div className="memory-task-copy">
                        <div className="memory-action-title">
                          {formatVisualSource(observation.source)} observation
                        </div>
                        <div className="memory-task-meta">
                          {getVisualObservationMeta(observation)}
                        </div>
                        <p className="panel-section-text">
                          {observation.summary}
                        </p>
                      </div>
                      <div className="memory-task-actions">
                        <button
                          className="memory-task-delete-btn"
                          type="button"
                          onClick={() =>
                            handleDeleteVisualObservation(observation.id)
                          }
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            )}

            <div className="panel-action-row">
              <button
                className="panel-action-btn panel-action-btn-danger"
                type="button"
                disabled={
                  visualContext.recentObservations.length === 0 &&
                  !visualContext.enabled
                }
                onClick={handleClearVisualContext}
              >
                Clear Visual
              </button>
            </div>
          </div>

          <div className="panel-section memory-sync-section">
            <div className="panel-section-title">Focus Nudges</div>
            <div className="memory-list">
              {focusNudges.map((nudge) => (
                <div className="memory-action-item" key={nudge.id}>
                  <div className="memory-task-copy">
                    <div className="memory-action-title">{nudge.title}</div>
                    <div className="memory-task-meta">{nudge.detail}</div>
                    <p className="panel-section-text">
                      Say “{nudge.command}” or tap the suggested action.
                    </p>
                  </div>
                  <div className="memory-task-actions">
                    <button
                      className="panel-action-btn"
                      type="button"
                      onClick={() => runFocusNudge(nudge, pushResultToast)}
                    >
                      {nudge.actionLabel}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel-section memory-sync-section">
            <div className="panel-section-title">Sync Status</div>
            <p className="panel-section-text">{memorySyncMessage}</p>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Memory Controls</div>
            <p className="panel-section-text">
              Export or import Memory, or reset supported mutable categories.
              Active Focus and Focus history are managed by the verified Focus
              lifecycle and are never cleared from this panel.
            </p>
            {activeSession && (
              <div className="memory-control-note">
                Task and note resets are disabled while a Focus is active so a
                broad Memory reset cannot silently undermine linked Focus state.
                End or complete the Focus first if you want a clean test reset.
              </div>
            )}
            <input
              ref={memoryImportInputRef}
              type="file"
              accept="application/json,.json"
              style={{ display: 'none' }}
              onChange={onImportMemoryFile}
            />
            <div className="panel-action-row">
              <button
                className="panel-action-btn"
                type="button"
                onClick={onExportMemory}
              >
                Export JSON
              </button>
              <button
                className="panel-action-btn"
                type="button"
                onClick={() => memoryImportInputRef.current?.click()}
              >
                Import JSON
              </button>
            </div>
            <div className="panel-action-row">
              <button
                className="panel-action-btn panel-action-btn-danger"
                type="button"
                disabled={Boolean(activeSession)}
                onClick={onResetTasksOnly}
              >
                Reset Tasks
              </button>
              <button
                className="panel-action-btn panel-action-btn-danger"
                type="button"
                disabled={Boolean(activeSession)}
                onClick={onResetNotesOnly}
              >
                Reset Notes
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
                    onSaveMemoryTaskDraft();
                  }
                }}
                placeholder="Add a task..."
              />
              <button
                className="panel-action-btn"
                type="button"
                disabled={!memoryTaskDraft.trim()}
                onClick={onSaveMemoryTaskDraft}
              >
                Save
              </button>
            </div>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Open Tasks</div>
            {openTasks.length === 0 ? (
              <p className="panel-section-text">
                No open tasks. Say “remember to test the Pi as a task,” or type
                one above.
              </p>
            ) : (
              <div className="memory-list">
                {openTasks.map((task) => (
                  <div className="memory-task-item" key={task.id}>
                    <div className="memory-task-copy">
                      <div className="memory-task-title">{task.title}</div>
                      <div className="memory-task-meta">
                        Saved {formatMemoryTime(task.createdAt)}
                      </div>
                    </div>
                    <div className="memory-task-actions">
                      <button
                        className="memory-task-done-btn"
                        type="button"
                        onClick={() => {
                          const completedTask = markMemoryTaskDoneById(task.id);
                          if (completedTask) {
                            addRecentAction(
                              'Completed task',
                              completedTask.title,
                            );
                            pushResultToast({
                              kind: 'success',
                              title: 'Task complete',
                              detail: completedTask.title,
                            });
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
                            pushResultToast({
                              kind: 'warning',
                              title: 'Task deleted',
                              detail: deletedTask.title,
                            });
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

          {completedTasks.length > 0 && (
            <div className="panel-section">
              <div className="panel-section-title">Completed Tasks</div>
              <div className="memory-list">
                {completedTasks.map((task) => (
                  <div
                    className="memory-action-item memory-completed-task"
                    key={task.id}
                  >
                    <div className="memory-task-copy">
                      <div className="memory-action-title">{task.title}</div>
                      <div className="memory-task-meta">
                        Done{' '}
                        {task.completedAt
                          ? formatMemoryTime(task.completedAt)
                          : 'recently'}
                      </div>
                    </div>
                    <div className="memory-task-actions">
                      <button
                        className="memory-task-reopen-btn"
                        type="button"
                        onClick={() => {
                          const reopenedTask = reopenMemoryTask(task.id);
                          if (reopenedTask) {
                            pushResultToast({
                              kind: 'info',
                              title: 'Task reopened',
                              detail: reopenedTask.title,
                            });
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
                            pushResultToast({
                              kind: 'warning',
                              title: 'Task deleted',
                              detail: deletedTask.title,
                            });
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
                      detail:
                        removedCount > 0
                          ? `${removedCount} removed.`
                          : 'No completed tasks to clear.',
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
              Start naturally: “I am working on my Java class.” Then ask “what
              should I do next?” or “what do you need to know?” Use “open
              memory” to manage focus, tasks, notes, read-only Focus history,
              and visual context.
            </p>
          </div>

          <button className="close-panel-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
