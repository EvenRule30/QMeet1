import { QMEET_API_BASE_URL } from '../api';
import type { ActiveSession, MemoryTask } from '../types';
import {
  buildNativeFocusContextTaskTitles,
  readNativeFocusContext,
} from './nativeFocusContext';
import {
  applyVerifiedFocusProjection,
  readVerifiedFocusProjection,
} from './nativeFocusLifecycle';

const MEMORY_TASKS_STORAGE_KEY = 'qmeet-memory-tasks';
const MEMORY_TASKS_STATE_EVENT = 'qmeet-memory-tasks-state';

export const NATIVE_FOCUS_TASK_OWNERSHIP_VERSION = 'phase20e2b';

type NativeFocusTaskVerification = {
  activeFocusMatches?: unknown;
  tasksPersisted?: unknown;
  relationshipPersisted?: unknown;
  sourceTurnUnique?: unknown;
  details?: unknown;
};

type NativeFocusTasksPayload = {
  ok?: unknown;
  operation?: unknown;
  outcome?: unknown;
  verified?: unknown;
  focusId?: unknown;
  focusTitle?: unknown;
  tasks?: unknown;
  memoryTasks?: unknown;
  createdTaskIds?: unknown;
  receiptId?: unknown;
  linkedAt?: unknown;
  sourceTurnId?: unknown;
  verification?: unknown;
  message?: unknown;
};

export type VerifiedNativeFocusTasksResult = {
  ok: true;
  operation: 'link_focus_tasks';
  outcome: 'created' | 'linked' | 'reused';
  verified: true;
  focusId: string;
  focusTitle: string;
  tasks: MemoryTask[];
  memoryTasks: MemoryTask[];
  createdTaskIds: string[];
  receiptId: string;
  linkedAt: string;
  sourceTurnId: string;
  message: string;
};

export class NativeFocusTasksClientError extends Error {
  code: string;

  constructor(message: string, code = 'native_focus_tasks_failed') {
    super(message);
    this.name = 'NativeFocusTasksClientError';
    this.code = code;
  }
}

