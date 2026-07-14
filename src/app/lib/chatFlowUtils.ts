import type { Message } from '../types';

export type CommandRoute = 'exact' | 'interpreter' | 'confirmed';

export function createUserMessage(idSeed: number | string, content: string): Message {
  return {
    id: `u-${idSeed}`,
    role: 'user',
    content,
    timestamp: new Date(),
  };
}

export function createAssistantMessage(
  idSeed: number | string,
  content: string,
  variant?: Message['variant'],
): Message {
  return {
    id: `a-${idSeed}`,
    role: 'assistant',
    ...(variant ? { variant } : {}),
    content,
    timestamp: new Date(),
  };
}

export function getLocalCommandRouteLabel(commandRoute: CommandRoute): string {
  if (commandRoute === 'interpreter') return 'Fuzzy interpreter command';
  if (commandRoute === 'confirmed') return 'Confirmed destructive command';
  return 'Exact local command';
}

export function getInterpreterUnavailableReason(error: unknown): string {
  return error instanceof Error ? error.message : 'Interpreter request failed.';
}

export function buildInterpreterDestructivePrompt(frontendCommand: string): string {
  return `I interpreted that as: ${frontendCommand}. This changes or deletes local data. Say "confirm" to run it, or "cancel" to stop.`;
}

export function buildInterpreterClarifyPrompt(frontendCommand: string, destructiveCommand: boolean): string {
  return destructiveCommand
    ? `I think that may mean: ${frontendCommand}. This changes or deletes local data. Say "confirm" to run it, or "cancel" to stop.`
    : `I think that may be a command, but I am not certain. Try saying: "${frontendCommand}".`;
}
