import type { BackendStatus, OrbState } from '../types';
import './StatusOverlay.css';

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

function sentenceCase(value: string): string {
  const normalized = value.trim();
  if (!normalized) return 'Unknown';
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function cleanDiagnosticValue(value: string): string {
  const normalized = value.trim();
  if (!normalized || normalized === 'None' || normalized === 'Not used') {
    return 'None';
  }
  return normalized;
}

export function StatusOverlay({
  activePanelLabel,
  backendStatus,
  orbState,
  voiceInputSupported,
  lastHeardTranscript,
  lastNormalizedTranscript: _lastNormalizedTranscript,
  lastLocalCommand,
  lastInputRoute,
  lastInterpreterAction: _lastInterpreterAction,
  lastInterpreterFrontendCommand: _lastInterpreterFrontendCommand,
  interpreterConfidenceLabel: _interpreterConfidenceLabel,
  interpreterReasonLabel: _interpreterReasonLabel,
  pendingInterpreterLabel,
  voiceOutputEnabled,
  speechRate,
  chatActive,
  messagesCount: _messagesCount,
  statusNotesCount,
  statusOpenTasksCount,
  statusCompletedTasksCount,
  memorySyncState,
  calendarEventsCount: _calendarEventsCount,
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
  const backendOnline = Boolean(backendStatus?.ok);
  const pendingAction = cleanDiagnosticValue(pendingInterpreterLabel);
  const lastRoute = cleanDiagnosticValue(lastInputRoute);
  const lastCommand = cleanDiagnosticValue(lastLocalCommand);
  const lastHeard = lastHeardTranscript.trim();
  const calendarBusy = googleCalendarLoading ? 'Refreshing' : statusGoogleCalendarLabel;
  const voiceState = voiceOutputEnabled ? 'Ready' : 'Muted';

  return (
    <div className="panel-overlay">
      <div className="panel-content panel-content-status status-remaster-panel">
        <div className="panel-header">Status</div>

        <div className="panel-body status-remaster-body">
          <section className="status-remaster-hero">
            <div className="status-remaster-hero-copy">
              <div className="status-remaster-kicker">QMeet system</div>
              <div className="status-remaster-title">
                {backendOnline ? 'Ready to help' : 'Backend unavailable'}
              </div>
              <div className="status-remaster-subtitle">
                {statusDateLabel} · {statusTimeLabel}
              </div>
            </div>
            <div
              className={`status-remaster-health ${
                backendOnline
                  ? 'status-remaster-health-good'
                  : 'status-remaster-health-warn'
              }`}
            >
              <span className="status-remaster-health-dot" />
              {backendOnline ? 'Online' : 'Offline'}
            </div>
          </section>

          <section className="status-remaster-section">
            <div className="status-remaster-section-header">
              <div>
                <div className="status-remaster-section-kicker">System</div>
                <div className="status-remaster-section-title">At a glance</div>
              </div>
              <div className="status-remaster-section-note">
                {chatActive ? 'Conversation active' : 'Standing by'}
              </div>
            </div>

            <div className="status-remaster-grid">
              <div className="status-remaster-card">
                <div className="status-remaster-card-label">QMeet</div>
                <div className="status-remaster-card-value">
                  {sentenceCase(orbState)}
                </div>
                <div className="status-remaster-card-meta">
                  {activePanelLabel === 'None'
                    ? 'Home interface'
                    : `${activePanelLabel} panel open`}
                </div>
              </div>

              <div
                className={`status-remaster-card ${
                  backendOnline
                    ? 'status-remaster-card-good'
                    : 'status-remaster-card-warn'
                }`}
              >
                <div className="status-remaster-card-label">Backend</div>
                <div className="status-remaster-card-value">
                  {backendOnline ? 'Connected' : 'Disconnected'}
                </div>
                <div className="status-remaster-card-meta">
                  {backendStatus?.provider || 'Unknown provider'}
                  {backendStatus?.model ? ` · ${backendStatus.model}` : ''}
                </div>
              </div>

              <div className="status-remaster-card">
                <div className="status-remaster-card-label">Voice</div>
                <div className="status-remaster-card-value">{voiceState}</div>
                <div className="status-remaster-card-meta">
                  {voiceInputSupported ? 'Mic supported' : 'Mic unavailable'} ·{' '}
                  {speechRate.toFixed(2)}×
                </div>
              </div>

              <div className="status-remaster-card">
                <div className="status-remaster-card-label">Calendar</div>
                <div className="status-remaster-card-value">{calendarBusy}</div>
                <div className="status-remaster-card-meta">
                  Today {statusTodayEventsCount} · Tomorrow {statusTomorrowEventsCount}
                  {statusGoogleEventsCount > 0
                    ? ` · ${statusGoogleEventsCount} Google loaded`
                    : ''}
                </div>
              </div>
            </div>
          </section>

          <section className="status-remaster-section">
            <div className="status-remaster-section-header">
              <div>
                <div className="status-remaster-section-kicker">Workspace</div>
                <div className="status-remaster-section-title">What QMeet is holding</div>
              </div>
              <div className="status-remaster-section-note">{memorySyncState}</div>
            </div>

            <div className="status-remaster-workspace">
              <div className="status-remaster-stat">
                <span className="status-remaster-stat-value">{statusOpenTasksCount}</span>
                <span className="status-remaster-stat-label">Open tasks</span>
                <span className="status-remaster-stat-meta">
                  {statusCompletedTasksCount} completed
                </span>
              </div>
              <div className="status-remaster-stat">
                <span className="status-remaster-stat-value">{statusNotesCount}</span>
                <span className="status-remaster-stat-label">Notes</span>
                <span className="status-remaster-stat-meta">Saved context</span>
              </div>
              <div className="status-remaster-stat status-remaster-stat-wide">
                <span className="status-remaster-stat-label">Search</span>
                <span className="status-remaster-stat-inline-value">
                  {searchStatusLabel}
                </span>
                <span className="status-remaster-stat-meta status-remaster-ellipsis">
                  {searchStatusMeta || 'No active search'}
                </span>
              </div>
            </div>
          </section>

          <section className="status-remaster-section status-remaster-activity-section">
            <div className="status-remaster-section-header">
              <div>
                <div className="status-remaster-section-kicker">Recent activity</div>
                <div className="status-remaster-section-title">Last interaction</div>
              </div>
              {pendingAction !== 'None' && (
                <div className="status-remaster-pending-chip">Awaiting confirmation</div>
              )}
            </div>

            <div className="status-remaster-activity-list">
              <div className="status-remaster-activity-row">
                <span>Last heard</span>
                <strong>{lastHeard || 'No voice input yet'}</strong>
              </div>
              <div className="status-remaster-activity-row">
                <span>Last route</span>
                <strong>{lastRoute}</strong>
              </div>
              <div className="status-remaster-activity-row">
                <span>Last command</span>
                <strong>{lastCommand}</strong>
              </div>
              {pendingAction !== 'None' && (
                <div className="status-remaster-activity-row status-remaster-activity-pending">
                  <span>Pending</span>
                  <strong>{pendingAction}</strong>
                </div>
              )}
            </div>
          </section>

          <button className="close-panel-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
