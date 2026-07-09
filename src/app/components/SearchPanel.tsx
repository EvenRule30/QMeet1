import { SearchResponse } from '../types';

interface SearchPanelProps {
  query: string;
  result: SearchResponse | null;
  loading: boolean;
  error: string;
  onQueryChange: (query: string) => void;
  onRunSearch: (query?: string) => void | Promise<void>;
  onClearSearch: () => void;
  onClose: () => void;
}

export function SearchPanel({
  query,
  result,
  loading,
  error,
  onQueryChange,
  onRunSearch,
  onClearSearch,
  onClose,
}: SearchPanelProps) {
  const trimmedQuery = query.trim();
  const hasResult = Boolean(result?.summary?.trim());

  return (
    <div className="panel-overlay">
      <div className="panel-content search-panel">
        <div className="panel-header">Search</div>

        <div className="panel-body search-panel-body">
          <div className="search-hero">
            <div>
              <div className="search-kicker">Web Search</div>
              <div className="search-title">Ask QMeet to search the web and summarize results.</div>
            </div>
            <div className="search-chip">{loading ? 'Searching' : hasResult ? 'Results' : 'Ready'}</div>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Search Query</div>
            <div className="search-input-row">
              <input
                className="search-input"
                value={query}
                onChange={(event) => onQueryChange(event.target.value)}
                placeholder="Search the web..."
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && trimmedQuery && !loading) {
                    onRunSearch(trimmedQuery);
                  }
                }}
              />
              <button
                className="panel-action-btn"
                type="button"
                onClick={() => onRunSearch(trimmedQuery)}
                disabled={!trimmedQuery || loading}
              >
                {loading ? 'Searching…' : 'Search'}
              </button>
              <button
                className="panel-action-btn"
                type="button"
                onClick={onClearSearch}
                disabled={!trimmedQuery && !hasResult && !error}
              >
                Clear
              </button>
            </div>
          </div>

          {error && (
            <div className="search-placeholder-result search-error-result">
              <div className="search-placeholder-title">Search issue</div>
              <p className="search-placeholder-text">{error}</p>
            </div>
          )}

          {!error && loading && (
            <div className="search-placeholder-result">
              <div className="search-placeholder-title">Searching the web…</div>
              <p className="search-placeholder-text">
                QMeet is gathering current web results for “{trimmedQuery}”.
              </p>
            </div>
          )}

          {!error && !loading && !hasResult && (
            <div className="search-placeholder-result">
              <div className="search-placeholder-title">
                {trimmedQuery ? `Ready to search: ${trimmedQuery}` : 'No active search yet.'}
              </div>
              <p className="search-placeholder-text">
                Say “search for raspberry pi kiosk mode,” “look up Chromium flags,” or type a query and press Search.
              </p>
            </div>
          )}

          {!error && !loading && result && hasResult && (
            <div className="search-result-card">
              <div className="search-result-kicker">Result for</div>
              <div className="search-result-query">{result.query}</div>
              <p className="search-result-summary">{result.summary}</p>

              {result.sources.length > 0 && (
                <div className="search-sources">
                  <div className="panel-section-title">Sources</div>
                  {result.sources.slice(0, 5).map((source, index) => (
                    <a
                      className="search-source-link"
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      key={`${source.url}-${index}`}
                    >
                      <span className="search-source-title">{source.title || source.domain || source.url}</span>
                      <span className="search-source-domain">{source.domain || source.url}</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="panel-section">
            <div className="panel-section-title">Supported Commands</div>
            <p className="panel-section-text">
              Say “open search,” “search for raspberry pi kiosk mode,” “look up local voice assistant,” “google chromium flags,” “clear search,” “close search,” or “go home.”
            </p>
          </div>

          <button className="close-panel-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
