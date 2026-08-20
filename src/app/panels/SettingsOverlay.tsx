import type { BackendStatus } from '../types';
import './SettingsOverlay.css';

type SpeechOptions = {
  enabled?: boolean;
  rate?: number;
};

type SettingsOverlayProps = {
  backendStatus: BackendStatus | null;
  voiceOutputEnabled: boolean;
  speechRate: number;
  setVoiceOutput: (enabled: boolean) => void;
  speakAssistantText: (text: string, options?: SpeechOptions) => void;
  adjustSpeechRate: (nextRate: number) => number;
  onClose: () => void;
};

function getSpeechRateLabel(rate: number): string {
  if (rate < 0.9) return 'Slower';
  if (rate > 1.1) return 'Faster';
  return 'Natural';
}

export function SettingsOverlay({
  backendStatus,
  voiceOutputEnabled,
  speechRate,
  setVoiceOutput,
  speakAssistantText,
  adjustSpeechRate,
  onClose,
}: SettingsOverlayProps) {
  const backendState = backendStatus === null
    ? 'Checking'
    : backendStatus.ok
      ? 'Connected'
      : 'Disconnected';
  const backendTone = backendStatus === null
    ? 'checking'
    : backendStatus.ok
      ? 'connected'
      : 'disconnected';

  const handleVoiceToggle = () => {
    const nextEnabled = !voiceOutputEnabled;
    setVoiceOutput(nextEnabled);
    if (nextEnabled) {
      speakAssistantText('Voice output enabled.', { enabled: true });
    }
  };

  const handleVoicePreview = () => {
    speakAssistantText('This is how QMeet will sound at the current voice speed.', {
      enabled: true,
      rate: speechRate,
    });
  };

  const handleResetRate = () => {
    const nextRate = adjustSpeechRate(1);
    if (voiceOutputEnabled) {
      speakAssistantText('Voice speed reset to normal.', {
        enabled: true,
        rate: nextRate,
      });
    }
  };

  return (
    <div className="panel-overlay">
      <div className="panel-content settings-panel">
        <div className="panel-header">Settings</div>
        <div className="panel-body settings-panel-body">
          <section className="settings-hero" aria-label="QMeet settings summary">
            <div>
              <div className="settings-kicker">QMeet preferences</div>
              <div className="settings-hero-title">Voice & system</div>
              <div className="settings-hero-copy">
                Adjust how QMeet speaks and review the services powering the assistant.
              </div>
            </div>
            <div className={`settings-health-chip settings-health-chip-${backendTone}`}>
              <span className="settings-health-dot" aria-hidden="true" />
              {backendState}
            </div>
          </section>

          <section className="settings-card" aria-labelledby="settings-voice-title">
            <div className="settings-card-header">
              <div>
                <div className="settings-card-kicker">Assistant voice</div>
                <div className="settings-card-title" id="settings-voice-title">
                  Spoken responses
                </div>
              </div>
              <button
                type="button"
                className={`settings-toggle ${voiceOutputEnabled ? 'settings-toggle-on' : ''}`}
                aria-pressed={voiceOutputEnabled}
                onClick={handleVoiceToggle}
              >
                <span className="settings-toggle-track" aria-hidden="true">
                  <span className="settings-toggle-thumb" />
                </span>
                <span>{voiceOutputEnabled ? 'On' : 'Muted'}</span>
              </button>
            </div>

            <div className="settings-divider" />

            <div className="settings-rate-row">
              <div>
                <div className="settings-control-label">Voice speed</div>
                <div className="settings-control-hint">
                  {getSpeechRateLabel(speechRate)} delivery
                </div>
              </div>
              <div className="settings-rate-value">{speechRate.toFixed(2)}×</div>
            </div>

            <div className="settings-slider-wrap">
              <span className="settings-slider-label">0.75×</span>
              <input
                className="settings-rate-slider"
                type="range"
                min="0.75"
                max="1.35"
                step="0.05"
                value={speechRate}
                aria-label="QMeet voice speed"
                onChange={(event) => {
                  adjustSpeechRate(Number(event.target.value));
                }}
              />
              <span className="settings-slider-label">1.35×</span>
            </div>

            <div className="settings-action-row">
              <button
                type="button"
                className="settings-secondary-btn"
                onClick={handleResetRate}
                disabled={Math.abs(speechRate - 1) < 0.001}
              >
                Reset speed
              </button>
              <button
                type="button"
                className="settings-primary-btn"
                onClick={handleVoicePreview}
                disabled={!voiceOutputEnabled}
              >
                Test voice
              </button>
            </div>

            <div className="settings-footnote">
              Voice preference and speed are saved on this device.
            </div>
          </section>

          <div className="settings-grid">
            <section className="settings-card settings-info-card" aria-labelledby="settings-interface-title">
              <div className="settings-card-kicker">Interface</div>
              <div className="settings-card-title" id="settings-interface-title">
                Tablet display
              </div>
              <div className="settings-detail-list">
                <div className="settings-detail-row">
                  <span>Theme</span>
                  <strong>Dark</strong>
                </div>
                <div className="settings-detail-row">
                  <span>Target</span>
                  <strong>1024×600</strong>
                </div>
                <div className="settings-detail-row">
                  <span>Input</span>
                  <strong>Touch + voice</strong>
                </div>
              </div>
            </section>

            <section className="settings-card settings-info-card" aria-labelledby="settings-backend-title">
              <div className="settings-card-kicker">System</div>
              <div className="settings-card-title" id="settings-backend-title">
                Assistant backend
              </div>
              <div className="settings-detail-list">
                <div className="settings-detail-row">
                  <span>Status</span>
                  <strong className={`settings-status-text settings-status-text-${backendTone}`}>
                    {backendState}
                  </strong>
                </div>
                <div className="settings-detail-row">
                  <span>Provider</span>
                  <strong>{backendStatus?.provider || 'Unknown'}</strong>
                </div>
                <div className="settings-detail-row">
                  <span>Model</span>
                  <strong>{backendStatus?.model || 'Unknown'}</strong>
                </div>
              </div>
            </section>
          </div>

          <button className="close-panel-btn" type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
