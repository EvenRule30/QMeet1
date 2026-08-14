import { parseCommand, type CommandMatch } from '../commands';
import type { PromotedSingleIntentDecision } from './agentShadowObserver';
import { buildCalendarEditFrontendCommand } from './calendarUtils';

export type PromotedSearchToolCommand = {
  query: string;
  commandMatch: CommandMatch;
};

export type PromotedTaskCreateToolCommand = {
  title: string;
  commandMatch: CommandMatch;
};

export type PromotedTaskReadToolCommand = {
  scope: 'global';
  commandMatch: CommandMatch;
};

export type PromotedTaskCompletionToolCommand = {
  scope: 'global';
  query: string;
  commandMatch: CommandMatch;
};

export type PromotedNoteSaveToolCommand = {
  content: string;
  commandMatch: CommandMatch;
};

export type PromotedNoteReadToolCommand = {
  commandMatch: CommandMatch;
};

export type PromotedCalendarReadView = 'today' | 'tomorrow' | 'all';

export type PromotedCalendarReadToolCommand = {
  view: PromotedCalendarReadView;
  commandMatch: CommandMatch;
};

export type PromotedCalendarCreateDay = 'today' | 'tomorrow';

export type PromotedCalendarCreateToolCommand = {
  day: PromotedCalendarCreateDay;
  title: string;
  time: string | null;
  commandMatch: CommandMatch;
};

export type PromotedCalendarDeleteToolCommand = {
  day: PromotedCalendarCreateDay;
  title: string | null;
  time: string | null;
  commandMatch: CommandMatch;
};

export type PromotedCalendarEditTargetCriteria = {
  day: PromotedCalendarCreateDay;
  query: string;
  time: string | null;
};

export type PromotedCalendarEditChanges = {
  day?: PromotedCalendarCreateDay;
  title?: string;
  time?: string;
};

export type PromotedCalendarEditToolCommand = {
  target: PromotedCalendarEditTargetCriteria;
  changes: PromotedCalendarEditChanges;
  commandMatch: CommandMatch;
};

export type DeferredCalendarWriteAction =
  | 'add-calendar-event'
  | 'edit-last-event'
  | 'delete-calendar-event'
  | 'delete-last-event'
  | 'clear-calendar';

const DEFERRED_CALENDAR_WRITE_ACTIONS = new Set<DeferredCalendarWriteAction>([
  'delete-last-event',
  'clear-calendar',
]);

const MAX_PROMOTED_SEARCH_QUERY_LENGTH = 500;
const MAX_PROMOTED_TASK_TITLE_LENGTH = 240;
const MAX_PROMOTED_NOTE_CONTENT_LENGTH = 6000;
const MAX_PROMOTED_CALENDAR_TITLE_LENGTH = 240;
const MAX_PROMOTED_CALENDAR_TIME_LENGTH = 32;
const PROMOTED_CALENDAR_READ_VIEWS = new Set<PromotedCalendarReadView>([
  'today',
  'tomorrow',
  'all',
]);
const PROMOTED_CALENDAR_CREATE_DAYS = new Set<PromotedCalendarCreateDay>([
  'today',
  'tomorrow',
]);
const BROAD_CALENDAR_CONTAINER_TITLE = /^(?:(?:my|our|the)\s+)?(?:day|schedule|agenda|plans?)$/i;
const CONTROL_CHARACTER_RE = /[\u0000-\u001f\u007f]/;
const CALENDAR_TITLE_SMALL_WORDS = new Set([
  'and', 'or', 'of', 'the', 'to', 'for', 'with', 'at', 'in', 'on',
]);

export function normalizePromotedCalendarCreateTitle(rawTitle: string): string {
  const withoutLeadingFiller = rawTitle
    .trim()
    .replace(/^(?:a|an|the|my|our)\s+/i, '')
    .replace(/\s+/g, ' ');
  const words = withoutLeadingFiller.split(' ').filter(Boolean);
  return words
    .map((word, index) => {
      if (/[A-Z]/.test(word.slice(1)) || /[&0-9]/.test(word)) return word;
      const lower = word.toLowerCase();
      if (
        index > 0 &&
        index < words.length - 1 &&
        CALENDAR_TITLE_SMALL_WORDS.has(lower)
      ) {
        return lower;
      }
      return `${word.slice(0, 1).toUpperCase()}${word.slice(1).toLowerCase()}`;
    })
    .join(' ');
}

