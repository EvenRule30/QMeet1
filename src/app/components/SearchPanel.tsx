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

function sanitizeUiText(value: string | undefined, maxLength = 240): string {
  const cleaned = String(value ?? '')
    .replace(/\[([^\]]+)\]\((?:https?:\/\/|www\.)[^)]+\)/g, '$1')
    .replace(/[*`#>]+/g, '')
    .replace(/[_]+/g, ' ')
    .replace(/\s+[—–]\s+/g, ' ')
    .replace(/\s+-\s+/g, ' ')
    .replace(/\b(?:the|a|an)\s+(?=Responses API|web search|Calendar API|OpenAI API)/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^[-•\s]+|[-•\s]+$/g, '')
    .trim();

  if (cleaned.length <= maxLength) return cleaned;
  return `${cleaned.slice(0, maxLength - 1).trim()}…`;
}

function stripLeadingNumber(text: string): string {
  let cleaned = sanitizeUiText(text, 220);

  // The UI adds numbering, so remove model-generated numbering or bullets.
  for (let i = 0; i < 4; i += 1) {
    cleaned = cleaned
      .replace(/^\s*(?:\d{1,2}[.)]|[-•*])\s+/g, '')
      .replace(/^\s*(?:step\s+)?\d{1,2}\s*[:.)-]\s+/gi, '')
      .trim();
  }

  return cleaned;
}

function sourceTitle(source: SearchResponse['sources'][number]): string {
  const title = sanitizeUiText(source.title, 90);
  const domain = sanitizeUiText(source.domain, 90).toLowerCase();
  const url = source.url?.trim() ?? '';
  const lowerTitle = title.toLowerCase();

  const looksBad =
    !title ||
    title.length > 80 ||
    lowerTitle === domain ||
    lowerTitle.includes('best for') ||
    lowerTitle.includes('utm source') ||
    lowerTitle.includes('http') ||
    /^\d+\s/.test(lowerTitle) ||
    lowerTitle.includes('do the openai api models') ||
    lowerTitle.includes('official information on');

  if (!looksBad) return title;

  if (domain.includes('platform.openai.com')) return 'OpenAI API documentation';
  if (domain.includes('help') && domain.includes('openai.com')) return 'OpenAI Help Center';
  if (domain.includes('openai.com')) return 'OpenAI product update';
  if (domain.includes('raspberrypi.com')) return 'Official Raspberry Pi guide';
  if (domain.includes('raspberrytips.com')) return 'Raspberry Pi Tips guide';
  if (domain.includes('zbotic.in')) return 'Touchscreen kiosk guide';

  try {
    const parsed = new URL(url);
    const slug = parsed.pathname.split('/').filter(Boolean).pop() ?? '';
    const inferred = sanitizeUiText(slug.replace(/[-_]+/g, ' ').replace(/\.(html?|md|php)$/i, ''), 80);
    if (inferred) return inferred.charAt(0).toUpperCase() + inferred.slice(1);
  } catch {
    // Ignore malformed URLs; fall back to domain.
  }

  return sanitizeUiText(domain || url || 'Source', 80);
}

function sourceUse(source: SearchResponse['sources'][number]): string {
  const rawUsedFor = sanitizeUiText(source.usedFor, 110)
    .replace(/^best for\s*:?\s*/i, '')
    .replace(/^official information (?:on|about)\s*/i, '')
    .trim();

  const domain = sanitizeUiText(source.domain, 90).toLowerCase();

  if (
    rawUsedFor &&
    rawUsedFor.length <= 90 &&
    !rawUsedFor.toLowerCase().includes('official information')
  ) {
    return rawUsedFor;
  }

  if (domain.includes('platform.openai.com')) return 'API reference and tool behavior.';
  if (domain.includes('help') && domain.includes('openai.com')) return 'Help article or implementation note.';
  if (domain.includes('openai.com')) return 'Official OpenAI announcement or guide.';
  if (domain.includes('raspberrypi.com')) return 'Official Raspberry Pi setup reference.';
  if (domain.includes('raspberrytips.com')) return 'Practical setup walkthrough.';
  if (domain.includes('zbotic.in')) return 'Touchscreen and display notes.';

  return 'Supporting reference.';
}

function sourceDomain(source: SearchResponse['sources'][number]): string {
  const domain = sanitizeUiText(source.domain, 90);
  if (domain) return domain;

  try {
    return new URL(source.url).hostname.replace(/^www\./, '');
  } catch {
    return sanitizeUiText(source.url, 90);
  }
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
  const steps = (result?.steps ?? []).map(stripLeadingNumber).filter(Boolean).slice(0, 5);
  const cards = (result?.cards ?? [])
    .map((card) => ({
      title: sanitizeUiText(card.title, 50),
      detail: sanitizeUiText(card.detail, 220),
    }))
    .filter((card) => card.title || card.detail)
    .slice(0, 4);
  const sources = result?.sources ?? [];
  const hasResult = Boolean(
    result?.summary?.trim() ||
    result?.recommendation?.trim() ||
    steps.length > 0 ||
    cards.length > 0 ||
    sources.length > 0
  );

  const sectionStyle = {
    marginTop: '12px',
  } as const;

  const cardStyle = {
    display: 'block',
    padding: '12px 14px',
    borderRadius: '12px',
    border: '1px solid rgba(0, 206, 255, 0.22)',
    background: 'rgba(5, 24, 48, 0.72)',
    color: 'inherit',
    textDecoration: 'none',
  } as const;

  const mutedStyle = {
    marginTop: '6px',
    fontSize: '13px',
    lineHeight: 1.45,
    color: 'rgba(211, 226, 247, 0.72)',
  } as const;

  return (
    <div className="panel-overlay">
      <div className="panel-content search-panel">
        <div className="panel-header">Search</div>

        <div className="panel-body search-panel-body">
          <div className="search-hero">
            <div>
              <div className="search-kicker">Web Search</div>
              <div className="search-title">Search the web, then turn results into a usable action card.</div>
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
              <div className="search-result-query">{sanitizeUiText(result.query, 140)}</div>

              {result.summary && (
                <div className="panel-section" style={sectionStyle}>
                  <div className="panel-section-title">Summary</div>
                  <p className="panel-section-text">{sanitizeUiText(result.summary, 260)}</p>
                </div>
              )}

              {result.recommendation && (
                <div className="search-placeholder-result" style={sectionStyle}>
                  <div className="search-placeholder-title">Recommended Setup</div>
                  <p className="search-placeholder-text">{sanitizeUiText(result.recommendation, 320)}</p>
                </div>
              )}

              {steps.length > 0 && (
                <div className="panel-section" style={sectionStyle}>
                  <div className="panel-section-title">Action Steps</div>
                  <div style={{ display: 'grid', gap: '8px' }}>
                    {steps.map((step, index) => (
                      <div style={cardStyle} key={`${step}-${index}`}>
                        <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                          <span
                            style={{
                              display: 'inline-flex',
                              minWidth: '24px',
                              height: '24px',
                              alignItems: 'center',
                              justifyContent: 'center',
                              borderRadius: '999px',
                              background: 'rgba(0, 206, 255, 0.13)',
                              color: '#00d7ff',
                              fontSize: '13px',
                              fontWeight: 700,
                            }}
                          >
                            {index + 1}
                          </span>
                          <span style={{ lineHeight: 1.45 }}>{step}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {cards.length > 0 && (
                <div className="panel-section" style={sectionStyle}>
                  <div className="panel-section-title">Useful Details</div>
                  <div style={{ display: 'grid', gap: '8px' }}>
                    {cards.map((card, index) => (
                      <div style={cardStyle} key={`${card.title}-${index}`}>
                        {card.title && <div style={{ fontWeight: 700 }}>{card.title}</div>}
                        {card.detail && <div style={mutedStyle}>{card.detail}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {sources.length > 0 && (
                <div className="panel-section" style={sectionStyle}>
                  <div className="panel-section-title">Sources</div>
                  <div style={{ display: 'grid', gap: '8px' }}>
                    {sources.slice(0, 4).map((source, index) => (
                      <a
                        style={cardStyle}
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                        key={`${source.url}-${index}`}
                      >
                        <div style={{ fontWeight: 700 }}>{sourceTitle(source)}</div>
                        <div style={mutedStyle}>Use for: {sourceUse(source)}</div>
                        <div style={{ ...mutedStyle, color: 'rgba(0, 215, 255, 0.9)' }}>{sourceDomain(source)}</div>
                      </a>
                    ))}
                  </div>
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
