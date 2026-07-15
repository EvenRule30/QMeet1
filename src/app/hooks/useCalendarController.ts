import { useCallback, useEffect, useState } from 'react';
import {
  createCalendarEvent,
  deleteGoogleCalendarEvent,
  getCalendarEvents,
  getCalendarStatus,
  resetCalendarAuth,
  startCalendarAuth,
  updateGoogleCalendarEvent,
} from '../api';
import {
  ActivePanel,
  CalendarBackendStatus,
  CalendarBackendView,
  CalendarEvent,
} from '../types';
import {
  getDateKeyForCalendarView,
  isEventForCalendarView,
  type CalendarView,
} from '../lib/dateUtils';
import {
  calendarEventMatchesDeleteCriteria,
  type CalendarDeleteCriteria,
} from '../lib/calendarUtils';

const CALENDAR_EVENTS_STORAGE_KEY = 'qmeet-calendar-events';
const LEGACY_CALENDAR_EVENTS_STORAGE_KEYS = [
  'qmeet-calendar',
  'qmeet-events',
  'calendar-events',
];

type CalendarEventInput = {
  day?: CalendarView;
  time?: string;
  title?: string;
};

type UseCalendarControllerInput = {
  activePanel: ActivePanel;
};


function readStoredCalendarEvents(): CalendarEvent[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawEvents = window.localStorage.getItem(
      CALENDAR_EVENTS_STORAGE_KEY,
    );
    if (!rawEvents) return [];

    const parsedEvents = JSON.parse(rawEvents);
    if (!Array.isArray(parsedEvents)) return [];

    return parsedEvents
      .filter(
        (event) =>
          event &&
          typeof event.title === 'string' &&
          typeof event.dateKey === 'string',
      )
      .map((event) => ({
        id:
          typeof event.id === 'string'
            ? event.id
            : `event-${Date.now()}-${Math.random()
                .toString(36)
                .slice(2)}`,
        title: event.title,
        dateKey: event.dateKey,
        time:
          typeof event.time === 'string'
            ? event.time
            : 'Later',
        createdAt:
          typeof event.createdAt === 'string'
            ? event.createdAt
            : new Date().toISOString(),
        source: 'local' as const,
      }));
  } catch {
    return [];
  }
}

function getCreatedTimestamp(event: CalendarEvent): number {
  const parsed = Date.parse(event.createdAt || '');
  return Number.isFinite(parsed) ? parsed : 0;
}

function selectMostRecentlyCreatedEvent(
  events: CalendarEvent[],
  view: CalendarView,
): CalendarEvent | null {
  const visibleEvents = events.filter((event) =>
    isEventForCalendarView(event, view),
  );

  // "Last/latest event" means the event most recently added to the calendar,
  // not the next event by clock time. Google events include their original
  // creation timestamp, while local events are also stamped when saved.
  const sortedEvents = [...visibleEvents].sort(
    (left, right) =>
      getCreatedTimestamp(right) -
      getCreatedTimestamp(left),
  );

  return sortedEvents[0] ?? null;
}

