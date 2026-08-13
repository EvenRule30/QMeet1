import { QMEET_API_BASE_URL } from '../api';
import type { LocalCommand } from '../commands';
import type { ActivePanel, Message, OrbState } from '../types';
import { hasFailureLanguage } from './toastUtils';

export type ToolContinuationCapability =
  | 'focus'
  | 'calendar'
  | 'search'
  | 'memory'
  | 'tasks'
  | 'notes'
  | 'visual'
  | 'voice'
  | 'ui'
  | 'other';

type StateSetter<T> = (value: T | ((previous: T) => T)) => void;

type ToolContinuationConversationMessage = {
  role: 'user' | 'assistant' | 'tool';
  content: string;
};

type ToolContinuationRequest = {
  userMessage: string;
  capability: ToolContinuationCapability;
  action: string;
  toolResult: string;
  toolContext?: string;
  verified: true;
  success: true;
  verificationSource: 'frontend-deterministic-command';
  recentConversation: ToolContinuationConversationMessage[];
  uiContext: {
    activePanel: ActivePanel;
    command: LocalCommand;
  };
};

type ToolContinuationUiOptions = {
  userMessage: string;
  command: LocalCommand;
  toolResult: string;
  toolContext?: string;
  recentMessages: Message[];
  activePanel: ActivePanel;
  voiceOutputEnabled: boolean;
  setMessages: StateSetter<Message[]>;
  setShowThinkingBubble: StateSetter<boolean>;
  setOrbState: StateSetter<OrbState>;
  speakAssistantText: (
    text: string,
    options?: { enabled?: boolean; rate?: number },
  ) => void;
};

type ParsedServerSentEvent = {
  event: string;
  data: string;
};

const FOCUS_COMMANDS = new Set<LocalCommand>([
  'start-focus-session',
  'update-focus-session',
  'read-focus-session',
  'end-focus-session',
  'focus-to-tasks',
  'summarize-focus-session',
  'save-focus-summary',
  'end-focus-with-summary',
  'read-last-focus-session',
  'read-focus-history',
  'resume-last-focus-session',
  'recap-focus-activity',
  'enhanced-focus-recap',
  'prepare-calendar-focus',
  'create-meeting-follow-up-tasks',
  'wrap-up-meeting-focus',
  'link-visual-to-focus',
  'read-focus-visuals',
]);

const CALENDAR_COMMANDS = new Set<LocalCommand>([
  'add-calendar-event',
  'read-calendar',
  'refresh-calendar',
  'edit-last-event',
  'delete-calendar-event',
  'delete-last-event',
  'clear-calendar',
]);

const SEARCH_COMMANDS = new Set<LocalCommand>(['run-search']);

const NOTES_COMMANDS = new Set<LocalCommand>([
  'new-note',
  'save-note',
  'read-notes',
  'delete-last-note',
  'clear-notes',
]);

const TASK_COMMANDS = new Set<LocalCommand>([
  'remember-task',
  'mark-task-done',
  'delete-last-task',
  'clear-done-tasks',
]);

const MEMORY_COMMANDS = new Set<LocalCommand>(['read-memory']);

const VISUAL_COMMANDS = new Set<LocalCommand>([
  'create-visual-observation',
  'read-visual-context',
  'read-last-visual-observation',
  'read-visual-history',
  'summarize-visual-context',
  'clear-visual-context',
  'delete-last-visual-observation',
]);

const VOICE_COMMANDS = new Set<LocalCommand>([
  'voice-output-on',
  'voice-output-off',
  'voice-output-toggle',
  'voice-slower',
  'voice-faster',
  'voice-normal',
  'stop-speaking',
  'what-did-you-hear',
]);

const TOOL_CARD_COMPLETE_COMMANDS = new Set<LocalCommand>([
  'read-focus-session',
]);

const UI_COMMANDS = new Set<LocalCommand>([
  'help',
  'identity',
  'open-menu',
  'open-notes',
  'close-notes',
  'open-memory',
  'close-memory',
  'open-calendar',
  'close-calendar',
  'show-today',
  'show-tomorrow',
  'open-search',
  'clear-search',
  'close-search',
  'close-menu',
  'open-settings',
  'close-settings',
  'go-home',
  'show-status',
  'close-status',
  'hide-status',
  'cancel-action',
  'clear-chat',
  'end-chat',
  'close-generic',
]);

