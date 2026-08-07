import { useState, useEffect } from 'react';

import { AssistantActivity, OrbState, BackendStatus } from '../types';

interface TopStatusBarProps {
  orbState: OrbState;
  chatActive: boolean;
  onEnd: () => void;
  backendStatus: BackendStatus | null;
  activity?: AssistantActivity | null;
}

interface ActiveFocusSessionSnapshot {
  id?: string;
  title?: string;
  mode?: string;
  goal?: string;
  summary?: string | null;
}
const ACTIVE_SESSION_STORAGE_KEYS = [
  'qmeet-active-session-live',
  'qmeet-active-session',
];

function parseStoredSession(value: string | null): ActiveFocusSessionSnapshot | null {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    return normalizeSessionSnapshot(parsed);
  } catch {
    return null;
  }
}
function normalizeSessionSnapshot(value: unknown): ActiveFocusSessionSnapshot | null {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const maybeWrapped = value as {
    activeSession?: unknown;
    session?: unknown;
    id?: unknown;
    title?: unknown;
    mode?: unknown;
    goal?: unknown;
    summary?: unknown;
  };

  if ('activeSession' in maybeWrapped) {
    return normalizeSessionSnapshot(maybeWrapped.activeSession);
  }
  if ('session' in maybeWrapped) {
    return normalizeSessionSnapshot(maybeWrapped.session);
  }
  const title = typeof maybeWrapped.title === 'string' ? maybeWrapped.title.trim() : '';
  const goal = typeof maybeWrapped.goal === 'string' ? maybeWrapped.goal.trim() : '';
  const mode = typeof maybeWrapped.mode === 'string' ? maybeWrapped.mode.trim() : '';
  const summary = typeof maybeWrapped.summary === 'string' ? maybeWrapped.summary.trim() : null;
  const id = typeof maybeWrapped.id === 'string' ? maybeWrapped.id.trim() : undefined;

  if (!title && !goal && !mode && !id) {
    return null;
  }
  return {
    id,
    title,
    mode,
    goal,
    summary,
  };
}

function readStoredFocusSession(): ActiveFocusSessionSnapshot | null {
  if (typeof window === 'undefined') {
    return null;
  }

  for (const key of ACTIVE_SESSION_STORAGE_KEYS) {
    const sessionValue = parseStoredSession(window.sessionStorage.getItem(key));
    if (sessionValue) {
      return sessionValue;
    }
  }
  for (const key of ACTIVE_SESSION_STORAGE_KEYS) {
    const localValue = parseStoredSession(window.localStorage.getItem(key));
    if (localValue) {
      return localValue;
    }
  }

  return null;
}

function formatMode(mode?: string): string {
  if (!mode) {
    return '';
  }

  return mode.charAt(0).toUpperCase() + mode.slice(1).toLowerCase();
}
function formatFocusLabel(session: ActiveFocusSessionSnapshot): string {
  const mode = formatMode(session.mode);
  const title = session.title?.trim();
  const goal = session.goal?.trim();

  if (mode && title) {
    return `${mode}: ${title}`;
  }

  if (title) {
    return title;
  }

  if (goal) {
    return goal;
  }

  if (mode) {
    return `${mode} focus`;
  }

  return 'Active focus';
}

function dispatchPromptCommand(command: string): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent('qmeet-prompt-command', {
      detail: { command },
    }),
  );
}
function FocusStatusStyles() {
  return (
    <style>{`
      .status-focus-chip {
        display: inline-flex;
        align-items: center;
        min-width: 0;
        max-width: min(34vw, 360px);
        gap: 0.42rem;
        border: 1px solid rgba(103, 232, 249, 0.22);
        border-radius: 999px;
        background: rgba(6, 18, 28, 0.52);
        color: rgba(221, 253, 255, 0.9);
        padding: 0.18rem 0.58rem;
        cursor: pointer;
        font: inherit;
        transition: border-color 160ms ease, background 160ms ease, box-shadow 160ms ease, transform 160ms ease;
      }
      .status-focus-chip:hover,
      .status-focus-chip:focus-visible {
        border-color: rgba(103, 232, 249, 0.42);
        background: rgba(10, 31, 44, 0.78);
        box-shadow: 0 0 18px rgba(34, 211, 238, 0.12);
        transform: translateY(-1px);
        outline: none;
      }
      .status-focus-dot {
        width: 0.42rem;
        height: 0.42rem;
        border-radius: 999px;
        background: rgba(45, 212, 191, 0.95);
        box-shadow: 0 0 10px rgba(45, 212, 191, 0.6);
        flex: 0 0 auto;
      }

      .status-focus-text {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 0.72rem;
        letter-spacing: 0.04em;
        text-transform: none;
      }
      @media (max-width: 720px) {
        .status-focus-chip {
          max-width: 38vw;
          padding-inline: 0.46rem;
        }

        .status-focus-text {
          font-size: 0.66rem;
        }
      }
    `}</style>
  );
}

