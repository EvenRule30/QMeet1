import { parseCommand, type CommandMatch } from '../commands';
import type { PromotedSingleIntentDecision } from './agentShadowObserver';

export type PromotedSearchToolCommand = {
  query: string;
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

export type DeferredCalendarWriteAction =
  | 'add-calendar-event'
  | 'edit-last-event'
  | 'delete-calendar-event'
  | 'delete-last-event'
  | 'clear-calendar';

const DEFERRED_CALENDAR_WRITE_ACTIONS = new Set<DeferredCalendarWriteAction>([
  'edit-last-event',
  'delete-calendar-event',
  'delete-last-event',
  'clear-calendar',
]);

const MAX_PROMOTED_SEARCH_QUERY_LENGTH = 500;
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
 * Promote exactly one Calendar mutation in this slice: add-calendar-event.
 * The model only proposes typed arguments. This validator constructs the
 * canonical CommandMatch that re-enters App.tsx's existing confirmation and
 * deterministic Calendar execution pipeline. No Calendar state changes here.
 */
export function resolvePromotedCalendarCreateToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedCalendarCreateToolCommand | null {
  if (!isPromotedCalendarCreateToolDecision(decision)) return null;
  if (!decision || decision.proposedCapability !== 'calendar') return null;

  const validated = readValidatedCalendarCreateArguments(decision.proposedArguments);
  if (!validated || !calendarCreateRoundTripsThroughCanonicalParser(validated)) return null;

  return {
    ...validated,
    commandMatch: {
      command: 'add-calendar-event',
      confirmation: 'Added event.',
      calendarEvent: {
        day: validated.day,
        time: validated.time ?? 'Later',
        title: validated.title,
      },
    },
  };
}

/**
 * Calendar edits/deletes remain unpromoted. This helper preserves only their
 * canonical action id so the existing guarded interpreter result can be
 * checked before reaching the deterministic Calendar write path. Create is no
 * longer deferred: it must pass resolvePromotedCalendarCreateToolCommand.
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
