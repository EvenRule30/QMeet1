export function hasFailureLanguage(text: string): boolean {
  return /\b(?:could not|did not|failed|error|not connected|not supported|no |none|missing|unavailable|denied)\b/i.test(
    text,
  );
}

export function getBriefToolSpeech(command: string, fullText: string): string {
  const trimmed = fullText.trim();
  if (!trimmed) return '';
  if (hasFailureLanguage(trimmed)) {
    return trimmed;
  }

  switch (command) {
    case 'open-menu':
      return 'Menu open.';
    case 'open-settings':
      return 'Settings open.';
    case 'show-status':
      return 'Status open.';
    case 'open-notes':
    case 'new-note':
      return 'Notes open.';
    case 'open-calendar':
    case 'show-today':
    case 'show-tomorrow':
      return 'Calendar open.';
    case 'open-search':
      return 'Search open.';
    case 'close-menu':
    case 'close-settings':
    case 'close-status':
    case 'hide-status':
    case 'close-notes':
    case 'close-memory':
    case 'close-calendar':
    case 'close-search':
    case 'close-generic':
      return 'Closed.';
    case 'go-home':
      return trimmed;
    case 'save-note':
      return 'Saved.';
    case 'delete-last-note':
      return 'Deleted.';
    case 'clear-notes':
      return 'Notes cleared.';
    case 'read-notes':
      return 'Notes are open.';
    case 'read-memory':
      return trimmed;
    case 'remember-task':
      return 'Task saved.';
    case 'focus-to-tasks':
      return 'Tasks created.';
    case 'mark-task-done':
      return 'Task marked done.';
    case 'delete-last-task':
      return 'Task deleted.';
    case 'clear-done-tasks':
      return 'Completed tasks cleared.';
    case 'refresh-calendar':
      return 'Calendar refreshed.';
    case 'add-calendar-event':
      return 'Event added.';
    case 'edit-last-event':
      return 'Event updated.';
    case 'delete-calendar-event':
      return 'Event deleted.';
    case 'read-calendar':
      return trimmed;
    case 'delete-last-event':
      return 'Event deleted.';
    case 'clear-calendar':
      return 'Calendar cleared.';
    case 'run-search':
      return 'Search complete.';
    case 'clear-search':
      return 'Search cleared.';
    case 'cancel-action':
      return 'Cancelled.';
    case 'voice-output-on':
    case 'voice-output-off':
    case 'voice-output-toggle':
    case 'voice-slower':
    case 'voice-faster':
    case 'voice-normal':
    case 'what-did-you-hear':
      return trimmed;
    default:
      return trimmed;
  }
}

export type ResultToastKind =
  | 'success'
  | 'info'
  | 'warning'
  | 'error'
  | 'search'
  | 'calendar'
  | 'notes';

export type ResultToast = {
  id: string;
  kind: ResultToastKind;
  title: string;
  detail: string;
  createdAt: number;
};

type MemorySyncState = 'local' | 'syncing' | 'synced' | 'error';

export function compactToastDetail(text: string, maxLength = 88): string {
  const cleaned = text
    .replace(/\s+/g, ' ')
    .replace(/^I understood that as:\s*/i, '')
    .trim();

  if (cleaned.length <= maxLength) return cleaned;

  return `${cleaned.slice(0, maxLength - 1).trim()}…`;
}

