import { QMEET_API_BASE_URL } from '../api';
import type { CalendarEvent } from '../types';
import { isCanonicalCalendarDateKey } from './calendarAbsoluteCreate';

export async function updateCalendarEventOnAbsoluteDate(options: {
  eventId: string;
  date: string;
  title?: string;
  time?: string;
}): Promise<{ ok: boolean; event?: CalendarEvent; message: string }> {
  if (!isCanonicalCalendarDateKey(options.date)) {
    throw new Error('Invalid Calendar date.');
  }
  const response = await fetch(
    `${QMEET_API_BASE_URL}/api/calendar/events/${encodeURIComponent(options.eventId)}/absolute`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        date: options.date,
        title: options.title?.trim() ?? '',
        time: options.time?.trim() ?? '',
      }),
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
    throw new Error(detail || `Calendar update failed with HTTP ${response.status}.`);
  }
  return (await response.json()) as { ok: boolean; event?: CalendarEvent; message: string };
}
