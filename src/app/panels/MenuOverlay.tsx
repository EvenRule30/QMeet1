import type { ActivePanel } from '../types';

const BRIEF_ME_EVENT = 'qmeet:brief-me';

type MenuOverlayProps = {
  openLauncherPanel: (panel: ActivePanel) => void;
  onClose: () => void;
};

export function MenuOverlay({ openLauncherPanel, onClose }: MenuOverlayProps) {
  const handleBriefMe = () => {
    onClose();
    window.dispatchEvent(new Event(BRIEF_ME_EVENT));
  };

  return (
    <div className="panel-overlay">
      <div className="panel-content panel-content-launcher">
        <div className="panel-header">Menu</div>

        <div className="panel-body">
          <div className="launcher-intro">
            <p className="panel-section-text">
              Choose a QMeet tool by touch, or use the same commands by voice.
            </p>
          </div>

          <div className="launcher-grid" aria-label="QMeet app launcher">
            <button
              type="button"
              className="launcher-card"
              onClick={handleBriefMe}
            >
              <span className="launcher-title">Brief Me</span>
              <span className="launcher-description">
                Start a daily briefing using calendar events, tasks, notes, and recent work.
              </span>
              <span className="launcher-command">Shortcut: brief me</span>
            </button>

            <button
              type="button"
              className="launcher-card"
              onClick={() => openLauncherPanel('notes')}
            >
              <span className="launcher-title">Notes</span>
              <span className="launcher-description">Write and review local notes.</span>
              <span className="launcher-command">Say: open notes</span>
            </button>

            <button
              type="button"
              className="launcher-card"
              onClick={() => openLauncherPanel('memory')}
            >
              <span className="launcher-title">Memory</span>
              <span className="launcher-description">Review tasks and recent work.</span>
              <span className="launcher-command">Say: what was I working on</span>
            </button>

            <button
              type="button"
              className="launcher-card"
              onClick={() => openLauncherPanel('calendar')}
            >
              <span className="launcher-title">Calendar</span>
              <span className="launcher-description">
                View Google Calendar and local events.
              </span>
              <span className="launcher-command">Say: open calendar</span>
            </button>

            <button
              type="button"
              className="launcher-card"
              onClick={() => openLauncherPanel('search')}
            >
              <span className="launcher-title">Search</span>
              <span className="launcher-description">
                Search the web and review result sources.
              </span>
              <span className="launcher-command">Say: open search</span>
            </button>

            <button
              type="button"
              className="launcher-card"
              onClick={() => openLauncherPanel('settings')}
            >
              <span className="launcher-title">Settings</span>
              <span className="launcher-description">
                Adjust voice output and interface options.
              </span>
              <span className="launcher-command">Say: show settings</span>
            </button>

            <button
              type="button"
              className="launcher-card"
              onClick={() => openLauncherPanel('status')}
            >
              <span className="launcher-title">Status</span>
              <span className="launcher-description">
                Check orb, backend, calendar, memory, and voice state.
              </span>
              <span className="launcher-command">Say: show status</span>
            </button>
          </div>

          <div className="panel-section launcher-help-section">
            <div className="panel-section-title">Quick Commands</div>
            <p className="panel-section-text">
              Try &quot;brief me&quot;, &quot;start my day&quot;,
              &quot;what was I working on&quot;, &quot;note that buy milk&quot;,
              &quot;search for kiosk mode&quot;, &quot;what&apos;s on my calendar&quot;,
              &quot;go home&quot;, or &quot;mute voice&quot;.
            </p>
          </div>

          <button
            type="button"
            className="close-panel-btn"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
