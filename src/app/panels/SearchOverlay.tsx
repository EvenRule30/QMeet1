import { SearchPanel } from '../components/SearchPanel';
import type { SearchResponse } from '../types';

type SearchOverlayProps = {
  query: string;
  result: SearchResponse | null;
  loading: boolean;
  error: string;
  onQueryChange: (query: string) => void;
  onRunSearch: (query?: string) => void | Promise<unknown>;
  onClearSearch: () => void;
  onClose: () => void;
};

export function SearchOverlay({
  query,
  result,
  loading,
  error,
  onQueryChange,
  onRunSearch,
  onClearSearch,
  onClose,
}: SearchOverlayProps) {
  return (
    <SearchPanel
      query={query}
      result={result}
      loading={loading}
      error={error}
      onQueryChange={onQueryChange}
      onRunSearch={(nextQuery) => {
        void onRunSearch(nextQuery);
      }}
      onClearSearch={onClearSearch}
      onClose={onClose}
    />
  );
}
