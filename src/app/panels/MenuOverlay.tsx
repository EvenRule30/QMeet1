import type { ActivePanel } from '../types';

type MenuOverlayProps = {
  openLauncherPanel: (panel: ActivePanel) => void;
  onClose: () => void;
};

export function MenuOverlay({ openLauncherPanel, onClose }: MenuOverlayProps) {
  return (
    <div className="panel-overlay">
      <div className="panel-content panel-content-launcher">
        <div className="panel-header">Menu</div>
        <div className="panel-body">
          <div className="launcher-intro">
            <p className="panel-section-text">
              Choose a local QMeet tool by touch, or use the same commands by voice.
            </p>
          </div>

          <div className="launcher-grid" aria-label="QMeet app launcher">
            <button className="launcher-card" onClick={() => openLauncherPanel('notes')}>
              <span className="launcher-title">Notes</span>
              <span className="launcher-description">Write and review local notes.</span>
              <span className="launcher-command">Say: open notes</span>
            </button>

            <button className="launcher-card" onClick={() => openLauncherPanel('memory')}>
              <span className="launcher-title">Memory</span>
              <span className="launcher-description">Review tasks and recent work.</span>
              <span className="launcher-command">Say: what was I working on</span>
            </button>

            <button className="launcher-card" onClick={() => openLauncherPanel('calendar')}>
              <span className="launcher-title">Calendar</span>
              <span className="launcher-description">View today or tomorrow placeholders.</span>
              <span className="launcher-command">Say: open calendar</span>
            </button>

            <button className="launcher-card" onClick={() => openLauncherPanel('search')}>
              <span className="launcher-title">Search</span>
              <span className="launcher-description">Open the local search/browser shell.</span>
              <span className="launcher-command">Say: open search</span>
            </button>

            <button className="launcher-card" onClick={() => openLauncherPanel('settings')}>
              <span className="launcher-title">Settings</span>
              <span className="launcher-description">Adjust voice output and interface options.</span>
              <span className="launcher-command">Say: show settings</span>
            </button>

            <button className="launcher-card" onClick={() => openLauncherPanel('status')}>
              <span className="launcher-title">Status</span>
              <span className="launcher-description">Check orb, backend, and voice state.</span>
              <span className="launcher-command">Say: show status</span>
            </button>
          </div>

          <div className="panel-section launcher-help-section">
            <div className="panel-section-title">Quick Commands</div>
            <p className="panel-section-text">
              Try "what can you do", "note that buy milk", "remember to test the Pi as a task", "what was I working on", "search for kiosk mode", "add event tomorrow at 3 called meeting", "what's on my calendar", "what did you hear", "cancel", "go home", or "mute voice".
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
