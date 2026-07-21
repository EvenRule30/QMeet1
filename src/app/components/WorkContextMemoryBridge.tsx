import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { createPortal } from 'react-dom';

type WorkContextStage =
  | 'discovery'
  | 'planning'
  | 'in-progress'
  | 'ready'
  | 'complete';

type BackgroundWorkContext = {
  sessionId: string;
  title: string;
  mode: string;
  objective: string;
  knownFacts: string[];
  constraints: string[];
  decisions: string[];
  openQuestions: string[];
  nextAction: string;
  recentProgress: string[];
  stage: WorkContextStage;
  confidence: number;
  updatedAt: string;
};

type WorkContextResponse = {
  ok: boolean;
  provider?: string;
  activeContext: BackgroundWorkContext | null;
  message?: string;
};

type LoadState = 'idle' | 'loading' | 'ready' | 'error';

const WORK_CONTEXT_STATE_EVENT = 'qmeet-work-context-state';
const ACTIVE_SESSION_STATE_EVENT = 'qmeet-active-session-state';
const MEMORY_BODY_SELECTOR = '.memory-panel-body';
const PORTAL_ATTRIBUTE = 'data-qmeet-work-context-portal';
const POLL_INTERVAL_MS = 1500;

function getApiBaseUrl() {
  const configuredUrl = import.meta.env.VITE_QMEET_API_URL?.trim();
  return (configuredUrl || 'http://localhost:8000').replace(/\/+$/, '');
}

function cleanText(value: unknown, fallback = '') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function cleanList(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === 'string')
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeStage(value: unknown): WorkContextStage {
  return value === 'planning' ||
    value === 'in-progress' ||
    value === 'ready' ||
    value === 'complete'
    ? value
    : 'discovery';
}

function normalizeContext(value: unknown): BackgroundWorkContext | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<BackgroundWorkContext>;
  const sessionId = cleanText(candidate.sessionId);
  const title = cleanText(candidate.title);

  if (!sessionId || !title) return null;

  const confidence =
    typeof candidate.confidence === 'number' &&
    Number.isFinite(candidate.confidence)
      ? Math.max(0, Math.min(1, candidate.confidence))
      : 0;

  return {
    sessionId,
    title,
    mode: cleanText(candidate.mode, 'general'),
    objective: cleanText(candidate.objective),
    knownFacts: cleanList(candidate.knownFacts),
    constraints: cleanList(candidate.constraints),
    decisions: cleanList(candidate.decisions),
    openQuestions: cleanList(candidate.openQuestions),
    nextAction: cleanText(candidate.nextAction),
    recentProgress: cleanList(candidate.recentProgress),
    stage: normalizeStage(candidate.stage),
    confidence,
    updatedAt: cleanText(candidate.updatedAt),
  };
}

function normalizeResponse(value: unknown): WorkContextResponse {
  if (!value || typeof value !== 'object') {
    return {
      ok: false,
      activeContext: null,
      message: 'The work-context response was not valid.',
    };
  }

  const candidate = value as Partial<WorkContextResponse>;
  return {
    ok: candidate.ok === true,
    provider: cleanText(candidate.provider) || undefined,
    activeContext: normalizeContext(candidate.activeContext),
    message: cleanText(candidate.message),
  };
}

function formatStage(stage: WorkContextStage) {
  if (stage === 'in-progress') return 'In progress';
  return stage.charAt(0).toUpperCase() + stage.slice(1);
}

function formatMode(mode: string) {
  return mode.charAt(0).toUpperCase() + mode.slice(1);
}

function formatUpdatedAt(value: string) {
  if (!value) return 'Updated recently';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'Updated recently';

  return `Updated ${date.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  })}`;
}

function findCurrentFocusSection(memoryBody: HTMLElement) {
  return Array.from(memoryBody.children).find((child) => {
    if (!(child instanceof HTMLElement)) return false;
    const title = child.querySelector('.panel-section-title');
    return title?.textContent?.trim() === 'Current Focus';
  }) as HTMLElement | undefined;
}

function ensurePortalTarget() {
  if (typeof document === 'undefined') return null;

  const memoryBody = document.querySelector<HTMLElement>(MEMORY_BODY_SELECTOR);
  if (!memoryBody) return null;

  const existingTarget = memoryBody.querySelector<HTMLElement>(
    `[${PORTAL_ATTRIBUTE}="true"]`,
  );
  if (existingTarget) return existingTarget;

  const target = document.createElement('div');
  target.setAttribute(PORTAL_ATTRIBUTE, 'true');
  target.className = 'qmeet-work-context-portal';

  const currentFocusSection = findCurrentFocusSection(memoryBody);
  if (currentFocusSection?.nextSibling) {
    memoryBody.insertBefore(target, currentFocusSection.nextSibling);
  } else if (currentFocusSection) {
    memoryBody.appendChild(target);
  } else {
    memoryBody.prepend(target);
  }

  return target;
}