let activeToolContinuationController: AbortController | null = null;
let continuationMessageSequence = 0;
let continuationRunToken = 0;

export function getToolContinuationCapability(
  command: LocalCommand,
): ToolContinuationCapability {
  if (FOCUS_COMMANDS.has(command)) return 'focus';
  if (CALENDAR_COMMANDS.has(command)) return 'calendar';
  if (SEARCH_COMMANDS.has(command)) return 'search';
  if (NOTES_COMMANDS.has(command)) return 'notes';
  if (TASK_COMMANDS.has(command)) return 'tasks';
  if (MEMORY_COMMANDS.has(command)) return 'memory';
  if (VISUAL_COMMANDS.has(command)) return 'visual';
  if (VOICE_COMMANDS.has(command)) return 'voice';
  if (UI_COMMANDS.has(command)) return 'ui';
  return 'other';
}

export function shouldRequestToolContinuation(
  command: LocalCommand,
  toolResult: string,
): boolean {
  if (hasFailureLanguage(toolResult)) return false;
  if (TOOL_CARD_COMPLETE_COMMANDS.has(command)) return false;

  const capability = getToolContinuationCapability(command);
  return capability !== 'voice' && capability !== 'ui';
}

export function cancelActiveToolContinuation(): void {
  continuationRunToken += 1;
  activeToolContinuationController?.abort();
  activeToolContinuationController = null;
}

function buildRecentConversation(
  messages: Message[],
): ToolContinuationConversationMessage[] {
  return messages
    .slice(-10)
    .map((message): ToolContinuationConversationMessage | null => {
      const content = message.content.trim();
      if (!content) return null;

      if (message.role === 'assistant' && message.variant === 'tool') {
        return { role: 'tool', content };
      }

      return {
        role: message.role,
        content,
      };
    })
    .filter(
      (
        message,
      ): message is ToolContinuationConversationMessage => message !== null,
    );
}

function buildRequest(
  options: ToolContinuationUiOptions,
): ToolContinuationRequest {
  return {
    userMessage: options.userMessage.trim(),
    capability: getToolContinuationCapability(options.command),
    action: options.command,
    toolResult: options.toolResult.trim(),
    toolContext: options.toolContext?.trim() || undefined,
    verified: true,
    success: true,
    verificationSource: 'frontend-deterministic-command',
    recentConversation: buildRecentConversation(options.recentMessages),
    uiContext: {
      activePanel: options.activePanel,
      command: options.command,
    },
  };
}

function parseServerSentEvent(rawEvent: string): ParsedServerSentEvent | null {
  const lines = rawEvent.split('\n');
  let event = 'message';
  const dataLines: string[] = [];

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(':')) continue;

    const separatorIndex = line.indexOf(':');
    const field = separatorIndex === -1 ? line : line.slice(0, separatorIndex);
    let value = separatorIndex === -1 ? '' : line.slice(separatorIndex + 1);
    if (value.startsWith(' ')) value = value.slice(1);

    if (field === 'event') {
      event = value.trim() || 'message';
    } else if (field === 'data') {
      dataLines.push(value);
    }
  }

  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join('\n') };
}

function getEventPayload(rawData: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(rawData) as unknown;
    return parsed && typeof parsed === 'object'
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    throw new Error('Malformed tool-continuation streaming event.');
  }
}

function getPayloadString(
  payload: Record<string, unknown>,
  key: string,
): string {
  const value = payload[key];
  return typeof value === 'string' ? value : '';
}

function createContinuationMessageId(): string {
  continuationMessageSequence += 1;
  return `tool-continuation-${Date.now()}-${continuationMessageSequence}`;
}

function appendOrUpdateContinuationMessage(
  setMessages: StateSetter<Message[]>,
  messageId: string,
  content: string,
): void {
  setMessages((previous) => {
    const existingIndex = previous.findIndex(
      (message) => message.id === messageId,
    );

    if (existingIndex === -1) {
      const assistantMessage: Message = {
        id: messageId,
        role: 'assistant',
        content,
        timestamp: new Date(),
      };
      return [...previous, assistantMessage];
    }

    return previous.map((message, index) =>
      index === existingIndex
        ? {
            ...message,
            content,
          }
        : message,
    );
  });
}

