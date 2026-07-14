import type { ChangeEvent, RefObject } from 'react';
import type { MemoryTask } from '../types';
import type { ResultToast } from '../lib/toastUtils';
import { formatMemoryTime } from '../lib/memoryUtils';

type MemorySyncState = 'local' | 'syncing' | 'synced' | 'error';
type ToastInput = Omit<ResultToast, 'id' | 'createdAt'> | null;

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
  const openTasks = memoryTasks.filter((task) => !task.completedAt);
  const completedTasks = memoryTasks.filter((task) => task.completedAt);

  return (
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
              onChange={onImportMemoryFile}
            />
            <div className="panel-action-row">
              <button className="panel-action-btn" type="button" onClick={onExportMemory}>
                Export JSON
              </button>
              <button className="panel-action-btn" type="button" onClick={() => memoryImportInputRef.current?.click()}>
                Import JSON
              </button>
              <button className="panel-action-btn panel-action-btn-danger" type="button" onClick={onClearAllMemory}>
                Clear All
              </button>
            </div>
            <div className="panel-action-row">
              <button className="panel-action-btn panel-action-btn-danger" type="button" onClick={onResetTasksOnly}>
                Reset Tasks
              </button>
              <button className="panel-action-btn panel-action-btn-danger" type="button" onClick={onResetNotesOnly}>
                Reset Notes
              </button>
              <button className="panel-action-btn panel-action-btn-danger" type="button" onClick={onResetRecentContextOnly}>
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
              <p className="panel-section-text">No open tasks. Say “remember to test the Pi as a task,” or type one above.</p>
            ) : (
              <div className="memory-list">
                {openTasks.map((task) => (
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

          {completedTasks.length > 0 && (
            <div className="panel-section">
              <div className="panel-section-title">Completed Tasks</div>
              <div className="memory-list">
                {completedTasks.map((task) => (
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

          <button className="close-panel-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
