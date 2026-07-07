import { CalendarEvent } from '../types';

type CalendarView = 'today' | 'tomorrow';

interface CalendarPanelProps {
  view: CalendarView;
  events: CalendarEvent[];
  onViewChange: (view: CalendarView) => void;
  onDeleteEvent: (eventId: string) => void;
  onClose: () => void;
}

function getDateForView(view: CalendarView): Date {
  const date = new Date();

  if (view === 'tomorrow') {
    date.setDate(date.getDate() + 1);
  }

  return date;
}

function getLocalDateKeyForView(view: CalendarView): string {
  const date = getDateForView(view);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');

  return `${year}-${month}-${day}`;
}

function getLegacyUtcDateKeyForView(view: CalendarView): string {
  return getDateForView(view).toISOString().slice(0, 10);
}

function getAcceptedDateKeysForView(view: CalendarView): Set<string> {
  return new Set([
    getLocalDateKeyForView(view),
    getLegacyUtcDateKeyForView(view),
  ]);
}

function formatPanelDate(view: CalendarView): string {
  return getDateForView(view).toLocaleDateString([], {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatCompactDate(view: CalendarView): string {
  return getDateForView(view).toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
  });
}

function formatEventCreatedAt(createdAt: string): string {
  const date = new Date(createdAt);

  if (Number.isNaN(date.getTime())) {
    return 'Local event';
  }

  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function CalendarPanel({ view, events, onViewChange, onDeleteEvent, onClose }: CalendarPanelProps) {
  const title = view === 'today' ? "Today's Calendar" : "Tomorrow's Calendar";
  const acceptedDateKeys = getAcceptedDateKeysForView(view);
  const visibleEvents = events.filter((event) => acceptedDateKeys.has(event.dateKey));

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
            <div className="panel-section-title">Local Agenda</div>
            <div className="calendar-agenda">
              {visibleEvents.length === 0 ? (
                <>
                  <div className="calendar-agenda-item">
                    <span className="calendar-agenda-time">—</span>
                    <span className="calendar-agenda-text">
                      No local events saved for {view === 'today' ? 'today' : 'tomorrow'}.
                    </span>
                  </div>
                  <div className="calendar-agenda-item">
                    <span className="calendar-agenda-time">Later</span>
                    <span className="calendar-agenda-text">
                      Google Calendar integration can be added in a future phase.
                    </span>
                  </div>
                </>
              ) : (
                visibleEvents.map((event) => (
                  <div className="calendar-agenda-item calendar-agenda-event" key={event.id}>
                    <span className="calendar-agenda-time">{event.time || '—'}</span>
                    <span className="calendar-agenda-text">
                      <span className="calendar-event-title">{event.title}</span>
                      <span className="calendar-event-meta">
                        Added {formatEventCreatedAt(event.createdAt)}
                      </span>
                      <button
                        className="calendar-event-delete-btn"
                        onClick={() => onDeleteEvent(event.id)}
                      >
                        Delete
                      </button>
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Supported Commands</div>
            <p className="panel-section-text">
              Say “add event tomorrow at 3 called meeting,” “what's on my calendar,” “show today's events,” “show tomorrow's events,” “delete last event,” “clear calendar,” “close calendar,” or “go home.”
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