function removeContinuationMessage(
  setMessages: StateSetter<Message[]>,
  messageId: string,
): void {
  setMessages((previous) =>
    previous.filter((message) => message.id !== messageId),
  );
}

async function readContinuationStream(
  response: Response,
  signal: AbortSignal,
  onChunk: (chunk: string) => void,
): Promise<void> {
  if (!response.body) {
    throw new Error('Tool continuation response body was empty.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let terminalEventSeen = false;

  const processRawEvent = (rawEvent: string) => {
    if (!rawEvent.trim() || terminalEventSeen) return;

    const parsedEvent = parseServerSentEvent(rawEvent);
    if (!parsedEvent) return;

    const payload = getEventPayload(parsedEvent.data);
    if (parsedEvent.event === 'chunk') {
      onChunk(getPayloadString(payload, 'text'));
      return;
    }

    if (parsedEvent.event === 'done') {
      terminalEventSeen = true;
      return;
    }

    if (parsedEvent.event === 'error') {
      terminalEventSeen = true;
      throw new Error(
        getPayloadString(payload, 'message') ||
          'QMeet could not generate a post-tool continuation.',
      );
    }
  };

  const processBufferedEvents = () => {
    let boundaryIndex = buffer.indexOf('\n\n');
    while (boundaryIndex !== -1) {
      const rawEvent = buffer.slice(0, boundaryIndex);
      buffer = buffer.slice(boundaryIndex + 2);
      processRawEvent(rawEvent);
      boundaryIndex = buffer.indexOf('\n\n');
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder
        .decode(value, { stream: true })
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n');
      processBufferedEvents();
    }

    buffer += decoder.decode().replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    processBufferedEvents();

    const finalBufferedEvent = buffer.trim();
    if (finalBufferedEvent) processRawEvent(finalBufferedEvent);

    if (!terminalEventSeen && !signal.aborted) {
      throw new Error(
        'Tool continuation stream closed before QMeet finished the response.',
      );
    }
  } finally {
    reader.releaseLock();
  }
}

export async function continueAfterVerifiedToolUpdate(
  options: ToolContinuationUiOptions,
): Promise<void> {
  if (!shouldRequestToolContinuation(options.command, options.toolResult)) {
    return;
  }

  cancelActiveToolContinuation();
  continuationRunToken += 1;
  const runToken = continuationRunToken;
  const controller = new AbortController();
  activeToolContinuationController = controller;

  const messageId = createContinuationMessageId();
  let reply = '';
  let visibleChunkSeen = false;
  let handedOffToSpeech = false;

  options.setShowThinkingBubble(true);
  options.setOrbState('thinking');

  try {
    const response = await fetch(
      `${QMEET_API_BASE_URL}/api/chat/tool-continuation/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(buildRequest(options)),
        signal: controller.signal,
      },
    );

    if (!response.ok) {
      throw new Error(
        `Tool continuation backend returned ${response.status}.`,
      );
    }

    await readContinuationStream(response, controller.signal, (chunk) => {
      if (!chunk || runToken !== continuationRunToken) return;

      reply += chunk;
      if (!visibleChunkSeen) {
        visibleChunkSeen = true;
        options.setShowThinkingBubble(false);
      }
      appendOrUpdateContinuationMessage(
        options.setMessages,
        messageId,
        reply,
      );
    });

    const finalReply = reply.trim();
    if (finalReply && runToken === continuationRunToken) {
      handedOffToSpeech = true;
      options.speakAssistantText(finalReply, {
        enabled: options.voiceOutputEnabled,
      });
    }
  } catch (error) {
    if (!controller.signal.aborted && runToken === continuationRunToken) {
      if (visibleChunkSeen) {
        removeContinuationMessage(options.setMessages, messageId);
      }
      console.warn(
        'Post-tool conversational continuation failed; preserving the verified tool result without retrying the tool.',
        error,
      );
    }
  } finally {
    if (runToken !== continuationRunToken) return;
    if (activeToolContinuationController === controller) {
      activeToolContinuationController = null;
    }
    options.setShowThinkingBubble(false);
    if (!controller.signal.aborted && !handedOffToSpeech) {
      options.setOrbState('idle');
    }
  }
}