export function useCalendarController({
  activePanel,
}: UseCalendarControllerInput) {
  const [calendarView, setCalendarView] =
    useState<CalendarView>('today');
  const [calendarEvents, setCalendarEvents] =
    useState<CalendarEvent[]>(readStoredCalendarEvents);
  const [googleCalendarStatus, setGoogleCalendarStatus] =
    useState<CalendarBackendStatus | null>(null);
  const [googleCalendarEvents, setGoogleCalendarEvents] =
    useState<CalendarEvent[]>([]);
  const [googleCalendarLoading, setGoogleCalendarLoading] =
    useState(false);
  const [googleCalendarError, setGoogleCalendarError] =
    useState('');

  useEffect(() => {
    try {
      window.localStorage.setItem(
        CALENDAR_EVENTS_STORAGE_KEY,
        JSON.stringify(calendarEvents),
      );
    } catch (error) {
      console.error(
        'Failed to save calendar events:',
        error,
      );
    }
  }, [calendarEvents]);

  const loadGoogleCalendarStatus = useCallback(
    async (): Promise<CalendarBackendStatus | null> => {
      try {
        const status = await getCalendarStatus();
        setGoogleCalendarStatus(status);

        if (status.connected) {
          setGoogleCalendarError('');
        }

        return status;
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : 'Could not load Google Calendar status.';

        setGoogleCalendarStatus(null);
        setGoogleCalendarError(message);
        return null;
      }
    },
    [],
  );

  const refreshGoogleCalendar = useCallback(
    async (
      viewInput: CalendarBackendView = calendarView,
    ): Promise<CalendarEvent[]> => {
      setGoogleCalendarLoading(true);
      setGoogleCalendarError('');

      try {
        const status = await getCalendarStatus();
        setGoogleCalendarStatus(status);

        if (!status.connected) {
          setGoogleCalendarEvents([]);
          setGoogleCalendarError(status.message);
          return [];
        }

        const response = await getCalendarEvents(viewInput);
        setGoogleCalendarEvents(response.events);
        setGoogleCalendarError(response.message);
        return response.events;
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : 'Could not read Google Calendar events.';

        setGoogleCalendarError(message);
        return [];
      } finally {
        setGoogleCalendarLoading(false);
      }
    },
    [calendarView],
  );

  const saveCalendarEvent = useCallback(
    async (
      eventInput?: CalendarEventInput,
    ): Promise<CalendarEvent | null> => {
      const title = eventInput?.title?.trim() ?? '';

      if (!title) {
        return null;
      }

      const view = eventInput?.day ?? 'today';
      const eventTime =
        eventInput?.time?.trim() || 'Later';

      if (
        googleCalendarStatus?.connected &&
        googleCalendarStatus?.writeEnabled
      ) {
        setGoogleCalendarLoading(true);
        setGoogleCalendarError('');

        try {
          const response = await createCalendarEvent({
            title,
            day: view,
            time: eventTime,
          });

          if (response.event) {
            setGoogleCalendarEvents((prev) => [
              response.event as CalendarEvent,
              ...prev.filter(
                (event) =>
                  event.id !== response.event?.id,
              ),
            ]);
            setGoogleCalendarError(
              response.message ||
                'Google Calendar event created.',
            );
            return response.event;
          }

          setGoogleCalendarError(
            response.message ||
              'Google Calendar did not return the created event.',
          );
          return null;
        } catch (error) {
          const message =
            error instanceof Error
              ? error.message
              : 'Could not create Google Calendar event.';

          setGoogleCalendarError(message);
          return null;
        } finally {
          setGoogleCalendarLoading(false);
        }
      }

      const event: CalendarEvent = {
        id: `event-${Date.now()}-${Math.random()
          .toString(36)
          .slice(2)}`,
        title,
        dateKey: getDateKeyForCalendarView(view),
        time: eventTime,
        createdAt: new Date().toISOString(),
        source: 'local',
      };

      setCalendarEvents((prev) => [event, ...prev]);
      return event;
    },
    [
      googleCalendarStatus?.connected,
      googleCalendarStatus?.writeEnabled,
    ],
  );

  const deleteCalendarEvent = useCallback(
    async (
      eventId: string,
    ): Promise<CalendarEvent | null> => {
      let googleEvent = googleCalendarEvents.find(
        (event) =>
          event.id === eventId ||
          event.googleEventId === eventId,
      );

      // A cold-start edit can identify an event from the array returned by a
      // refresh before React has committed that array to state. Refresh and
      // resolve the event directly instead of treating it as a local event.
      if (
        !googleEvent &&
        googleCalendarStatus?.connected
      ) {
        const refreshedEvents =
          await refreshGoogleCalendar(calendarView);

        googleEvent = refreshedEvents.find(
          (event) =>
            event.id === eventId ||
            event.googleEventId === eventId,
        );
      }

      if (googleEvent?.source === 'google') {
        const googleEventId =
          googleEvent.googleEventId ||
          googleEvent.id.replace(/^google-/, '');

        if (!googleEventId) {
          setGoogleCalendarError(
            'Could not identify the Google Calendar event to delete.',
          );
          return null;
        }

        setGoogleCalendarLoading(true);
        setGoogleCalendarError('');

        try {
          const response =
            await deleteGoogleCalendarEvent(
              googleEventId,
            );

          setGoogleCalendarEvents((prev) =>
            prev.filter(
              (event) =>
                event.id !== googleEvent.id &&
                event.googleEventId !==
                  googleEvent.googleEventId &&
                event.googleEventId !== googleEventId,
            ),
          );
          setGoogleCalendarError(
            response.message ||
              'Deleted Google Calendar event.',
          );
          return googleEvent;
        } catch (error) {
          const message =
            error instanceof Error
              ? error.message
              : 'Could not delete Google Calendar event.';

          setGoogleCalendarError(message);
          return null;
        } finally {
          setGoogleCalendarLoading(false);
        }
      }

      const localEvent =
        calendarEvents.find(
          (event) => event.id === eventId,
        ) ?? null;

      setCalendarEvents((prev) =>
        prev.filter((event) => event.id !== eventId),
      );
      return localEvent;
    },
    [calendarEvents, googleCalendarEvents],
  );

  const updateCalendarEvent = useCallback(
    async (
      eventId: string,
      changes?: CalendarEventInput,
    ): Promise<CalendarEvent | null> => {
      if (
        !changes ||
        (!changes.day &&
          !changes.time?.trim() &&
          !changes.title?.trim())
      ) {
        setGoogleCalendarError(
          'No calendar event changes were provided.',
        );
        return null;
      }

      const googleEvent = googleCalendarEvents.find(
        (event) =>
          event.id === eventId ||
          event.googleEventId === eventId,
      );

      if (googleEvent?.source === 'google') {
        const googleEventId =
          googleEvent.googleEventId ||
          googleEvent.id.replace(/^google-/, '');

        if (!googleEventId) {
          setGoogleCalendarError(
            'Could not identify the Google Calendar event to update.',
          );
          return null;
        }

        setGoogleCalendarLoading(true);
        setGoogleCalendarError('');

        try {
          const response =
            await updateGoogleCalendarEvent(
              googleEventId,
              {
                ...(changes.title?.trim()
                  ? { title: changes.title.trim() }
                  : {}),
                ...(changes.day
                  ? { day: changes.day }
                  : {}),
                ...(changes.time?.trim()
                  ? { time: changes.time.trim() }
                  : {}),
              },
            );

          if (response.event) {
            setGoogleCalendarEvents((prev) => [
              response.event as CalendarEvent,
              ...prev.filter(
                (event) =>
                  event.id !== googleEvent.id &&
                  event.googleEventId !==
                    googleEvent.googleEventId &&
                  event.googleEventId !==
                    googleEventId,
              ),
            ]);
            setGoogleCalendarError(
              response.message ||
                'Updated Google Calendar event.',
            );
            return response.event;
          }

          setGoogleCalendarError(
            response.message ||
              'Google Calendar did not return the updated event.',
          );
          return null;
        } catch (error) {
          const message =
            error instanceof Error
              ? error.message
              : 'Could not update Google Calendar event.';

          setGoogleCalendarError(message);
          return null;
        } finally {
          setGoogleCalendarLoading(false);
        }
      }

      const localEvent =
        calendarEvents.find(
          (event) => event.id === eventId,
        ) ?? null;

      if (!localEvent) {
        return null;
      }

      const updatedLocalEvent: CalendarEvent = {
        ...localEvent,
        title:
          changes.title?.trim() || localEvent.title,
        time:
          changes.time?.trim() || localEvent.time,
        dateKey: changes.day
          ? getDateKeyForCalendarView(changes.day)
          : localEvent.dateKey,
        source: localEvent.source ?? 'local',
      };

      setCalendarEvents((prev) =>
        prev.map((event) =>
          event.id === localEvent.id
            ? updatedLocalEvent
            : event,
        ),
      );

      return updatedLocalEvent;
    },
    [
      calendarEvents,
      calendarView,
      googleCalendarEvents,
      googleCalendarStatus?.connected,
      refreshGoogleCalendar,
    ],
  );

  const clearCalendarEvents = useCallback(() => {
    setCalendarEvents([]);

    try {
      window.localStorage.setItem(
        CALENDAR_EVENTS_STORAGE_KEY,
        '[]',
      );

      for (const legacyKey of
        LEGACY_CALENDAR_EVENTS_STORAGE_KEYS) {
        window.localStorage.removeItem(legacyKey);
      }
    } catch (error) {
      console.error(
        'Failed to clear calendar events:',
        error,
      );
    }
  }, []);

  const getNextCalendarEventForDeletion =
    useCallback((): CalendarEvent | null => {
      const sourceEvents =
        googleCalendarStatus?.connected
          ? googleCalendarEvents
          : calendarEvents;

      return selectMostRecentlyCreatedEvent(
        sourceEvents,
        calendarView,
      );
    }, [
      calendarEvents,
      calendarView,
      googleCalendarEvents,
      googleCalendarStatus?.connected,
    ]);

  const getNextCalendarEventForChange =
    useCallback((): CalendarEvent | null => {
      const sourceEvents =
        googleCalendarStatus?.connected
          ? googleCalendarEvents
          : calendarEvents;

      return selectMostRecentlyCreatedEvent(
        sourceEvents,
        calendarView,
      );
    }, [
      calendarEvents,
      calendarView,
      googleCalendarEvents,
      googleCalendarStatus?.connected,
    ]);

  const findCalendarEventForChange = useCallback(
    async (): Promise<CalendarEvent | null> => {
      const sourceEvents =
        googleCalendarStatus?.connected
          ? await refreshGoogleCalendar(calendarView)
          : calendarEvents;

      // Use the refresh result directly. React state may still contain an
      // empty pre-refresh array during a cold-start edit command.
      return selectMostRecentlyCreatedEvent(
        sourceEvents,
        calendarView,
      );
    },
    [
      calendarEvents,
      calendarView,
      googleCalendarStatus?.connected,
      refreshGoogleCalendar,
    ],
  );

  const editLastCalendarEvent = useCallback(
    async (
      changes?: CalendarEventInput,
    ): Promise<CalendarEvent | null> => {
      const targetEvent =
        await findCalendarEventForChange();

      if (!targetEvent) return null;

      return updateCalendarEvent(
        targetEvent.id,
        changes,
      );
    },
    [
      findCalendarEventForChange,
      updateCalendarEvent,
    ],
  );

  const deleteLastCalendarEvent = useCallback(
    async (): Promise<CalendarEvent | null> => {
      const targetEvent =
        getNextCalendarEventForDeletion();

      if (!targetEvent) return null;

      if (
        targetEvent.source === 'google' ||
        targetEvent.googleEventId
      ) {
        return deleteCalendarEvent(targetEvent.id);
      }

      setCalendarEvents((prev) =>
        prev.filter(
          (event) => event.id !== targetEvent.id,
        ),
      );
      return targetEvent;
    },
    [
      deleteCalendarEvent,
      getNextCalendarEventForDeletion,
    ],
  );

  const getCalendarReadout = useCallback(
    (
      view: CalendarView | 'all' = 'all',
      remoteEvents: CalendarEvent[] =
        googleCalendarEvents,
    ) => {
      const googleConnected = Boolean(
        googleCalendarStatus?.connected,
      );
      const sourceEvents = googleConnected
        ? remoteEvents
        : calendarEvents;
      const sourceLabel = googleConnected
        ? 'Google Calendar'
        : 'local calendar';

      const getEventsForView = (
        targetView: CalendarView,
      ) =>
        sourceEvents.filter((event) =>
          isEventForCalendarView(event, targetView),
        );

      const describeEvents = (
        label: string,
        eventsForDate: CalendarEvent[],
      ) => {
        if (eventsForDate.length === 0) {
          return `No ${sourceLabel} events saved for ${label}.`;
        }

        const eventText = eventsForDate
          .slice(0, 5)
          .map(
            (event) =>
              `${event.time}: ${event.title}${
                event.location
                  ? ` at ${event.location}`
                  : ''
              }`,
          )
          .join(' ');

        const remainingCount =
          eventsForDate.length - 5;
        const suffix =
          remainingCount > 0
            ? ` Plus ${remainingCount} more.`
            : '';

        return `${label
          .charAt(0)
          .toUpperCase()}${label.slice(
          1,
        )} ${sourceLabel}: ${eventText}${suffix}`;
      };

      if (view === 'today') {
        return describeEvents(
          'today',
          getEventsForView('today'),
        );
      }

      if (view === 'tomorrow') {
        return describeEvents(
          'tomorrow',
          getEventsForView('tomorrow'),
        );
      }

      const todayEvents = getEventsForView('today');
      const tomorrowEvents =
        getEventsForView('tomorrow');

      if (
        todayEvents.length === 0 &&
        tomorrowEvents.length === 0
      ) {
        return googleConnected
          ? 'You do not have any Google Calendar events for today or tomorrow.'
          : 'You do not have any local calendar events saved for today or tomorrow.';
      }

      return `${describeEvents(
        'today',
        todayEvents,
      )} ${describeEvents(
        'tomorrow',
        tomorrowEvents,
      )}`;
    },
    [
      calendarEvents,
      googleCalendarEvents,
      googleCalendarStatus?.connected,
    ],
  );

  const getCalendarEventsForDeleteCriteria =
    useCallback(
      async (
        criteria?: CalendarDeleteCriteria,
      ): Promise<CalendarEvent[]> => {
        if (googleCalendarStatus?.connected) {
          const targetView =
            criteria?.day ?? calendarView;
          return refreshGoogleCalendar(targetView);
        }

        return calendarEvents;
      },
      [
        calendarEvents,
        calendarView,
        googleCalendarStatus?.connected,
        refreshGoogleCalendar,
      ],
    );

  const findCalendarEventForDeletion = useCallback(
    async (
      criteria?: CalendarDeleteCriteria,
    ): Promise<CalendarEvent | null> => {
      const sourceEvents =
        await getCalendarEventsForDeleteCriteria(
          criteria,
        );
      const matchingEvents = sourceEvents.filter(
        (event) =>
          calendarEventMatchesDeleteCriteria(
            event,
            criteria,
          ),
      );

      if (
        criteria?.day ||
        criteria?.time ||
        criteria?.title
      ) {
        return matchingEvents[0] ?? null;
      }

      // Use the events returned by the refresh itself. Reading React state
      // here can still see the pre-refresh empty array during a cold-start
      // command such as "delete last event."
      return selectMostRecentlyCreatedEvent(
        sourceEvents,
        calendarView,
      );
    },
    [
      calendarView,
      getCalendarEventsForDeleteCriteria,
    ],
  );

  const deleteCalendarEventByCriteria = useCallback(
    async (
      criteria?: CalendarDeleteCriteria,
    ): Promise<CalendarEvent | null> => {
      const targetEvent =
        await findCalendarEventForDeletion(criteria);

      if (!targetEvent) return null;

      if (
        targetEvent.source === 'google' ||
        targetEvent.googleEventId
      ) {
        return deleteCalendarEvent(targetEvent.id);
      }

      setCalendarEvents((prev) =>
        prev.filter(
          (event) => event.id !== targetEvent.id,
        ),
      );
      return targetEvent;
    },
    [deleteCalendarEvent, findCalendarEventForDeletion],
  );

  const handleStartGoogleCalendarAuth = useCallback(
    async () => {
      setGoogleCalendarLoading(true);
      setGoogleCalendarError('');

      try {
        const response = await startCalendarAuth();

        if (response.authUrl) {
          window.open(
            response.authUrl,
            '_blank',
            'noopener,noreferrer',
          );
          setGoogleCalendarError(
            'Google authorization opened in a new tab. After approving access, return here and press Refresh.',
          );
        } else {
          setGoogleCalendarError(
            response.message ||
              'Google Calendar authorization did not return a URL.',
          );
        }
      } catch (error) {
        setGoogleCalendarError(
          error instanceof Error
            ? error.message
            : 'Could not start Google Calendar authorization.',
        );
      } finally {
        setGoogleCalendarLoading(false);
        loadGoogleCalendarStatus();
      }
    },
    [loadGoogleCalendarStatus],
  );

  const handleResetGoogleCalendarAuth = useCallback(
    async () => {
      setGoogleCalendarLoading(true);
      setGoogleCalendarError('');

      try {
        const response = await resetCalendarAuth();
        setGoogleCalendarEvents([]);
        setGoogleCalendarError(
          response.message ||
            'Google Calendar authorization reset.',
        );
        await loadGoogleCalendarStatus();
      } catch (error) {
        setGoogleCalendarError(
          error instanceof Error
            ? error.message
            : 'Could not reset Google Calendar authorization.',
        );
      } finally {
        setGoogleCalendarLoading(false);
      }
    },
    [loadGoogleCalendarStatus],
  );

  useEffect(() => {
    loadGoogleCalendarStatus();
  }, [loadGoogleCalendarStatus]);

  useEffect(() => {
    if (activePanel === 'calendar') {
      refreshGoogleCalendar(calendarView);
    }
  }, [
    activePanel,
    calendarView,
    refreshGoogleCalendar,
  ]);

  return {
    calendarView,
    setCalendarView,
    calendarEvents,
    googleCalendarStatus,
    googleCalendarEvents,
    googleCalendarLoading,
    googleCalendarError,
    saveCalendarEvent,
    deleteCalendarEvent,
    updateCalendarEvent,
    clearCalendarEvents,
    getNextCalendarEventForDeletion,
    getNextCalendarEventForChange,
    editLastCalendarEvent,
    deleteLastCalendarEvent,
    getCalendarReadout,
    loadGoogleCalendarStatus,
    refreshGoogleCalendar,
    getCalendarEventsForDeleteCriteria,
    findCalendarEventForDeletion,
    findCalendarEventForChange,
    deleteCalendarEventByCriteria,
    handleStartGoogleCalendarAuth,
    handleResetGoogleCalendarAuth,
  };
}
