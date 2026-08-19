import { QMEET_API_BASE_URL } from '../api';
import type { CalendarCreateEventResponse } from '../types';

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export type CalendarAbsoluteDateKey = `${number}-${number}-${number}`;

export type CalendarAbsoluteCreateRequest = {
  title: string;
  date: string;
  time: string;
};

export function isCanonicalCalendarDateKey(
  value: unknown,
): value is CalendarAbsoluteDateKey {
  if (typeof value !== 'string' || !ISO_DATE_RE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function formatCalendarAbsoluteDate(value: string): string {
  if (!isCanonicalCalendarDateKey(value)) return value;
  const parsed = new Date(`${value}T12:00:00Z`);
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parsed);
}

export async function createCalendarEventOnDate(
  request: CalendarAbsoluteCreateRequest,
): Promise<CalendarCreateEventResponse> {
  const title = request.title.trim();
  const time = request.time.trim() || 'Later';
  if (!title || !isCanonicalCalendarDateKey(request.date)) {
    throw new Error('Calendar create request was not a valid absolute-date event.');
  }

  const response = await fetch(`${QMEET_API_BASE_URL}/api/calendar/events/absolute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      title,
      date: request.date,
      time,
    }),
  });

  if (!response.ok) {
    const raw = await response.text();
    let detail = raw.trim();
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown; message?: unknown };
      if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
        detail = parsed.detail.trim();
      } else if (typeof parsed.message === 'string' && parsed.message.trim()) {
        detail = parsed.message.trim();
      }
    } catch {
      // Keep the raw backend message when it is not JSON.
    }
    throw new Error(detail || `Calendar create event error: ${response.status}`);
  }

  return response.json() as Promise<CalendarCreateEventResponse>;
}
