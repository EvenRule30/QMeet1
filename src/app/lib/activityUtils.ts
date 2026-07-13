import type { ActivePanel, AssistantActivity, OrbState } from '../types';

export type ActivityInput = {
  orbState: OrbState;
  activePanel: ActivePanel;
  chatActive: boolean;
  searchLoading: boolean;
  googleCalendarLoading: boolean;
  pendingCommand: unknown | null;
  searchQuery: string;
  hasSearchResult: boolean;
  notesCount: number;
  calendarCount: number;
  taskCount: number;
};

export function getPanelLabel(panel: ActivePanel): string {
  switch (panel) {
    case 'menu':
      return 'Menu';
    case 'settings':
      return 'Settings';
    case 'status':
      return 'Status';
    case 'notes':
      return 'Notes';
    case 'calendar':
      return 'Calendar';
    case 'search':
      return 'Search';
    case 'memory':
      return 'Memory';
    default:
      return 'Home';
  }
}


export function getAssistantActivity(input: ActivityInput): AssistantActivity {
  if (input.pendingCommand) {
    return {
      kind: 'confirmation',
      label: 'Confirm action',
      detail: 'Say confirm or cancel',
    };
  }

  if (input.searchLoading) {
    return {
      kind: 'search',
      label: 'Searching web',
      detail: input.searchQuery ? input.searchQuery : 'Gathering results',
    };
  }

  if (input.googleCalendarLoading) {
    return {
      kind: 'calendar',
      label: 'Calendar sync',
      detail: 'Reading Google Calendar',
    };
  }

  if (input.orbState === 'listening') {
    return {
      kind: 'listening',
      label: 'Listening',
      detail: 'Speak naturally',
    };
  }

  if (input.orbState === 'thinking') {
    return {
      kind: 'thinking',
      label: 'Working',
      detail: 'Routing request',
    };
  }

  if (input.orbState === 'speaking') {
    return {
      kind: 'speaking',
      label: 'Responding',
      detail: 'Tap orb to stop',
    };
  }

  if (input.orbState === 'error') {
    return {
      kind: 'error',
      label: 'Needs attention',
      detail: 'Check the message panel',
    };
  }

  if (input.activePanel === 'search') {
    return {
      kind: 'search',
      label: input.hasSearchResult ? 'Search results' : 'Search ready',
      detail: input.searchQuery || 'Ask me to search the web',
    };
  }

  if (input.activePanel === 'calendar') {
    return {
      kind: 'calendar',
      label: 'Calendar open',
      detail: `${input.calendarCount} local event${input.calendarCount === 1 ? '' : 's'}`,
    };
  }

  if (input.activePanel === 'notes') {
    return {
      kind: 'notes',
      label: 'Notes open',
      detail: `${input.notesCount} saved note${input.notesCount === 1 ? '' : 's'}`,
    };
  }

  if (input.activePanel === 'memory') {
    return {
      kind: 'memory',
      label: 'Memory open',
      detail: `${input.taskCount} open task${input.taskCount === 1 ? '' : 's'}`,
    };
  }

  if (input.activePanel === 'settings') {
    return {
      kind: 'settings',
      label: 'Settings',
      detail: 'Voice and display controls',
    };
  }

  if (input.activePanel === 'status') {
    return {
      kind: 'status',
      label: 'Status',
      detail: 'System dashboard open',
    };
  }

  if (input.activePanel === 'menu') {
    return {
      kind: 'navigation',
      label: 'Menu',
      detail: 'Choose a QMeet tool',
    };
  }

  return {
    kind: 'idle',
    label: input.chatActive ? 'Ready' : 'Tap to speak',
    detail: input.chatActive ? 'Ask a follow-up' : 'Voice-first mode',
  };
}