function createSourceTurnId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `focus-tasks-${crypto.randomUUID()}`;
  }
  return `focus-tasks-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

function normalizeTask(value: unknown): MemoryTask | null {
  if (!value || typeof value !== 'object') return null;
  const task = value as Record<string, unknown>;
  const id = normalizeText(task.id);
  const title = normalizeText(task.title);
  const createdAt = normalizeText(task.createdAt);
  const completedAt = normalizeText(task.completedAt);
  if (!id || !title || !createdAt) return null;
  return {
    id,
    title,
    createdAt,
    ...(completedAt ? { completedAt } : {}),
  };
}

function normalizeTaskList(value: unknown): MemoryTask[] | null {
  if (!Array.isArray(value)) return null;
  const tasks = value.map(normalizeTask);
  if (tasks.some((task) => task === null)) return null;
  const normalized = tasks as MemoryTask[];
  const ids = normalized.map((task) => task.id);
  if (new Set(ids).size !== ids.length) return null;
  return normalized;
}

function normalizeStringList(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const values = value.map(normalizeText);
  if (values.some((item) => !item)) return null;
  return values;
}

function parseErrorPayload(payload: unknown): { code: string; message: string } {
  if (!payload || typeof payload !== 'object') {
    return {
      code: 'native_focus_tasks_failed',
      message: 'The Focus task request failed.',
    };
  }
  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  if (detail && typeof detail === 'object') {
    const detailRecord = detail as Record<string, unknown>;
    return {
      code: normalizeText(detailRecord.code) || 'native_focus_tasks_failed',
      message:
        normalizeText(detailRecord.message) || 'The Focus task request failed.',
    };
  }
  return {
    code: normalizeText(record.code) || 'native_focus_tasks_failed',
    message: normalizeText(record.message) || 'The Focus task request failed.',
  };
}

function validatePayload(
  rawPayload: unknown,
  expectedFocusId: string,
  expectedTaskTitles: string[],
  expectedSourceTurnId: string,
): VerifiedNativeFocusTasksResult {
  if (!rawPayload || typeof rawPayload !== 'object') {
    throw new NativeFocusTasksClientError(
      'The canonical Focus task response was not an object.',
      'invalid_response',
    );
  }

  const payload = rawPayload as NativeFocusTasksPayload;
  const verification = payload.verification as NativeFocusTaskVerification | null;
  const tasks = normalizeTaskList(payload.tasks);
  const memoryTasks = normalizeTaskList(payload.memoryTasks);
  const createdTaskIds = normalizeStringList(payload.createdTaskIds);
  const outcome = payload.outcome;
  const focusId = normalizeText(payload.focusId);
  const sourceTurnId = normalizeText(payload.sourceTurnId);
  const receiptId = normalizeText(payload.receiptId);
  const linkedAt = normalizeText(payload.linkedAt);
  const message = normalizeText(payload.message);
  const normalizedExpectedTitles = expectedTaskTitles.map(normalizeText);
  const taskTitlesMatch =
    tasks !== null &&
    tasks.length === normalizedExpectedTitles.length &&
    tasks.every((task, index) => task.title === normalizedExpectedTitles[index]);
  const taskIds = new Set((tasks ?? []).map((task) => task.id));
  const memoryTaskMap = new Map(
    (memoryTasks ?? []).map((task) => [task.id, task] as const),
  );
  const receiptTasksAppearInMemory = (tasks ?? []).every((task) => {
    const persisted = memoryTaskMap.get(task.id);
    return (
      persisted?.title === task.title &&
      persisted.createdAt === task.createdAt &&
      persisted.completedAt === task.completedAt
    );
  });
  const createdIdsAreReceiptTasks = (createdTaskIds ?? []).every((id) =>
    taskIds.has(id),
  );

  const valid =
    payload.ok === true &&
    payload.operation === 'link_focus_tasks' &&
    (outcome === 'created' || outcome === 'linked' || outcome === 'reused') &&
    payload.verified === true &&
    focusId === expectedFocusId &&
    sourceTurnId === expectedSourceTurnId &&
    Boolean(receiptId) &&
    Boolean(linkedAt) &&
    Boolean(message) &&
    tasks !== null &&
    tasks.length > 0 &&
    memoryTasks !== null &&
    createdTaskIds !== null &&
    taskTitlesMatch &&
    receiptTasksAppearInMemory &&
    createdIdsAreReceiptTasks &&
    verification?.activeFocusMatches === true &&
    verification?.tasksPersisted === true &&
    verification?.relationshipPersisted === true &&
    verification?.sourceTurnUnique === true;

  if (
    !valid ||
    !tasks ||
    !memoryTasks ||
    !createdTaskIds ||
    (outcome !== 'created' && outcome !== 'linked' && outcome !== 'reused')
  ) {
    throw new NativeFocusTasksClientError(
      'The canonical Focus task response did not prove that the exact tasks and Focus relationship were persisted.',
      'verification_failed',
    );
  }

  return {
    ok: true,
    operation: 'link_focus_tasks',
    outcome,
    verified: true,
    focusId,
    focusTitle: normalizeText(payload.focusTitle),
    tasks,
    memoryTasks,
    createdTaskIds,
    receiptId,
    linkedAt,
    sourceTurnId,
    message,
  };
}

function compactTaskSubject(value: string, fallback: string): string {
  const cleaned = normalizeText(value);
  if (!cleaned) return fallback;
  return cleaned.length > 72 ? `${cleaned.slice(0, 69).trim()}...` : cleaned;
}

function uniqueTaskTitles(titles: string[]): string[] {
  const seen = new Set<string>();
  const uniqueTitles: string[] = [];
  for (const title of titles) {
    const cleaned = normalizeText(title);
    if (!cleaned) continue;
    const key = cleaned.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    uniqueTitles.push(cleaned);
  }
  return uniqueTitles.slice(0, 5);
}

function inferFocusTaskKind(
  activeSession: ActiveSession,
): 'java-hello-world' | 'coding' | ActiveSession['mode'] {
  const combined = `${activeSession.title} ${activeSession.goal}`.toLowerCase();
  if (
    /\b(java|javac|jdk|eclipse|intellij|netbeans)\b/.test(combined) &&
    /hello\s*world/.test(combined)
  ) {
    return 'java-hello-world';
  }
  if (
    activeSession.mode === 'coding' ||
    /\b(code|coding|program|programming|script|app|bug|debug|compile|compiler|function|class|method|java|python|javascript|typescript|react|html|css|sql)\b/.test(
      combined,
    )
  ) {
    return 'coding';
  }
  return activeSession.mode;
}

function generateCodingFocusTaskTitles(activeSession: ActiveSession): string[] {
  const title = compactTaskSubject(activeSession.title, 'current coding focus');
  const goal = compactTaskSubject(activeSession.goal, title);
  const target = activeSession.goal ? goal : title;
  return uniqueTaskTitles([
    `Write down the exact expected result for ${target}`,
    `Create the smallest working version of ${target}`,
    'Run it and copy the first error or output back into QMeet',
    `Fix one issue at a time until ${target} runs correctly`,
    `Save or submit the finished ${title} work`,
  ]);
}

export function buildNativeFocusTaskTitles(
  activeSession: ActiveSession,
): string[] {
  const title = compactTaskSubject(activeSession.title, 'current focus');
  const goal = compactTaskSubject(activeSession.goal, title);
  const target = activeSession.goal ? goal : title;
  const taskKind = inferFocusTaskKind(activeSession);

  switch (taskKind) {
    case 'java-hello-world':
      return uniqueTaskTitles([
        'Create `HelloWorld.java` with a `public class HelloWorld`',
        'Add `public static void main(String[] args)`',
        'Print `Hello, world!` from inside `main`',
        'Compile with `javac HelloWorld.java`',
        'Run with `java HelloWorld` and verify the output',
      ]);
    case 'coding':
      return generateCodingFocusTaskTitles(activeSession);
    case 'research':
      return uniqueTaskTitles([
        `Write the main question you need answered for ${title}`,
        `Find two useful sources or examples for ${target}`,
        `Compare the sources and note the tradeoffs for ${title}`,
        `Choose the next action from the ${title} research`,
      ]);
    case 'meeting':
      return uniqueTaskTitles([
        `Write the meeting objective for ${title}`,
        `Prepare the three agenda points for ${target}`,
        `Capture decisions from ${title}`,
        `Save follow-up tasks after ${title}`,
      ]);
    case 'planning':
      return uniqueTaskTitles([
        `Define the finished outcome for ${title}`,
        `Break ${target} into visible milestones`,
        `Identify blockers or dependencies for ${title}`,
        'Choose the first action you can do in 10 minutes',
      ]);
    case 'personal':
      return uniqueTaskTitles([
        `Describe what done looks like for ${title}`,
        `Choose one small next step for ${target}`,
        `Set aside time for ${title}`,
        `Review progress on ${title}`,
      ]);
    default:
      return uniqueTaskTitles([
        `Decide the finished result for ${title}`,
        `Write the first concrete step for ${target}`,
        'Do the first step and report what happened',
        'Ask QMeet for help with the first blocker',
      ]);
  }
}


export async function buildContextAwareNativeFocusTaskTitles(
  activeSession: ActiveSession,
): Promise<string[]> {
  const baseTitles = buildNativeFocusTaskTitles(activeSession);
  try {
    const context = await readNativeFocusContext(activeSession.id);
    const contextTitles = buildNativeFocusContextTaskTitles(context);
    if (contextTitles.length === 0) return baseTitles;
    return uniqueTaskTitles([
      baseTitles[0] ?? `Decide the finished result for ${activeSession.title}`,
      ...contextTitles,
      ...baseTitles.slice(1),
    ]);
  } catch (error) {
    console.warn(
      'Canonical Focus context was unavailable while generating tasks; using the verified Focus objective only:',
      error,
    );
    return baseTitles;
  }
}

function getMeetingSubject(activeSession: ActiveSession): string {
  const withoutPrepPrefix = activeSession.title
    .replace(/^prepare\s+for\s+/i, '')
    .replace(/\s+/g, ' ')
    .trim();
  return compactTaskSubject(
    withoutPrepPrefix || activeSession.title,
    'this meeting',
  );
}

export function buildNativeMeetingFollowUpTaskTitles(
  activeSession: ActiveSession,
): string[] {
  const meetingSubject = getMeetingSubject(activeSession);
  return uniqueTaskTitles([
    `Capture decisions and outcomes from ${meetingSubject}`,
    `Send follow-up notes for ${meetingSubject}`,
    `Confirm owners and deadlines for action items from ${meetingSubject}`,
    `Schedule or confirm the next step after ${meetingSubject}`,
    `Update QMeet memory with remaining open questions from ${meetingSubject}`,
  ]);
}

export async function createNativeFocusTasksVerified(input: {
  expectedFocusId: string;
  taskTitles: string[];
  sourceTurnId?: string;
}): Promise<VerifiedNativeFocusTasksResult> {
  const expectedFocusId = normalizeText(input.expectedFocusId);
  const taskTitles = uniqueTaskTitles(input.taskTitles);
  if (!expectedFocusId) {
    throw new NativeFocusTasksClientError(
      'No verified active Focus is available for these tasks.',
      'missing_focus',
    );
  }
  if (taskTitles.length === 0) {
    throw new NativeFocusTasksClientError(
      'No valid Focus task titles were generated.',
      'missing_tasks',
    );
  }

  const sourceTurnId = normalizeText(input.sourceTurnId) || createSourceTurnId();
  let response: Response;
  try {
    response = await fetch(`${QMEET_API_BASE_URL}/api/focus/lifecycle/tasks`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'x-qmeet-turn-id': sourceTurnId,
      },
      body: JSON.stringify({
        expectedFocusId,
        taskTitles,
        sourceTurnId,
      }),
    });
  } catch (error) {
    throw new NativeFocusTasksClientError(
      error instanceof Error && error.message.trim()
        ? error.message
        : 'The native Focus task endpoint was unavailable.',
      'endpoint_unavailable',
    );
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Validation below reports an unreadable response safely.
  }
  if (!response.ok) {
    const parsed = parseErrorPayload(payload);
    throw new NativeFocusTasksClientError(parsed.message, parsed.code);
  }
  return validatePayload(payload, expectedFocusId, taskTitles, sourceTurnId);
}

export function applyVerifiedFocusTaskProjection(
  result: VerifiedNativeFocusTasksResult,
): ActiveSession {
  const current = readVerifiedFocusProjection();
  if (!current || current.id !== result.focusId) {
    throw new NativeFocusTasksClientError(
      'The displayed Focus changed before its verified tasks could be projected.',
      'stale_projection',
    );
  }
  if (typeof window === 'undefined') {
    throw new NativeFocusTasksClientError(
      'The browser task projection is unavailable.',
      'projection_unavailable',
    );
  }

  window.localStorage.setItem(
    MEMORY_TASKS_STORAGE_KEY,
    JSON.stringify(result.memoryTasks),
  );
  window.dispatchEvent(
    new CustomEvent(MEMORY_TASKS_STATE_EVENT, {
      detail: { tasks: result.memoryTasks },
    }),
  );

  const next: ActiveSession = {
    ...current,
    linkedTaskIds: [
      ...result.tasks.map((task) => task.id),
      ...current.linkedTaskIds.filter(
        (id) => !result.tasks.some((task) => task.id === id),
      ),
    ],
    updatedAt: result.linkedAt,
  };
  applyVerifiedFocusProjection(next);
  return next;
}

export function describeNativeFocusTasksFailure(error: unknown): string {
  const detail =
    error instanceof Error && error.message.trim()
      ? ` ${error.message.trim()}`
      : '';
  return (
    'I could not verify that the exact tasks and their canonical Focus relationship were saved, ' +
    `so I will not claim they were created.${detail}`
  );
}
