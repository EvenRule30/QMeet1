import type { BackendStatus } from '../types';

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

export function SettingsOverlay({
  backendStatus,
  voiceOutputEnabled,
  speechRate,
  setVoiceOutput,
  speakAssistantText,
  adjustSpeechRate,
  onClose,
}: SettingsOverlayProps) {
  return (
    <div className="panel-overlay">
      <div className="panel-content">
        <div className="panel-header">Settings</div>
        <div className="panel-body">
          <div className="panel-section">
            <div className="panel-section-title">Voice Settings</div>
            <p className="panel-section-text">
              Microphone: Enabled · Language: English (US) · Recognition: Online · Voice preferences persist across reloads
            </p>
            <div className="settings-control-row">
              <span className="settings-control-label">Spoken responses</span>
              <button
                className={`panel-action-btn ${voiceOutputEnabled ? 'panel-action-btn-active' : ''}`}
                onClick={() => {
                  const nextEnabled = !voiceOutputEnabled;
                  setVoiceOutput(nextEnabled);
                  if (nextEnabled) {
                    speakAssistantText('Voice output enabled.', { enabled: true });
                  }
                }}
              >
                {voiceOutputEnabled ? 'On' : 'Muted'}
              </button>
            </div>
            <div className="settings-control-row">
              <span className="settings-control-label">Voice speed</span>
              <span className="settings-control-value">{speechRate.toFixed(2)}×</span>
            </div>
            <div className="panel-action-row">
              <button
                className="panel-action-btn"
                onClick={() => {
                  const nextRate = adjustSpeechRate(speechRate - 0.15);
                  speakAssistantText(`Voice speed is now ${nextRate.toFixed(2)}×.`, { rate: nextRate });
                }}
              >
                Slower
              </button>
              <button
                className="panel-action-btn"
                onClick={() => {
                  const nextRate = adjustSpeechRate(1);
                  speakAssistantText('Voice speed reset to normal.', { rate: nextRate });
                }}
              >
                Normal
              </button>
              <button
                className="panel-action-btn"
                onClick={() => {
                  const nextRate = adjustSpeechRate(speechRate + 0.15);
                  speakAssistantText(`Voice speed is now ${nextRate.toFixed(2)}×.`, { rate: nextRate });
                }}
              >
                Faster
              </button>
            </div>
          </div>
          <div className="panel-section">
            <div className="panel-section-title">Display</div>
            <p className="panel-section-text">
              Theme: Dark · Resolution: 1024×600 · Interface: Optimized
            </p>
          </div>
          <div className="panel-section">
            <div className="panel-section-title">Backend</div>
            <p className="panel-section-text">
              Status: {backendStatus?.ok ? 'Connected' : 'Disconnected'} · Provider: {backendStatus?.provider || 'Unknown'}
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
