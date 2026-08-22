import { QMEET_API_BASE_URL } from '../api';
import type { CalendarEvent } from '../types';
import { rememberCalendarPanelDateHint } from './calendarUiContext';

export type CalendarReadRange = {
  startDate: string;
  endDate: string;
};

export type CalendarRangeEventsResponse = {
  ok: boolean;
  configured: boolean;
  connected: boolean;
  source: 'google';
  view: 'range';
  startDate: string;
  endDate: string;
  events: CalendarEvent[];
  message: string;
};

const RANGE_PAYLOAD_PREFIX = 'calendar-read-range:v1:';
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const MAX_CALENDAR_READ_RANGE_DAYS = 31;

function parseIsoDateKey(value: string): number | null {
  if (!ISO_DATE_RE.test(value)) return null;
  const [yearText, monthText, dayText] = value.split('-');
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const utc = Date.UTC(year, month - 1, day);
  const parsed = new Date(utc);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    return null;
  }
  return utc;
}

export function validateCalendarReadRange(
  value: unknown,
): CalendarReadRange | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  if (
    keys.length !== 2 ||
    keys[0] !== 'endDate' ||
    keys[1] !== 'startDate'
  ) {
    return null;
  }
  const rawStart = record.startDate;
  const rawEnd = record.endDate;
  if (typeof rawStart !== 'string' || typeof rawEnd !== 'string') return null;
  const startDate = rawStart.trim();
  const endDate = rawEnd.trim();
  const startUtc = parseIsoDateKey(startDate);
  const endUtc = parseIsoDateKey(endDate);
  if (startUtc === null || endUtc === null || endUtc < startUtc) return null;
  const dayCount = Math.floor((endUtc - startUtc) / 86_400_000) + 1;
  if (dayCount < 1 || dayCount > MAX_CALENDAR_READ_RANGE_DAYS) return null;
  return { startDate, endDate };
}

export function encodeCalendarReadRangePayload(
  range: CalendarReadRange,
): string {
  const validated = validateCalendarReadRange(range);
  if (!validated) {
    throw new Error('Invalid Calendar read range.');
  }
  return `${RANGE_PAYLOAD_PREFIX}${validated.startDate}:${validated.endDate}`;
}

export function decodeCalendarReadRangePayload(
  payload: string | undefined,
): CalendarReadRange | null {
  if (!payload?.startsWith(RANGE_PAYLOAD_PREFIX)) return null;
  const encoded = payload.slice(RANGE_PAYLOAD_PREFIX.length);
  const match = encoded.match(/^(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$/);
  if (!match) return null;
  return validateCalendarReadRange({
    startDate: match[1],
    endDate: match[2],
  });
}

export function filterCalendarEventsForRange(
  events: CalendarEvent[],
  range: CalendarReadRange,
): CalendarEvent[] {
  const validated = validateCalendarReadRange(range);
  if (!validated) return [];
  return events
    .filter(
      (event) =>
        typeof event.dateKey === 'string' &&
        event.dateKey >= validated.startDate &&
        event.dateKey <= validated.endDate,
    )
    .sort((left, right) => {
      const dateOrder = left.dateKey.localeCompare(right.dateKey);
      if (dateOrder !== 0) return dateOrder;
      return left.time.localeCompare(right.time);
    });
}

export async function fetchCalendarEventsRange(
  range: CalendarReadRange,
): Promise<CalendarRangeEventsResponse> {
  const validated = validateCalendarReadRange(range);
  if (!validated) {
    throw new Error('Invalid Calendar read range.');
  }

  const params = new URLSearchParams({
    startDate: validated.startDate,
    endDate: validated.endDate,
  });
  const response = await fetch(
    `${QMEET_API_BASE_URL}/api/calendar/events/range?${params.toString()}`,
    {
      method: 'GET',
      headers: { Accept: 'application/json' },
    },
  );
  if (!response.ok) {
    let detail = '';
    try {
      const payload = (await response.json()) as { detail?: unknown };
      detail = typeof payload.detail === 'string' ? payload.detail.trim() : '';
    } catch {
      detail = '';
    }
    throw new Error(
      detail || `Calendar range read failed with HTTP ${response.status}.`,
    );
  }
  const payload = (await response.json()) as CalendarRangeEventsResponse;
  const responseRange = validateCalendarReadRange({
    startDate: payload.startDate,
    endDate: payload.endDate,
  });
  if (
    !payload?.ok ||
    payload.view !== 'range' ||
    !responseRange ||
    responseRange.startDate !== validated.startDate ||
    responseRange.endDate !== validated.endDate ||
    !Array.isArray(payload.events)
  ) {
    throw new Error('Calendar range read returned an unexpected response.');
  }
  return payload;
}

function dateForLabel(dateKey: string): Date {
  const [year, month, day] = dateKey.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function formatSingleDate(dateKey: string, includeYear: boolean): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    ...(includeYear ? { year: 'numeric' } : {}),
    timeZone: 'UTC',
  }).format(dateForLabel(dateKey));
}

export function describeCalendarReadRange(range: CalendarReadRange): string {
  const validated = validateCalendarReadRange(range);
  if (!validated) return 'the requested dates';
  if (validated.startDate === validated.endDate) {
    return formatSingleDate(validated.startDate, true);
  }
  const start = dateForLabel(validated.startDate);
  const end = dateForLabel(validated.endDate);
  const sameYear = start.getUTCFullYear() === end.getUTCFullYear();
  const sameMonth = sameYear && start.getUTCMonth() === end.getUTCMonth();

  if (sameMonth) {
    const month = new Intl.DateTimeFormat(undefined, {
      month: 'long',
      timeZone: 'UTC',
    }).format(start);
    return `${month} ${start.getUTCDate()}–${end.getUTCDate()}, ${end.getUTCFullYear()}`;
  }
  const startLabel = new Intl.DateTimeFormat(undefined, {
    month: 'long',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
    timeZone: 'UTC',
  }).format(start);
  const endLabel = new Intl.DateTimeFormat(undefined, {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(end);
  return `${startLabel}–${endLabel}`;
}

export function formatCalendarRangeReadout(options: {
  range: CalendarReadRange;
  events: CalendarEvent[];
  googleConnected: boolean;
}): string {
  const range = validateCalendarReadRange(options.range);
  if (!range) return 'I could not validate that Calendar date range.';
  if (range.startDate === range.endDate) {
    rememberCalendarPanelDateHint(range.startDate);
  }
  const events = filterCalendarEventsForRange(options.events, range);
  const rangeLabel = describeCalendarReadRange(range);
  if (events.length === 0) {
    return options.googleConnected
      ? `No Google Calendar events saved for ${rangeLabel}.`
      : `No calendar events saved for ${rangeLabel}.`;
  }
  const lines = [`Calendar for ${rangeLabel}:`];
  let previousDate = '';
  for (const event of events) {
    if (event.dateKey !== previousDate) {
      lines.push('', `${formatSingleDate(event.dateKey, true)}:`);
      previousDate = event.dateKey;
    }
    lines.push(`• ${event.time}: ${event.title}`);
  }
  return lines.join('\n');
}
