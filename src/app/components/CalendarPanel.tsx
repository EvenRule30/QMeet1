type CalendarView = 'today' | 'tomorrow';

interface CalendarPanelProps {
  view: CalendarView;
  onViewChange: (view: CalendarView) => void;
  onClose: () => void;
}

function formatPanelDate(view: CalendarView): string {
  const date = new Date();
  if (view === 'tomorrow') {
    date.setDate(date.getDate() + 1);
  }

  return date.toLocaleDateString([], {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatCompactDate(view: CalendarView): string {
  const date = new Date();
  if (view === 'tomorrow') {
    date.setDate(date.getDate() + 1);
  }

  return date.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
  });
}

export function CalendarPanel({ view, onViewChange, onClose }: CalendarPanelProps) {
  const title = view === 'today' ? "Today's Calendar" : "Tomorrow's Calendar";

  return (
    <div className="panel-overlay">
      <div className="panel-content calendar-panel">
        <div className="panel-header">{title}</div>

        <div className="panel-body calendar-panel-body">
          <div className="calendar-hero">
            <div>
              <div className="calendar-kicker">{view === 'today' ? 'Today' : 'Tomorrow'}</div>
              <div className="calendar-date">{formatPanelDate(view)}</div>
            </div>
            <div className="calendar-date-chip">{formatCompactDate(view)}</div>
          </div>

          <div className="panel-action-row">
            <button
              className={`panel-action-btn ${view === 'today' ? 'panel-action-btn-active' : ''}`}
              onClick={() => onViewChange('today')}
            >
              Today
            </button>
            <button
              className={`panel-action-btn ${view === 'tomorrow' ? 'panel-action-btn-active' : ''}`}
              onClick={() => onViewChange('tomorrow')}
            >
              Tomorrow
            </button>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Agenda</div>
            <div className="calendar-agenda">
              <div className="calendar-agenda-item">
                <span className="calendar-agenda-time">—</span>
                <span className="calendar-agenda-text">No connected calendar yet.</span>
              </div>
              <div className="calendar-agenda-item">
                <span className="calendar-agenda-time">Later</span>
                <span className="calendar-agenda-text">Google Calendar or local schedule integration can be added in a future phase.</span>
              </div>
            </div>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Supported Commands</div>
            <p className="panel-section-text">
              Say “open calendar,” “today,” “tomorrow,” “close calendar,” or “go home.”
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
