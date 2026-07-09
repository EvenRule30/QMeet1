import { CalendarBackendStatus, CalendarEvent } from '../types';

type CalendarView = 'today' | 'tomorrow';

interface CalendarPanelProps {
  view: CalendarView;
  events: CalendarEvent[];
  googleEvents?: CalendarEvent[];
  googleStatus?: CalendarBackendStatus | null;
  googleLoading?: boolean;
  googleError?: string;
  onViewChange: (view: CalendarView) => void;
  onDeleteEvent: (eventId: string) => void;
  onConnectGoogleCalendar?: () => void;
  onRefreshGoogleCalendar?: () => void;
  onResetGoogleCalendar?: () => void;
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

function getEventSortValue(event: CalendarEvent): number {
  if (event.start) {
    const startDate = new Date(event.start);
    if (!Number.isNaN(startDate.getTime())) return startDate.getTime();
  }

  const time = (event.time || '').toLowerCase().trim();
  if (!time || time === 'later' || time === 'all day') return Number.MAX_SAFE_INTEGER;

  const match = time.match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/i);
  if (!match) return Number.MAX_SAFE_INTEGER - 1;

  let hour = Number(match[1]);
  const minute = Number(match[2] ?? '0');
  const meridiem = match[3]?.toLowerCase();

  if (meridiem === 'pm' && hour < 12) hour += 12;
  if (meridiem === 'am' && hour === 12) hour = 0;

  return hour * 60 + minute;
}

function sortCalendarEvents(events: CalendarEvent[]): CalendarEvent[] {
  return [...events].sort((a, b) => getEventSortValue(a) - getEventSortValue(b));
}

function getGoogleStatusLabel(status?: CalendarBackendStatus | null): string {
  if (!status) return 'Checking';
  if (!status.configured) return 'Not configured';
  if (!status.connected) return 'Needs authorization';
  return status.writeEnabled ? 'Connected · Write enabled' : 'Connected · Read only';
}

function CalendarEventRow({
  event,
  canDelete,
  onDelete,
}: {
  event: CalendarEvent;
  canDelete: boolean;
  onDelete?: (eventId: string) => void;
}) {
  const sourceLabel = event.source === 'google' ? 'Google Calendar' : 'Local event';

  return (
    <div className="calendar-agenda-item calendar-agenda-event" key={event.id}>
      <span className="calendar-agenda-time">{event.time || '—'}</span>
      <span className="calendar-agenda-text">
        <span className="calendar-event-title">{event.title}</span>
        <span className="calendar-event-meta">
          {sourceLabel}
          {event.location ? ` · ${event.location}` : ''}
          {event.source !== 'google' ? ` · Added ${formatEventCreatedAt(event.createdAt)}` : ''}
        </span>
        {canDelete && onDelete && (
          <button
            className="calendar-event-delete-btn"
            onClick={() => {
              const confirmed = window.confirm(
                `Delete ${sourceLabel}: ${event.time || '—'}: ${event.title}?`
              );

              if (confirmed) {
                onDelete(event.id);
              }
            }}
          >
            Delete
          </button>
        )}
      </span>
    </div>
  );
}

export function CalendarPanel({
  view,
  events,
  googleEvents = [],
  googleStatus = null,
  googleLoading = false,
  googleError = '',
  onViewChange,
  onDeleteEvent,
  onConnectGoogleCalendar,
  onRefreshGoogleCalendar,
  onResetGoogleCalendar,
  onClose,
}: CalendarPanelProps) {
  const title = view === 'today' ? "Today's Calendar" : "Tomorrow's Calendar";
  const acceptedDateKeys = getAcceptedDateKeysForView(view);
  const visibleLocalEvents = sortCalendarEvents(events.filter((event) => acceptedDateKeys.has(event.dateKey)));
  const visibleGoogleEvents = sortCalendarEvents(googleEvents.filter((event) => acceptedDateKeys.has(event.dateKey)));
  const googleConnected = Boolean(googleStatus?.connected);

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
            <div className="panel-section-title">Google Calendar</div>
            <p className="panel-section-text">
              Status: {getGoogleStatusLabel(googleStatus)}
              {googleStatus?.calendarId ? ` · Calendar: ${googleStatus.calendarId}` : ''}
              {googleStatus?.writeEnabled ? ' · Event creation enabled' : googleStatus?.connected ? ' · Read-only / writes disabled' : ''}
              {googleLoading ? ' · Loading…' : ''}
            </p>
            {(googleError || googleStatus?.message) && (
              <p className="panel-section-text">
                {googleError || googleStatus?.message}
              </p>
            )}
            <div className="panel-action-row">
              {!googleConnected && (
                <button className="panel-action-btn" onClick={onConnectGoogleCalendar} disabled={googleLoading}>
                  Connect
                </button>
              )}
              <button className="panel-action-btn" onClick={onRefreshGoogleCalendar} disabled={googleLoading}>
                {googleLoading ? 'Refreshing…' : 'Refresh'}
              </button>
              {googleStatus?.connected && (
                <button className="panel-action-btn" onClick={onResetGoogleCalendar} disabled={googleLoading}>
                  Disconnect
                </button>
              )}
            </div>
          </div>

          <div className="panel-section">
            <div className="panel-section-title">
              {googleConnected ? 'Google Agenda' : 'Local Agenda'}
            </div>
            <div className="calendar-agenda">
              {googleConnected ? (
                visibleGoogleEvents.length === 0 ? (
                  <div className="calendar-agenda-item">
                    <span className="calendar-agenda-time">—</span>
                    <span className="calendar-agenda-text">
                      No Google Calendar events found for {view === 'today' ? 'today' : 'tomorrow'}. Press Refresh after creating or deleting events from another device.
                    </span>
                  </div>
                ) : (
                  visibleGoogleEvents.map((event) => (
                    <CalendarEventRow
                      key={event.id}
                      event={event}
                      canDelete={Boolean(googleStatus?.writeEnabled)}
                      onDelete={onDeleteEvent}
                    />
                  ))
                )
              ) : visibleLocalEvents.length === 0 ? (
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
                      Connect Google Calendar to read, create, and delete real events. Local events stay on this device only.
                    </span>
                  </div>
                </>
              ) : (
                visibleLocalEvents.map((event) => (
                  <CalendarEventRow
                    key={event.id}
                    event={{ ...event, source: event.source ?? 'local' }}
                    canDelete
                    onDelete={onDeleteEvent}
                    />
                ))
              )}
            </div>
          </div>

          {googleConnected && visibleLocalEvents.length > 0 && (
            <div className="panel-section">
              <div className="panel-section-title">Local Events</div>
              <div className="calendar-agenda">
                {visibleLocalEvents.map((event) => (
                  <CalendarEventRow
                    key={event.id}
                    event={{ ...event, source: event.source ?? 'local' }}
                    canDelete
                    onDelete={onDeleteEvent}
                  />
                ))}
              </div>
            </div>
          )}

          <div className="panel-section">
            <div className="panel-section-title">Supported Commands</div>
            <p className="panel-section-text">
               Say “what's on my calendar,” “show today's events,” or “show tomorrow's events” to read Google Calendar. When Google Calendar is connected with writing enabled, “add event tomorrow at 3 called meeting” creates a real Google event after confirmation, “reschedule last event to tomorrow at 4” or “rename last event to project sync” edits the next visible event after confirmation, and “delete last event” deletes the next visible Google event after confirmation. Clear calendar still affects only local prototype events.
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
