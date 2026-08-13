import type { CommandMatch } from '../commands';
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

export type DeferredCalendarWriteAction =
  | 'add-calendar-event'
  | 'edit-last-event'
  | 'delete-calendar-event'
  | 'delete-last-event'
  | 'clear-calendar';

const DEFERRED_CALENDAR_WRITE_ACTIONS = new Set<DeferredCalendarWriteAction>([
  'add-calendar-event',
  'edit-last-event',
  'delete-calendar-event',
  'delete-last-event',
  'clear-calendar',
]);

const MAX_PROMOTED_SEARCH_QUERY_LENGTH = 500;
const PROMOTED_CALENDAR_READ_VIEWS = new Set<PromotedCalendarReadView>([
  'today',
  'tomorrow',
  'all',
]);

function readValidatedSearchQuery(
  argumentsValue: Record<string, unknown>,
): string | null {
  const keys = Object.keys(argumentsValue);
  if (keys.length !== 1 || keys[0] !== 'query') return null;
  const rawQuery = argumentsValue.query;
  if (typeof rawQuery !== 'string') return null;

  const query = rawQuery.trim();
  if (!query || query.length > MAX_PROMOTED_SEARCH_QUERY_LENGTH) return null;
  if(/[\u0000-\u001f\u007f]/.test(query)) return null;
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
 * Calendar promotion is intentionally read-only. The agent can choose Calendar
 * ownership and one canonical read action, but only this exact one-field view
 * contract is allowed back into the existing deterministic Calendar executor.
 * Calendar writes, edits, and deletes cannot produce a CommandMatch here.
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
 * Calendar writes are still NOT promoted for execution. This helper only
 * preserves the unified agent's canonical write classification long enough to
 * validate the older command interpreter's result. Proposed write arguments
 * are deliberately ignored, and no CommandMatch can be created here.
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
