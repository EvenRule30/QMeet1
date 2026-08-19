import type {
  ActivePanel,
  CalendarBackendStatus,
  CalendarBackendView,
  CalendarEvent,
} from '../types';
import type { CommandMatch } from '../commands';
import {
  getCalendarViewLabel,
  isEventForCalendarView,
  type CalendarView,
} from '../lib/dateUtils';
import { isCanonicalCalendarDateKey } from '../lib/calendarAbsoluteCreate';
import {
  describeCalendarDeletePayload,
  type CalendarDeleteCriteria,
} from '../lib/calendarUtils';
import {
  createCalendarEventOnDate,
  formatCalendarAbsoluteDate,
} from '../lib/calendarAbsoluteCreate';
import {
  decodeCalendarReadRangePayload,
  fetchCalendarEventsRange,
  filterCalendarEventsForRange,
  formatCalendarRangeReadout,
} from '../lib/calendarReadRange';
import {
  beginExplicitCalendarRead,
  clearExplicitCalendarRead,
  consumeLatestCalendarFocusResponse,
} from '../lib/focusTurnHeaders';

export type CalendarCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
  continuationContext?: string;
};

function formatVerifiedCalendarEvent(event: CalendarEvent): string {
  const dateLabel = isCanonicalCalendarDateKey(event.dateKey)
    ? formatCalendarAbsoluteDate(event.dateKey)
    : event.dateKey;
  return `${dateLabel} at ${event.time}: ${event.title}`;
}

function buildVerifiedCalendarEditContinuationContext(
  event: CalendarEvent,
): string {
  return [
    'qmeetScope=calendar.',
    'qmeetCalendarWriteVerified=true.',
    'qmeetCalendarWriteAction=edit.',
    `verifiedEventDate=${event.dateKey}.`,
    `verifiedEventTime=${event.time}.`,
    `verifiedEventTitle=${JSON.stringify(event.title)}.`,
    'These fields are the authoritative post-write Calendar state returned by deterministic execution.',
    'Any continuation claim about the updated event date, time, or title must use these verified values.',
    'Do not reconstruct or shorten the destination date from the original user wording.',
  ].join(' ');
}

function buildVerifiedCalendarDeleteContinuationContext(
  event: CalendarEvent,
): string {
  return [
    'qmeetScope=calendar.',
    'qmeetCalendarWriteVerified=true.',
    'qmeetCalendarWriteAction=delete.',
    `verifiedDeletedEventDate=${event.dateKey}.`,
    `verifiedDeletedEventTime=${event.time}.`,
    `verifiedDeletedEventTitle=${JSON.stringify(event.title)}.`,
    'These fields identify the exact Calendar event that deterministic execution deleted.',
    'Do not reconstruct a different date, time, or title from recent conversation.',
  ].join(' ');
}