function WorkContextStyles() {
  return (
    <style>{`
      .qmeet-work-context-section {
        border: 1px solid rgba(202, 189, 255, 0.2);
        background:
          linear-gradient(145deg, rgba(76, 55, 126, 0.2), rgba(31, 24, 53, 0.28)),
          rgba(19, 15, 33, 0.5);
        overflow: hidden;
      }

      .qmeet-work-context-heading {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 10px;
      }

      .qmeet-work-context-kicker {
        color: rgba(225, 217, 255, 0.66);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }

      .qmeet-work-context-title {
        margin-top: 3px;
        color: rgba(251, 249, 255, 0.98);
        font-size: 16px;
        font-weight: 720;
        line-height: 1.2;
      }

      .qmeet-work-context-meta {
        margin-top: 4px;
        color: rgba(222, 215, 241, 0.62);
        font-size: 11px;
      }

      .qmeet-work-context-actions {
        display: flex;
        align-items: center;
        gap: 7px;
        flex-shrink: 0;
      }

      .qmeet-work-context-stage {
        border: 1px solid rgba(194, 177, 255, 0.22);
        border-radius: 999px;
        background: rgba(156, 126, 255, 0.13);
        color: rgba(236, 229, 255, 0.86);
        padding: 5px 8px;
        font-size: 10px;
        font-weight: 680;
        white-space: nowrap;
      }

      .qmeet-work-context-refresh {
        border: 1px solid rgba(217, 206, 255, 0.16);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.04);
        color: rgba(238, 232, 255, 0.78);
        min-height: 28px;
        padding: 0 9px;
        font: inherit;
        font-size: 10px;
        cursor: pointer;
      }

      .qmeet-work-context-refresh:hover,
      .qmeet-work-context-refresh:focus-visible {
        background: rgba(255, 255, 255, 0.09);
        color: rgba(255, 255, 255, 0.96);
        outline: none;
      }

      .qmeet-work-context-primary-grid {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        gap: 8px;
      }

      .qmeet-work-context-primary-card,
      .qmeet-work-context-list-card {
        border: 1px solid rgba(216, 206, 255, 0.11);
        border-radius: 11px;
        background: rgba(10, 8, 19, 0.22);
        padding: 10px;
        min-width: 0;
      }

      .qmeet-work-context-card-label {
        color: rgba(219, 209, 252, 0.56);
        font-size: 9px;
        font-weight: 760;
        letter-spacing: 0.09em;
        text-transform: uppercase;
      }

      .qmeet-work-context-card-value {
        margin-top: 5px;
        color: rgba(247, 244, 255, 0.9);
        font-size: 12px;
        line-height: 1.42;
        overflow-wrap: anywhere;
      }

      .qmeet-work-context-next {
        border-color: rgba(166, 138, 255, 0.22);
        background: rgba(117, 86, 213, 0.12);
      }

      .qmeet-work-context-detail-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
        margin-top: 8px;
      }

      .qmeet-work-context-list {
        display: grid;
        gap: 6px;
        margin: 7px 0 0;
        padding: 0;
        list-style: none;
      }

      .qmeet-work-context-list li {
        position: relative;
        padding-left: 11px;
        color: rgba(238, 233, 251, 0.78);
        font-size: 11px;
        line-height: 1.35;
        overflow-wrap: anywhere;
      }

      .qmeet-work-context-list li::before {
        content: '';
        position: absolute;
        left: 1px;
        top: 0.52em;
        width: 4px;
        height: 4px;
        border-radius: 999px;
        background: rgba(183, 161, 255, 0.68);
      }

      .qmeet-work-context-question {
        margin-top: 8px;
        border: 1px solid rgba(227, 210, 154, 0.15);
        border-radius: 10px;
        background: rgba(152, 119, 41, 0.08);
        padding: 9px 10px;
      }

      .qmeet-work-context-empty,
      .qmeet-work-context-error {
        color: rgba(232, 226, 247, 0.7);
        font-size: 12px;
        line-height: 1.45;
      }

      .qmeet-work-context-error {
        color: rgba(255, 199, 205, 0.84);
      }

      @media (max-width: 760px) {
        .qmeet-work-context-primary-grid,
        .qmeet-work-context-detail-grid {
          grid-template-columns: 1fr;
        }
      }
    `}</style>
  );
}

