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
  clearVisualContext,
  deleteVisualObservationById,
  getRecentFocusSessions,
  getVisualContext,
} from '../api';
import './MemoryOverlay.css';

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
    // Storage can fail in restricted browser modes.
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

function dispatchActiveSessionCommand(detail: ActiveSessionCommandEventDetail) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent<ActiveSessionCommandEventDetail>(
      ACTIVE_SESSION_COMMAND_EVENT,
      { detail },
    ),
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

function dispatchPromptCommand(command: string) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent<PromptCommandEventDetail>(QMEET_PROMPT_COMMAND_EVENT, {
      detail: { command },
    }),
  );
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

function getRecentFocusSessionMeta(session: RecentFocusSession) {
  const pieces = [
    `${formatSessionMode(session.mode)} mode`,
    `Ended ${formatMemoryTime(session.endedAt)}`,
  ];

  if (session.linkedTaskIds.length > 0) {
    pieces.push(
      `${session.linkedTaskIds.length} linked task${
        session.linkedTaskIds.length === 1 ? '' : 's'
      }`,
    );
  }
  if (session.pinnedNoteIds.length > 0 || session.summaryNoteId) {
    pieces.push('summary saved');
  }

  return pieces.join(' · ');
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
    void loadRecentFocusSessions();
  }, [loadRecentFocusSessions, activeSession?.id]);

  useEffect(() => {
    void loadVisualContext();
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
      <div className="panel-content memory-panel memory-remaster">
        <div className="panel-header">Memory</div>
        <div className="panel-body memory-remaster-body">
          <section className="memory-remaster-hero">
            <div>
              <div className="memory-remaster-kicker">QMeet Memory</div>
              <div className="memory-remaster-title">
                Focus, tasks, and saved context QMeet can use.
              </div>
            </div>
            <div
              className={`memory-remaster-sync memory-remaster-sync-${memorySyncState}`}
              title={memorySyncMessage}
            >
              <span className="memory-remaster-sync-dot" />
              {memorySyncState === 'synced'
                ? 'Synced'
                : memorySyncState === 'syncing'
                  ? 'Syncing'
                  : memorySyncState === 'error'
                    ? 'Sync issue'
                    : 'Local'}
            </div>
          </section>

          <section
            className="memory-remaster-overview"
            aria-label="Memory overview"
          >
            <div className="memory-remaster-stat memory-remaster-stat-focus">
              <span>Focus</span>
              <strong>{activeSession ? activeSession.title : 'None'}</strong>
            </div>
            <div className="memory-remaster-stat">
              <span>Open tasks</span>
              <strong>{openTasks.length}</strong>
            </div>
            <div className="memory-remaster-stat">
              <span>Completed</span>
              <strong>{completedTasks.length}</strong>
            </div>
            <div className="memory-remaster-stat">
              <span>Saved context</span>
              <strong>{visualContext.recentObservations.length}</strong>
            </div>
          </section>

          <section className="memory-remaster-card memory-remaster-focus-card">
            <div className="memory-remaster-section-head">
              <div>
                <div className="memory-remaster-section-label">Current Focus</div>
                <div className="memory-remaster-section-title">
                  {activeSession ? activeSession.title : 'No active Focus'}
                </div>
              </div>
              {activeSession && (
                <span className="memory-remaster-pill">
                  {formatSessionMode(activeSession.mode)} ·{' '}
                  {getFocusAgeLabel(activeSession)}
                </span>
              )}
            </div>

            {activeSession ? (
              <>
                <p className="memory-remaster-focus-goal">
                  {activeSession.goal
                    ? activeSession.goal
                    : 'No goal set yet. Ask QMeet to set a goal when you are ready.'}
                </p>
                <div className="memory-remaster-actions">
                  <button
                    className="panel-action-btn"
                    type="button"
                    onClick={() =>
                      runFocusQuickAction(
                        'what should I do next for this focus',
                        'Next step',
                        pushResultToast,
                      )
                    }
                  >
                    Next step
                  </button>
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
                    onClick={() =>
                      runFocusQuickAction(
                        'end and summarize this focus',
                        'End with summary',
                        pushResultToast,
                      )
                    }
                  >
                    End + summary
                  </button>
                  <button
                    className="memory-remaster-end-btn"
                    type="button"
                    onClick={() => {
                      clearStoredActiveSession();
                      setActiveSession(null);
                      dispatchActiveSessionState(null);
                      dispatchActiveSessionCommand({ action: 'end' });
                    }}
                  >
                    End focus
                  </button>
                </div>
              </>
            ) : (
              <div className="memory-remaster-empty-row">
                <span>
                  Start a Focus when you want QMeet to keep one goal and its
                  related work in the foreground.
                </span>
                <button
                  className="panel-action-btn"
                  type="button"
                  onClick={() => {
                    const title = window.prompt('What should this Focus be called?');
                    const trimmedTitle = title?.trim();
                    if (trimmedTitle) {
                      runFocusQuickAction(
                        `start a focus session for ${trimmedTitle}`,
                        'Start Focus',
                        pushResultToast,
                      );
                    }
                  }}
                >
                  Start Focus
                </button>
              </div>
            )}
          </section>

          <section className="memory-remaster-card">
            <div className="memory-remaster-section-head memory-remaster-section-head-compact">
              <div>
                <div className="memory-remaster-section-label">Tasks</div>
                <div className="memory-remaster-section-title">
                  {openTasks.length} open
                </div>
              </div>
              {completedTasks.length > 0 && (
                <span className="memory-remaster-pill">
                  {completedTasks.length} completed
                </span>
              )}
            </div>

            <div className="memory-remaster-task-input-row">
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
                Add
              </button>
            </div>

            {openTasks.length === 0 ? (
              <div className="memory-remaster-empty">
                No open tasks. Ask QMeet to create one or add it above.
              </div>
            ) : (
              <div className="memory-remaster-list">
                {openTasks.map((task) => (
                  <div className="memory-remaster-task" key={task.id}>
                    <div className="memory-remaster-task-copy">
                      <div className="memory-remaster-task-title">{task.title}</div>
                      <div className="memory-remaster-meta">
                        Saved {formatMemoryTime(task.createdAt)}
                      </div>
                    </div>
                    <div className="memory-remaster-task-actions">
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
          </section>

          {completedTasks.length > 0 && (
            <details className="memory-remaster-details">
              <summary>
                <span>Completed tasks</span>
                <span>{completedTasks.length}</span>
              </summary>
              <div className="memory-remaster-details-body">
                <div className="memory-remaster-list">
                  {completedTasks.map((task) => (
                    <div
                      className="memory-remaster-task memory-remaster-task-complete"
                      key={task.id}
                    >
                      <div className="memory-remaster-task-copy">
                        <div className="memory-remaster-task-title">
                          {task.title}
                        </div>
                        <div className="memory-remaster-meta">
                          Done{' '}
                          {task.completedAt
                            ? formatMemoryTime(task.completedAt)
                            : 'recently'}
                        </div>
                      </div>
                      <div className="memory-remaster-task-actions">
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
                <div className="memory-remaster-detail-actions">
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
                    Clear completed
                  </button>
                </div>
              </div>
            </details>
          )}

          <details className="memory-remaster-details">
            <summary>
              <span>Recent Focus history</span>
              <span>{recentFocusSessions.length}</span>
            </summary>
            <div className="memory-remaster-details-body">
              {recentFocusSessions.length === 0 ? (
                <div className="memory-remaster-empty">
                  {recentFocusSessionMessage ||
                    'Ended Focus sessions will appear here.'}
                </div>
              ) : (
                <div className="memory-remaster-list">
                  {recentFocusSessions.slice(0, 5).map((session) => (
                    <div className="memory-remaster-history" key={session.id}>
                      <div className="memory-remaster-task-title">
                        {session.title}
                      </div>
                      <div className="memory-remaster-meta">
                        {getRecentFocusSessionMeta(session)}
                      </div>
                      {session.goal && (
                        <div className="memory-remaster-history-goal">
                          {session.goal}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>

          <details className="memory-remaster-details">
            <summary>
              <span>Saved visual context</span>
              <span>{visualContext.recentObservations.length}</span>
            </summary>
            <div className="memory-remaster-details-body">
              {visualContext.recentObservations.length === 0 ? (
                <div className="memory-remaster-empty">
                  {visualContextMessage || 'No visual observations saved.'}
                </div>
              ) : (
                <div className="memory-remaster-list">
                  {visualContext.recentObservations
                    .slice(0, 5)
                    .map((observation) => (
                      <div className="memory-remaster-history" key={observation.id}>
                        <div className="memory-remaster-history-row">
                          <div>
                            <div className="memory-remaster-task-title">
                              {formatVisualSource(observation.source)} observation
                            </div>
                            <div className="memory-remaster-meta">
                              {getVisualObservationMeta(observation)}
                            </div>
                          </div>
                          <button
                            className="memory-task-delete-btn"
                            type="button"
                            onClick={() =>
                              void handleDeleteVisualObservation(observation.id)
                            }
                          >
                            Remove
                          </button>
                        </div>
                        <div className="memory-remaster-history-goal">
                          {observation.summary}
                        </div>
                      </div>
                    ))}
                </div>
              )}
              <div className="memory-remaster-detail-actions">
                <button
                  className="panel-action-btn panel-action-btn-danger"
                  type="button"
                  disabled={
                    visualContext.recentObservations.length === 0 &&
                    !visualContext.enabled
                  }
                  onClick={() => void handleClearVisualContext()}
                >
                  Clear visual context
                </button>
              </div>
            </div>
          </details>

          <details className="memory-remaster-details memory-remaster-maintenance">
            <summary>
              <span>Data & maintenance</span>
              <span>Advanced</span>
            </summary>
            <div className="memory-remaster-details-body">
              <div className="memory-remaster-maintenance-status">
                <span>Sync status</span>
                <strong>{memorySyncMessage}</strong>
              </div>

              {activeSession && (
                <div className="memory-remaster-warning">
                  Task and note resets stay disabled while a Focus is active so
                  broad cleanup cannot silently undermine linked Focus state.
                </div>
              )}

              <input
                ref={memoryImportInputRef}
                type="file"
                accept="application/json,.json"
                style={{ display: 'none' }}
                onChange={onImportMemoryFile}
              />

              <div className="memory-remaster-detail-actions">
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
                <button
                  className="panel-action-btn panel-action-btn-danger"
                  type="button"
                  disabled={Boolean(activeSession)}
                  onClick={onResetTasksOnly}
                >
                  Reset tasks
                </button>
                <button
                  className="panel-action-btn panel-action-btn-danger"
                  type="button"
                  disabled={Boolean(activeSession)}
                  onClick={onResetNotesOnly}
                >
                  Reset notes
                </button>
              </div>
            </div>
          </details>

          <button className="close-panel-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
