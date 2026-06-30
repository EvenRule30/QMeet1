import { useState, useCallback, useEffect } from 'react';
import { Orb } from './components/Orb';
import { TopStatusBar } from './components/TopStatusBar';
import { ChatPanel } from './components/ChatPanel';
import { PromptBar } from './components/PromptBar';
import { Message, OrbState, BackendStatus } from './types';
import { sendChatMessage, getBackendStatus } from "./api";
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
  const handleEndChat = useCallback(() => {
    setOrbState('idle');
    setChatActive(false);
    setMessages([]);
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

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setOrbState('thinking');

    try {
      const data = await sendChatMessage(trimmed);

      setOrbState('speaking');

      const assistantMsg: Message = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: data.reply,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMsg]);

      window.setTimeout(() => {
        setOrbState('idle');
      }, 1200);
    } catch (error) {
      console.error('QMeet backend error:', error);

      setOrbState('error');

      const errorMsg: Message = {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content:
          'Backend connection failed. Make sure the QMeet backend is running on http://localhost:8000.',
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, errorMsg]);

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