function hasExactlyKeys(
  value: Record<string, unknown>,
  expectedKeys: readonly string[],
): boolean {
  const keys = Object.keys(value).sort();
  const expected = [...expectedKeys].sort();
  return keys.length === expected.length && keys.every((key, index) => key === expected[index]);
}

function readValidatedSearchQuery(
  argumentsValue: Record<string, unknown>,
): string | null {
  const keys = Object.keys(argumentsValue);
  if (keys.length !== 1 || keys[0] !== 'query') return null;
  const rawQuery = argumentsValue.query;
  if (typeof rawQuery !== 'string') return null;

  const query = rawQuery.trim();
  if (!query || query.length > MAX_PROMOTED_SEARCH_QUERY_LENGTH) return null;
  if (CONTROL_CHARACTER_RE.test(query)) return null;
  return query;
}

function readValidatedTaskCreateTitle(
  argumentsValue: Record<string, unknown>,
): string | null {
  const keys = Object.keys(argumentsValue);
  if (keys.length !== 1 || keys[0] !== 'title') return null;

  const rawTitle = argumentsValue.title;
  if (typeof rawTitle !== 'string') return null;
  const title = rawTitle.replace(/\s+/g, ' ').trim();
  if (!title || title.length > MAX_PROMOTED_TASK_TITLE_LENGTH) return null;
  if (CONTROL_CHARACTER_RE.test(title)) return null;
  return title;
}

function hasValidTaskReadArguments(
  argumentsValue: Record<string, unknown>,
): boolean {
  return (
    Object.keys(argumentsValue).length === 1 &&
    argumentsValue.scope === 'global'
  );
}

function readValidatedTaskCompletionQuery(
  argumentsValue: Record<string, unknown>,
): string | null {
  if (!hasExactlyKeys(argumentsValue, ['scope', 'query'])) return null;
  if (argumentsValue.scope !== 'global') return null;
  const rawQuery = argumentsValue.query;
  if (typeof rawQuery !== 'string') return null;
  const query = rawQuery.replace(/\s+/g, ' ').trim();
  if (!query || query.length > MAX_PROMOTED_TASK_TITLE_LENGTH) return null;
  if (CONTROL_CHARACTER_RE.test(query)) return null;
  return query;
}

function readValidatedNoteSaveContent(
  argumentsValue: Record<string, unknown>,
): string | null {
  const keys = Object.keys(argumentsValue);
  if (keys.length !== 1 || keys[0] !== 'content') return null;

  const rawContent = argumentsValue.content;
  if (typeof rawContent !== 'string') return null;
  const content = rawContent.trim();
  if (!content || content.length > MAX_PROMOTED_NOTE_CONTENT_LENGTH) return null;
  if (CONTROL_CHARACTER_RE.test(content)) return null;
  return content;
}

function hasValidNoteReadArguments(
  argumentsValue: Record<string, unknown>,
): boolean {
  return Object.keys(argumentsValue).length === 0;
}

function readValidatedCalendarReadView(
  argumentsValue: Record<string, unknown>,
): PromotedCalendarReadView | null {
  const keys = Object.keys(argumentsValue);
  if (keys.length !== 1 || keys[0] !== 'view') return null;

  const rawView = argumentsValue.view;
  if (typeof rawView !== 'string') return null;
  if (!PROMOTED_CALENDAR_READ_VIEWS.has(rawView as PromotedCalendarReadView)) {
    return null;
  }

  return rawView as PromotedCalendarReadView;
}

function readValidatedCalendarCreateTime(rawTime: unknown): string | null | undefined {
  if (rawTime === null) return null;
  if (typeof rawTime !== 'string') return undefined;

  const time = rawTime.trim();
  if (!time || time.length > MAX_PROMOTED_CALENDAR_TIME_LENGTH) return undefined;
  if (CONTROL_CHARACTER_RE.test(time)) return undefined;

  const normalized = time.toLowerCase().replace(/\./g, '').replace(/\s+/g, ' ').trim();
  if (normalized === 'noon' || normalized === 'midnight') return time;

  const match = normalized.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/);
  if (!match) return undefined;

  const hour = Number(match[1]);
  const minute = match[2] === undefined ? 0 : Number(match[2]);
  const meridiem = match[3] ?? null;
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || minute < 0 || minute > 59) {
    return undefined;
  }
  if (meridiem) {
    if (hour < 1 || hour > 12) return undefined;
  } else if (hour < 0 || hour > 23) {
    return undefined;
  }

  return time;
}

