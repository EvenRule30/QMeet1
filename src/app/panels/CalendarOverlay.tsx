import { CalendarPanel } from '../components/CalendarPanel';
import type { CalendarBackendStatus, CalendarEvent } from '../types';
import type { CalendarView } from '../lib/dateUtils';

type CalendarOverlayProps = {
  view: CalendarView;
  events: CalendarEvent[];
  googleEvents: CalendarEvent[];
  googleStatus: CalendarBackendStatus | null;
  googleLoading: boolean;
  googleError: string;
  onViewChange: (view: CalendarView) => void;
  onDeleteEvent: (eventId: string) => void | Promise<unknown>;
  onConnectGoogleCalendar: () => void | Promise<unknown>;
  onRefreshGoogleCalendar: () => void | Promise<unknown>;
  onResetGoogleCalendar: () => void | Promise<unknown>;
  onClose: () => void;
};

export function CalendarOverlay({
  view,
  events,
  googleEvents,
  googleStatus,
  googleLoading,
  googleError,
  onViewChange,
  onDeleteEvent,
  onConnectGoogleCalendar,
  onRefreshGoogleCalendar,
  onResetGoogleCalendar,
  onClose,
}: CalendarOverlayProps) {
  return (
    <CalendarPanel
      view={view}
      events={events}
      googleEvents={googleEvents}
      googleStatus={googleStatus}
      googleLoading={googleLoading}
      googleError={googleError}
      onViewChange={onViewChange}
      onDeleteEvent={(eventId) => {
        void onDeleteEvent(eventId);
      }}
      onConnectGoogleCalendar={() => {
        void onConnectGoogleCalendar();
      }}
      onRefreshGoogleCalendar={() => {
        void onRefreshGoogleCalendar();
      }}
      onResetGoogleCalendar={() => {
        void onResetGoogleCalendar();
      }}
      onClose={onClose}
    />
  );
}
