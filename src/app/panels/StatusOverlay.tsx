import type { BackendStatus, OrbState } from '../types';

type StatusOverlayProps = {
  activePanelLabel: string;
  backendStatus: BackendStatus | null;
  orbState: OrbState;
  voiceInputSupported: boolean;
  lastHeardTranscript: string;
  lastNormalizedTranscript: string;
  lastLocalCommand: string;
  lastInputRoute: string;
  lastInterpreterAction: string;
  lastInterpreterFrontendCommand: string;
  interpreterConfidenceLabel: string;
  interpreterReasonLabel: string;
  pendingInterpreterLabel: string;
  voiceOutputEnabled: boolean;
  speechRate: number;
  chatActive: boolean;
  messagesCount: number;
  statusNotesCount: number;
  statusOpenTasksCount: number;
  statusCompletedTasksCount: number;
  memorySyncState: string;
  calendarEventsCount: number;
  statusTodayEventsCount: number;
  statusTomorrowEventsCount: number;
  statusGoogleCalendarLabel: string;
  statusGoogleEventsCount: number;
  googleCalendarLoading: boolean;
  searchStatusLabel: string;
  searchStatusMeta: string;
  statusDateLabel: string;
  statusTimeLabel: string;
  onClose: () => void;
};

export function StatusOverlay({
  activePanelLabel,
  backendStatus,
  orbState,
  voiceInputSupported,
  lastHeardTranscript,
  lastNormalizedTranscript,
  lastLocalCommand,
  lastInputRoute,
  lastInterpreterAction,
  lastInterpreterFrontendCommand,
  interpreterConfidenceLabel,
  interpreterReasonLabel,
  pendingInterpreterLabel,
  voiceOutputEnabled,
  speechRate,
  chatActive,
  messagesCount,
  statusNotesCount,
  statusOpenTasksCount,
  statusCompletedTasksCount,
  memorySyncState,
  calendarEventsCount,
  statusTodayEventsCount,
  statusTomorrowEventsCount,
  statusGoogleCalendarLabel,
  statusGoogleEventsCount,
  googleCalendarLoading,
  searchStatusLabel,
  searchStatusMeta,
  statusDateLabel,
  statusTimeLabel,
  onClose,
}: StatusOverlayProps) {
  return (
    <div className="panel-overlay">
      <div className="panel-content panel-content-status">
        <div className="panel-header">System Status</div>
        <div className="panel-body status-panel-body">
          <div className="status-hero">
            <div>
              <div className="status-kicker">QMeet Prototype</div>
              <div className="status-title">Local tablet assistant dashboard</div>
            </div>
            <div className={`status-health-chip ${backendStatus?.ok ? 'status-health-good' : 'status-health-warn'}`}>
              {backendStatus?.ok ? 'Online' : 'Offline'}
            </div>
          </div>

          <div className="status-grid">
            <div className="status-card">
              <div className="status-card-title">Orb</div>
              <div className="status-card-value">{orbState.charAt(0).toUpperCase() + orbState.slice(1)}</div>
              <div className="status-card-meta">Current interaction state</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Active Panel</div>
              <div className="status-card-value">{activePanelLabel}</div>
              <div className="status-card-meta">Current UI surface</div>
            </div>

            <div className={`status-card ${backendStatus?.ok ? 'status-card-good' : 'status-card-warn'}`}>
              <div className="status-card-title">Backend</div>
              <div className="status-card-value">{backendStatus?.ok ? 'Connected' : 'Disconnected'}</div>
              <div className="status-card-meta">FastAPI agent service</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Provider</div>
              <div className="status-card-value">{backendStatus?.provider || 'Unknown'}</div>
              <div className="status-card-meta">Model: {backendStatus?.model || 'Unknown'}</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Voice Input</div>
              <div className="status-card-value">{voiceInputSupported ? 'Supported' : 'Unavailable'}</div>
              <div className="status-card-meta">Browser speech recognition</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Last Heard</div>
              <div className="status-card-value">{lastHeardTranscript || 'None'}</div>
              <div className="status-card-meta">{lastNormalizedTranscript ? `Normalized: ${lastNormalizedTranscript}` : 'Last voice transcript'}</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Last Command</div>
              <div className="status-card-value">{lastLocalCommand}</div>
              <div className="status-card-meta">Last local command matched</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Input Route</div>
              <div className="status-card-value">{lastInputRoute}</div>
              <div className="status-card-meta">Exact parser, interpreter, or chat</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Interpreter</div>
              <div className="status-card-value">{lastInterpreterAction}</div>
              <div className="status-card-meta">Confidence: {interpreterConfidenceLabel}</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Mapped Command</div>
              <div className="status-card-value">{lastInterpreterFrontendCommand}</div>
              <div className="status-card-meta">{interpreterReasonLabel}</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Pending Confirm</div>
              <div className="status-card-value">{pendingInterpreterLabel}</div>
              <div className="status-card-meta">Destructive fuzzy commands wait for confirm</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Voice Output</div>
              <div className="status-card-value">{voiceOutputEnabled ? 'On' : 'Muted'}</div>
              <div className="status-card-meta">Speed: {speechRate.toFixed(2)}×</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Chat</div>
              <div className="status-card-value">{chatActive ? 'Active' : 'Idle'}</div>
              <div className="status-card-meta">Messages: {messagesCount}</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Notes</div>
              <div className="status-card-value">{statusNotesCount}</div>
              <div className="status-card-meta">Saved locally</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Open Tasks</div>
              <div className="status-card-value">{statusOpenTasksCount}</div>
              <div className="status-card-meta">{statusCompletedTasksCount} completed · {memorySyncState}</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Calendar</div>
              <div className="status-card-value">{calendarEventsCount}</div>
              <div className="status-card-meta">Local events total</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Today</div>
              <div className="status-card-value">{statusTodayEventsCount}</div>
              <div className="status-card-meta">Events saved for today</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Tomorrow</div>
              <div className="status-card-value">{statusTomorrowEventsCount}</div>
              <div className="status-card-meta">Events saved for tomorrow</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Google Calendar</div>
              <div className="status-card-value">{statusGoogleCalendarLabel}</div>
              <div className="status-card-meta">{statusGoogleEventsCount} loaded · {googleCalendarLoading ? 'Loading' : 'Idle'}</div>
            </div>

            <div className="status-card">
              <div className="status-card-title">Search</div>
              <div className="status-card-value">{searchStatusLabel}</div>
              <div className="status-card-meta">{searchStatusMeta}</div>
            </div>
          </div>

          <div className="panel-section status-detail-section">
            <div className="panel-section-title">Backend Details</div>
            <div className="status-detail-list">
              <div className="status-detail-row">
                <span>OpenAI key</span>
                <strong>{backendStatus?.hasOpenAIKey ? 'Configured' : 'Missing / Unknown'}</strong>
              </div>
              <div className="status-detail-row">
                <span>Max output tokens</span>
                <strong>{backendStatus?.maxOutputTokens ?? 'Unknown'}</strong>
              </div>
              <div className="status-detail-row">
                <span>Status refresh</span>
                <strong>Every 10 seconds</strong>
              </div>
            </div>
          </div>

          <div className="panel-section status-detail-section">
            <div className="panel-section-title">Interface</div>
            <div className="status-detail-list">
              <div className="status-detail-row">
                <span>Date</span>
                <strong>{statusDateLabel}</strong>
              </div>
              <div className="status-detail-row">
                <span>Time snapshot</span>
                <strong>{statusTimeLabel}</strong>
              </div>
              <div className="status-detail-row">
                <span>Display target</span>
                <strong>1024×600</strong>
              </div>
            </div>
          </div>

          <div className="panel-section status-detail-section">
            <div className="panel-section-title">Local Storage</div>
            <div className="status-detail-list">
              <div className="status-detail-row">
                <span>Voice output preference</span>
                <strong>Saved</strong>
              </div>
              <div className="status-detail-row">
                <span>Voice speed preference</span>
                <strong>Saved</strong>
              </div>
              <div className="status-detail-row">
                <span>Notes and calendar events</span>
                <strong>Saved locally</strong>
              </div>
            </div>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Supported Status Commands</div>
            <p className="panel-section-text">
              Say “show status,” “system status,” “diagnostics,” “what did you hear,” “read my notes,” “what was I working on,” “what's on my calendar,” “close status,” or “go home.” This panel also shows whether the last input used the exact parser, fuzzy command interpreter, or normal chat.
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