function readValidatedCalendarCreateArguments(
  argumentsValue: Record<string, unknown>,
): { day: PromotedCalendarCreateDay; title: string; time: string | null } | null {
  if (!hasExactlyKeys(argumentsValue, ['day', 'title', 'time'])) return null;

  const rawDay = argumentsValue.day;
  if (
    typeof rawDay !== 'string' ||
    !PROMOTED_CALENDAR_CREATE_DAYS.has(rawDay as PromotedCalendarCreateDay)
  ) {
    return null;
  }

  const rawTitle = argumentsValue.title;
  if (typeof rawTitle !== 'string') return null;
  const title = rawTitle.trim();
  if (
    !title ||
    title.length > MAX_PROMOTED_CALENDAR_TITLE_LENGTH ||
    CONTROL_CHARACTER_RE.test(title) ||
    BROAD_CALENDAR_CONTAINER_TITLE.test(title)
  ) {
    return null;
  }

  const time = readValidatedCalendarCreateTime(argumentsValue.time);
  if (time === undefined) return null;

  return {
    day: rawDay as PromotedCalendarCreateDay,
    title,
    time,
  };
}

function readValidatedCalendarDeleteArguments(
  argumentsValue: Record<string, unknown>,
): { day: PromotedCalendarCreateDay; title: string | null; time: string | null } | null {
  if (!hasExactlyKeys(argumentsValue, ['day', 'title', 'time'])) return null;

  const rawDay = argumentsValue.day;
  if (
    typeof rawDay !== 'string' ||
    !PROMOTED_CALENDAR_CREATE_DAYS.has(rawDay as PromotedCalendarCreateDay)
  ) {
    return null;
  }

  const rawTitle = argumentsValue.title;
  let title: string | null = null;
  if (rawTitle !== null) {
    if (typeof rawTitle !== 'string') return null;
    title = rawTitle.trim();
    if (
      !title ||
      title.length > MAX_PROMOTED_CALENDAR_TITLE_LENGTH ||
      CONTROL_CHARACTER_RE.test(title)
    ) {
      return null;
    }
  }

  const time = readValidatedCalendarCreateTime(argumentsValue.time);
  if (time === undefined) return null;
  if (!title && !time) return null;

  return {
    day: rawDay as PromotedCalendarCreateDay,
    title,
    time,
  };
}


function readValidatedCalendarNullableTitle(rawTitle: unknown): string | null | undefined {
  if (rawTitle === null) return null;
  if (typeof rawTitle !== 'string') return undefined;
  const title = rawTitle.trim();
  if (
    !title ||
    title.length > MAX_PROMOTED_CALENDAR_TITLE_LENGTH ||
    CONTROL_CHARACTER_RE.test(title)
  ) {
    return undefined;
  }
  return title;
}

