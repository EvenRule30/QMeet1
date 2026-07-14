export function normalizeMemoryLookup(
  value: string,
): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function formatMemoryTime(
  value: string,
): string {
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

export function getCommandActionLabel(
  command: string,
): string {
  switch (command) {
    case 'save-note':
      return 'Saved note';
    case 'delete-last-note':
      return 'Deleted note';
    case 'clear-notes':
      return 'Cleared notes';
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
