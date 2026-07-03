export type LocalCommand = 
  | 'open-menu'
  | 'close-menu'
  | 'open-settings'
  | 'close-settings'
  | 'go-home'
  | 'show-status'
  | 'hide-status'
  | 'clear-chat'
  | 'end-chat';

export type ActivePanel = 'none' | 'menu' | 'settings' | 'status';

interface CommandMatch {
  command: LocalCommand;
  confirmation: string;
}

const COMMAND_PATTERNS: Record<LocalCommand, RegExp> = {
  'open-menu': /^(?:open\s+)?menu$/i,
  'close-menu': /^(?:close\s+)?menu$/i,
  'open-settings': /^(?:open\s+)?settings?$/i,
  'close-settings': /^(?:close\s+)?settings?$/i,
  'go-home': /^(?:go\s+)?home$/i,
  'show-status': /^(?:show\s+)?status$/i,
  'hide-status': /^(?:hide\s+)?status$/i,
  'clear-chat': /^clear(?:\s+chat)?$/i,
  'end-chat': /^(?:end|exit|quit)(?:\s+chat)?$/i,
};

const CONFIRMATIONS: Record<LocalCommand, string> = {
  'open-menu': 'Opening menu.',
  'close-menu': 'Closing menu.',
  'open-settings': 'Opening settings.',
  'close-settings': 'Closing settings.',
  'go-home': 'Going home.',
  'show-status': 'Showing status.',
  'hide-status': 'Hiding status.',
  'clear-chat': 'Chat cleared.',
  'end-chat': 'Ending conversation.',
};

export function parseCommand(text: string): CommandMatch | null {
  const trimmed = text.trim();

  for (const [command, pattern] of Object.entries(COMMAND_PATTERNS)) {
    if (pattern.test(trimmed)) {
      return {
        command: command as LocalCommand,
        confirmation: CONFIRMATIONS[command as LocalCommand],
      };
    }
  }

  return null;
}
