import type { ActiveSession, MemoryTask } from '../types';

type TaskCompletionSpec =
  | { kind: 'first'; count: number }
  | { kind: 'last'; count: number }
  | { kind: 'indexes'; indexes: number[] }
  | { kind: 'all' }
  | { kind: 'lookup'; lookup: string };

function normalizeTaskLookup(value: string): string {
  return value
    .toLowerCase()
    .replace(/[`"']/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function readSmallNumber(value: string | undefined): number | null {
  if (!value) return null;
  const text = value.toLowerCase().trim();
  if (/^\d+$/.test(text)) return Number.parseInt(text, 10);

  const words: Record<string, number> = {
    one: 1,
    first: 1,
    two: 2,
    second: 2,
    couple: 2,
    both: 2,
    three: 3,
    third: 3,
    few: 3,
    four: 4,
    fourth: 4,
    five: 5,
    fifth: 5,
    six: 6,
    sixth: 6,
    seven: 7,
    seventh: 7,
    eight: 8,
    eighth: 8,
    nine: 9,
    ninth: 9,
    ten: 10,
    tenth: 10,
  };

  return words[text] ?? null;
}

function parseTaskCompletionSpec(payload: string | undefined): TaskCompletionSpec {
  const rawPayload = (payload ?? '').replace(/\s+/g, ' ').trim();
  if (!rawPayload) return { kind: 'first', count: 1 };

  const normalized = rawPayload
    .toLowerCase()
    .replace(/[.,;:!?]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (/\b(?:all|everything|the whole list|every task|all tasks)\b/.test(normalized)) {
    return { kind: 'all' };
  }

  const firstMatch = normalized.match(
    /\bfirst\s+(\d+|one|two|couple|both|three|few|four|five|six|seven|eight|nine|ten)\b/,
  );
  const firstCount = readSmallNumber(firstMatch?.[1]);
  if (firstCount && firstCount > 0) {
    return { kind: 'first', count: firstCount };
  }

  const lastMatch = normalized.match(
    /\b(?:last|latest|most recent)\s+(\d+|one|two|couple|both|three|few|four|five|six|seven|eight|nine|ten)\b/,
  );
  const lastCount = readSmallNumber(lastMatch?.[1]);
  if (lastCount && lastCount > 0) {
    return { kind: 'last', count: lastCount };
  }

  if (/\b(?:both|the two|these two|those two)\b/.test(normalized)) {
    return { kind: 'first', count: 2 };
  }

  const ordinalWords: Record<string, number> = {
    first: 1,
    second: 2,
    third: 3,
    fourth: 4,
    fifth: 5,
    sixth: 6,
    seventh: 7,
    eighth: 8,
    ninth: 9,
    tenth: 10,
  };
  const wordIndexes = Array.from(
    normalized.matchAll(
      /\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b/g,
    ),
  )
    .map((match) => ordinalWords[match[1]])
    .filter(Boolean);
  if (
    wordIndexes.length > 0 &&
    !/\bfirst\s+(?:task|tasks)?\b/.test(normalized)
  ) {
    return { kind: 'indexes', indexes: Array.from(new Set(wordIndexes)) };
  }

  const cardinalIndexWords: Record<string, number> = {
    one: 1,
    two: 2,
    three: 3,
    four: 4,
    five: 5,
    six: 6,
    seven: 7,
    eight: 8,
    nine: 9,
    ten: 10,
  };
  const cardinalIndexes = Array.from(
    normalized
      .replace(/\bnumber\s+/g, '')
      .matchAll(/\b(one|two|three|four|five|six|seven|eight|nine|ten)\b/g),
  )
    .map((match) => cardinalIndexWords[match[1]])
    .filter(Boolean);
  if (cardinalIndexes.length > 0 && /\b(?:and|,)\b/.test(normalized)) {
    return { kind: 'indexes', indexes: Array.from(new Set(cardinalIndexes)) };
  }

  const numericIndexMatches = Array.from(
    normalized.matchAll(/(?:^|\b)(?:task\s*)?(\d+)(?:\b|$)/g),
  ).map((match) => Number.parseInt(match[1], 10));
  if (numericIndexMatches.length > 0) {
    return {
      kind: 'indexes',
      indexes: Array.from(
        new Set(numericIndexMatches.filter((value) => value > 0)),
      ),
    };
  }

  const lookup = rawPayload
    .replace(/^(?:the\s+)?(?:task|tasks)\s+(?:called|named|about)?\s*/i, '')
    .replace(/\s+(?:task|tasks)$/i, '')
    .trim();
  return { kind: 'lookup', lookup };
}

function orderedOpenTasksForCompletion(
  tasks: MemoryTask[],
  activeSession: ActiveSession | null,
): MemoryTask[] {
  const openTaskById = new Map(
    tasks.filter((task) => !task.completedAt).map((task) => [task.id, task]),
  );
  const linkedOpenTasks = activeSession
    ? activeSession.linkedTaskIds
        .map((taskId) => openTaskById.get(taskId))
        .filter((task): task is MemoryTask => Boolean(task))
    : [];

  if (linkedOpenTasks.length > 0) return linkedOpenTasks;
  return tasks.filter((task) => !task.completedAt);
}

export function resolveTaskCompletionPreviewTargets(
  payload: string | undefined,
  tasks: MemoryTask[],
  activeSession: ActiveSession | null,
): MemoryTask[] {
  const candidateTasks = orderedOpenTasksForCompletion(tasks, activeSession);
  if (candidateTasks.length === 0) return [];

  const spec = parseTaskCompletionSpec(payload);
  let selectedTasks: MemoryTask[] = [];

  if (spec.kind === 'all') {
    selectedTasks = candidateTasks;
  } else if (spec.kind === 'first') {
    selectedTasks = candidateTasks.slice(0, Math.max(1, spec.count));
  } else if (spec.kind === 'last') {
    selectedTasks = candidateTasks.slice(-Math.max(1, spec.count));
  } else if (spec.kind === 'indexes') {
    selectedTasks = spec.indexes
      .map((index) => candidateTasks[index - 1])
      .filter((task): task is MemoryTask => Boolean(task));
  } else {
    const lookup = normalizeTaskLookup(spec.lookup);
    selectedTasks = lookup
      ? candidateTasks
          .filter((task) => {
            const title = normalizeTaskLookup(task.title);
            return title.includes(lookup) || lookup.includes(title);
          })
          .slice(0, 3)
      : [];
  }

  return Array.from(
    new Map(selectedTasks.map((task) => [task.id, task])).values(),
  );
}

export function describeTaskCompletionPreviewTargets(
  tasks: MemoryTask[],
): string | null {
  if (tasks.length === 0) return null;
  if (tasks.length === 1) {
    return `mark "${tasks[0].title}" as done`;
  }

  return `mark ${tasks.length} tasks as done: ${tasks
    .map((task) => `"${task.title}"`)
    .join('; ')}`;
}

export function describeUnresolvedTaskCompletionRequest(
  payload: string | undefined,
): string {
  const target = (payload ?? '').replace(/\s+/g, ' ').trim();
  return target
    ? `I couldn't find an open task matching "${target}". No task was changed.`
    : `I couldn't find an open task to complete. No task was changed.`;
}
