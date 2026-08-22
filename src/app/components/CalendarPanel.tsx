import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CalendarBackendStatus, CalendarEvent } from '../types';
import {
  getAcceptedDateKeysForCalendarView,
  getDateKeyForCalendarView,
  type CalendarView,
} from '../lib/dateUtils';
import { fetchCalendarEventsRange } from '../lib/calendarReadRange';
import { consumeCalendarPanelDateHint } from '../lib/calendarUiContext';

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

const ISO_DATE_KEY_RE = /^\d{4}-\d{2}-\d{2}$/;

function parseLocalDateKey(dateKey: string): Date | null {
  if (!ISO_DATE_KEY_RE.test(dateKey)) return null;
  const [year, month, day] = dateKey.split('-').map(Number);
  const date = new Date(year, month - 1, day, 12, 0, 0, 0);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return date;
}

function toLocalDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function shiftDateKey(dateKey: string, offsetDays: number): string {
  const date = parseLocalDateKey(dateKey) ?? new Date();
  date.setDate(date.getDate() + offsetDays);
  return toLocalDateKey(date);
}

function getRelativeViewForDateKey(dateKey: string): CalendarView | null {
  if (dateKey === getDateKeyForCalendarView('today')) return 'today';
  if (dateKey === getDateKeyForCalendarView('tomorrow')) return 'tomorrow';
  return null;
}