export function getResultToastForCommand(
  command: string,
  fullText: string,
): Omit<ResultToast, 'id' | 'createdAt'> | null {
  const trimmed = fullText.trim();
  if (!trimmed) return null;

  if (hasFailureLanguage(trimmed)) {
    return {
      kind: 'error',
      title: 'Needs attention',
      detail: compactToastDetail(trimmed, 96),
    };
  }

  switch (command) {
    case 'save-note':
      return {
        kind: 'notes',
        title: 'Saved note',
        detail: 'Added to Notes.',
      };
    case 'delete-last-note':
      return {
        kind: 'notes',
        title: 'Deleted note',
        detail: 'Removed the latest note.',
      };
    case 'clear-notes':
      return {
        kind: 'notes',
        title: 'Notes cleared',
        detail: 'All local notes were removed.',
      };
    case 'read-notes':
      return {
        kind: 'notes',
        title: 'Notes open',
        detail: 'Readout is available in the chat.',
      };
    case 'open-notes':
    case 'new-note':
      return {
        kind: 'notes',
        title: 'Notes open',
        detail: 'Ready for local notes.',
      };
    case 'open-memory':
      return {
        kind: 'info',
        title: 'Memory open',
        detail: 'Tasks and recent actions are visible.',
      };
    case 'read-memory':
      return {
        kind: 'info',
        title: 'Memory summary',
        detail: 'Current tasks and recent work summarized.',
      };
    case 'remember-task':
      return {
        kind: 'success',
        title: 'Task saved',
        detail: compactToastDetail(trimmed),
      };
    case 'focus-to-tasks':
      return {
        kind: 'success',
        title: 'Focus tasks created',
        detail: compactToastDetail(trimmed),
      };
    case 'mark-task-done':
      return {
        kind: 'success',
        title: 'Task complete',
        detail: compactToastDetail(trimmed),
      };
    case 'delete-last-task':
      return {
        kind: 'warning',
        title: 'Task deleted',
        detail: compactToastDetail(trimmed),
      };
    case 'clear-done-tasks':
      return {
        kind: 'warning',
        title: 'Completed tasks cleared',
        detail: compactToastDetail(trimmed),
      };
    case 'close-memory':
      return {
        kind: 'info',
        title: 'Memory closed',
        detail: 'Panel dismissed.',
      };
    case 'add-calendar-event':
      return {
        kind: 'calendar',
        title: 'Event added',
        detail: compactToastDetail(trimmed),
      };
    case 'edit-last-event':
      return {
        kind: 'calendar',
        title: 'Event updated',
        detail: compactToastDetail(trimmed),
      };
    case 'delete-calendar-event':
    case 'delete-last-event':
      return {
        kind: 'calendar',
        title: 'Event deleted',
        detail: compactToastDetail(trimmed),
      };
    case 'refresh-calendar':
      return {
        kind: 'calendar',
        title: 'Calendar refreshed',
        detail: compactToastDetail(trimmed),
      };
    case 'read-calendar':
      return {
        kind: 'calendar',
        title: 'Calendar readout',
        detail: 'Speaking calendar events now.',
      };
    case 'clear-calendar':
      return {
        kind: 'calendar',
        title: 'Local calendar cleared',
        detail: 'Local-only events were removed.',
      };
    case 'open-calendar':
    case 'show-today':
    case 'show-tomorrow':
      return {
        kind: 'calendar',
        title: 'Calendar open',
        detail: 'Calendar panel is visible.',
      };
    case 'run-search':
      return trimmed === 'Opening search.'
        ? {
            kind: 'search',
            title: 'Search open',
            detail: 'Ready for a web query.',
          }
        : {
            kind: 'search',
            title: 'Search complete',
            detail: 'Full result is open in Search.',
          };
    case 'clear-search':
      return {
        kind: 'search',
        title: 'Search cleared',
        detail: 'Previous result removed.',
      };
    case 'open-search':
      return {
        kind: 'search',
        title: 'Search open',
        detail: 'Ready for a web query.',
      };
    case 'open-menu':
      return {
        kind: 'info',
        title: 'Menu open',
        detail: 'Choose a QMeet tool.',
      };
    case 'open-settings':
      return {
        kind: 'info',
        title: 'Settings open',
        detail: 'Voice and display controls.',
      };
    case 'show-status':
      return {
        kind: 'info',
        title: 'Status open',
        detail: 'System dashboard visible.',
      };
    case 'go-home':
      return {
        kind: 'info',
        title: 'Home',
        detail: 'Returned to the orb.',
      };
    case 'close-menu':
    case 'close-settings':
    case 'close-status':
    case 'hide-status':
    case 'close-notes':
    case 'close-calendar':
    case 'close-search':
    case 'close-generic':
      return {
        kind: 'info',
        title: 'Closed',
        detail: 'Panel dismissed.',
      };
    case 'voice-output-on':
    case 'voice-output-off':
    case 'voice-output-toggle':
    case 'voice-slower':
    case 'voice-faster':
    case 'voice-normal':
      return {
        kind: 'info',
        title: 'Voice updated',
        detail: compactToastDetail(trimmed),
      };
    case 'cancel-action':
      return {
        kind: 'warning',
        title: 'Cancelled',
        detail: 'Current action stopped.',
      };
    case 'clear-chat':
      return {
        kind: 'info',
        title: 'Chat cleared',
        detail: 'Conversation reset locally.',
      };
  }

  return null;
}
