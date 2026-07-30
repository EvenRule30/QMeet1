import type { LocalCommand } from '../commands';

const MEANINGFUL_RECENT_ACTION_COMMANDS = new Set<LocalCommand>([
  'save-note',
  'delete-last-note',
  'clear-notes',
  'start-focus-session',
  'update-focus-session',
  'end-focus-session',
  'focus-to-tasks',
  'summarize-focus-session',
  'save-focus-summary',
  'end-focus-with-summary',
  'resume-last-focus-session',
  'prepare-calendar-focus',
  'create-meeting-follow-up-tasks',
  'wrap-up-meeting-focus',
  'create-visual-observation',
  'link-visual-to-focus',
  'clear-visual-context',
  'delete-last-visual-observation',
  'remember-task',
  'mark-task-done',
  'delete-last-task',
  'run-search',
  'add-calendar-event',
  'edit-last-event',
  'delete-calendar-event',
  'delete-last-event',
  'clear-calendar',
]);

export function normalizeMemoryLookup(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function formatMemoryTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Saved';
  }

  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function shouldRecordRecentAction(command: LocalCommand): boolean {
  return MEANINGFUL_RECENT_ACTION_COMMANDS.has(command);
}

export function getCommandActionLabel(command: string): string {
  switch (command) {
    case 'save-note':
      return 'Saved note';
    case 'delete-last-note':
      return 'Deleted note';
    case 'clear-notes':
      return 'Cleared notes';
    case 'start-focus-session':
      return 'Started focus session';
    case 'update-focus-session':
      return 'Updated focus session';
    case 'read-focus-session':
      return 'Read focus session';
    case 'focus-to-tasks':
      return 'Created focus tasks';
    case 'summarize-focus-session':
      return 'Summarized focus session';
    case 'save-focus-summary':
      return 'Saved focus summary';
    case 'end-focus-with-summary':
      return 'Ended focus with summary';
    case 'end-focus-session':
      return 'Ended focus session';
    case 'resume-last-focus-session':
      return 'Resumed focus session';
    case 'prepare-calendar-focus':
      return 'Prepared meeting focus';
    case 'create-meeting-follow-up-tasks':
      return 'Created meeting follow-up tasks';
    case 'wrap-up-meeting-focus':
      return 'Wrapped up meeting focus';
    case 'create-visual-observation':
      return 'Saved visual observation';
    case 'link-visual-to-focus':
      return 'Linked visual context to focus';
    case 'clear-visual-context':
      return 'Cleared visual context';
    case 'delete-last-visual-observation':
      return 'Deleted visual observation';
    case 'remember-task':
      return 'Saved task';
    case 'mark-task-done':
      return 'Completed task';
    case 'delete-last-task':
      return 'Deleted task';
    case 'clear-done-tasks':
      return 'Cleared completed tasks';
    case 'run-search':
      return 'Searched web';
    case 'clear-search':
      return 'Cleared search';
    case 'add-calendar-event':
      return 'Added calendar event';
    case 'edit-last-event':
      return 'Edited calendar event';
    case 'delete-calendar-event':
    case 'delete-last-event':
      return 'Deleted calendar event';
    case 'clear-calendar':
      return 'Cleared calendar';
    case 'read-calendar':
      return 'Read calendar';
    case 'read-notes':
      return 'Read notes';
    case 'read-memory':
      return 'Read memory';
    default:
      return command.replace(/-/g, ' ');
  }
}
