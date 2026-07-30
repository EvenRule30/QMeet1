import type { MemoryTask } from '../types';

const MEMORY_TASKS_STORAGE_KEY = 'qmeet-memory-tasks';

function normalizeStoredTask(value: unknown): MemoryTask | null {
  if (!value || typeof value !== 'object') return null;

  const task = value as Partial<MemoryTask>;
  if (typeof task.title !== 'string' || !task.title.trim()) return null;

  return {
    id:
      typeof task.id === 'string' && task.id.trim()
        ? task.id
        : `task-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    title: task.title.trim(),
    createdAt:
      typeof task.createdAt === 'string' && task.createdAt.trim()
        ? task.createdAt
        : new Date().toISOString(),
    ...(typeof task.completedAt === 'string' && task.completedAt.trim()
      ? { completedAt: task.completedAt }
      : {}),
  };
}

export function readStoredMemoryTasks(): MemoryTask[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawTasks = window.localStorage.getItem(MEMORY_TASKS_STORAGE_KEY);
    if (!rawTasks) return [];

    const parsedTasks: unknown = JSON.parse(rawTasks);
    if (!Array.isArray(parsedTasks)) return [];

    return parsedTasks
      .map(normalizeStoredTask)
      .filter((task): task is MemoryTask => task !== null);
  } catch {
    return [];
  }
}

export function formatOpenTasksReadout(tasks: MemoryTask[]): string {
  const openTasks = tasks.filter(
    (task) => !task.completedAt && task.title.trim().length > 0,
  );

  if (openTasks.length === 0) {
    return 'You do not have any open tasks.';
  }

  const taskLines = openTasks.map(
    (task, index) => `${index + 1}. ${task.title.trim()}`,
  );

  return `Open tasks:\n\n${taskLines.join('\n')}`;
}
