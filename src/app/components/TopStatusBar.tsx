import { useState, useEffect } from 'react';
import { OrbState, BackendStatus } from '../types';

interface TopStatusBarProps {
  orbState: OrbState;
  chatActive: boolean;
  onEnd: () => void;
  backendStatus: BackendStatus | null;
}

export function TopStatusBar({ orbState, chatActive, onEnd, backendStatus }: TopStatusBarProps) {
  const [time, setTime] = useState(() => new Date());

  useEffect(() => {
    const ticker = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(ticker);
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
      <div className="status-left">
        <span className="status-logo">QMeet</span>
        <span className="status-divider">|</span>
        <span className={`status-state state-${orbState}`}>
          {stateLabel[orbState]}
        </span>
      </div>
      <div className="status-right">
        <span className="status-time">
          {time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
        {chatActive && (
          <button className="end-btn" onClick={onEnd} aria-label="End conversation">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
              strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
            End
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
