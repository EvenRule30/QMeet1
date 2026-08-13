import type { ActivePanel, SearchResponse } from '../types';
import type { CommandMatch } from '../commands';

export type SearchCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
  continuationContext?: string;
};

function compactText(value: unknown, maxLength: number): string {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`;
}

function buildSearchContinuationContext(response: SearchResponse): string {
  return JSON.stringify({
    query: compactText(response.query, 500),
    summary: compactText(response.summary, 4000),
    recommendation: compactText(response.recommendation, 1800),
    steps: (response.steps ?? []).slice(0, 6).map((step) => compactText(step, 700)),
    cards: (response.cards ?? []).slice(0, 6).map((card) => ({
      title: compactText(card.title, 240),
      detail: compactText(card.detail, 900),
    })),
    sources: (response.sources ?? []).slice(0, 8).map((source) => ({
      title: compactText(source.title, 240),
      url: compactText(source.url, 1200),
      domain: compactText(source.domain, 200),
      usedFor: compactText(source.usedFor, 500),
    })),
    provider: compactText(response.provider, 120),
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

      if (preparedSearchQuery) {
        const searchResponse = await deps.runWebSearch(preparedSearchQuery);

        if (searchResponse?.ok) {
          continuationContext = buildSearchContinuationContext(searchResponse);
          const guardedText = searchResponse.focusResponse?.text?.trim() ?? '';
          if (guardedText) {
            confirmationContent = guardedText;
          } else {
            const sourceCount = searchResponse.sources?.length ?? 0;
            const stepCount = searchResponse.steps?.length ?? 0;
            const sourceText = sourceCount > 0
              ? ` ${sourceCount} source${sourceCount === 1 ? '' : 's'} added.`
              : '';
            const stepText = stepCount > 0
              ? ` ${stepCount} action step${stepCount === 1 ? '' : 's'} included.`
              : '';
            confirmationContent = `Search complete.\nI put the full result in the Search panel.${stepText}${sourceText}`;
          }
        } else {
          confirmationContent = searchResponse?.message
            || deps.searchError
            || 'Web search failed.';
        }
      }
      return {
        handled: true,
        confirmationContent,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
        continuationContext,
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
