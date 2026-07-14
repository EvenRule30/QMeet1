export type BriefingPeriod =
  | 'morning'
  | 'afternoon'
  | 'evening'
  | 'late-night';

const BRIEFING_REQUEST_PATTERN =
  /\b(brief me|daily brief(?:ing)?|morning brief(?:ing)?|start my day|plan my day|what(?:'s| is) my day(?: look like)?|what(?:'s| is) on deck|what(?:'s| is) my agenda|overview of my day)\b/i;

export function isBriefingRequest(text: string): boolean {
  return BRIEFING_REQUEST_PATTERN.test((text || '').trim());
}

export function getBriefingPeriod(now: Date = new Date()): BriefingPeriod {
  const hour = now.getHours();

  if (hour >= 5 && hour < 12) {
    return 'morning';
  }

  if (hour >= 12 && hour < 17) {
    return 'afternoon';
  }

  if (hour >= 17 && hour < 22) {
    return 'evening';
  }

  return 'late-night';
}

function getPeriodInstructions(period: BriefingPeriod): string[] {
  switch (period) {
    case 'morning':
      return [
        'Treat this as a start-of-day briefing.',
        'Lead with the next upcoming commitment and the most useful first priority.',
        'Suggest work that realistically fits before the next fixed event.',
      ];

    case 'afternoon':
      return [
        'Treat this as a remaining-afternoon briefing.',
        'Ignore completed morning commitments unless they affect what happens next.',
        'Prioritize the next event, remaining work blocks, and one task that can still be finished today.',
      ];

    case 'evening':
      return [
        'Treat this as an evening briefing.',
        'Focus only on remaining commitments, one sensible wrap-up task, and preparation for tomorrow.',
        'Do not overload the evening with optional work.',
      ];

    case 'late-night':
      return [
        'Treat this as a late-night briefing.',
        'Mention only urgent remaining commitments, a reasonable stopping point, and tomorrow’s first priority.',
        'Do not encourage unnecessary late-night work.',
      ];
  }
}

export function buildBriefingRequest(now: Date = new Date()): string {
  let timeZone = 'local';

  try {
    timeZone =
      Intl.DateTimeFormat().resolvedOptions().timeZone?.trim() || 'local';
  } catch {
    timeZone = 'local';
  }

  const period = getBriefingPeriod(now);
  const localDateTime = now.toLocaleString([], {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

  return [
    'Give me a concise, time-aware daily briefing.',
    `Current local date and time: ${localDateTime}.`,
    `Current timezone: ${timeZone}.`,
    `Current part of day: ${period}.`,
    'Treat calendar events scheduled earlier than the current time as past.',
    ...getPeriodInstructions(period),
    'Use calendar events as fixed commitments and tasks, notes, and recent work as flexible context.',
    'End with one concrete action I can take now.',
  ].join('\n');
}
