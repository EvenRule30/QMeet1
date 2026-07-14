export const COMMAND_INTERPRETER_EXECUTE_THRESHOLD =
  0.8;
export const COMMAND_INTERPRETER_CLARIFY_THRESHOLD =
  0.5;

export type PendingInterpreterCommand = {
  originalText: string;
  frontendCommand: string;
  action: string;
  confidence: number;
  reason: string;
};

const DESTRUCTIVE_FRONTEND_COMMANDS = new Set([
  'clear chat',
  'end chat',
  'delete last note',
  'clear notes',
  'mark task done',
  'delete last task',
  'clear completed tasks',
  'delete last event',
  'delete event',
  'edit last event',
  'clear calendar',
]);

const DESTRUCTIVE_LOCAL_COMMANDS = new Set([
  'clear-chat',
  'end-chat',
  'delete-last-note',
  'clear-notes',
  'mark-task-done',
  'delete-last-task',
  'clear-done-tasks',
  'delete-last-event',
  'delete-calendar-event',
  'edit-last-event',
  'clear-calendar',
]);

const LOCAL_COMMAND_TO_FRONTEND_COMMAND:
  Record<string, string> = {
    'clear-chat': 'clear chat',
    'end-chat': 'end chat',
    'delete-last-note': 'delete last note',
    'clear-notes': 'clear notes',
    'mark-task-done': 'mark task done',
    'delete-last-task': 'delete last task',
    'clear-done-tasks': 'clear completed tasks',
    'delete-last-event': 'delete last event',
    'delete-calendar-event': 'delete event',
    'edit-last-event': 'edit last event',
    'clear-calendar': 'clear calendar',
  };

export function normalizePendingDecisionText(
  text: string,
): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[?!.,;:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function isDestructiveInterpreterCommand(
  frontendCommand: string,
): boolean {
  const normalizedCommand =
    normalizePendingDecisionText(frontendCommand);

  return (
    DESTRUCTIVE_FRONTEND_COMMANDS.has(
      normalizedCommand,
    ) ||
    /^delete event\b/.test(normalizedCommand)
  );
}

export function isDestructiveLocalCommand(
  command: string,
): boolean {
  return DESTRUCTIVE_LOCAL_COMMANDS.has(command);
}

export function getFrontendCommandForLocalCommand(
  command: string,
): string {
  return (
    LOCAL_COMMAND_TO_FRONTEND_COMMAND[command] ??
    command.replace(/-/g, ' ')
  );
}

export function isConfirmingPendingCommand(
  text: string,
): boolean {
  return /^(?:yes|yeah|yep|correct|confirm|confirmed|do it|run it|execute it|go ahead|proceed|that is right|that's right)$/i.test(
    normalizePendingDecisionText(text),
  );
}

export function isRejectingPendingCommand(
  text: string,
): boolean {
  return /^(?:no|nope|cancel|cancel it|cancel that|stop|nevermind|never mind|do not|don't|dont|abort|forget it|forget that)$/i.test(
    normalizePendingDecisionText(text),
  );
}
