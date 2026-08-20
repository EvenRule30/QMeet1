import type { ActivePanel, SearchResponse } from '../types';
import type { CommandMatch } from '../commands';

export type SearchCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
  continuationContext?: string;
  compositeBindings?: {
    searchResultText?: string;
  };
};

function cleanSearchText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function verifiedSearchSteps(searchResponse: SearchResponse): string[] {
  return (searchResponse.steps ?? [])
    .map((step) => cleanSearchText(step))
    .filter(Boolean);
}

function verifiedSearchSources(searchResponse: SearchResponse) {
  return (searchResponse.sources ?? [])
    .map((source) => ({
      title: cleanSearchText(source.title),
      domain: cleanSearchText(source.domain),
      url: cleanSearchText(source.url),
    }))
    .filter((source) => source.title || source.domain || source.url);
}

/**
 * Build one deterministic, portable text representation from the successful
 * SearchResponse returned by QMeet's existing Search backend.
 *
 * Phase 21G2C may expose this exact value as a verified composite binding. The
 * composite planner never writes or rewrites it.
 */
export function buildVerifiedSearchResultText(
  searchResponse: SearchResponse,
): string {
  if (!searchResponse.ok) return '';

  const query = cleanSearchText(searchResponse.query);
  const summary =
    cleanSearchText(searchResponse.summary) ||
    cleanSearchText(searchResponse.focusResponse?.text);
  const recommendation = cleanSearchText(searchResponse.recommendation);
  const steps = verifiedSearchSteps(searchResponse);
  const sources = verifiedSearchSources(searchResponse);

  const sections: string[] = [];
  if (query) {
    sections.push(`Search: ${query}`);
  }
  if (summary) {
    sections.push(summary);
  }
  if (recommendation && recommendation !== summary) {
    sections.push(`Recommendation: ${recommendation}`);
  }
  if (steps.length > 0) {
    sections.push(
      `Action steps: ${steps
        .map((step, index) => `${index + 1}. ${step}`)
        .join('; ')}`,
    );
  }
  if (sources.length > 0) {
    sections.push(
      `Sources: ${sources
        .map((source) => {
          const label = source.title || source.domain || source.url;
          const metadata = [source.domain, source.url]
            .filter(
              (value, index, values) =>
                value && values.indexOf(value) === index,
            )
            .join(' — ');
          return metadata ? `- ${label} (${metadata})` : `- ${label}`;
        })
        .join('; ')}`,
    );
  }

  // Existing Notes promotion rejects content above 6000 characters. Leave a
  // small margin while preserving only deterministic Search output.
  return sections.join(' | ').replace(/\s+/g, ' ').trim().slice(0, 5900);
}

/**
 * Preserve the Phase 21B verified Search -> tool-continuation contract.
 *
 * The continuation model receives structured data copied only from the actual
 * successful SearchResponse. It must not reconstruct Search findings from
 * conversation history or model memory.
 */
export function buildVerifiedSearchContinuationContext(
  searchResponse: SearchResponse,
): string {
  if (!searchResponse.ok) return '';

  const resultText = buildVerifiedSearchResultText(searchResponse);
  if (!resultText) return '';

  return JSON.stringify({
    qmeetScope: 'search',
    qmeetSearchResultVerified: true,
    query: cleanSearchText(searchResponse.query),
    summary: cleanSearchText(searchResponse.summary),
    recommendation: cleanSearchText(searchResponse.recommendation),
    steps: verifiedSearchSteps(searchResponse),
    sources: verifiedSearchSources(searchResponse),
    resultText,
  });
}

export async function handleSearchCommand(
  commandMatch: CommandMatch,
  deps: {
    voiceOutputEnabled: boolean;
    searchError: string;
    setActivePanel: (panel: ActivePanel) => void;
    closePanel: () => void;
    runWebSearch: (queryInput?: string) => Promise<SearchResponse | null>;
    clearSearchState: () => void;
  },
): Promise<SearchCommandResult> {
  switch (commandMatch.command) {
    case 'open-search':
      deps.setActivePanel('search');
      return { handled: true };

    case 'run-search': {
      const preparedSearchQuery = commandMatch.payload?.trim() ?? '';
      deps.setActivePanel('search');
      let confirmationContent = 'Opening search.';
      let continuationContext: string | undefined;
      let compositeBindings: SearchCommandResult['compositeBindings'];

      if (preparedSearchQuery) {
        const searchResponse = await deps.runWebSearch(preparedSearchQuery);

        if (searchResponse?.ok) {
          const guardedText = searchResponse.focusResponse?.text?.trim() ?? '';
          if (guardedText) {
            confirmationContent = guardedText;
          } else {
            const sourceCount = searchResponse.sources?.length ?? 0;
            const stepCount = searchResponse.steps?.length ?? 0;
            const sourceText =
              sourceCount > 0
                ? ` ${sourceCount} source${sourceCount === 1 ? '' : 's'} added.`
                : '';
            const stepText =
              stepCount > 0
                ? ` ${stepCount} action step${stepCount === 1 ? '' : 's'} included.`
                : '';
            confirmationContent = `Search complete.

I put the full result in the Search panel.${stepText}${sourceText}`;
          }

          continuationContext =
            buildVerifiedSearchContinuationContext(searchResponse);

          const searchResultText = buildVerifiedSearchResultText(searchResponse);
          if (searchResultText) {
            compositeBindings = {
              searchResultText,
            };
          }
        } else {
          confirmationContent =
            searchResponse?.message ||
            deps.searchError ||
            'Web search failed.';
        }
      }

      return {
        handled: true,
        confirmationContent,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
        ...(continuationContext ? { continuationContext } : {}),
        ...(compositeBindings ? { compositeBindings } : {}),
      };
    }

    case 'clear-search':
      deps.clearSearchState();
      deps.setActivePanel('search');
      return {
        handled: true,
        confirmationContent: 'Search cleared.',
      };

    case 'close-search':
      deps.closePanel();
      return { handled: true };

    default:
      return { handled: false };
  }
}