function readValidatedCalendarEditArguments(
  argumentsValue: Record<string, unknown>,
): {
  target: PromotedCalendarEditTargetCriteria;
  changes: PromotedCalendarEditChanges;
} | null {
  if (
    !hasExactlyKeys(argumentsValue, [
      'targetDay',
      'query',
      'currentTime',
      'changeField',
      'changeValue',
    ])
  ) {
    return null;
  }

  const rawTargetDay = argumentsValue.targetDay;
  if (
    typeof rawTargetDay !== 'string' ||
    !PROMOTED_CALENDAR_CREATE_DAYS.has(rawTargetDay as PromotedCalendarCreateDay)
  ) {
    return null;
  }

  const rawQuery = argumentsValue.query;
  if (typeof rawQuery !== 'string') return null;
  const query = rawQuery.trim();
  if (
    !query ||
    query.length > MAX_PROMOTED_CALENDAR_TITLE_LENGTH ||
    CONTROL_CHARACTER_RE.test(query)
  ) {
    return null;
  }

  const currentTime = readValidatedCalendarCreateTime(argumentsValue.currentTime);
  if (currentTime === undefined) return null;

  const changeField = argumentsValue.changeField;
  const changeValue = argumentsValue.changeValue;
  if (changeField === 'time') {
    const newTime = readValidatedCalendarCreateTime(changeValue);
    if (!newTime) return null;
    return {
      target: {
        day: rawTargetDay as PromotedCalendarCreateDay,
        query,
        time: currentTime,
      },
      changes: { time: newTime },
    };
  }

  if (changeField === 'title') {
    const newTitle = readValidatedCalendarNullableTitle(changeValue);
    if (!newTitle) return null;
    return {
      target: {
        day: rawTargetDay as PromotedCalendarCreateDay,
        query,
        time: currentTime,
      },
      changes: { title: newTitle },
    };
  }

  if (changeField === 'day') {
    if (
      typeof changeValue !== 'string' ||
      !PROMOTED_CALENDAR_CREATE_DAYS.has(
        changeValue as PromotedCalendarCreateDay,
      ) ||
      changeValue === rawTargetDay
    ) {
      return null;
    }
    return {
      target: {
        day: rawTargetDay as PromotedCalendarCreateDay,
        query,
        time: currentTime,
      },
      changes: { day: changeValue as PromotedCalendarCreateDay },
    };
  }

  return null;
}

function calendarEditRoundTripsThroughCanonicalParser(
  changes: PromotedCalendarEditChanges,
): boolean {
  if (
    changes.day &&
    !changes.time &&
    !changes.title &&
    PROMOTED_CALENDAR_CREATE_DAYS.has(changes.day)
  ) {
    // The deterministic exact-id Calendar updater supports a day-only move and
    // preserves the event's existing time. The legacy text parser represents
    // `edit last event to tomorrow` ambiguously, so confirmation carries this
    // validated CommandMatch directly rather than reparsing that string.
    return true;
  }
  const parsed = parseCommand(buildCalendarEditFrontendCommand(changes));
  if (parsed?.command !== 'edit-last-event' || !parsed.calendarEdit) return false;

  const parsedDay = parsed.calendarEdit.day ?? null;
  const parsedTitle = parsed.calendarEdit.title?.trim() ?? null;
  const parsedTime = parsed.calendarEdit.time?.trim().toLowerCase() ?? null;
  return (
    parsedDay === (changes.day ?? null) &&
    parsedTitle === (changes.title?.trim() ?? null) &&
    parsedTime === (changes.time?.trim().toLowerCase() ?? null)
  );
}

function buildCalendarDeleteFrontendCommand(options: {
  day: PromotedCalendarCreateDay;
  title: string | null;
  time: string | null;
}): string {
  const parts = ['delete event', options.day];
  if (options.time) parts.push(`at ${options.time}`);
  if (options.title) parts.push(`called ${options.title}`);
  return parts.join(' ');
}

function calendarDeleteRoundTripsThroughCanonicalParser(options: {
  day: PromotedCalendarCreateDay;
  title: string | null;
  time: string | null;
}): boolean {
  const parsed = parseCommand(buildCalendarDeleteFrontendCommand(options));
  if (parsed?.command !== 'delete-calendar-event' || !parsed.calendarDelete) return false;

  const parsedDay = parsed.calendarDelete.day ?? null;
  const parsedTitle = parsed.calendarDelete.title?.trim() ?? null;
  const parsedTime = parsed.calendarDelete.time?.trim().toLowerCase() ?? null;
  return (
    parsedDay === options.day &&
    parsedTitle === options.title &&
    parsedTime === (options.time?.trim().toLowerCase() ?? null)
  );
}

function buildCalendarCreateFrontendCommand(options: {
  day: PromotedCalendarCreateDay;
  title: string;
  time: string | null;
}): string {
  return `add event ${options.day} at ${options.time ?? 'Later'} called ${options.title}`;
}

function calendarCreateRoundTripsThroughCanonicalParser(options: {
  day: PromotedCalendarCreateDay;
  title: string;
  time: string | null;
}): boolean {
  const parsed = parseCommand(buildCalendarCreateFrontendCommand(options));
  if (parsed?.command !== 'add-calendar-event' || !parsed.calendarEvent) return false;

  return (
    parsed.calendarEvent.day === options.day &&
    parsed.calendarEvent.time.trim().toLowerCase() ===
      (options.time ?? 'Later').trim().toLowerCase() &&
    parsed.calendarEvent.title.trim() === options.title
  );
}

