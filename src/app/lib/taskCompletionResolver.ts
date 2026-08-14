import type { MemoryTask } from '../types';

export type TaskCompletionReferenceResolution =
  | { kind: 'exact'; task: MemoryTask }
  | { kind: 'likely'; task: MemoryTask }
  | { kind: 'ambiguous'; candidates: MemoryTask[] }
  | { kind: 'none' };

export type NaturalGlobalTaskCompletionRequest = {
  query: string;
  resolution: TaskCompletionReferenceResolution;
};

const REFERENCE_STOP_WORDS = new Set([
  'a',
  'an',
  'already',
  'as',
  'done',
  'have',
  'i',
  'just',
  'my',
  'our',
  'task',
  'tasks',
  'the',
  'this',
  'to',
  'we',
]);

const TOKEN_ALIASES: Record<string, string> = {
  sent: 'send',
  sending: 'send',
  submitted: 'submit',
  submitting: 'submit',
  reviewed: 'review',
  reviewing: 'review',
  finished: 'finish',
  finishing: 'finish',
  completed: 'complete',
  completing: 'complete',
  handled: 'handle',
  handling: 'handle',
  resolved: 'resolve',
  resolving: 'resolve',
  fixed: 'fix',
  fixing: 'fix',
};

function normalizeToken(rawToken: string): string {
  const token = rawToken.toLowerCase();
  if (TOKEN_ALIASES[token]) return TOKEN_ALIASES[token];

  if (/^[a-z]{5,}ies$/.test(token)) return `${token.slice(0, -3)}y`;
  if (/^[a-z]{5,}ing$/.test(token)) return token.slice(0, -3);
  if (/^[a-z]{4,}s$/.test(token) && !token.endsWith('ss')) {
    return token.slice(0, -1);
  }

  return token;
}

function tokenizeReference(value: string): string[] {
  const normalized = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!normalized) return [];

  return Array.from(
    new Set(
      normalized
        .split(' ')
        .map(normalizeToken)
        .filter((token) => token.length > 1 || /^\d+$/.test(token))
        .filter((token) => !REFERENCE_STOP_WORDS.has(token)),
    ),
  );
}

function normalizedReference(value: string): string {
  return tokenizeReference(value).join(' ');
}

function openTasks(tasks: MemoryTask[]): MemoryTask[] {
  return tasks.filter((task) => !task.completedAt);
}

function containsAllQueryTokens(
  queryTokens: string[],
  task: MemoryTask,
): boolean {
  if (queryTokens.length === 0) return false;

  const taskTokens = tokenizeReference(task.title);
  if (taskTokens.length === 0) return false;

  const taskSet = new Set(taskTokens);
  return queryTokens.every((token) => taskSet.has(token));
}

function scoreCandidate(queryTokens: string[], task: MemoryTask): number {
  if (queryTokens.length === 0) return 0;

  const taskTokens = tokenizeReference(task.title);
  if (taskTokens.length === 0) return 0;

  const taskSet = new Set(taskTokens);
  const querySet = new Set(queryTokens);
  const overlap = queryTokens.filter((token) => taskSet.has(token)).length;

  if (overlap === 0) return 0;

  const queryCoverage = overlap / queryTokens.length;
  const taskCoverage =
    taskTokens.filter((token) => querySet.has(token)).length /
    taskTokens.length;

  if (queryTokens.length === 1) return queryCoverage;
  if (queryCoverage < 0.67 || overlap < 2) return 0;

  return queryCoverage * 0.8 + taskCoverage * 0.2;
}

export function resolveGlobalTaskCompletionReference(
  query: string,
  tasks: MemoryTask[],
): TaskCompletionReferenceResolution {
  const normalizedQuery = normalizedReference(query);
  if (!normalizedQuery) return { kind: 'none' };

  const candidates = openTasks(tasks);
  if (candidates.length === 0) return { kind: 'none' };

  const exact = candidates.filter(
    (task) => normalizedReference(task.title) === normalizedQuery,
  );

  if (exact.length === 1) {
    return { kind: 'exact', task: exact[0] };
  }

  if (exact.length > 1) {
    return {
      kind: 'ambiguous',
      candidates: exact.slice(0, 5),
    };
  }

  const queryTokens = tokenizeReference(query);

  // Phase 21C5: make partial task references an explicit deterministic tier.
  //
  // Examples:
  //   "invoice" -> "sending invoice"
  //   "presentation outline" -> "review presentation outline"
  //
  // This is intentionally state-aware and ambiguity-safe. A partial reference
  // is accepted only when every normalized query token exists in exactly one
  // real open task title. If more than one open task contains the same query
  // tokens, QMeet asks the user to disambiguate instead of choosing one.
  const contained = candidates.filter((task) =>
    containsAllQueryTokens(queryTokens, task),
  );

  if (contained.length === 1) {
    return { kind: 'likely', task: contained[0] };
  }

  if (contained.length > 1) {
    return {
      kind: 'ambiguous',
      candidates: contained.slice(0, 5),
    };
  }

  const scored = candidates
    .map((task) => ({
      task,
      score: scoreCandidate(queryTokens, task),
    }))
    .filter((candidate) => candidate.score > 0)
    .sort((left, right) => right.score - left.score);

  if (scored.length === 0) {
    return { kind: 'none' };
  }

  if (scored.length === 1) {
    return { kind: 'likely', task: scored[0].task };
  }

  const best = scored[0];
  const runnerUp = scored[1];

  if (
    queryTokens.length === 1 ||
    Math.abs(best.score - runnerUp.score) < 0.15
  ) {
    return {
      kind: 'ambiguous',
      candidates: scored.slice(0, 5).map((candidate) => candidate.task),
    };
  }

  return { kind: 'likely', task: best.task };
}

function extractNaturalCompletionQuery(statement: string): string | null {
  const trimmed = statement.replace(/\s+/g, ' ').trim();
  if (!trimmed) return null;

  const markDone = trimmed.match(
    /^(?:please\s+)?mark\s+(.+?)\s+(?:as\s+)?(?:done|complete|completed)\s*[.!?]*$/i,
  );

  if (markDone?.[1]) return markDone[1].trim();

  const firstPerson = trimmed.match(
    /^(?:i|we)(?:['’]ve|\s+have)?\s+(?:already\s+|just\s+)?(?:finished|completed|sent|submitted|reviewed|handled|resolved|fixed|did|got\s+through|took\s+care\s+of)\s+(.+?)\s*[.!?]*$/i,
  );

  if (!firstPerson?.[1]) return null;

  return firstPerson[1]
    .replace(/^(?:the|my|our)\s+task\s+(?:called|named|about)?\s*/i, '')
    .replace(/\s+(?:task|tasks)$/i, '')
    .trim();
}

/**
 * State-aware ownership fallback for natural completed-work language. It only
 * activates when the current utterance describes completed work AND that
 * reference matches one or more real open global tasks. It never mutates state.
 */
export function resolveNaturalGlobalTaskCompletionRequest(
  statement: string,
  tasks: MemoryTask[],
): NaturalGlobalTaskCompletionRequest | null {
  const query = extractNaturalCompletionQuery(statement);
  if (!query) return null;

  const resolution = resolveGlobalTaskCompletionReference(query, tasks);
  if (resolution.kind === 'none') return null;

  return { query, resolution };
}
