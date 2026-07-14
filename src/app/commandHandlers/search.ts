import type { ActivePanel, SearchResponse } from '../types';
import type { CommandMatch } from '../commands';

export type SearchCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
};

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

      if (preparedSearchQuery) {
        const searchResponse = await deps.runWebSearch(preparedSearchQuery);

        if (searchResponse?.ok) {
          const sourceCount = searchResponse.sources?.length ?? 0;
          const stepCount = searchResponse.steps?.length ?? 0;
          const sourceText = sourceCount > 0
            ? ` ${sourceCount} source${sourceCount === 1 ? '' : 's'} added.`
            : '';
          const stepText = stepCount > 0
            ? ` ${stepCount} action step${stepCount === 1 ? '' : 's'} included.`
            : '';
          confirmationContent = `Search complete. I put the full result in the Search panel.${stepText}${sourceText}`;
        } else {
          confirmationContent = searchResponse?.message || deps.searchError || 'Web search failed.';
        }
      }

      return {
        handled: true,
        confirmationContent,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
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