/**
 * Search promotion remains unchanged in this slice. The model may propose
 * ownership/action/arguments, but this function is the deterministic gate that
 * decides whether those arguments are executable. No other owner or action can
 * produce a Search CommandMatch here.
 */
export function resolvePromotedSearchToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedSearchToolCommand | null {
  if (!decision || decision.disposition !== 'tool') return null;
  if (decision.turnOwner !== 'search') return null;
  if (decision.proposedCapability !== 'search') return null;
  if (decision.proposedAction !== 'run-search') return null;
  const query = readValidatedSearchQuery(decision.proposedArguments);
  if (!query) return null;

  return {
    query,
    commandMatch: {
      command: 'run-search',
      confirmation: `Searching the web: ${query}`,
      payload: query,
    },
  };
}

/**
 * True when the unified agent is proposing one new task. Malformed proposals
 * fail closed in App instead of falling through to a legacy parser or chat.
 */
export function isPromotedTaskCreateToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.disposition === 'tool' &&
      decision.turnOwner === 'tasks' &&
      decision.proposedAction === 'remember-task',
  );
}

/**
 * Promote one task title into the existing remember-task CommandMatch. The
 * model proposes semantics only; the Memory handler remains the sole writer.
 */
export function resolvePromotedTaskCreateToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedTaskCreateToolCommand | null {
  if (!isPromotedTaskCreateToolDecision(decision)) return null;
  if (!decision || decision.proposedCapability !== 'tasks') return null;

  const title = readValidatedTaskCreateTitle(decision.proposedArguments);
  if (!title) return null;

  return {
    title,
    commandMatch: {
      command: 'remember-task',
      confirmation: 'Saved task.',
      payload: title,
    },
  };
}

/**
 * True when the unified agent proposes an authoritative global task read.
 * Focus-linked task questions are intentionally excluded from this contract.
 */
export function isPromotedTaskReadToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.disposition === 'tool' &&
      decision.turnOwner === 'tasks' &&
      decision.proposedAction === 'read-memory',
  );
}

/**
 * Validate the global task-read scope. read-memory remains the legacy canonical
 * action id, while scope=global prevents Active Focus from changing the result.
 */
export function resolvePromotedTaskReadToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedTaskReadToolCommand | null {
  if (!isPromotedTaskReadToolDecision(decision)) return null;
  if (!decision || decision.proposedCapability !== 'tasks') return null;
  if (!hasValidTaskReadArguments(decision.proposedArguments)) return null;

  return {
    scope: 'global',
    commandMatch: {
      command: 'read-memory',
      confirmation: 'Reading tasks.',
      payload: 'global-task-read',
    },
  };
}

const GLOBAL_TASK_READ_NOUN = /\b(?:tasks?|task\s+list|to[-\s]?do(?:\s+list)?|todo(?:\s+list)?|checklist)\b/i;
const GLOBAL_TASK_READ_VERB = /\b(?:read|list|show|display|review|recall|tell\s+me|what|which)\b/i;
const TASK_MUTATION_OR_COMPLETION = /\b(?:add|create|make|put|save|remember|mark|complete|completed|finish|finished|delete|remove|clear|reopen|restore)\b/i;
const FOCUS_TASK_REFERENCE = /\b(?:focus|focus\s+session|linked\s+tasks?|tasks?\s+(?:for|from|in|under)\s+(?:this|my|the|our)?\s*focus)\b/i;

/**
 * Resolve the legacy exact-parser ambiguity where task-list reads currently map
 * to read-memory. This is only an ownership/scope detector; it never reads state.
 */
export function isExplicitGlobalTaskReadRequest(
  userMessage: string,
  parsedCommand: string | null,
): boolean {
  const text = userMessage.trim();
  if (!text || !GLOBAL_TASK_READ_NOUN.test(text)) return false;
  if (FOCUS_TASK_REFERENCE.test(text)) return false;
  if (TASK_MUTATION_OR_COMPLETION.test(text)) return false;
  if (!GLOBAL_TASK_READ_VERB.test(text)) return false;
  return parsedCommand === null || parsedCommand === 'read-memory';
}

