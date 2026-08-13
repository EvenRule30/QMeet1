import { parseCommand, type CommandMatch } from '../commands';
import type { DeferredCalendarWriteAction } from './agentToolPromotion';

export type ExplicitCalendarWriteIntent = {
  expectedAction: DeferredCalendarWriteAction;
  canonicalFrontendCommand?: string;
  commandMatch?: CommandMatch;
  reason: string;
};

const CALENDAR_TARGET_TERM = /\b(?:calendar|calender|calander|schedule|agenda|event|appointment|meeting|reminder)\b/i;
const SCHEDULE_AS_NOUN_OR_READ = /^(?:schedule)\s+(?:looks?|is|seems?|appears?|for|of|today\b|tomorrow\b)/i;
const BROAD_SCHEDULING_PLAN_TITLE = /^(?:(?:my|our|the)\s+)?(?:day|schedule|agenda|plans?)$/i;

function normalizeExplicitWriteText(value: string): string {
  return value
    .trim()
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/[?!.,;:]+$/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function stripRequestPrefix(value: string): string {
  return value
    .replace(
      /^(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+(?:want|need)\s+(?:you\s+)?to\s+)?/i,
      '',
    )
    .trim();
}

function buildExactNoTimeScheduleCommand(
  writeText: string,
): ExplicitCalendarWriteIntent | null {
  if (SCHEDULE_AS_NOUN_OR_READ.test(writeText)) return null;

  const match = writeText.match(
    /^schedule\s+(.+?)\s+(?:(?:for|on)\s+)?(today|tomorrow)$/i,
  );
  if (!match) return null;

  const title = match[1].trim();
  const day = match[2].toLowerCase() as 'today' | 'tomorrow';
  if (!title || BROAD_SCHEDULING_PLAN_TITLE.test(title)) return null;

  const canonicalFrontendCommand = `add event ${day} called ${title}`;
  const commandMatch = parseCommand(canonicalFrontendCommand);
  if (
    !commandMatch ||
    commandMatch.command !== 'add-calendar-event' ||
    commandMatch.calendarEvent?.day !== day ||
    !commandMatch.calendarEvent?.title?.trim()
  ) {
    return null;
  }

  return {
    expectedAction: 'add-calendar-event',
    canonicalFrontendCommand,
    commandMatch,
    reason:
      'Explicit schedule syntax named one today/tomorrow event without a time; normalized through the existing Calendar parser, which preserves its established Later-time behavior.',
  };
}

function classifyUnparsedExplicitCalendarWrite(
  writeText: string,
): DeferredCalendarWriteAction | null {
  if (!writeText || SCHEDULE_AS_NOUN_OR_READ.test(writeText)) return null;

  if (
    /^(?:clear|wipe)\b/i.test(writeText) &&
    /\b(?:calendar|calender|calander|schedule|agenda|events?)\b/i.test(writeText)
  ) {
    return 'clear-calendar';
  }

  if (/^schedule\b/i.test(writeText)) {
    const scheduleTarget = writeText.replace(/^schedule\s+/i, '').trim();
    if (BROAD_SCHEDULING_PLAN_TITLE.test(scheduleTarget.replace(/\s+(?:today|tomorrow)$/i, '').trim())) {
      return null;
    }
    return 'add-calendar-event';
  }

  if (
    /^(?:add|create|make|put)\b/i.test(writeText) &&
    CALENDAR_TARGET_TERM.test(writeText)
  ) {
    return 'add-calendar-event';
  }

  if (
    /^(?:delete|remove|erase|cancel)\b/i.test(writeText) &&
    CALENDAR_TARGET_TERM.test(writeText)
  ) {
    return 'delete-calendar-event';
  }

  if (
    /^(?:edit|update|change|rename|retitle|reschedule|move)\b/i.test(writeText) &&
    CALENDAR_TARGET_TERM.test(writeText)
  ) {
    return 'edit-last-event';
  }

  return null;
}

/**
 * Protect explicit Calendar mutations before agent-first ownership.
 *
 * Existing exact parse results remain authoritative and are left alone. For the
 * one safe grammar gap this slice needs -- `schedule <title> today|tomorrow`
 * without a time -- the helper rewrites to an already-supported canonical
 * frontend command and re-parses it through commands.ts. It never executes a
 * Calendar write itself.
 *
 * Other explicit but underspecified Calendar writes only return the expected
 * canonical mutation id. They deliberately do not create a CommandMatch, so
 * the existing interpreter/confirmation path must either resolve the same
 * mutation safely or leave Calendar unchanged. This prevents a write request
 * such as `delete tomorrow's meeting` from being answered as ordinary chat.
 */
export function resolveExplicitCalendarWriteIntentBeforeAgent(options: {
  userMessage: string;
  parsedCommand: CommandMatch | null;
}): ExplicitCalendarWriteIntent | null {
  if (options.parsedCommand) return null;

  const normalized = normalizeExplicitWriteText(options.userMessage);
  if (!normalized) return null;
  const writeText = stripRequestPrefix(normalized);
  if (!writeText) return null;

  const exactScheduleCommand = buildExactNoTimeScheduleCommand(writeText);
  if (exactScheduleCommand) return exactScheduleCommand;

  const expectedAction = classifyUnparsedExplicitCalendarWrite(writeText);
  if (!expectedAction) return null;

  return {
    expectedAction,
    reason:
      'Explicit Calendar mutation syntax was detected before agent-first conversation ownership, but the existing exact parser did not safely resolve all mutation arguments.',
  };
}
