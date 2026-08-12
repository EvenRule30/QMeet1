import { QMEET_API_BASE_URL } from '../api';
import type { ActivePanel, Message, OrbState } from '../types';


type StateSetter<T> = (value: T | ((previous: T) => T)) => void;

type ConversationLaneMessage = {
  role: 'user' | 'assistant' | 'tool';
  content: string;
};

export type ConversationOwnershipHint = {
  source: 'agent-shadow';
  turnOwner: 'general_chat' | 'focus';
  focusRelevant: boolean;
  confidence: number;
  turnId: string;
};

type ConversationLaneRequest = {
  userMessage: string;
  recentConversation: ConversationLaneMessage[];
  uiContext: {
    activePanel: ActivePanel;
  };
  ownershipHint: ConversationOwnershipHint | null;
};

type ConversationLaneUiOptions = {
  userMessage: string;
  visibleUserText: string;
  recentMessages: Message[];
  activePanel: ActivePanel;
  ownershipHint?: ConversationOwnershipHint | null;
  voiceOutputEnabled: boolean;
  setMessages: StateSetter<Message[]>;
  setShowThinkingBubble: StateSetter<boolean>;
  setOrbState: StateSetter<OrbState>;
  setChatActive: StateSetter<boolean>;
  setConversationResponseActive: StateSetter<boolean>;
  speakAssistantText: (
    text: string,
    options?: { enabled?: boolean; rate?: number },
  ) => void;
};

type ParsedServerSentEvent = {
  event: string;
  data: string;
};

let activeConversationLaneController: AbortController | null = null;
let conversationMessageSequence = 0;
let conversationRunToken = 0;

type PromotedConversationOwner = 'general_chat' | 'focus';
const conversationMessageOwners = new Map<string, PromotedConversationOwner>();
const CONVERSATION_OWNER_REGISTRY_LIMIT = 240;

function getPromotedConversationOwner(
  hint: ConversationOwnershipHint | null | undefined,
): PromotedConversationOwner | null {
  if (!hint) return null;
  return hint.turnOwner;
}

function rememberConversationMessageOwner(
  messageId: string,
  owner: PromotedConversationOwner | null,
): void {
  if (!owner) return;
  conversationMessageOwners.set(messageId, owner);
  while (conversationMessageOwners.size > CONVERSATION_OWNER_REGISTRY_LIMIT) {
    const oldestKey = conversationMessageOwners.keys().next().value as string | undefined;
    if (!oldestKey) break;
    conversationMessageOwners.delete(oldestKey);
  }
}

export function cancelActiveConversationLane(): void {
  conversationRunToken += 1;
  activeConversationLaneController?.abort();
  activeConversationLaneController = null;
}

function buildRecentConversation(
  messages: Message[],
  ownershipHint: ConversationOwnershipHint | null | undefined,
): ConversationLaneMessage[] {
  const promotedOwner = getPromotedConversationOwner(ownershipHint);
  const recentMessages = promotedOwner === 'general_chat'
    ? messages.filter(
        (message) => conversationMessageOwners.get(message.id) === 'general_chat',
      )
    : messages;

  return recentMessages
    .slice(-10)
    .map((message): ConversationLaneMessage | null => {
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
      (message): message is ConversationLaneMessage => message !== null,
    );
}

function buildRequest(options: ConversationLaneUiOptions): ConversationLaneRequest {
  return {
    userMessage: options.userMessage.trim(),
    recentConversation: buildRecentConversation(
      options.recentMessages,
      options.ownershipHint,
    ),
    uiContext: {
      activePanel: options.activePanel,
    },
    ownershipHint: options.ownershipHint ?? null,
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
    throw new Error('Malformed conversation streaming event.');
  }
}

function getPayloadString(
  payload: Record<string, unknown>,
  key: string,
): string {
  const value = payload[key];
  return typeof value === 'string' ? value : '';
}

function createUserMessage(
  content: string,
  owner: PromotedConversationOwner | null,
): Message {
  conversationMessageSequence += 1;
  const id = `conversation-user-${Date.now()}-${conversationMessageSequence}`;
  rememberConversationMessageOwner(id, owner);
  return {
    id,
    role: 'user',
    content,
    timestamp: new Date(),
  };
}

function createAssistantMessageId(
  owner: PromotedConversationOwner | null,
): string {
  conversationMessageSequence += 1;
  const id = `conversation-assistant-${Date.now()}-${conversationMessageSequence}`;
  rememberConversationMessageOwner(id, owner);
  return id;
}

function appendOrUpdateAssistantMessage(
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

async function readConversationStream(
  response: Response,
  signal: AbortSignal,
  onChunk: (chunk: string) => void,
): Promise<void> {
  if (!response.body) {
    throw new Error('Conversation response body was empty.');
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
          'QMeet could not generate a conversation response.',
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
        'Conversation stream closed before QMeet finished the response.',
      );
    }
  } finally {
    reader.releaseLock();
  }
}

export async function sendConversationLaneMessage(
  options: ConversationLaneUiOptions,
): Promise<void> {
  const userMessage = options.userMessage.trim();
  const visibleUserText = options.visibleUserText.trim() || userMessage;
  if (!userMessage || !visibleUserText) return;

  cancelActiveConversationLane();
  conversationRunToken += 1;
  const runToken = conversationRunToken;
  const controller = new AbortController();
  activeConversationLaneController = controller;

  const promotedOwner = getPromotedConversationOwner(options.ownershipHint);
  const assistantMessageId = createAssistantMessageId(promotedOwner);
  let reply = '';
  let visibleChunkSeen = false;
  let handedOffToSpeech = false;

  options.setChatActive(true);
  options.setConversationResponseActive(true);
  options.setShowThinkingBubble(true);
  options.setOrbState('thinking');
  options.setMessages((previous) => [
    ...previous,
    createUserMessage(visibleUserText, promotedOwner),
  ]);

  try {
    const response = await fetch(
      `${QMEET_API_BASE_URL}/api/chat/conversation/stream`,
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
      throw new Error(`Conversation backend returned ${response.status}.`);
    }

    await readConversationStream(response, controller.signal, (chunk) => {
      if (!chunk || runToken !== conversationRunToken) return;

      reply += chunk;
      if (!visibleChunkSeen) {
        visibleChunkSeen = true;
        options.setShowThinkingBubble(false);
      }
      appendOrUpdateAssistantMessage(
        options.setMessages,
        assistantMessageId,
        reply,
      );
    });

    const finalReply = reply.trim();
    if (finalReply && runToken === conversationRunToken) {
      handedOffToSpeech = true;
      options.speakAssistantText(finalReply, {
        enabled: options.voiceOutputEnabled,
      });
    }
  } catch (error) {
    if (!controller.signal.aborted && runToken === conversationRunToken) {
      console.error('Conversation lane failed:', error);
      appendOrUpdateAssistantMessage(
        options.setMessages,
        assistantMessageId,
        'I could not generate that response just now.',
      );
    }
  } finally {
    if (runToken !== conversationRunToken) return;
    if (activeConversationLaneController === controller) {
      activeConversationLaneController = null;
    }
    options.setConversationResponseActive(false);
    options.setShowThinkingBubble(false);
    if (!controller.signal.aborted && !handedOffToSpeech) {
      options.setOrbState('idle');
    }
  }
}