export function buildExplicitGlobalTaskReadToolCommand(): PromotedTaskReadToolCommand {
  return {
    scope: 'global',
    commandMatch: {
      command: 'read-memory',
      confirmation: 'Reading tasks.',
      payload: 'global-task-read',
    },
  };
}

/**
 * True when the unified agent proposes completion of one named/referenced task.
 * The proposal contains lookup language only; it never contains task identity.
 */
export function isPromotedTaskCompletionToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.disposition === 'tool' &&
      decision.turnOwner === 'tasks' &&
      decision.proposedAction === 'mark-task-done',
  );
}

/**
 * Validate one semantic task-completion reference. Canonical task state still
 * resolves this query to zero/one/multiple real open tasks before confirmation.
 */
export function resolvePromotedTaskCompletionToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedTaskCompletionToolCommand | null {
  if (!isPromotedTaskCompletionToolDecision(decision)) return null;
  if (!decision || decision.proposedCapability !== 'tasks') return null;
  const query = readValidatedTaskCompletionQuery(decision.proposedArguments);
  if (!query) return null;
  return {
    scope: 'global',
    query,
    commandMatch: {
      command: 'mark-task-done',
      confirmation: 'Marked task done.',
      payload: query,
    },
  };
}

/**
 * True when the unified agent proposes one Notes save. Malformed proposals
 * fail closed in App instead of falling through to conversation.
 */
export function isPromotedNoteSaveToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.disposition === 'tool' &&
      decision.turnOwner === 'notes' &&
      decision.proposedAction === 'save-note',
  );
}

/**
 * Save exactly one validated note through the existing Notes handler.
 */
export function resolvePromotedNoteSaveToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedNoteSaveToolCommand | null {
  if (!isPromotedNoteSaveToolDecision(decision)) return null;
  if (!decision || decision.proposedCapability !== 'notes') return null;

  const content = readValidatedNoteSaveContent(decision.proposedArguments);
  if (!content) return null;

  return {
    content,
    commandMatch: {
      command: 'save-note',
      confirmation: 'Saved note.',
      payload: content,
    },
  };
}

/**
 * True when the unified agent proposes an authoritative Notes read.
 */
export function isPromotedNoteReadToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.disposition === 'tool' &&
      decision.turnOwner === 'notes' &&
      decision.proposedAction === 'read-notes',
  );
}

/**
 * Read authoritative saved Notes through the existing Notes handler. The read
 * action has no model-provided lookup payload in this slice.
 */
export function resolvePromotedNoteReadToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedNoteReadToolCommand | null {
  if (!isPromotedNoteReadToolDecision(decision)) return null;
  if (!decision || decision.proposedCapability !== 'notes') return null;
  if (!hasValidNoteReadArguments(decision.proposedArguments)) return null;

  return {
    commandMatch: {
      command: 'read-notes',
      confirmation: 'Reading notes.',
    },
  };
}

/**
 * Calendar reads remain executable only through the canonical read-calendar
 * action and one validated view argument.
 */
export function resolvePromotedCalendarReadToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedCalendarReadToolCommand | null {
  if (!decision || decision.disposition !== 'tool') return null;
  if (decision.turnOwner !== 'calendar') return null;
  if (decision.proposedCapability !== 'calendar') return null;
  if (decision.proposedAction !== 'read-calendar') return null;

  const view = readValidatedCalendarReadView(decision.proposedArguments);
  if (!view) return null;

  return {
    view,
    commandMatch: {
      command: 'read-calendar',
      confirmation: 'Reading calendar.',
      calendarView: view,
    },
  };
}

/**
 * True when the unified agent is trying to propose Calendar creation. This is
 * intentionally broader than the executable validator so malformed create
 * proposals can fail closed instead of falling through to chat or a legacy
 * interpreter.
 */
export function isPromotedCalendarCreateToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.disposition === 'tool' &&
      decision.turnOwner === 'calendar' &&
      decision.proposedAction === 'add-calendar-event',
  );
}

/**
 * Promote Calendar creation with typed arguments only. This validator constructs
 * the canonical CommandMatch that re-enters App.tsx's existing confirmation and
 * deterministic Calendar execution pipeline. No Calendar state changes here.
 * Targeted deletion has its own criteria-only validator below.
 */
export function resolvePromotedCalendarCreateToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedCalendarCreateToolCommand | null {
  if (!isPromotedCalendarCreateToolDecision(decision)) return null;
  if (!decision || decision.proposedCapability !== 'calendar') return null;

  const validated = readValidatedCalendarCreateArguments(decision.proposedArguments);
  if (!validated) return null;
  const normalized = {
    ...validated,
    title: normalizePromotedCalendarCreateTitle(validated.title),
  };
  if (
    !normalized.title ||
    !calendarCreateRoundTripsThroughCanonicalParser(normalized)
  ) {
    return null;
  }

  return {
    ...normalized,
    commandMatch: {
      command: 'add-calendar-event',
      confirmation: 'Added event.',
      calendarEvent: {
        day: normalized.day,
        time: normalized.time ?? 'Later',
        title: normalized.title,
      },
    },
  };
}

/**
 * True when the unified agent is proposing a targeted Calendar deletion.
 * Malformed delete proposals fail closed rather than falling through to chat
 * or being reinterpreted as some other mutation.
 */
export function isPromotedCalendarDeleteToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.disposition === 'tool' &&
      decision.turnOwner === 'calendar' &&
      decision.proposedAction === 'delete-calendar-event',
  );
}

/**
 * Promote targeted Calendar deletion as a typed criteria proposal only. The
 * agent never selects an event id. App.tsx resolves these validated criteria
 * against canonical Calendar state and requires exactly one match before the
 * existing destructive confirmation path can proceed.
 */
export function resolvePromotedCalendarDeleteToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedCalendarDeleteToolCommand | null {
  if (!isPromotedCalendarDeleteToolDecision(decision)) return null;
  if (!decision || decision.proposedCapability !== 'calendar') return null;

  const validated = readValidatedCalendarDeleteArguments(decision.proposedArguments);
  if (!validated || !calendarDeleteRoundTripsThroughCanonicalParser(validated)) return null;

  return {
    ...validated,
    commandMatch: {
      command: 'delete-calendar-event',
      confirmation: 'Deleted event.',
      calendarDelete: {
        day: validated.day,
        ...(validated.time ? { time: validated.time } : {}),
        ...(validated.title ? { title: validated.title } : {}),
      },
    },
  };
}

/**
 * True when the unified agent is proposing one targeted Calendar edit. The
 * proposal carries lookup criteria and requested changes only; it never carries
 * an event id and cannot mutate Calendar state directly.
 */
export function isPromotedCalendarEditToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.disposition === 'tool' &&
      decision.turnOwner === 'calendar' &&
      decision.proposedAction === 'edit-last-event',
  );
}

/**
 * Promote one Calendar edit as target criteria plus validated changes. App.tsx
 * must resolve the target criteria against authoritative Calendar state and
 * bind exactly one canonical event id before the existing confirmation/executor
 * path may run.
 */
export function resolvePromotedCalendarEditToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedCalendarEditToolCommand | null {
  if (!isPromotedCalendarEditToolDecision(decision)) return null;
  if (!decision || decision.proposedCapability !== 'calendar') return null;

  const validated = readValidatedCalendarEditArguments(decision.proposedArguments);
  if (!validated || !calendarEditRoundTripsThroughCanonicalParser(validated.changes)) {
    return null;
  }

  return {
    ...validated,
    commandMatch: {
      command: 'edit-last-event',
      confirmation: 'Updated the last event.',
      calendarEdit: validated.changes,
    },
  };
}

/**
 * Calendar delete-last/clear remain unpromoted. Their canonical action ids stay
 * available so the existing guarded interpreter result can be checked before
 * reaching the deterministic Calendar write path. Create, targeted delete, and
 * targeted edit have capability-specific validators above.
 */
export function resolveDeferredCalendarWriteAction(
  decision: PromotedSingleIntentDecision | null,
): DeferredCalendarWriteAction | null {
  if (!decision || decision.disposition !== 'tool') return null;
  if (decision.turnOwner !== 'calendar') return null;
  if (decision.proposedCapability !== 'calendar') return null;

  const proposedAction = decision.proposedAction as DeferredCalendarWriteAction;
  if (!DEFERRED_CALENDAR_WRITE_ACTIONS.has(proposedAction)) return null;
  return proposedAction;
}