function ContextListCard({
  label,
  items,
}: {
  label: string;
  items: string[];
}) {
  if (items.length === 0) return null;

  return (
    <div className="qmeet-work-context-list-card">
      <div className="qmeet-work-context-card-label">{label}</div>
      <ul className="qmeet-work-context-list">
        {items.map((item, index) => (
          <li key={`${label}-${index}-${item}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function WorkContextSection({
  response,
  loadState,
  errorMessage,
  onRefresh,
}: {
  response: WorkContextResponse | null;
  loadState: LoadState;
  errorMessage: string;
  onRefresh: () => void;
}) {
  const context = response?.activeContext ?? null;

  let content: ReactNode;
  if (loadState === 'error') {
    content = (
      <div className="qmeet-work-context-error">
        {errorMessage || 'The live work context could not be loaded.'}
      </div>
    );
  } else if (!context) {
    content = (
      <div className="qmeet-work-context-empty">
        {loadState === 'loading'
          ? 'Loading the live work context…'
          : response?.message ||
            'No active background context is available yet. Start a focus naturally and QMeet will begin building it.'}
      </div>
    );
  } else {
    content = (
      <>
        <div className="qmeet-work-context-heading">
          <div>
            <div className="qmeet-work-context-kicker">Live Work Context</div>
            <div className="qmeet-work-context-title">{context.title}</div>
            <div className="qmeet-work-context-meta">
              {formatMode(context.mode)} · {formatUpdatedAt(context.updatedAt)}
            </div>
          </div>
          <div className="qmeet-work-context-actions">
            <span className="qmeet-work-context-stage">
              {formatStage(context.stage)}
            </span>
            <button
              className="qmeet-work-context-refresh"
              type="button"
              onClick={onRefresh}
              disabled={loadState === 'loading'}
            >
              {loadState === 'loading' ? 'Refreshing' : 'Refresh'}
            </button>
          </div>
        </div>

        <div className="qmeet-work-context-primary-grid">
          <div className="qmeet-work-context-primary-card">
            <div className="qmeet-work-context-card-label">Goal</div>
            <div className="qmeet-work-context-card-value">
              {context.objective || 'QMeet is still clarifying the goal.'}
            </div>
          </div>
          <div className="qmeet-work-context-primary-card qmeet-work-context-next">
            <div className="qmeet-work-context-card-label">Next action</div>
            <div className="qmeet-work-context-card-value">
              {context.nextAction || 'QMeet is deciding the next useful action.'}
            </div>
          </div>
        </div>

        <div className="qmeet-work-context-detail-grid">
          <ContextListCard label="What QMeet knows" items={context.knownFacts} />
          <ContextListCard label="Constraints" items={context.constraints} />
          <ContextListCard label="Decisions" items={context.decisions} />
          <ContextListCard
            label="Completed and recent progress"
            items={context.recentProgress}
          />
        </div>

        {context.openQuestions.length > 0 && (
          <div className="qmeet-work-context-question">
            <div className="qmeet-work-context-card-label">
              Most useful open question
            </div>
            <div className="qmeet-work-context-card-value">
              {context.openQuestions[0]}
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <section className="panel-section qmeet-work-context-section">
      <WorkContextStyles />
      {!context && loadState !== 'error' && (
        <div className="qmeet-work-context-heading">
          <div>
            <div className="qmeet-work-context-kicker">Live Work Context</div>
            <div className="qmeet-work-context-title">Background focus memory</div>
          </div>
          <button
            className="qmeet-work-context-refresh"
            type="button"
            onClick={onRefresh}
            disabled={loadState === 'loading'}
          >
            {loadState === 'loading' ? 'Refreshing' : 'Refresh'}
          </button>
        </div>
      )}
      {content}
    </section>
  );
}

export function WorkContextMemoryBridge() {
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);
  const [response, setResponse] = useState<WorkContextResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  const apiUrl = useMemo(() => `${getApiBaseUrl()}/api/work-context`, []);

  const refreshContext = useCallback(async () => {
    if (!portalTarget) return;

    setLoadState((current) => (current === 'ready' ? current : 'loading'));
    setErrorMessage('');

    try {
      const result = await fetch(apiUrl, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });

      if (!result.ok) {
        const text = await result.text();
        throw new Error(text || `Work context request failed: ${result.status}`);
      }

      const nextResponse = normalizeResponse(await result.json());
      setResponse(nextResponse);
      setLoadState('ready');

      window.dispatchEvent(
        new CustomEvent(WORK_CONTEXT_STATE_EVENT, {
          detail: nextResponse,
        }),
      );
    } catch (error) {
      setLoadState('error');
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'The live work context could not be loaded.',
      );
    }
  }, [apiUrl, portalTarget]);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    const updatePortalTarget = () => {
      const nextTarget = ensurePortalTarget();
      setPortalTarget((currentTarget) =>
        currentTarget === nextTarget ? currentTarget : nextTarget,
      );
    };

    updatePortalTarget();
    const observer = new MutationObserver(updatePortalTarget);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!portalTarget) {
      setResponse(null);
      setLoadState('idle');
      setErrorMessage('');
      return;
    }

    void refreshContext();
    const intervalId = window.setInterval(() => {
      void refreshContext();
    }, POLL_INTERVAL_MS);

    const handleSessionChange = () => {
      window.setTimeout(() => void refreshContext(), 120);
    };

    window.addEventListener(ACTIVE_SESSION_STATE_EVENT, handleSessionChange);
    window.addEventListener('focus', handleSessionChange);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener(ACTIVE_SESSION_STATE_EVENT, handleSessionChange);
      window.removeEventListener('focus', handleSessionChange);
    };
  }, [portalTarget, refreshContext]);

  if (!portalTarget) return null;

  return createPortal(
    <WorkContextSection
      response={response}
      loadState={loadState}
      errorMessage={errorMessage}
      onRefresh={() => void refreshContext()}
    />,
    portalTarget,
  );
}
