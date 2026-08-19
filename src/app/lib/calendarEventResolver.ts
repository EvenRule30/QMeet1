import type { CalendarEvent } from '../types';
import { isEventForCalendarView, type CalendarView } from './dateUtils';
import {
  calendarLookupTimeHasMeridiem,
  calendarLookupTimeWithoutMeridiem,
  getCalendarEventTimeCandidates,
  normalizeCalendarLookupText,
  normalizeCalendarLookupTime,
} from './calendarUtils';

export type CalendarEventReferenceCriteria = {
  day?: CalendarView;
  query?: string | null;
  time?: string | null;
};

export type CalendarEventReferenceResolution =
  | {
      kind: 'none';
      candidates: [];
    }
  | {
      kind: 'exact';
      event: CalendarEvent;
      score: 1;
    }
  | {
      kind: 'likely';
      event: CalendarEvent;
      score: number;
    }
  | {
      kind: 'ambiguous';
      candidates: CalendarEvent[];
    };

const TITLE_STOP_WORDS = new Set(['a', 'an', 'the', 'my', 'our']);
const LIKELY_MATCH_THRESHOLD = 0.82;
const LIKELY_MATCH_MARGIN = 0.08;

function normalizeReferenceTitle(value: string | undefined | null): string {
  return normalizeCalendarLookupText(value)
    .split(' ')
    .filter((token) => token && !TITLE_STOP_WORDS.has(token))
    .join(' ');
}

function levenshteinDistance(left: string, right: string): number {
  if (left === right) return 0;
  if (!left) return right.length;
  if (!right) return left.length;

  const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  const current = new Array<number>(right.length + 1);

  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    current[0] = leftIndex;
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      const substitutionCost =
        left[leftIndex - 1] === right[rightIndex - 1] ? 0 : 1;
      current[rightIndex] = Math.min(
        current[rightIndex - 1] + 1,
        previous[rightIndex] + 1,
        previous[rightIndex - 1] + substitutionCost,
      );
    }
    for (let index = 0; index < current.length; index += 1) {
      previous[index] = current[index];
    }
  }

  return previous[right.length];
}

function stringSimilarity(left: string, right: string): number {
  if (!left || !right) return 0;
  if (left === right) return 1;
  const maxLength = Math.max(left.length, right.length);
  if (maxLength === 0) return 1;
  return 1 - levenshteinDistance(left, right) / maxLength;
}

function tokenCoverage(query: string, candidate: string): number {
  const queryTokens = query.split(' ').filter(Boolean);
  const candidateTokens = candidate.split(' ').filter(Boolean);
  if (queryTokens.length === 0 || candidateTokens.length === 0) return 0;

  const matched = queryTokens.map((queryToken) =>
    Math.max(
      ...candidateTokens.map((candidateToken) =>
        stringSimilarity(queryToken, candidateToken),
      ),
    ),
  );
  return matched.reduce((sum, score) => sum + score, 0) / matched.length;
}

function titleSimilarity(query: string, candidate: string): number {
  const phrase = stringSimilarity(query, candidate);
  const coverage = tokenCoverage(query, candidate);
  const containment =
    candidate.includes(query) || query.includes(candidate) ? 1 : 0;
  return Math.max(
    phrase,
    0.62 * phrase + 0.38 * coverage,
    containment ? 0.84 * coverage : 0,
  );
}

function eventMatchesRequestedTime(
  event: CalendarEvent,
  requestedTime: string | undefined | null,
): boolean {
  const targetTime = normalizeCalendarLookupTime(requestedTime);
  if (!targetTime) return true;

  const targetWithoutMeridiem = calendarLookupTimeWithoutMeridiem(targetTime);
  const targetHasMeridiem = calendarLookupTimeHasMeridiem(targetTime);
  const eventTimes = getCalendarEventTimeCandidates(event).map(
    normalizeCalendarLookupTime,
  );

  return eventTimes.some((eventTime) => {
    if (eventTime === targetTime) return true;
    if (!targetHasMeridiem) {
      return (
        calendarLookupTimeWithoutMeridiem(eventTime) === targetWithoutMeridiem
      );
    }
    return false;
  });
}

export function resolveCalendarEventReference(
  events: CalendarEvent[],
  criteria: CalendarEventReferenceCriteria,
): CalendarEventReferenceResolution {
  const scopedCandidates = events.filter(
    (event) =>
      (!criteria.day || isEventForCalendarView(event, criteria.day)) &&
      eventMatchesRequestedTime(event, criteria.time),
  );

  const query = normalizeReferenceTitle(criteria.query);
  if (!query) {
    if (scopedCandidates.length === 1) {
      return { kind: 'exact', event: scopedCandidates[0], score: 1 };
    }
    if (scopedCandidates.length > 1) {
      return { kind: 'ambiguous', candidates: scopedCandidates };
    }
    return { kind: 'none', candidates: [] };
  }

  const exactMatches = scopedCandidates.filter(
    (event) => normalizeReferenceTitle(event.title) === query,
  );
  if (exactMatches.length === 1) {
    return { kind: 'exact', event: exactMatches[0], score: 1 };
  }
  if (exactMatches.length > 1) {
    return { kind: 'ambiguous', candidates: exactMatches };
  }

  const ranked = scopedCandidates
    .map((event) => ({
      event,
      score: titleSimilarity(query, normalizeReferenceTitle(event.title)),
    }))
    .sort((left, right) => right.score - left.score);

  const credible = ranked.filter(
    (candidate) => candidate.score >= LIKELY_MATCH_THRESHOLD,
  );
  if (credible.length === 0) {
    return { kind: 'none', candidates: [] };
  }

  if (credible.length === 1) {
    return {
      kind: 'likely',
      event: credible[0].event,
      score: credible[0].score,
    };
  }

  const [best, second] = credible;
  if (best.score - second.score >= LIKELY_MATCH_MARGIN) {
    return { kind: 'likely', event: best.event, score: best.score };
  }

  return {
    kind: 'ambiguous',
    candidates: credible.map((candidate) => candidate.event),
  };
}
