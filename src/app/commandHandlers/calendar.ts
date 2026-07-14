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
import {
  describeCalendarDeletePayload,
  type CalendarDeleteCriteria,
} from '../lib/calendarUtils';

export type CalendarCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
};

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
      return {
        handled: true,
        confirmationContent: updatedEvent
          ? `Updated ${updatedEvent.source === 'google' ? 'Google Calendar' : 'local'} event: ${updatedEvent.time}: ${updatedEvent.title}.`
          : deps.googleCalendarStatus?.connected
            ? 'I could not update the Google Calendar event. Check the Calendar panel status.'
            : 'No local calendar events to update.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'add-calendar-event': {
      const addedEvent = await deps.saveCalendarEvent(commandMatch.calendarEvent);
      const targetView = commandMatch.calendarEvent?.day ?? 'today';
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
      const requestedCalendarView = commandMatch.calendarView ?? 'all';
      const remoteCalendarView: CalendarBackendView =
        requestedCalendarView === 'all' ? 'week' : requestedCalendarView;
      const remoteEvents = deps.googleCalendarStatus?.connected
        ? await deps.refreshGoogleCalendar(remoteCalendarView)
        : deps.googleCalendarEvents;
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

      deps.setCalendarView(targetView);
      deps.setActivePanel('calendar');
      return {
        handled: true,
        confirmationContent: deps.getCalendarReadout(requestedCalendarView, remoteEvents),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'delete-calendar-event': {
      const targetView = commandMatch.calendarDelete?.day ?? deps.calendarView;
      const deletedEvent = await deps.deleteCalendarEventByCriteria(commandMatch.calendarDelete);
      deps.setCalendarView(targetView);
      deps.setActivePanel('calendar');
      return {
        handled: true,
        confirmationContent: deletedEvent
          ? `Deleted ${deletedEvent.source === 'google' ? 'Google Calendar' : 'local'} event: ${deletedEvent.time}: ${deletedEvent.title}.`
          : deps.googleCalendarStatus?.connected
            ? `No Google Calendar event matched ${describeCalendarDeletePayload(commandMatch.calendarDelete)}.`
            : `No local calendar event matched ${describeCalendarDeletePayload(commandMatch.calendarDelete)}.`,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
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
