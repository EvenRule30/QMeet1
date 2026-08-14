import { createMemoryTask } from '../api';
import type { MemoryTask } from '../types';

const MEMORY_TASKS_STORAGE_KEY = 'qmeet-memory-tasks';
const MEMORY_TASKS_STATE_EVENT = 'qmeet-memory-tasks-state';

export type VerifiedGlobalTaskCreateResult =
  | {
      ok: true;
      task: MemoryTask;
      tasks: MemoryTask[];
      message: string;
    }
  | {
      ok: false;
      task: null;
      tasks: MemoryTask[];
      message: string;
    };

function normalizeTaskTitle(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function applyVerifiedTaskProjection(tasks: MemoryTask[]): void {
  if (typeof window === 'undefined') return;

  try {
    window.localStorage.setItem(
      MEMORY_TASKS_STORAGE_KEY,
      JSON.stringify(tasks),
    );
  } catch (error) {
    console.warn('Verified task projection local save failed:', error);
  }

  window.dispatchEvent(
    new CustomEvent(MEMORY_TASKS_STATE_EVENT, {
      detail: { tasks },
    }),
  );
}

export async function createVerifiedGlobalTask(
  title: string,
): Promise<VerifiedGlobalTaskCreateResult> {
  const cleanTitle = normalizeTaskTitle(title);
  if (!cleanTitle) {
    return {
      ok: false,
      task: null,
      tasks: [],
      message: 'I did not catch the task text. No task was added.',
    };
  }

  try {
    const response = await createMemoryTask({ title: cleanTitle });
    const tasks = Array.isArray(response.tasks) ? response.tasks : [];
    const createdTask = tasks[0] ?? null;

    if (
      !createdTask ||
      createdTask.completedAt ||
      normalizeTaskTitle(createdTask.title) !== cleanTitle
    ) {
      return {
        ok: false,
        task: null,
        tasks,
        message:
          'The backend did not return the newly created task as an open canonical task, so QMeet did not report it as saved.',
      };
    }

    applyVerifiedTaskProjection(tasks);
    return {
      ok: true,
      task: createdTask,
      tasks,
      message: response.message?.trim() || `Saved task: ${createdTask.title}.`,
    };
  } catch (error) {
    const detail =
      error instanceof Error && error.message.trim()
        ? ` ${error.message.trim()}`
        : '';
    return {
      ok: false,
      task: null,
      tasks: [],
      message: `I could not save that task to canonical task storage, so no task was added.${detail}`,
    };
  }
}
