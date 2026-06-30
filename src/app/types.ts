export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

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
