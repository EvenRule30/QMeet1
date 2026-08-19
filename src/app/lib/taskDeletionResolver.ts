import type { MemoryTask } from '../types';
import type { PromotedSingleIntentDecision } from './agentShadowObserver';

export type TaskDeletionReferenceResolution =
  | { kind: 'exact'; task: MemoryTask }
  | { kind: 'likely'; task: MemoryTask }
  | { kind: 'ambiguous'; candidates: MemoryTask[] }
  | { kind: 'none' };

export type NaturalGlobalTaskDeletionRequest = {
  query: string;
  resolution: TaskDeletionReferenceResolution;
};

export type PromotedTaskDeleteToolCommand = {
  query: string;
};

const REFERENCE_STOP_WORDS = new Set([
  'a',
  'an',
  'from',
  'list',
  'my',
  'our',
  'task',
  'tasks',
  'the',
  'this',
  'to',
  'todo',
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

export function resolveTaskDeletionReference(
  query: string,
  tasks: MemoryTask[],
): TaskDeletionReferenceResolution {
  const normalizedQuery = normalizedReference(query);
  if (!normalizedQuery) return { kind: 'none' };
  if (tasks.length === 0) return { kind: 'none' };

  const exact = tasks.filter(
    (task) => normalizedReference(task.title) === normalizedQuery,
  );

  if (exact.length === 1) {
    return { kind: 'exact', task: exact[0] };
  }

  if (exact.length > 1) {
    return { kind: 'ambiguous', candidates: exact.slice(0, 5) };
  }

  const queryTokens = tokenizeReference(query);
  const contained = tasks.filter((task) =>
    containsAllQueryTokens(queryTokens, task),
  );

  if (contained.length === 1) {
    return { kind: 'likely', task: contained[0] };
  }

  if (contained.length > 1) {
    return { kind: 'ambiguous', candidates: contained.slice(0, 5) };
  }

  const scored = tasks
    .map((task) => ({ task, score: scoreCandidate(queryTokens, task) }))
    .filter((candidate) => candidate.score > 0)
    .sort((left, right) => right.score - left.score);

  if (scored.length === 0) return { kind: 'none' };
  if (scored.length === 1) return { kind: 'likely', task: scored[0].task };

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

function readClarificationOrdinalIndex(value: string): number | null {
  const normalized = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  const ordinalByToken: Record<string, number> = {
    '1': 0,
    '1st': 0,
    first: 0,
    '2': 1,
    '2nd': 1,
    second: 1,
    '3': 2,
    '3rd': 2,
    third: 2,
    '4': 3,
    '4th': 3,
    fourth: 3,
    '5': 4,
    '5th': 4,
    fifth: 4,
  };

  const tokens = normalized.split(' ').filter(Boolean);
  const ordinalTokens = tokens
    .map((token) => ordinalByToken[token])
    .filter((index): index is number => index !== undefined);

  if (ordinalTokens.length !== 1) return null;
  return ordinalTokens[0];
}

export function resolveTaskDeletionClarificationReference(
  reply: string,
  candidates: MemoryTask[],
): TaskDeletionReferenceResolution {
  if (candidates.length === 0) return { kind: 'none' };

  const ordinalIndex = readClarificationOrdinalIndex(reply);
  if (ordinalIndex !== null) {
    const ordinalTask = candidates[ordinalIndex] ?? null;
    return ordinalTask
      ? { kind: 'exact', task: ordinalTask }
      : { kind: 'none' };
  }

  return resolveTaskDeletionReference(reply, candidates);
}

function cleanDeletionQuery(value: string): string {
  return value
    .replace(/^["'`]+|["'`]+$/g, '')
    .replace(/^(?:the|my|our)\s+/i, '')
    .replace(/\s+(?:task|to[- ]?do)$/i, '')
    .replace(/[.!?]+$/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractNaturalDeletionQuery(statement: string): string | null {
  const trimmed = statement.replace(/\s+/g, ' ').trim();
  if (!trimmed) return null;

  const taskFirst = trimmed.match(
    /^(?:please\s+)?(?:delete|remove|erase)\s+(?:the\s+)?(?:task|to[- ]?do)\s+(?:(?:called|named|about)\s+)?(.+?)\s*[.!?]*$/i,
  );
  if (taskFirst?.[1]) return cleanDeletionQuery(taskFirst[1]);

  const fromList = trimmed.match(
    /^(?:please\s+)?(?:delete|remove|erase)\s+(.+?)\s+from\s+(?:(?:my|our|the)\s+)?(?:tasks?|task\s+list|to[- ]?do(?:\s+list)?|todo(?:\s+list)?)\s*[.!?]*$/i,
  );
  if (fromList?.[1]) return cleanDeletionQuery(fromList[1]);

  const taskLast = trimmed.match(
    /^(?:please\s+)?(?:delete|remove|erase)\s+(?:the\s+)?(.+?)\s+(?:task|to[- ]?do)\s*[.!?]*$/i,
  );
  if (taskLast?.[1]) return cleanDeletionQuery(taskLast[1]);

  return null;
}

export function resolveNaturalGlobalTaskDeletionRequest(
  statement: string,
  tasks: MemoryTask[],
): NaturalGlobalTaskDeletionRequest | null {
  const query = extractNaturalDeletionQuery(statement);
  if (!query) return null;

  return {
    query,
    resolution: resolveTaskDeletionReference(query, tasks),
  };
}

function readValidatedDeleteQuery(
  argumentsValue: Record<string, unknown>,
): string | null {
  if (Object.keys(argumentsValue).length !== 2) return null;
  if (argumentsValue.scope !== 'global') return null;

  const query = argumentsValue.query;
  if (typeof query !== 'string') return null;

  const cleanQuery = query.replace(/\s+/g, ' ').trim();
  if (
    !cleanQuery ||
    cleanQuery.length > 240 ||
    /[\x00-\x1f\x7f]/.test(cleanQuery)
  ) {
    return null;
  }

  return cleanQuery;
}

export function isPromotedTaskDeleteToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.turnOwner === 'tasks' &&
      decision.disposition === 'tool' &&
      decision.proposedCapability === 'tasks' &&
      decision.proposedAction === 'delete-task',
  );
}

export function resolvePromotedTaskDeleteToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedTaskDeleteToolCommand | null {
  if (!isPromotedTaskDeleteToolDecision(decision) || !decision) return null;

  const query = readValidatedDeleteQuery(decision.proposedArguments);
  if (!query) return null;

  return { query };
}
