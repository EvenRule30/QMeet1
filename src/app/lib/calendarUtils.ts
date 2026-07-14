import type { CalendarEvent } from '../types';
import {
  isEventForCalendarView,
  type CalendarView,
} from './dateUtils';

export type CalendarDeleteCriteria = {
  day?: CalendarView;
  time?: string;
  title?: string;
};

export function describeCalendarEditPayload(changes?: {
  day?: CalendarView;
  time?: string;
  title?: string;
}): string {
  if (!changes) return 'no changes';

  const parts: string[] = [];
  const day = changes.day?.trim();
  const time = changes.time?.trim();
  const title = changes.title?.trim();

  if (day || time) {
    parts.push(
      `${day ? day : 'same day'}${
        time ? ` at ${time}` : ''
      }`,
    );
  }

  if (title) {
    parts.push(`title "${title}"`);
  }

  return parts.length > 0
    ? parts.join(', ')
    : 'no changes';
}

export function buildCalendarEditFrontendCommand(changes?: {
  day?: CalendarView;
  time?: string;
  title?: string;
}): string {
  const day = changes?.day?.trim();
  const time = changes?.time?.trim();
  const title = changes?.title?.trim();

  if (title && !day && !time) {
    return `rename last event to ${title}`;
  }

  const when = `${day ? `${day} ` : ''}${
    time ? `at ${time}` : ''
  }`.trim();
  const titlePart = title ? ` called ${title}` : '';

  if (when) {
    return `edit last event to ${when}${titlePart}`;
  }

  if (title) {
    return `rename last event to ${title}`;
  }

  return 'edit last event';
}

export function buildCalendarDeleteFrontendCommand(
  criteria?: CalendarDeleteCriteria,
): string {
  const day = criteria?.day?.trim();
  const time = criteria?.time?.trim();
  const title = criteria?.title?.trim();

  const parts = ['delete event'];

  if (day) parts.push(day);
  if (time) parts.push(`at ${time}`);
  if (title) parts.push(`called ${title}`);

  return parts.join(' ');
}

export function describeCalendarDeletePayload(
  criteria?: CalendarDeleteCriteria,
): string {
  const day = criteria?.day?.trim();
  const time = criteria?.time?.trim();
  const title = criteria?.title?.trim();

  const parts: string[] = [];
  if (day) parts.push(day);
  if (time) parts.push(`at ${time}`);
  if (title) parts.push(`called "${title}"`);

  return parts.length > 0
    ? parts.join(' ')
    : 'matching event';
}

export function normalizeCalendarLookupText(
  value: string | undefined | null,
): string {
  return (value ?? '')
    .toLowerCase()
    .replace(/[._-]+/g, ' ')
    .replace(/[^a-z0-9:\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeCalendarTitleForComparison(
  value: string | undefined | null,
): string {
  return normalizeCalendarLookupText(value)
    .split(' ')
    .filter(
      (token) =>
        token && token !== 'a' && token !== 'an' && token !== 'the',
    )
    .join(' ');
}

export function normalizeCalendarLookupTime(
  value: string | undefined | null,
): string {
  const cleaned = normalizeCalendarLookupText(value)
    .replace(/\b([ap])\s*m\b/g, '$1m')
    .replace(/\bnoon\b/g, '12:00pm')
    .replace(/\bmidnight\b/g, '12:00am')
    .replace(/\s+/g, ' ')
    .trim();

  const match = cleaned.match(
    /^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/i,
  );
  if (!match) return cleaned.replace(/\s+/g, '');

  const hour = String(Number(match[1]));
  const minute = match[2] ?? '00';
  const suffix = match[3] ?? '';

  return `${hour}:${minute}${suffix}`;
}

export function calendarLookupTimeHasMeridiem(
  value: string,
): boolean {
  return /(?:am|pm)$/i.test(value);
}

export function calendarLookupTimeWithoutMeridiem(
  value: string,
): string {
  return value.replace(/(?:am|pm)$/i, '');
}

export function getCalendarEventTimeCandidates(
  event: CalendarEvent,
): string[] {
  const candidates = [event.time];

  if (event.start) {
    const startDate = new Date(event.start);
    if (!Number.isNaN(startDate.getTime())) {
      candidates.push(
        startDate.toLocaleTimeString([], {
          hour: 'numeric',
          minute: '2-digit',
        }),
      );
    }
  }

  return candidates.filter(Boolean);
}

export function calendarEventMatchesDeleteCriteria(
  event: CalendarEvent,
  criteria?: CalendarDeleteCriteria,
): boolean {
  if (!criteria) return true;

  if (
    criteria.day &&
    !isEventForCalendarView(event, criteria.day)
  ) {
    return false;
  }

  const targetTitle = normalizeCalendarTitleForComparison(
    criteria.title,
  );
  if (targetTitle) {
    const eventTitle = normalizeCalendarTitleForComparison(
      event.title,
    );

    if (
      !eventTitle.includes(targetTitle) &&
      !targetTitle.includes(eventTitle)
    ) {
      return false;
    }
  }

  const targetTime = normalizeCalendarLookupTime(
    criteria.time,
  );
  if (targetTime) {
    const targetWithoutMeridiem =
      calendarLookupTimeWithoutMeridiem(targetTime);
    const targetHasMeridiem =
      calendarLookupTimeHasMeridiem(targetTime);
    const eventTimes = getCalendarEventTimeCandidates(
      event,
    ).map(normalizeCalendarLookupTime);

    const timeMatches = eventTimes.some(
      (eventTime) => {
        if (eventTime === targetTime) return true;
        if (!targetHasMeridiem) {
          return (
            calendarLookupTimeWithoutMeridiem(
              eventTime,
            ) === targetWithoutMeridiem
          );
        }
        return false;
      },
    );

    if (!timeMatches) return false;
  }

  return true;
}
