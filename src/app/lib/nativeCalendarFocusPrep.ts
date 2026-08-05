import {
  getCalendarEvents,
  getCalendarStatus,
  QMEET_API_BASE_URL,
} from '../api';
import type { ActiveSession, CalendarEvent, MemoryTask } from '../types';
import {
  applyVerifiedFocusProjection,
  isVerifiedNativeFocusStartResult,
  projectVerifiedFocusToActiveSession,
  type NativeFocusStartResult,
} from './nativeFocusLifecycle';
import {
  applyVerifiedFocusTaskProjection,
  type VerifiedNativeFocusTasksResult,
} from './nativeFocusTasks';

const CALENDAR_EVENTS_STORAGE_KEY = 'qmeet-calendar-events';

export const NATIVE_CALENDAR_FOCUS_OWNERSHIP_VERSION = 'phase20f';

type CalendarPrepVerificationPayload = {
  focusReceiptVerified?: unknown;
  taskReceiptVerified?: unknown;
  activeFocusMatches?: unknown;
  exactTasksPersisted?: unknown;
  relationshipPersisted?: unknown;
  sourceTurnUnique?: unknown;
  rollbackProtected?: unknown;
};

type CalendarPrepPayload = {
  ok?: unknown;
  operation?: unknown;
  outcome?: unknown;
  verified?: unknown;
  event?: unknown;
  focusReceipt?: unknown;
  taskReceipt?: unknown;
  sourceTurnId?: unknown;
  verification?: unknown;
  message?: unknown;
};

export type VerifiedNativeCalendarFocusPrepResult = {
  ok: true;
  operation: 'prepare_calendar_focus';
  outcome: 'created' | 'linked' | 'reused';
  verified: true;
  event: CalendarEvent;
  focusReceipt: NativeFocusStartResult;
  taskReceipt: VerifiedNativeFocusTasksResult;
  sourceTurnId: string;
  message: string;
};

export class NativeCalendarFocusPrepClientError extends Error {
  readonly code: string;

  constructor(message: string, code = 'native_calendar_focus_prep_failed') {
    super(message);
    this.name = 'NativeCalendarFocusPrepClientError';
    this.code = code;
  }
}

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

function stableCalendarFingerprint(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function createCalendarPrepSourceTurnId(event: CalendarEvent): string {
  const fingerprint = JSON.stringify([
    event.id,
    event.title,
    event.dateKey,
    event.time,
    event.start ?? '',
    event.end ?? '',
    event.location ?? '',
    event.description ?? '',
    event.googleEventId ?? '',
    event.calendarId ?? '',
  ]);
  return `calendar-focus-${stableCalendarFingerprint(fingerprint)}`;
}

function normalizeCalendarEvent(value: unknown): CalendarEvent | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Record<string, unknown>;
  const id = normalizeText(candidate.id);
  const title = normalizeText(candidate.title);
  if (!id || !title) return null;
  const source =
    candidate.source === 'google' || normalizeText(candidate.googleEventId)
      ? 'google'
      : 'local';
  return {
    id,
    title,
    dateKey: normalizeText(candidate.dateKey),
    time: normalizeText(candidate.time) || 'Later',
    createdAt: normalizeText(candidate.createdAt) || new Date().toISOString(),
    source,
    ...(normalizeText(candidate.googleEventId)
      ? { googleEventId: normalizeText(candidate.googleEventId) }
      : {}),
    ...(typeof candidate.start === 'string' && candidate.start.trim()
      ? { start: candidate.start.trim() }
      : {}),
    ...(typeof candidate.end === 'string' && candidate.end.trim()
      ? { end: candidate.end.trim() }
      : {}),
    ...(normalizeText(candidate.location)
      ? { location: normalizeText(candidate.location) }
      : {}),
    ...(normalizeText(candidate.description)
      ? { description: normalizeText(candidate.description) }
      : {}),
    ...(typeof candidate.allDay === 'boolean'
      ? { allDay: candidate.allDay }
      : {}),
    ...(normalizeText(candidate.calendarId)
      ? { calendarId: normalizeText(candidate.calendarId) }
      : {}),
  };
}

