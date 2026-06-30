import { useState, useCallback, useEffect } from 'react';
import { Orb } from './components/Orb';
import { TopStatusBar } from './components/TopStatusBar';
import { ChatPanel } from './components/ChatPanel';
import { PromptBar } from './components/PromptBar';
import { Message, OrbState, BackendStatus } from './types';
import { streamChatMessage, getBackendStatus, resetConversation } from "./api";
import './App.css';

export default function App() {
  const [chatActive, setChatActive] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [messages, setMessages] = useState<Message[]>([]);
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null);

  // Fetch and poll backend status
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const status = await getBackendStatus();
        setBackendStatus(status);
      } catch (error) {
        setBackendStatus(null);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  // End chat and return to idle state
  const handleEndChat = useCallback(async () => {
    setOrbState('idle');
    setChatActive(false);
    setMessages([]);

    try {
      await resetConversation();
    } catch (error) {
      console.error('Reset conversation error:', error);
    }
  }, []);

  // TODO: Backend integration
  // Replace this function body with actual FastAPI calls:
  //
  // Option 1: WebSocket streaming
  //   const ws = useRef<WebSocket | null>(null);
  //   useEffect(() => {
  //     ws.current = new WebSocket('ws://localhost:8000/ws/chat');
  //     ws.current.onmessage = (e) => {
  //       const data = JSON.parse(e.data);
  //       // Append assistant message chunks or complete message
  //     };
  //   }, []);
  //
  // Option 2: REST with polling
  //   const res = await fetch('http://localhost:8000/api/chat', {
  //     method: 'POST',
  //     headers: { 'Content-Type': 'application/json' },
  //     body: JSON.stringify({ message: text }),
  //   });
  //   const data = await res.json();
  //   // data.reply contains the assistant response
  //
  const handleSend = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    if (!chatActive) setChatActive(true);

    const now = Date.now();
    const assistantId = `a-${now}`;

    const userMsg: Message = {
      id: `u-${now}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };

    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setOrbState('thinking');

    try {
      await streamChatMessage(trimmed, {
        onStart: () => {
          setOrbState('speaking');
        },

        onChunk: (chunk) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantId
                ? { ...msg, content: msg.content + chunk }
                : msg
            )
          );
        },

        onDone: () => {
          setOrbState('idle');
        },

        onError: (message) => {
          setOrbState('error');

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantId
                ? { ...msg, content: message }
                : msg
            )
          );

          window.setTimeout(() => {
            setOrbState('idle');
          }, 2000);
        },
      });
    } catch (error) {
      console.error('QMeet streaming error:', error);

      setOrbState('error');

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                content:
                  'Streaming connection failed. Make sure the QMeet backend is running on http://localhost:8000.',
              }
            : msg
        )
      );

      window.setTimeout(() => {
        setOrbState('idle');
      }, 2000);
    }
  }, [chatActive]);

  // TODO: Backend integration for voice capture
  // Replace this with actual STT (speech-to-text) stream:
  // - Listen for audio from microphone
  // - Send audio chunks to backend
  // - Transition to 'thinking' state when transcription complete
  //
  const handleOrbClick = useCallback(() => {
    if (chatActive) return;
    setOrbState('listening');
    setTimeout(() => {
      setChatActive(true);
      setOrbState('idle');
    }, 1600);
  }, [chatActive]);

  return (
    <div className="agent-screen">
      <TopStatusBar orbState={orbState} chatActive={chatActive} onEnd={handleEndChat} backendStatus={backendStatus} />

      <div className="agent-body">
        {/* Orb area: full width when idle, 38% when chat active */}
        <div
          className={`orb-area${chatActive ? ' orb-area-active' : ''}`}
          onClick={handleOrbClick}
          role="button"
          aria-label="QMeet orb — tap to activate"
        >
          <Orb state={orbState} active={chatActive} />

          {!chatActive && (
            <div className="idle-hint">
              <span>Ask QMeet anything…</span>
            </div>
          )}
        </div>

        {/* Chat area: hidden when idle, 62% when active */}
        <div className={`chat-area ${chatActive ? 'chat-area-visible' : 'chat-area-hidden'}`}>
          <ChatPanel messages={messages} orbState={orbState} />
          <PromptBar onSend={handleSend} disabled={orbState === 'thinking'} />
        </div>
      </div>
    </div>
  );
}
