import type { CommandMatch } from '../commands';
import type { PromotedSingleIntentDecision } from './agentShadowObserver';

export type PromotedSearchToolCommand = {
  query: string;
  commandMatch: CommandMatch;
};

const MAX_PROMOTED_SEARCH_QUERY_LENGTH = 500;

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

/**
 * Phase 21B's first promoted tool contract is intentionally Search-only.
 * The model may propose ownership/action/arguments, but this function is the
 * deterministic gate that decides whether those arguments are executable.
 * No other owner or action can produce a CommandMatch here.
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
