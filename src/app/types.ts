export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';
export type ActivePanel = 'none' | 'menu' | 'settings' | 'status' | 'notes' | 'calendar' | 'search';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export interface BackendStatus {
  ok: boolean;
  provider: string;
  model: string;
  hasOpenAIKey: boolean;
  maxOutputTokens: number;
}

export interface Note {
  id: string;
  content: string;
  createdAt: string;
}

export interface CalendarEvent {
  id: string;
  title: string;
  dateKey: string;
  time: string;
  createdAt: string;
}


export type CommandIntentName = 'command' | 'chat';

export type CommandAction =
  | 'none'
  | 'open_panel'
  | 'close_panel'
  | 'go_home'
  | 'clear_chat'
  | 'end_chat'
  | 'save_note'
  | 'read_notes'
  | 'delete_last_note'
  | 'clear_notes'
  | 'prepare_search'
  | 'clear_search'
  | 'add_calendar_event'
  | 'read_calendar'
  | 'delete_last_calendar_event'
  | 'clear_calendar'
  | 'voice_output_on'
  | 'voice_output_off'
  | 'voice_slower'
  | 'voice_faster'
  | 'voice_normal'
  | 'cancel';

export interface CommandIntentResponse {
  intent: CommandIntentName;
  action: CommandAction;
  confidence: number;
  frontendCommand: string;
  payload: Record<string, unknown>;
  reason?: string;
}