export async function handleCalendarCommand(
  commandMatch: CommandMatch,
  deps: {
    voiceOutputEnabled: boolean;
    calendarView: CalendarView;
    calendarEvents: CalendarEvent[];
    googleCalendarStatus: CalendarBackendStatus | null;
    googleCalendarEvents: CalendarEvent[];
    setCalendarView: (view: CalendarView) => void;
    setActivePanel: (panel: ActivePanel) => void;
    closePanel: () => void;
    saveCalendarEvent: (eventInput?: { day?: CalendarView; time?: string; title?: string }) => Promise<CalendarEvent | null>;
    editLastCalendarEvent: (changes?: { day?: CalendarView; time?: string; title?: string }) => Promise<CalendarEvent | null>;
    deleteCalendarEventByCriteria: (criteria?: CalendarDeleteCriteria) => Promise<CalendarEvent | null>;
    deleteLastCalendarEvent: () => Promise<CalendarEvent | null>;
    clearCalendarEvents: () => void;
    refreshGoogleCalendar: (viewInput?: CalendarBackendView) => Promise<CalendarEvent[]>;
    getCalendarReadout: (view?: CalendarView | 'all', remoteEvents?: CalendarEvent[]) => string;
    resetConversation: () => Promise<void>;
  },
): Promise<CalendarCommandResult> {
  switch (commandMatch.command) {
    case 'open-calendar':
      deps.setCalendarView('today');
      deps.setActivePanel('calendar');
      return { handled: true };

    case 'refresh-calendar': {
      const refreshedEvents = await deps.refreshGoogleCalendar(deps.calendarView);
      deps.setActivePanel('calendar');
      return {
        handled: true,
        confirmationContent: deps.googleCalendarStatus?.connected
          ? `Refreshed Google Calendar. ${refreshedEvents.length} event${refreshedEvents.length === 1 ? '' : 's'} loaded.`
          : 'Calendar refreshed. Google Calendar is not connected, so QMeet is showing local calendar events.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'edit-last-event': {
      const updatedEvent = await deps.editLastCalendarEvent(commandMatch.calendarEdit);
      deps.setActivePanel('calendar');
      const confirmationContent = updatedEvent
        ? `Updated ${updatedEvent.source === 'google' ? 'Google Calendar' : 'local'} event ${formatVerifiedCalendarEvent(updatedEvent)}.`
        : deps.googleCalendarStatus?.connected
          ? 'I could not update the Google Calendar event. Check the Calendar panel status.'
          : 'No local calendar events to update.';
      return {
        handled: true,
        confirmationContent,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
        continuationContext: updatedEvent
          ? buildVerifiedCalendarEditContinuationContext(updatedEvent)
          : undefined,
      };
    }

    case 'add-calendar-event': {
      const targetDay = commandMatch.calendarEvent?.day ?? 'today';
      if (isCanonicalCalendarDateKey(targetDay)) {
        if (
          !deps.googleCalendarStatus?.connected ||
          !deps.googleCalendarStatus?.writeEnabled ||
          !commandMatch.calendarEvent?.title?.trim()
        ) {
          const failure =
            'I could not create that absolute-date Calendar event because Google Calendar write access is not available.';
          return {
            handled: true,
            confirmationContent: failure,
            shouldSpeakConfirmation: deps.voiceOutputEnabled,
          };
        }

        try {
          const response = await createCalendarEventOnDate({
            title: commandMatch.calendarEvent.title,
            date: targetDay,
            time: commandMatch.calendarEvent.time || 'Later',
          });
          const addedEvent = response.event;
          const confirmationContent = addedEvent
            ? `Added Google Calendar event ${formatCalendarAbsoluteDate(targetDay)} at ${addedEvent.time}: ${addedEvent.title}.`
            : 'Google Calendar did not return the created event.';
          // Do not open the today/tomorrow Calendar panel for a farther-date
          // event. The verified Tool receipt is the authoritative write result
          // until the Calendar UI itself supports arbitrary date navigation.
          return {
            handled: true,
            confirmationContent,
            shouldSpeakConfirmation: deps.voiceOutputEnabled,
            continuationContext: addedEvent ? confirmationContent : undefined,
          };
        } catch (error) {
          console.error('Calendar absolute-date create error:', error);
          const failure =
            error instanceof Error && error.message.trim()
              ? error.message
              : 'I could not create that Google Calendar event.';
          return {
            handled: true,
            confirmationContent: failure,
            shouldSpeakConfirmation: deps.voiceOutputEnabled,
          };
        }
      }

      const addedEvent = await deps.saveCalendarEvent(commandMatch.calendarEvent);
      const targetView = targetDay;
      deps.setCalendarView(targetView);
      deps.setActivePanel('calendar');
      return {
        handled: true,
        confirmationContent: addedEvent
          ? `Added ${addedEvent.source === 'google' ? 'Google Calendar' : 'local'} event ${getCalendarViewLabel(targetView)} at ${addedEvent.time}: ${addedEvent.title}.`
          : deps.googleCalendarStatus?.connected && deps.googleCalendarStatus?.writeEnabled
            ? 'I could not create the Google Calendar event. Check the Calendar panel status.'
            : 'I did not catch the event details.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-calendar': {
      const calendarRange = decodeCalendarReadRangePayload(commandMatch.payload);
      if (calendarRange) {
        // Range reads intentionally do not switch the existing today/tomorrow
        // panel. The verified Tool readout is the authoritative range surface
        // until the Calendar UI itself gains arbitrary-range navigation.
        consumeLatestCalendarFocusResponse();
        let rangeEvents = filterCalendarEventsForRange(
          deps.calendarEvents,
          calendarRange,
        );
        let googleConnected = Boolean(deps.googleCalendarStatus?.connected);
        if (googleConnected) {
          try {
            const response = await fetchCalendarEventsRange(calendarRange);
            rangeEvents = response.events;
            googleConnected = response.connected;
          } catch (error) {
            console.error('Calendar range read error:', error);
            const failure = 'I could not read that Google Calendar date range. Check the Calendar connection and try again.';
            return {
              handled: true,
              confirmationContent: failure,
              shouldSpeakConfirmation: deps.voiceOutputEnabled,
              continuationContext: failure,
            };
          }
        }

        const verifiedCalendarReadout = formatCalendarRangeReadout({
          range: calendarRange,
          events: rangeEvents,
          googleConnected,
        });
        return {
          handled: true,
          confirmationContent: verifiedCalendarReadout,
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
          continuationContext: verifiedCalendarReadout,
        };
      }

      const requestedCalendarView = commandMatch.calendarView ?? 'all';
      const remoteCalendarView: CalendarBackendView =
        requestedCalendarView === 'all' ? 'week' : requestedCalendarView;
      let remoteEvents = deps.googleCalendarEvents;
      if (deps.googleCalendarStatus?.connected) {
        beginExplicitCalendarRead();
        try {
          remoteEvents = await deps.refreshGoogleCalendar(remoteCalendarView);
        } finally {
          // The interceptor normally consumes the one-shot marker on the GET.
          // Clearing here also covers a disconnect or failure before that GET.
          clearExplicitCalendarRead();
        }
      }

      // Consume the one-shot middleware response so it cannot leak into a later
      // turn, but do not substitute Focus prose for the authoritative calendar
      // readout produced from the events the deterministic controller just read.
      consumeLatestCalendarFocusResponse();
      const sourceEvents = deps.googleCalendarStatus?.connected ? remoteEvents : deps.calendarEvents;
      const hasTodayEvents = sourceEvents.some((event) => isEventForCalendarView(event, 'today'));
      const hasTomorrowEvents = sourceEvents.some((event) => isEventForCalendarView(event, 'tomorrow'));
      const targetView = requestedCalendarView === 'today' || requestedCalendarView === 'tomorrow'
        ? requestedCalendarView
        : hasTodayEvents
          ? 'today'
          : hasTomorrowEvents
            ? 'tomorrow'
            : deps.calendarView;
      const verifiedCalendarReadout = deps.getCalendarReadout(
        requestedCalendarView,
        remoteEvents,
      );
      deps.setCalendarView(targetView);
      deps.setActivePanel('calendar');
      return {
        handled: true,
        confirmationContent: verifiedCalendarReadout,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
        continuationContext: verifiedCalendarReadout,
      };
    }

    case 'delete-calendar-event': {
      const targetView = commandMatch.calendarDelete?.day ?? deps.calendarView;
      const deletedEvent = await deps.deleteCalendarEventByCriteria(commandMatch.calendarDelete);
      if (!isCanonicalCalendarDateKey(targetView)) {
        deps.setCalendarView(targetView);
        deps.setActivePanel('calendar');
      }
      const confirmationContent = deletedEvent
        ? `Deleted ${deletedEvent.source === 'google' ? 'Google Calendar' : 'local'} event ${formatVerifiedCalendarEvent(deletedEvent)}.`
        : deps.googleCalendarStatus?.connected
          ? `No Google Calendar event matched ${describeCalendarDeletePayload(commandMatch.calendarDelete)}.`
          : `No local calendar event matched ${describeCalendarDeletePayload(commandMatch.calendarDelete)}.`;
      return {
        handled: true,
        confirmationContent,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
        continuationContext: deletedEvent
          ? buildVerifiedCalendarDeleteContinuationContext(deletedEvent)
          : undefined,
      };
    }

    case 'delete-last-event': {
      const deletedEvent = await deps.deleteLastCalendarEvent();
      deps.setActivePanel('calendar');
      return {
        handled: true,
        confirmationContent: deletedEvent
          ? `Deleted ${deletedEvent.source === 'google' ? 'Google Calendar' : 'local'} event: ${deletedEvent.time}: ${deletedEvent.title}.`
          : deps.googleCalendarStatus?.connected
            ? 'No Google Calendar events to delete for the current view.'
            : 'No local calendar events to delete.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'clear-calendar':
      deps.clearCalendarEvents();
      try {
        await deps.resetConversation();
      } catch (error) {
        console.error('Reset conversation after clearing calendar error:', error);
      }
      deps.setActivePanel('calendar');
      return {
        handled: true,
        confirmationContent: 'Cleared all local calendar events.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };

    case 'show-today':
      deps.setCalendarView('today');
      deps.setActivePanel('calendar');
      return { handled: true };

    case 'show-tomorrow':
      deps.setCalendarView('tomorrow');
      deps.setActivePanel('calendar');
      return { handled: true };

    case 'close-calendar':
      deps.closePanel();
      return { handled: true };

    default:
      return { handled: false };
  }
}