function calendarEventMatchesExpected(
  actual: CalendarEvent,
  expectedInput: CalendarEvent,
): boolean {
  const expected = normalizeCalendarEvent(expectedInput);
  if (!expected) return false;
  return (
    actual.id === expected.id &&
    actual.title === expected.title &&
    actual.dateKey === expected.dateKey &&
    actual.time === expected.time &&
    actual.createdAt === expected.createdAt &&
    actual.source === expected.source &&
    (actual.googleEventId ?? '') === (expected.googleEventId ?? '') &&
    (actual.start ?? '') === (expected.start ?? '') &&
    (actual.end ?? '') === (expected.end ?? '') &&
    (actual.location ?? '') === (expected.location ?? '') &&
    (actual.description ?? '') === (expected.description ?? '') &&
    Boolean(actual.allDay) === Boolean(expected.allDay) &&
    (actual.calendarId ?? '') === (expected.calendarId ?? '')
  );
}

function readStoredCalendarEvents(): CalendarEvent[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(CALENDAR_EVENTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map(normalizeCalendarEvent)
      .filter((event): event is CalendarEvent => event !== null);
  } catch {
    return [];
  }
}

function parseClockTimeForDate(dateKey: string, time: string): number | null {
  const baseDate = new Date(`${dateKey}T00:00:00`);
  if (Number.isNaN(baseDate.getTime())) return null;
  const cleanedTime = time.trim().toLowerCase();
  if (!cleanedTime || cleanedTime === 'later' || cleanedTime === 'all day') {
    baseDate.setHours(12, 0, 0, 0);
    return baseDate.getTime();
  }
  const match = cleanedTime.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/i);
  if (!match) {
    baseDate.setHours(12, 0, 0, 0);
    return baseDate.getTime();
  }
  let hours = Number(match[1]);
  const minutes = Number(match[2] ?? '0');
  const meridiem = match[3]?.toLowerCase();
  if (meridiem === 'pm' && hours < 12) hours += 12;
  if (meridiem === 'am' && hours === 12) hours = 0;
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null;
  baseDate.setHours(hours, minutes, 0, 0);
  return baseDate.getTime();
}

function getCalendarEventStartTimestamp(event: CalendarEvent): number {
  if (event.start) {
    const timestamp = Date.parse(event.start);
    if (Number.isFinite(timestamp)) return timestamp;
  }
  if (event.dateKey) {
    const timestamp = parseClockTimeForDate(event.dateKey, event.time || 'Later');
    if (timestamp !== null) return timestamp;
  }
  const created = Date.parse(event.createdAt || '');
  return Number.isFinite(created) ? created : 0;
}

export function selectNextCalendarEvent(
  events: CalendarEvent[],
  now = Date.now(),
): CalendarEvent | null {
  const candidates = events
    .map((event) => ({ event, timestamp: getCalendarEventStartTimestamp(event) }))
    .filter(({ timestamp }) => Number.isFinite(timestamp));
  const upcoming = candidates
    .filter(({ timestamp }) => timestamp >= now - 5 * 60 * 1000)
    .sort((left, right) => left.timestamp - right.timestamp);
  if (upcoming[0]) return upcoming[0].event;
  return candidates.sort((left, right) => right.timestamp - left.timestamp)[0]
    ?.event ?? null;
}

export function buildCalendarPrepTaskTitles(event: CalendarEvent): string[] {
  const title = normalizeText(event.title) || 'Calendar event';
  return [
    `Review details for ${title}`,
    `Gather relevant notes or documents for ${title}`,
    `Prepare questions for ${title}`,
    `Identify decisions or next steps needed for ${title}`,
    `Capture follow-up items after ${title}`,
  ];
}

async function readCalendarEventsForPrep(): Promise<CalendarEvent[]> {
  try {
    const status = await getCalendarStatus();
    if (status.connected) {
      const response = await getCalendarEvents('week');
      return response.events
        .map(normalizeCalendarEvent)
        .filter((event): event is CalendarEvent => event !== null);
    }
  } catch {
    // Local calendar events remain a valid input when Google Calendar is unavailable.
  }
  return readStoredCalendarEvents();
}

function normalizeTask(value: unknown): MemoryTask | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Record<string, unknown>;
  const id = normalizeText(candidate.id);
  const title = normalizeText(candidate.title);
  const createdAt = normalizeText(candidate.createdAt);
  const completedAt = normalizeText(candidate.completedAt);
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
  if (new Set(normalized.map((task) => task.id)).size !== normalized.length) {
    return null;
  }
  return normalized;
}

