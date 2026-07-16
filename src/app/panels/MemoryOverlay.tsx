import {
  type ChangeEvent,
  type RefObject,
  useEffect,
  useState,
} from 'react';

import type { ActiveSession, MemoryTask } from '../types';
import type { ResultToast } from '../lib/toastUtils';
import { formatMemoryTime } from '../lib/memoryUtils';

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
const ACTIVE_SESSION_COMMAND_EVENT = 'qmeet-active-session-command';
const ACTIVE_SESSION_STATE_EVENT = 'qmeet-active-session-state';
const MEMORY_OVERLAY_FOCUS_MARKER = 'phase13a-v1-focus-nudge-engine';

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


type FocusNudge = {
  id: string;
  title: string;
  detail: string;
  command: string;
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
        detail: 'Set the current work context so QMeet can connect chat, tasks, and notes.',
        command: 'start a focus session for …',
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
      detail: 'A goal makes focus-aware chat, summaries, and next steps more useful.',
      command: 'set my goal to …',
    });
  }

  if (activeSession.goal.trim() && linkedTasks.length === 0) {
    nudges.push({
      id: 'make-tasks',
      title: 'Turn this focus into tasks',
      detail: 'Create a short checklist from the current focus and goal.',
      command: 'turn this focus into tasks',
    });
  }

  if (openLinkedTasks.length > 0) {
    nudges.push({
      id: 'next-linked-task',
      title: 'Next linked task',
      detail: openLinkedTasks[0].title,
      command: `work on ${openLinkedTasks[0].title}`,
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
      detail: 'This focus has been active for a while and has not pinned a summary note yet.',
      command: 'save this focus as a note',
    });
  }

  if (nudges.length === 0) {
    nudges.push({
      id: 'keep-going',
      title: 'Keep momentum',
      detail: 'Your focus has a goal and linked context. Ask QMeet for the next step when you are ready.',
      command: 'what should I do next for this focus',
    });
  }

  return nudges.slice(0, 3);
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
  onClearAllMemory,
  onResetTasksOnly,
  onResetNotesOnly,
  onResetRecentContextOnly,
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
  const openTasks = memoryTasks.filter((task) => !task.completedAt);
  const completedTasks = memoryTasks.filter((task) => task.completedAt);
  const focusNudges = buildFocusNudges(activeSession, memoryTasks);

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

  return (
    <div className="panel-overlay">
      <div className="panel-content memory-panel">
        <div className="panel-header">Memory</div>

        <div className="panel-body memory-panel-body">
          <div className="memory-hero">
            <div>
              <div className="memory-kicker">Backend Memory</div>
              <div className="memory-title">
                Tasks, notes, work context, and active focus sync to FastAPI,
                with browser fallback.
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

          <div className="panel-section memory-sync-section">
            <div className="panel-section-title">Current Focus</div>
            {activeSession ? (
              <div className="memory-list">
                <div className="memory-action-item">
                  <div className="memory-task-copy">
                    <div className="memory-action-title">
                      {activeSession.title}
                    </div>
                    <div className="memory-task-meta">
                      {formatSessionMode(activeSession.mode)} mode · Started{' '}
                      {formatMemoryTime(activeSession.startedAt)}
                    </div>
                    <p className="panel-section-text">
                      {activeSession.goal
                        ? `Goal: ${activeSession.goal}`
                        : 'No goal set yet. Say “set my goal to …” to add one.'}
                    </p>
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
                No active focus session. Say “start a coding focus session for
                QMeet Phase 12” to create one.
              </p>
            )}
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
                      Say “{nudge.command}”
                    </p>
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
              Export a backup, import a saved QMeet memory JSON file, or reset
              stored memory categories.
            </p>

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
              <button
                className="panel-action-btn panel-action-btn-danger"
                type="button"
                onClick={onClearAllMemory}
              >
                Clear All
              </button>
            </div>

            <div className="panel-action-row">
              <button
                className="panel-action-btn panel-action-btn-danger"
                type="button"
                onClick={onResetTasksOnly}
              >
                Reset Tasks
              </button>
              <button
                className="panel-action-btn panel-action-btn-danger"
                type="button"
                onClick={onResetNotesOnly}
              >
                Reset Notes
              </button>
              <button
                className="panel-action-btn panel-action-btn-danger"
                type="button"
                onClick={onResetRecentContextOnly}
              >
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
                            addRecentAction('Completed task', completedTask.title);
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
              Say “start a coding focus session for QMeet Phase 12,” “what am I
              focused on,” “set my goal to wire focus commands,” “end focus
              session,” “remember to test the Pi as a task,” “mark task done,”
              or “turn this focus into tasks,” “save this focus as a note,”
              “what should I do next,” or “clear completed tasks.” Notes and
              recent actions sync in the background.
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
