import {
  Dispatch,
  SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { streamChatMessage } from '../api';
import { Message, OrbState } from '../types';

const BRIEF_ME_EVENT = 'qmeet:brief-me';

type UseChatStreamControllerOptions = {
  setOrbState: Dispatch<SetStateAction<OrbState>>;
  setChatActive: Dispatch<SetStateAction<boolean>>;
  speakAssistantText: (
    text: string,
    options?: { enabled?: boolean; rate?: number }
  ) => void;
};

function buildBriefingRequest(): string {
  const now = new Date();

  let timeZone = 'local';
  try {
    timeZone =
      Intl.DateTimeFormat().resolvedOptions().timeZone?.trim() || 'local';
  } catch {
    timeZone = 'local';
  }

  const localDateTime = now.toLocaleString([], {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

  return [
    'Brief me on my remaining day.',
    `Current local date and time: ${localDateTime}.`,
    `Current timezone: ${timeZone}.`,
    'Treat calendar events scheduled earlier than the current time as past.',
    'Focus on the next upcoming event, the remaining schedule, one or two useful flexible tasks, and one concrete action to take now.',
  ].join('\n');
}

export function useChatStreamController({
  setOrbState,
  setChatActive,
  speakAssistantText,
}: UseChatStreamControllerOptions) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [showThinkingBubble, setShowThinkingBubble] = useState(false);
  const [responseActive, setResponseActive] = useState(false);
  const responseTokenRef = useRef(0);
  const activeStreamAbortRef = useRef<AbortController | null>(null);

  const cancelActiveResponse = useCallback(() => {
    responseTokenRef.current += 1;

    if (activeStreamAbortRef.current) {
      activeStreamAbortRef.current.abort();
      activeStreamAbortRef.current = null;
    }

    setResponseActive(false);
    setShowThinkingBubble(false);
    setOrbState('idle');
  }, [setOrbState]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  const sendStreamingChat = useCallback(
    async (text: string, visibleUserText: string) => {
      setChatActive(true);

      const now = Date.now();
      const assistantId = `a-${now}`;

      const userMsg: Message = {
        id: `u-${now}`,
        role: 'user',
        content: visibleUserText,
        timestamp: new Date(),
      };

      cancelActiveResponse();

      setMessages((prev) => [...prev, userMsg]);
      setOrbState('thinking');
      setShowThinkingBubble(true);
      setResponseActive(true);

      const responseToken = responseTokenRef.current + 1;
      responseTokenRef.current = responseToken;
      const abortController = new AbortController();
      activeStreamAbortRef.current = abortController;

      let assistantReply = '';

      const upsertAssistantMessage = (
        content: string,
        mode: 'replace' | 'append' = 'append'
      ) => {
        setMessages((prev) => {
          const existingMessage = prev.find((msg) => msg.id === assistantId);

          if (existingMessage) {
            return prev.map((msg) =>
              msg.id === assistantId
                ? {
                    ...msg,
                    content:
                      mode === 'replace' ? content : msg.content + content,
                  }
                : msg
            );
          }

          return [
            ...prev,
            {
              id: assistantId,
              role: 'assistant',
              content,
              timestamp: new Date(),
            },
          ];
        });
      };

      try {
        await streamChatMessage(
          text,
          {
            onStart: () => {
              if (responseTokenRef.current !== responseToken) return;
              setOrbState('thinking');
            },

            onChunk: (chunk) => {
              if (
                responseTokenRef.current !== responseToken ||
                !chunk
              ) {
                return;
              }

              setShowThinkingBubble(false);
              assistantReply += chunk;
              upsertAssistantMessage(chunk, 'append');
            },

            onDone: () => {
              if (responseTokenRef.current !== responseToken) return;
              setShowThinkingBubble(false);
              setResponseActive(false);
              activeStreamAbortRef.current = null;
              speakAssistantText(assistantReply);
            },

            onError: (message) => {
              if (responseTokenRef.current !== responseToken) return;
              setShowThinkingBubble(false);
              setResponseActive(false);
              activeStreamAbortRef.current = null;
              setOrbState('error');
              upsertAssistantMessage(message, 'replace');

              window.setTimeout(() => {
                if (responseTokenRef.current === responseToken) {
                  setOrbState('idle');
                }
              }, 2000);
            },
          },
          { signal: abortController.signal }
        );
      } catch (error) {
        if (
          abortController.signal.aborted ||
          responseTokenRef.current !== responseToken
        ) {
          return;
        }

        console.error('QMeet streaming error:', error);

        activeStreamAbortRef.current = null;
        setShowThinkingBubble(false);
        setResponseActive(false);
        setOrbState('error');
        upsertAssistantMessage(
          'Streaming connection failed. Make sure the QMeet backend is running on http://localhost:8000.',
          'replace'
        );

        window.setTimeout(() => {
          if (responseTokenRef.current === responseToken) {
            setOrbState('idle');
          }
        }, 2000);
      }
    },
    [
      cancelActiveResponse,
      setChatActive,
      setOrbState,
      speakAssistantText,
    ]
  );

  useEffect(() => {
    const handleBriefMe = () => {
      void sendStreamingChat(buildBriefingRequest(), 'Brief me');
    };

    window.addEventListener(BRIEF_ME_EVENT, handleBriefMe);

    return () => {
      window.removeEventListener(BRIEF_ME_EVENT, handleBriefMe);
    };
  }, [sendStreamingChat]);

  return {
    messages,
    setMessages,
    showThinkingBubble,
    setShowThinkingBubble,
    responseActive,
    cancelActiveResponse,
    sendStreamingChat,
    clearMessages,
  };
}
