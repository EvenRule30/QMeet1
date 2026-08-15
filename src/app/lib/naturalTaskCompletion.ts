import type { ActiveSession, MemoryTask } from '../types';

type ScoredTask = {
  task: MemoryTask;
  score: number;
  matchedWeight: number;
  matchedTokenCount: number;
};

const COMPLETION_OPENING = /^(?:i|we)(?:\s+(?:have|had)|['’]ve)?\s+(?:already\s+|just\s+)?(?:checked|verified|confirmed|found|chose|chosen|picked|selected|decided|determined|wrote|written|drafted|created|made|used|incorporated|added|scheduled|booked|reviewed|tailored|adapted|customized|customised|adjusted|compared|researched|identified|set|planned|outlined|prepared|handled|fixed|resolved|sent|submitted|called|contacted|emailed|updated|tested|ran|built|implemented|finished|completed|did|got\s+through)\b/i;

const COMPLETION_VERB_FORMS = [
  'checked',
  'verified',
  'confirmed',
  'found',
  'chose',
  'chosen',
  'picked',
  'selected',
  'decided',
  'determined',
  'wrote',
  'written',
  'drafted',
  'created',
  'made',
  'used',
  'incorporated',
  'added',
  'scheduled',
  'booked',
  'reviewed',
  'tailored',
  'adapted',
  'customized',
  'customised',
  'adjusted',
  'compared',
  'researched',
  'identified',
  'set',
  'planned',
  'outlined',
  'prepared',
  'handled',
  'fixed',
  'resolved',
  'sent',
  'submitted',
  'called',
  'contacted',
  'emailed',
  'updated',
  'tested',
  'ran',
  'built',
  'implemented',
  'finished',
  'completed',
  'did',
];

const STOP_WORDS = new Set([
  'a',
  'an',
  'and',
  'are',
  'as',
  'at',
  'be',
  'been',
  'being',
  'but',
  'by',
  'for',
  'from',
  'had',
  'has',
  'have',
  'i',
  'in',
  'is',
  'it',
  'me',
  'my',
  'of',
  'on',
  'or',
  'our',
  'that',
  'the',
  'their',
  'them',
  'this',
  'to',
  'us',
  'was',
  'we',
  'were',
  'with',
  'you',
  'your',
  'already',
  'just',
  'done',
  'finish',
  'finished',
  'complete',
  'completed',
]);

const LOW_VALUE_TOKENS = new Set(['focus', 'plan', 'task', 'work']);

const TOKEN_ALIASES: Record<string, string> = {
  checked: 'check',
  did: 'do',
  checking: 'check',
  verifies: 'check',
  verified: 'check',
  verifying: 'check',
  found: 'select',
  finding: 'select',
  find: 'select',
  chose: 'select',
  chosen: 'select',
  choose: 'select',
  picked: 'select',
  picking: 'select',
  pick: 'select',
  selected: 'select',
  selecting: 'select',
  select: 'select',
  matches: 'match',
  matching: 'match',
  matched: 'match',
  constraints: 'constraint',
  preferences: 'preference',
  details: 'detail',
  days: 'day',
  dates: 'date',
  budget: 'budget',
  budgets: 'budget',
  cost: 'budget',
  costs: 'budget',
  outcome: 'outcome',
  outcomes: 'outcome',
  result: 'outcome',
  results: 'outcome',
  availability: 'available',
  destination: 'destination',
  destinations: 'destination',
  location: 'destination',
  locations: 'destination',
  place: 'destination',
  places: 'destination',
  confirmed: 'confirm',
  confirming: 'confirm',
  wrote: 'write',
  written: 'write',
  writing: 'write',
  drafted: 'write',
  drafting: 'write',
  decided: 'decide',
  determining: 'decide',
  determined: 'decide',
  used: 'use',
  using: 'use',
  incorporated: 'use',
  incorporating: 'use',
  reviewed: 'review',
  tailored: 'tailor',
  tailoring: 'tailor',
  adapted: 'tailor',
  adapting: 'tailor',
  customized: 'tailor',
  customizing: 'tailor',
  customised: 'tailor',
  customising: 'tailor',
  adjusted: 'tailor',
  adjusting: 'tailor',
  reviewing: 'review',
  compared: 'compare',
  comparing: 'compare',
  researched: 'research',
  researching: 'research',
  identified: 'identify',
  identifying: 'identify',
  scheduled: 'schedule',
  booking: 'book',
  booked: 'book',
  prepared: 'prepare',
  preparing: 'prepare',
  fixed: 'fix',
  fixing: 'fix',
  resolved: 'resolve',
  resolving: 'resolve',
  sent: 'send',
  submitted: 'submit',
  tested: 'test',
  testing: 'test',
  built: 'build',
  implemented: 'implement',
  implementing: 'implement',
};

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

function canonicalCompletionVerb(rawToken: string): string | null {
  const token = rawToken.toLowerCase();
  const exact = COMPLETION_VERB_FORMS.find((candidate) => candidate === token);
  if (exact) return exact;
  if (token.length < 5) return null;

  return (
    COMPLETION_VERB_FORMS.find(
      (candidate) =>
        candidate.length >= 5 &&
        differsByAtMostOneEdit(token, candidate),
    ) ?? null
  );
}

function looksLikeCompletedWorkStatement(value: string): boolean {
  if (COMPLETION_OPENING.test(value)) return true;

  const passive = value.match(
    /^(.+?)\s+(?:(?:has|have|had)\s+been|(?:was|were|is|are))\s+([a-z]+)\s*[.!?]*$/i,
  );
  if (passive?.[2] && canonicalCompletionVerb(passive[2])) {
    return true;
  }

  const firstPersonFuzzy = value.match(
    /^(?:i|we)(?:['’]ve|\s+have)?\s+(?:already\s+|just\s+)?([a-z]+)\b/i,
  );
  return Boolean(
    firstPersonFuzzy?.[1] &&
      canonicalCompletionVerb(firstPersonFuzzy[1]),
  );
}

function normalizeToken(
  rawToken: string,
  tolerateCompletionVerbTypos = false,
): string {
  let token = rawToken.toLowerCase();

  if (tolerateCompletionVerbTypos) {
    const completionVerb = canonicalCompletionVerb(token);
    if (completionVerb) token = completionVerb;
  }

  if (TOKEN_ALIASES[token]) return TOKEN_ALIASES[token];

  if (/^[a-z]{5,}ies$/.test(token)) {
    return `${token.slice(0, -3)}y`;
  }
  if (/^[a-z]{5,}s$/.test(token) && !token.endsWith('ss')) {
    return token.slice(0, -1);
  }
  return token;
}

function tokenize(
  value: string,
  options: { tolerateCompletionVerbTypos?: boolean } = {},
): string[] {
  const normalized = value
    .toLowerCase()
    .replace(/(\d),(?=\d{3}\b)/g, '$1')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!normalized) return [];

  return Array.from(
    new Set(
      normalized
        .split(' ')
        .map((token) =>
          normalizeToken(
            token,
            Boolean(options.tolerateCompletionVerbTypos),
          ),
        )
        .filter((token) => token.length > 1 || /^\d+$/.test(token))
        .filter((token) => !STOP_WORDS.has(token)),
    ),
  );
}

function tokenWeight(token: string): number {
  if (/^\d+$/.test(token)) return 3;
  if (LOW_VALUE_TOKENS.has(token)) return 0.35;
  if (token.length >= 7) return 1.4;
  if (token.length >= 5) return 1.2;
  return 1;
}

function openFocusLinkedTasks(
  tasks: MemoryTask[],
  activeSession: ActiveSession | null,
): MemoryTask[] {
  if (!activeSession) return [];

  const openTaskById = new Map(
    tasks.filter((task) => !task.completedAt).map((task) => [task.id, task]),
  );

  return activeSession.linkedTaskIds
    .map((taskId) => openTaskById.get(taskId))
    .filter((task): task is MemoryTask => Boolean(task));
}

function scoreTask(statementTokens: string[], task: MemoryTask): ScoredTask {
  const taskTokens = tokenize(task.title);
  const taskTokenSet = new Set(taskTokens);
  const matchedTokens = statementTokens.filter((token) =>
    taskTokenSet.has(token),
  );
  const statementWeight = statementTokens.reduce(
    (total, token) => total + tokenWeight(token),
    0,
  );
  const taskWeight = taskTokens.reduce(
    (total, token) => total + tokenWeight(token),
    0,
  );
  const matchedWeight = matchedTokens.reduce(
    (total, token) => total + tokenWeight(token),
    0,
  );
  const statementCoverage =
    statementWeight > 0 ? matchedWeight / statementWeight : 0;
  const taskCoverage = taskWeight > 0 ? matchedWeight / taskWeight : 0;
  const score = statementCoverage * 0.75 + taskCoverage * 0.25;

  return {
    task,
    score,
    matchedWeight,
    matchedTokenCount: matchedTokens.length,
  };
}

export function resolveNaturalFocusTaskCompletionTarget(
  statement: string,
  tasks: MemoryTask[],
  activeSession: ActiveSession | null,
): MemoryTask | null {
  const trimmed = statement.replace(/\s+/g, ' ').trim();
  if (!trimmed || !looksLikeCompletedWorkStatement(trimmed)) return null;

  const candidateTasks = openFocusLinkedTasks(tasks, activeSession);
  if (candidateTasks.length === 0) return null;

  const statementTokens = tokenize(trimmed, {
    tolerateCompletionVerbTypos: true,
  });
  if (statementTokens.length === 0) return null;

  const scoredTasks = candidateTasks
    .map((task) => scoreTask(statementTokens, task))
    .filter(
      (candidate) =>
        candidate.matchedTokenCount >= 2 &&
        candidate.matchedWeight >= 2 &&
        candidate.score >= 0.5,
    )
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score;
      if (right.matchedWeight !== left.matchedWeight) {
        return right.matchedWeight - left.matchedWeight;
      }
      return 0;
    });

  const best = scoredTasks[0];
  if (!best) return null;

  const runnerUp = scoredTasks[1];
  if (
    runnerUp &&
    Math.abs(best.score - runnerUp.score) < 0.12 &&
    Math.abs(best.matchedWeight - runnerUp.matchedWeight) < 1
  ) {
    return null;
  }

  return best.task;
}
