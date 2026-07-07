interface SearchPanelProps {
  query: string;
  onQueryChange: (query: string) => void;
  onClose: () => void;
}

export function SearchPanel({ query, onQueryChange, onClose }: SearchPanelProps) {
  const trimmedQuery = query.trim();

  return (
    <div className="panel-overlay">
      <div className="panel-content search-panel">
        <div className="panel-header">Search</div>

        <div className="panel-body search-panel-body">
          <div className="search-hero">
            <div>
              <div className="search-kicker">Browser Placeholder</div>
              <div className="search-title">Search and browsing controls will live here.</div>
            </div>
            <div className="search-chip">Local UI</div>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Search Query</div>
            <div className="search-input-row">
              <input
                className="search-input"
                value={query}
                onChange={(event) => onQueryChange(event.target.value)}
                placeholder="Type a future search query..."
              />
              <button
                className="panel-action-btn"
                type="button"
                onClick={() => onQueryChange('')}
                disabled={!trimmedQuery}
              >
                Clear
              </button>
            </div>
          </div>

          <div className="search-placeholder-result">
            <div className="search-placeholder-title">
              {trimmedQuery ? `Prepared search query: ${trimmedQuery}` : 'No active search yet.'}
            </div>
            <p className="search-placeholder-text">
              Real web browsing is not connected yet. This panel is a local prototype shell. Voice/text search commands currently prepare the query here for future browser/search integration.
            </p>
          </div>

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
