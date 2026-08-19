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
  asked: 'ask',
  asking: 'ask',
};

const COMPLETION_VERB_FORMS = [
  'finished',
  'completed',
  'sent',
  'submitted',
  'reviewed',
  'handled',
  'resolved',
  'fixed',
  'asked',
];

function differsByAtMostOneEdit(left: string, right: string): boolean {
  if (left === right) return true;
  if (Math.abs(left.length - right.length) > 1) return false;

  if (left.length === right.length) {
    let differences = 0;
    for (let index = 0; index < left.length; index += 1) {
      if (left[index] !== right[index]) {
        differences += 1;
        if (differences > 1) return false;
      }
    }
    return true;
  }

  const shorter = left.length < right.length ? left : right;
  const longer = left.length < right.length ? right : left;
  let shortIndex = 0;
  let longIndex = 0;
  let skipped = false;

  while (shortIndex < shorter.length && longIndex < longer.length) {
    if (shorter[shortIndex] === longer[longIndex]) {
      shortIndex += 1;
      longIndex += 1;
      continue;
    }
    if (skipped) return false;
    skipped = true;
    longIndex += 1;
  }

  return true;
}

function isCompletionVerbToken(rawToken: string): boolean {
  const token = rawToken.toLowerCase();
  if (COMPLETION_VERB_FORMS.includes(token)) return true;
  if (token.length < 5) return false;

  return COMPLETION_VERB_FORMS.some(
    (candidate) =>
      candidate.length >= 5 &&
      differsByAtMostOneEdit(token, candidate),
  );
}

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
  // A partial reference is accepted only when all query tokens occur in exactly
  // one real open task. Multiple matches remain ambiguous rather than guessed.
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

function cleanCompletionQuery(value: string): string {
  return value
    .replace(/^(?:the|my|our)\s+task\s+(?:called|named|about)?\s*/i, '')
    .replace(/\s+(?:task|tasks)$/i, '')
    .replace(/[.!?]+$/g, '')
    .trim();
}

function extractNaturalCompletionQuery(statement: string): string | null {
  const trimmed = statement.replace(/\s+/g, ' ').trim();
  if (!trimmed) return null;

  const markDone = trimmed.match(
    /^(?:please\s+)?mark\s+(.+?)\s+(?:as\s+)?(?:done|complete|completed)\s*[.!?]*$/i,
  );

  if (markDone?.[1]) return cleanCompletionQuery(markDone[1]);

  const firstPerson = trimmed.match(
    /^(?:i|we)(?:['’]ve|\s+have)?\s+(?:already\s+|just\s+)?(?:finished|completed|sent|submitted|reviewed|handled|resolved|fixed|asked|did|got\s+through|took\s+care\s+of)\s+(.+?)\s*[.!?]*$/i,
  );

  if (firstPerson?.[1]) {
    return cleanCompletionQuery(firstPerson[1]);
  }

  // Phase 21C6B: passive completed-work statements are still task mutations.
  // The verb check tolerates one ordinary insertion/deletion/substitution typo
  // for longer completion verbs without teaching the router one phrase-specific
  // misspelling.
  const passive = trimmed.match(
    /^(.+?)\s+(?:(?:has|have|had)\s+been|(?:was|were|is|are))\s+([a-z]+)\s*[.!?]*$/i,
  );

  if (passive?.[1] && passive?.[2] && isCompletionVerbToken(passive[2])) {
    return cleanCompletionQuery(passive[1]);
  }

  const firstPersonFuzzy = trimmed.match(
    /^(?:i|we)(?:['’]ve|\s+have)?\s+(?:already\s+|just\s+)?([a-z]+)\s+(.+?)\s*[.!?]*$/i,
  );

  if (
    firstPersonFuzzy?.[1] &&
    firstPersonFuzzy?.[2] &&
    isCompletionVerbToken(firstPersonFuzzy[1])
  ) {
    return cleanCompletionQuery(firstPersonFuzzy[2]);
  }

  return null;
}

/**
 * State-aware ownership fallback for natural completed-work language. It only
 * activates when the utterance describes completed work AND that reference
 * matches real open task state. It never mutates state by itself.
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