function formatPanelDate(dateKey: string): string {
  const date = parseLocalDateKey(dateKey);
  if (!date) return dateKey;
  return date.toLocaleDateString([], {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatCompactDate(dateKey: string): string {
  const date = parseLocalDateKey(dateKey);
  if (!date) return dateKey;
  return date.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
  });
}

function formatEventCreatedAt(createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return 'Local event';
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
  if (!time || time === 'later' || time === 'all day') {
    return Number.MAX_SAFE_INTEGER;
  }
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
  return [...events].sort(
    (left, right) => getEventSortValue(left) - getEventSortValue(right),
  );
}

function getGoogleStatusLabel(status?: CalendarBackendStatus | null): string {
  if (!status) return 'Checking';
  if (!status.configured) return 'Not configured';
  if (!status.connected) return 'Needs authorization';
  return status.writeEnabled
    ? 'Connected · Write enabled'
    : 'Connected · Read only';
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
  const sourceLabel =
    event.source === 'google' ? 'Google Calendar' : 'Local event';
  return (
    <div className="calendar-agenda-item calendar-agenda-event" key={event.id}>
      <span className="calendar-agenda-time">{event.time || '—'}</span>
      <span className="calendar-agenda-text">
        <span className="calendar-event-title">{event.title}</span>
        <span className="calendar-event-meta">
          {sourceLabel}
          {event.location ? ` · ${event.location}` : ''}
          {event.source !== 'google'
            ? ` · Added ${formatEventCreatedAt(event.createdAt)}`
            : ''}
        </span>
        {canDelete && onDelete && (
          <button
            className="calendar-event-delete-btn"
            onClick={() => {
              const confirmed = window.confirm(
                `Delete ${sourceLabel}: ${event.time || '—'}: ${event.title}?`,
              );
              if (confirmed) onDelete(event.id);
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
  const relativeViewDateKey = getDateKeyForCalendarView(view);
  const [selectedDateKey, setSelectedDateKey] = useState(
    () => consumeCalendarPanelDateHint() ?? relativeViewDateKey,
  );
  const previousViewRef = useRef(view);
  const [rangeGoogleEvents, setRangeGoogleEvents] = useState<CalendarEvent[]>([]);
  const [rangeLoading, setRangeLoading] = useState(false);
  const [rangeError, setRangeError] = useState('');

  useEffect(() => {
    if (previousViewRef.current === view) return;
    previousViewRef.current = view;
    setSelectedDateKey(relativeViewDateKey);
  }, [relativeViewDateKey, view]);

  const selectedRelativeView = useMemo(
    () => getRelativeViewForDateKey(selectedDateKey),
    [selectedDateKey],
  );

  const loadSelectedAbsoluteDate = useCallback(async () => {
    if (!googleStatus?.connected || selectedRelativeView) {
      setRangeGoogleEvents([]);
      setRangeError('');
      return;
    }
    setRangeLoading(true);
    setRangeError('');
    try {
      const response = await fetchCalendarEventsRange({
        startDate: selectedDateKey,
        endDate: selectedDateKey,
      });
      setRangeGoogleEvents(response.events);
      setRangeError(response.message || '');
    } catch (error) {
      setRangeGoogleEvents([]);
      setRangeError(
        error instanceof Error
          ? error.message
          : 'Could not read Google Calendar events for this date.',
      );
    } finally {
      setRangeLoading(false);
    }
  }, [googleStatus?.connected, selectedDateKey, selectedRelativeView]);

  useEffect(() => {
    if (googleStatus?.connected && !selectedRelativeView) {
      void loadSelectedAbsoluteDate();
    } else {
      setRangeGoogleEvents([]);
      setRangeError('');
    }
  }, [googleStatus?.connected, loadSelectedAbsoluteDate, selectedRelativeView]);

  const handleDateSelection = useCallback(
    (dateKey: string) => {
      if (!parseLocalDateKey(dateKey)) return;
      setSelectedDateKey(dateKey);
      const relativeView = getRelativeViewForDateKey(dateKey);
      if (relativeView) onViewChange(relativeView);
    },
    [onViewChange],
  );

  const handleRelativeViewSelection = useCallback(
    (nextView: CalendarView) => {
      onViewChange(nextView);
      setSelectedDateKey(getDateKeyForCalendarView(nextView));
    },
    [onViewChange],
  );

  const selectedAcceptedDateKeys = selectedRelativeView
    ? getAcceptedDateKeysForCalendarView(selectedRelativeView)
    : new Set([selectedDateKey]);
  const visibleLocalEvents = sortCalendarEvents(
    events.filter((event) => selectedAcceptedDateKeys.has(event.dateKey)),
  );
  const visibleGoogleEvents = sortCalendarEvents(
    (selectedRelativeView ? googleEvents : rangeGoogleEvents).filter((event) =>
      selectedAcceptedDateKeys.has(event.dateKey),
    ),
  );
  const googleConnected = Boolean(googleStatus?.connected);
  const selectedLoading = googleLoading || rangeLoading;
  const selectedGoogleError = rangeError || googleError;
  const selectedDateLabel = formatPanelDate(selectedDateKey);
  const selectedDateKicker =
    selectedRelativeView === 'today'
      ? 'Today'
      : selectedRelativeView === 'tomorrow'
        ? 'Tomorrow'
        : 'Selected date';

  const refreshSelectedDate = () => {
    if (selectedRelativeView) {
      onRefreshGoogleCalendar?.();
      return;
    }
    void loadSelectedAbsoluteDate();
  };

  return (
    <div className="panel-overlay">
      <div className="panel-content calendar-panel">
        <div className="panel-header">Calendar</div>
        <div className="panel-body calendar-panel-body">
          <div className="calendar-hero">
            <div>
              <div className="calendar-kicker">{selectedDateKicker}</div>
              <div className="calendar-date">{selectedDateLabel}</div>
            </div>
            <div className="calendar-date-chip">
              {formatCompactDate(selectedDateKey)}
            </div>
          </div>

          <div className="panel-action-row">
            <button
              className="panel-action-btn"
              aria-label="Previous day"
              onClick={() => handleDateSelection(shiftDateKey(selectedDateKey, -1))}
            >
              ‹
            </button>
            <button
              className={`panel-action-btn ${
                selectedRelativeView === 'today' ? 'panel-action-btn-active' : ''
              }`}
              onClick={() => handleRelativeViewSelection('today')}
            >
              Today
            </button>
            <button
              className={`panel-action-btn ${
                selectedRelativeView === 'tomorrow'
                  ? 'panel-action-btn-active'
                  : ''
              }`}
              onClick={() => handleRelativeViewSelection('tomorrow')}
            >
              Tomorrow
            </button>
            <button
              className="panel-action-btn"
              aria-label="Next day"
              onClick={() => handleDateSelection(shiftDateKey(selectedDateKey, 1))}
            >
              ›
            </button>
          </div>

          <div className="panel-action-row">
            <input
              className="search-input"
              type="date"
              aria-label="Calendar date"
              value={selectedDateKey}
              onChange={(event) => handleDateSelection(event.target.value)}
            />
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Google Calendar</div>
            <p className="panel-section-text">
              Status: {getGoogleStatusLabel(googleStatus)}
              {googleStatus?.calendarId
                ? ` · Calendar: ${googleStatus.calendarId}`
                : ''}
              {googleStatus?.writeEnabled
                ? ' · Event creation enabled'
                : googleStatus?.connected
                  ? ' · Read-only / writes disabled'
                  : ''}
              {selectedLoading ? ' · Loading…' : ''}
            </p>
            {(selectedGoogleError || googleStatus?.message) && (
              <p className="panel-section-text">
                {selectedGoogleError || googleStatus?.message}
              </p>
            )}
            <div className="panel-action-row">
              {!googleConnected && (
                <button
                  className="panel-action-btn"
                  onClick={onConnectGoogleCalendar}
                  disabled={selectedLoading}
                >
                  Connect
                </button>
              )}
              <button
                className="panel-action-btn"
                onClick={refreshSelectedDate}
                disabled={selectedLoading}
              >
                {selectedLoading ? 'Refreshing…' : 'Refresh'}
              </button>
              {googleStatus?.connected && (
                <button
                  className="panel-action-btn"
                  onClick={onResetGoogleCalendar}
                  disabled={selectedLoading}
                >
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
                      No Google Calendar events found for {selectedDateLabel}.
                      Press Refresh after creating or deleting events from another
                      device.
                    </span>
                  </div>
                ) : (
                  visibleGoogleEvents.map((event) => (
                    <CalendarEventRow
                      key={event.id}
                      event={event}
                      canDelete={Boolean(
                        googleStatus?.writeEnabled && selectedRelativeView,
                      )}
                      onDelete={onDeleteEvent}
                    />
                  ))
                )
              ) : visibleLocalEvents.length === 0 ? (
                <>
                  <div className="calendar-agenda-item">
                    <span className="calendar-agenda-time">—</span>
                    <span className="calendar-agenda-text">
                      No local events saved for {selectedDateLabel}.
                    </span>
                  </div>
                  <div className="calendar-agenda-item">
                    <span className="calendar-agenda-time">Later</span>
                    <span className="calendar-agenda-text">
                      Connect Google Calendar to browse real events. Local events
                      stay on this device only.
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
            {googleConnected && !selectedRelativeView && googleStatus?.writeEnabled && (
              <p className="panel-section-text">
                Arbitrary-date browsing uses the canonical Calendar range read.
                Use QMeet for edits or deletions on this selected date so its
                normal target-resolution and confirmation safeguards remain in
                control.
              </p>
            )}
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
            <div className="panel-section-title">Calendar Navigation</div>
            <p className="panel-section-text">
              Use Today and Tomorrow as shortcuts, the arrow buttons to move one
              day at a time, or the date field to jump directly to any date.
              Google Calendar dates outside Today and Tomorrow are read through
              QMeet's canonical range endpoint instead of the legacy two-day
              view.
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
