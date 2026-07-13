import { useCallback, useState } from 'react';
import { searchWeb } from '../api';
import type { SearchResponse } from '../types';

type UseSearchControllerOptions = {
  openSearchPanel: () => void;
};

export function useSearchController({ openSearchPanel }: UseSearchControllerOptions) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');

  const clearSearchState = useCallback(() => {
    setSearchQuery('');
    setSearchResult(null);
    setSearchError('');
    setSearchLoading(false);
  }, []);

  const runWebSearch = useCallback(async (queryInput?: string): Promise<SearchResponse | null> => {
    const query = (queryInput ?? searchQuery).trim();

    openSearchPanel();

    if (!query) {
      setSearchError('Enter a search query first.');
      setSearchResult(null);
      return null;
    }

    setSearchQuery(query);
    setSearchLoading(true);
    setSearchError('');

    try {
      const response = await searchWeb(query);
      setSearchResult(response);
      setSearchError(response.ok ? '' : response.message || 'Search failed.');
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Web search failed.';
      setSearchResult(null);
      setSearchError(message);
      return null;
    } finally {
      setSearchLoading(false);
    }
  }, [openSearchPanel, searchQuery]);

  return {
    searchQuery,
    setSearchQuery,
    searchResult,
    searchLoading,
    searchError,
    runWebSearch,
    clearSearchState,
  };
}