function formatFocusTitle(session: ActiveFocusSessionSnapshot): string {
  const lines = ['Current focus'];
  const mode = formatMode(session.mode);

  if (session.title) {
    lines.push(`Title: ${session.title}`);
  }

  if (mode) {
    lines.push(`Mode: ${mode}`);
  }
  if (session.goal) {
    lines.push(`Goal: ${session.goal}`);
  }

  if (session.summary) {
    lines.push(`Summary: ${session.summary}`);
  }

  return lines.join('\n');
}

export function TopStatusBar({ orbState, chatActive, onEnd, backendStatus, activity }: TopStatusBarProps) {
  const [time, setTime] = useState(() => new Date());
  const [activeFocusSession, setActiveFocusSession] = useState<ActiveFocusSessionSnapshot | null>(() =>
    readStoredFocusSession()
  );
  useEffect(() => {
    const ticker = setInterval(() => setTime(new Date()), 1000);

    return () => clearInterval(ticker);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }

    const refreshFocusFromStorage = () => {
      setActiveFocusSession(readStoredFocusSession());
    };

    const handleFocusState = (event: Event) => {
      const detail = (event as CustomEvent<unknown>).detail;
      const nextSession = normalizeSessionSnapshot(detail);
      if (nextSession || detail === null) {
        setActiveFocusSession(nextSession);
        return;
      }

      if (detail && typeof detail === 'object' && 'activeSession' in detail) {
        setActiveFocusSession(null);
        return;
      }

      refreshFocusFromStorage();
    };

    const handleFocusCommand = () => {
      window.setTimeout(refreshFocusFromStorage, 0);
    };
    const handleStorage = (event: StorageEvent) => {
      if (event.key && ACTIVE_SESSION_STORAGE_KEYS.includes(event.key)) {
        refreshFocusFromStorage();
      }
    };

    window.addEventListener('qmeet-active-session-state', handleFocusState as EventListener);
    window.addEventListener('qmeet-active-session-command', handleFocusCommand as EventListener);
    window.addEventListener('storage', handleStorage);

    refreshFocusFromStorage();
    return () => {
      window.removeEventListener('qmeet-active-session-state', handleFocusState as EventListener);
      window.removeEventListener('qmeet-active-session-command', handleFocusCommand as EventListener);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  const stateLabel: Record<OrbState, string> = {
    idle: 'Idle',
    listening: 'Listening',
    thinking: 'Processing',
    speaking: 'Responding',
    error: 'Error',
  };
  const isConnected = backendStatus !== null;
  const statusText = isConnected
    ? `${backendStatus.provider} / ${backendStatus.model}`
    : 'Disconnected';
  return (
    <div className="status-bar">
      <FocusStatusStyles />
      <div className="status-left">
        <span className="status-logo">QMeet</span>
        <span className="status-divider">|</span>
        <span className={`status-state state-${orbState}`}>
          {stateLabel[orbState]}
        </span>
        {activity && (
          <>
            <span className="status-divider status-activity-divider">|</span>
            <span className={`status-activity status-activity-${activity.kind}`}>
              {activity.label}
            </span>
          </>
        )}
        {activeFocusSession && (
          <>
            <span className="status-divider status-focus-divider">|</span>
            <button
              className="status-focus-chip"
              type="button"
              title={`${formatFocusTitle(activeFocusSession)}\n\nClick to open Memory.`}
              onClick={() => dispatchPromptCommand('open memory')}
            >
              <span className="status-focus-dot" />
              <span className="status-focus-text">
                Focus: {formatFocusLabel(activeFocusSession)}
              </span>
            </button>
          </>
        )}
      </div>
      <div className="status-right">
        <span className="status-time">
          {time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
        {chatActive && (
          <button className="end-btn" onClick={onEnd} aria-label="Close conversation">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
            Close chat
          </button>
        )}
        <div className={`connection-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
          <div className="conn-dot" />
          <span className="conn-label">{statusText}</span>
        </div>
      </div>
    </div>
  );
}