function normalizeStringList(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const normalized = value.map(normalizeText);
  return normalized.every(Boolean) ? normalized : null;
}

function validateTaskReceipt(
  value: unknown,
  expectedFocusId: string,
  expectedTitles: string[],
  expectedSourceTurnId: string,
): VerifiedNativeFocusTasksResult | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Record<string, unknown>;
  const verification = candidate.verification as Record<string, unknown> | null;
  const tasks = normalizeTaskList(candidate.tasks);
  const memoryTasks = normalizeTaskList(candidate.memoryTasks);
  const createdTaskIds = normalizeStringList(candidate.createdTaskIds);
  const taskIds = new Set((tasks ?? []).map((task) => task.id));
  const memoryById = new Map(
    (memoryTasks ?? []).map((task) => [task.id, task] as const),
  );
  const exactTitles =
    tasks?.length === expectedTitles.length &&
    tasks.every((task, index) => task.title === expectedTitles[index]);
  const exactMemory = (tasks ?? []).every((task) => {
    const persisted = memoryById.get(task.id);
    return (
      persisted?.title === task.title &&
      persisted.createdAt === task.createdAt &&
      persisted.completedAt === task.completedAt
    );
  });
  const createdIdsBelongToReceipt = (createdTaskIds ?? []).every((id) =>
    taskIds.has(id),
  );
  const outcome = candidate.outcome;
  if (
    candidate.ok !== true ||
    candidate.operation !== 'link_focus_tasks' ||
    (outcome !== 'created' && outcome !== 'linked' && outcome !== 'reused') ||
    candidate.verified !== true ||
    normalizeText(candidate.focusId) !== expectedFocusId ||
    normalizeText(candidate.sourceTurnId) !== expectedSourceTurnId ||
    !normalizeText(candidate.focusTitle) ||
    !normalizeText(candidate.receiptId) ||
    !normalizeText(candidate.linkedAt) ||
    !normalizeText(candidate.message) ||
    !tasks ||
    !memoryTasks ||
    !createdTaskIds ||
    !exactTitles ||
    !exactMemory ||
    !createdIdsBelongToReceipt ||
    verification?.activeFocusMatches !== true ||
    verification.tasksPersisted !== true ||
    verification.relationshipPersisted !== true ||
    verification.sourceTurnUnique !== true
  ) {
    return null;
  }
  return {
    ok: true,
    operation: 'link_focus_tasks',
    outcome,
    verified: true,
    focusId: expectedFocusId,
    focusTitle: normalizeText(candidate.focusTitle),
    tasks,
    memoryTasks,
    createdTaskIds,
    receiptId: normalizeText(candidate.receiptId),
    linkedAt: normalizeText(candidate.linkedAt),
    sourceTurnId: expectedSourceTurnId,
    message: normalizeText(candidate.message),
  };
}

function parseErrorPayload(payload: unknown): { code: string; message: string } {
  if (!payload || typeof payload !== 'object') {
    return {
      code: 'native_calendar_focus_prep_failed',
      message: 'The calendar Focus preparation request failed.',
    };
  }
  const candidate = payload as Record<string, unknown>;
  const detail = candidate.detail;
  if (detail && typeof detail === 'object') {
    const detailRecord = detail as Record<string, unknown>;
    return {
      code:
        normalizeText(detailRecord.code) || 'native_calendar_focus_prep_failed',
      message:
        normalizeText(detailRecord.message) ||
        'The calendar Focus preparation request failed.',
    };
  }
  return {
    code: normalizeText(candidate.code) || 'native_calendar_focus_prep_failed',
    message:
      normalizeText(candidate.message) ||
      'The calendar Focus preparation request failed.',
  };
}

