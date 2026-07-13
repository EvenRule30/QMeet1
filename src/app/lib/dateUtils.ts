import type { CalendarEvent } from '../types';

export type CalendarView = 'today' | 'tomorrow';

export function getLocalDateKey(offsetDays = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');

  return `${year}-${month}-${day}`;
}

export function getDateKeyForCalendarView(view: CalendarView): string {
  return view === 'tomorrow' ? getLocalDateKey(1) : getLocalDateKey(0);
}

export function getLegacyUtcDateKeyForCalendarView(view: CalendarView): string {
  const date = new Date();

  if (view === 'tomorrow') {
    date.setDate(date.getDate() + 1);
  }

  return date.toISOString().slice(0, 10);
}

export function getAcceptedDateKeysForCalendarView(view: CalendarView): Set<string> {
  return new Set([
    getDateKeyForCalendarView(view),
    getLegacyUtcDateKeyForCalendarView(view),
  ]);
}

export function isEventForCalendarView(event: CalendarEvent, view: CalendarView): boolean {
  return getAcceptedDateKeysForCalendarView(view).has(event.dateKey);
}

export function getCalendarViewLabel(view: CalendarView): string {
  return view === 'tomorrow' ? 'tomorrow' : 'today';
}


