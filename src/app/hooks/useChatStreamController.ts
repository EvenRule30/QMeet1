import {
  Dispatch,
  SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { QMEET_API_BASE_URL, streamChatMessage } from '../api';
import { buildBriefingRequest, isBriefingRequest } from '../lib/briefingUtils';
import { Message, OrbState } from '../types';

const BRIEF_ME_EVENT = 'qmeet:brief-me';

function buildStreamingFailureMessage(error: unknown): string {
  const connectionHint = `Make sure the QMeet backend is running at ${QMEET_API_BASE_URL}.`;

  if (error instanceof Error && error.message.trim()) {
    const message = error.message.trim();

    if (message.includes(QMEET_API_BASE_URL)) {
      return message;
    }

    return `${message}\n${connectionHint}`;
  }

  return `Streaming connection failed.\n${connectionHint}`;
}

type UseChatStreamControllerOptions = {
  setOrbState: Dispatch<SetStateAction<OrbState>>;
  setChatActive: Dispatch<SetStateAction<boolean>>;
  speakAssistantText: (
    text: string,
    options?: { enabled?: boolean; rate?: number },
  ) => void;
};

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
      const requestText = isBriefingRequest(text) ? buildBriefingRequest() : text;
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
        mode: 'replace' | 'append' = 'append',
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
                : msg,
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
          requestText,
          {
            onStart: () => {
              if (responseTokenRef.current !== responseToken) return;
              setOrbState('thinking');
            },
            onChunk: (chunk) => {
              if (responseTokenRef.current !== responseToken || !chunk) {
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
          { signal: abortController.signal },
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
        upsertAssistantMessage(buildStreamingFailureMessage(error), 'replace');

        window.setTimeout(() => {
          if (responseTokenRef.current === responseToken) {
            setOrbState('idle');
          }
        }, 2000);
      }
    },
    [cancelActiveResponse, setChatActive, setOrbState, speakAssistantText],
  );

  useEffect(() => {
    const handleBriefMe = () => {
      void sendStreamingChat('brief me', 'Brief me');
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