function validateCalendarPrepPayload(
  rawPayload: unknown,
  expectedEvent: CalendarEvent,
  expectedSourceTurnId: string,
): VerifiedNativeCalendarFocusPrepResult {
  if (!rawPayload || typeof rawPayload !== 'object') {
    throw new NativeCalendarFocusPrepClientError(
      'The canonical calendar Focus response was not an object.',
      'invalid_response',
    );
  }
  const payload = rawPayload as CalendarPrepPayload;
  const verification =
    payload.verification as CalendarPrepVerificationPayload | null;
  const event = normalizeCalendarEvent(payload.event);
  const focusReceipt = payload.focusReceipt;
  const expectedTitles = buildCalendarPrepTaskTitles(expectedEvent);
  if (!isVerifiedNativeFocusStartResult(focusReceipt, expectedSourceTurnId)) {
    throw new NativeCalendarFocusPrepClientError(
      'The calendar response did not contain a verified canonical Focus start receipt.',
      'verification_failed',
    );
  }
  const taskReceipt = validateTaskReceipt(
    payload.taskReceipt,
    focusReceipt.activeFocus.focusId,
    expectedTitles,
    expectedSourceTurnId,
  );
  const outcome = payload.outcome;
  const valid =
    payload.ok === true &&
    payload.operation === 'prepare_calendar_focus' &&
    (outcome === 'created' || outcome === 'linked' || outcome === 'reused') &&
    payload.verified === true &&
    normalizeText(payload.sourceTurnId) === expectedSourceTurnId &&
    Boolean(normalizeText(payload.message)) &&
    event !== null &&
    calendarEventMatchesExpected(event, expectedEvent) &&
    taskReceipt !== null &&
    verification?.focusReceiptVerified === true &&
    verification?.taskReceiptVerified === true &&
    verification?.activeFocusMatches === true &&
    verification?.exactTasksPersisted === true &&
    verification?.relationshipPersisted === true &&
    verification?.sourceTurnUnique === true &&
    verification?.rollbackProtected === true;
  if (
    !valid ||
    !event ||
    !taskReceipt ||
    (outcome !== 'created' && outcome !== 'linked' && outcome !== 'reused')
  ) {
    throw new NativeCalendarFocusPrepClientError(
      'The canonical response did not prove the exact calendar Focus, tasks, relationship, and source-turn receipt.',
      'verification_failed',
    );
  }
  return {
    ok: true,
    operation: 'prepare_calendar_focus',
    outcome,
    verified: true,
    event,
    focusReceipt,
    taskReceipt,
    sourceTurnId: expectedSourceTurnId,
    message: normalizeText(payload.message),
  };
}

export async function prepareNextCalendarFocusVerified(input: {
  sourceTurnId?: string;
} = {}): Promise<VerifiedNativeCalendarFocusPrepResult> {
  const events = await readCalendarEventsForPrep();
  const event = selectNextCalendarEvent(events);
  if (!event) {
    throw new NativeCalendarFocusPrepClientError(
      'No calendar event was found to prepare for. Connect Google Calendar or add a local event first.',
      'no_calendar_event',
    );
  }
  const sourceTurnId =
    normalizeText(input.sourceTurnId) || createCalendarPrepSourceTurnId(event);
  let response: Response;
  try {
    response = await fetch(
      `${QMEET_API_BASE_URL}/api/focus/lifecycle/calendar-prep`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'x-qmeet-turn-id': sourceTurnId,
        },
        body: JSON.stringify({ event, sourceTurnId }),
      },
    );
  } catch (error) {
    throw new NativeCalendarFocusPrepClientError(
      error instanceof Error && error.message.trim()
        ? error.message
        : 'The native calendar Focus endpoint was unavailable.',
      'endpoint_unavailable',
    );
  }
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Validation below rejects unreadable successful responses.
  }
  if (!response.ok) {
    const parsed = parseErrorPayload(payload);
    throw new NativeCalendarFocusPrepClientError(parsed.message, parsed.code);
  }
  return validateCalendarPrepPayload(payload, event, sourceTurnId);
}

export function applyVerifiedCalendarFocusPrepProjection(
  result: VerifiedNativeCalendarFocusPrepResult,
): ActiveSession {
  const focusProjection = projectVerifiedFocusToActiveSession(
    result.focusReceipt,
    'meeting',
  );
  applyVerifiedFocusProjection(focusProjection);
  return applyVerifiedFocusTaskProjection(result.taskReceipt);
}

export function describeNativeCalendarFocusPrepFailure(error: unknown): string {
  const reason =
    error instanceof Error && error.message.trim()
      ? ` ${error.message.trim()}`
      : '';
  return (
    'I could not verify one canonical transaction for the calendar Focus and its linked tasks, ' +
    `so I will not claim the preparation started.${reason}`
  );
}
