import type { CommandMatch } from '../commands';
import type { DeferredCalendarWriteAction } from './agentToolPromotion';

export type ExplicitCalendarWriteIntent = {
  expectedAction: DeferredCalendarWriteAction;
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
    const targetWithoutNearTermDay = scheduleTarget
      .replace(/\s+(?:today|tomorrow)$/i, '')
      .trim();
    if (BROAD_SCHEDULING_PLAN_TITLE.test(targetWithoutNearTermDay)) return null;
    return 'add-calendar-event';
  }

  if (
    /^(?:add|create|make|put|book)\b/i.test(writeText) &&
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
 * Deterministic ownership fallback only.
 *
 * Exact commands remain authoritative and bypass this helper. For an explicit
 * Calendar mutation that the exact parser did not understand, this helper only
 * preserves the expected Calendar mutation id so semantic Focus routing cannot
 * steal the turn if the agent is unavailable or returns no usable ownership.
 * It never synthesizes arguments, a frontend command, or a CommandMatch.
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

  const expectedAction = classifyUnparsedExplicitCalendarWrite(writeText);
  if (!expectedAction) return null;

  return {
    expectedAction,
    reason:
      'Explicit Calendar mutation syntax established deterministic Calendar ownership, but no write arguments or executable command were synthesized.',
  };
}
