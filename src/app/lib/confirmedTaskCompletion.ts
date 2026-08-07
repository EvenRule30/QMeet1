import type { MemoryTask } from '../types';

const MEMORY_TASKS_STORAGE_KEY = 'qmeet-memory-tasks';
const MEMORY_TASKS_STATE_EVENT = 'qmeet-memory-tasks-state';

export type ConfirmedTaskTarget = {
  id: string;
  title: string;
};

export type ConfirmedTaskCompletionResult =
  | {
      ok: true;
      completedTasks: MemoryTask[];
      nextTasks: MemoryTask[];
    }
  | {
      ok: false;
      reason: string;
      completedTasks: [];
      nextTasks: MemoryTask[];
    };

function normalizeTitle(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

export function completeConfirmedTaskTargets(
  tasks: MemoryTask[],
  targets: ConfirmedTaskTarget[],
  verifiedCompletedAtByTaskId: ReadonlyMap<string, string> = new Map(),
): ConfirmedTaskCompletionResult {
  if (targets.length === 0) {
    return {
      ok: false,
      reason: 'No confirmed task target was available.',
      completedTasks: [],
      nextTasks: tasks,
    };
  }

  const uniqueTargets = Array.from(
    new Map(targets.map((target) => [target.id, target])).values(),
  );
  if (uniqueTargets.length !== targets.length) {
    return {
      ok: false,
      reason: 'The confirmed task target set changed before execution.',
      completedTasks: [],
      nextTasks: tasks,
    };
  }

  const openTaskById = new Map(
    tasks.filter((task) => !task.completedAt).map((task) => [task.id, task]),
  );
  const resolvedTasks: MemoryTask[] = [];
  for (const target of uniqueTargets) {
    const task = openTaskById.get(target.id);
    if (!task || normalizeTitle(task.title) !== normalizeTitle(target.title)) {
      return {
        ok: false,
        reason:
          'A confirmed task is no longer open or no longer matches the task that was previewed.',
        completedTasks: [],
        nextTasks: tasks,
      };
    }
    resolvedTasks.push(task);
  }

  const fallbackCompletedAt = new Date().toISOString();
  const targetIds = new Set(resolvedTasks.map((task) => task.id));
  const nextTasks = tasks.map((task) => {
    if (!targetIds.has(task.id) || task.completedAt) {
      return task;
    }
    const verifiedCompletedAt = verifiedCompletedAtByTaskId.get(task.id)?.trim();
    return {
      ...task,
      completedAt: verifiedCompletedAt || fallbackCompletedAt,
    };
  });
  const completedById = new Map(nextTasks.map((task) => [task.id, task]));
  const completedTasks = resolvedTasks
    .map((task) => completedById.get(task.id))
    .filter((task): task is MemoryTask => Boolean(task));

  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(
        MEMORY_TASKS_STORAGE_KEY,
        JSON.stringify(nextTasks),
      );
    } catch (error) {
      console.warn('Confirmed task completion local save failed:', error);
    }
    window.dispatchEvent(
      new CustomEvent(MEMORY_TASKS_STATE_EVENT, {
        detail: { tasks: nextTasks },
      }),
    );
  }

  return {
    ok: true,
    completedTasks,
    nextTasks,
  };
}
