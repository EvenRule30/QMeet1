import { useState, useCallback, useEffect, useRef } from 'react';
import { Orb } from './components/Orb';
import { TopStatusBar } from './components/TopStatusBar';
import { ChatPanel } from './components/ChatPanel';
import { PromptBar } from './components/PromptBar';
import { Message, OrbState, BackendStatus, ActivePanel } from './types';
import { streamChatMessage, getBackendStatus, resetConversation } from "./api";
import { getSpeechRecognition, isSpeechRecognitionSupported } from './speechRecognition';
import { parseCommand } from './commands';
import './App.css';

export default function App() {
  const [chatActive, setChatActive] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>('idle');
  const [messages, setMessages] = useState<Message[]>([]);
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null);
  const [activePanel, setActivePanel] = useState<ActivePanel>('none');
  const recognitionRef = useRef<InstanceType<ReturnType<typeof getSpeechRecognition>> | null>(null);
  const transcriptSentRef = useRef(false);
  const listeningTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const suppressNextSpeechErrorRef = useRef(false);

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

  // Cleanup speech recognition state
  const finishListening = useCallback(() => {
    if (listeningTimeoutRef.current) {
      clearTimeout(listeningTimeoutRef.current);
      listeningTimeoutRef.current = null;
    }

    if (recognitionRef.current) {
      try {
        suppressNextSpeechErrorRef.current = true;
        recognitionRef.current.abort();
      } catch (error) {
        console.error('Error aborting recognition:', error);
      }
      recognitionRef.current = null;
    }

    transcriptSentRef.current = false;
    setOrbState('idle');
  }, []);

  // End chat and return to idle state
  const handleEndChat = useCallback(async () => {
    finishListening();
    setChatActive(false);
    setMessages([]);

    try {
      await resetConversation();
    } catch (error) {
      console.error('Reset conversation error:', error);
    }
  }, [finishListening]);

  const closePanel = useCallback(() => {
    setActivePanel('none');
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

    const commandMatch = parseCommand(trimmed);
    
    if (commandMatch) {
      finishListening();

      if (!chatActive) setChatActive(true);

      const now = Date.now();
      
      const userMsg: Message = {
        id: `u-${now}`,
        role: 'user',
        content: trimmed,
        timestamp: new Date(),
      };
      
      const confirmationMsg: Message = {
        id: `a-${now}`,
        role: 'assistant',
        content: 
        commandMatch.command === 'close-generic' && activePanel === 'none'
            ? 'No panel is open.'
            : commandMatch.confirmation,
        timestamp: new Date(),
      };
      
      setMessages((prev) => [...prev, userMsg, confirmationMsg]);
      
      if (commandMatch.command === 'open-menu') {
        setActivePanel('menu');
      } else if (commandMatch.command === 'close-menu') {
        closePanel();
      } else if (commandMatch.command === 'open-settings') {
        setActivePanel('settings');
      } else if (commandMatch.command === 'close-settings') {
        closePanel();
      } else if (commandMatch.command === 'go-home') {
        closePanel();
      } else if (commandMatch.command === 'show-status') {
        setActivePanel('status');
      } else if (commandMatch.command === 'close-status') {
        closePanel();
      } else if (commandMatch.command === 'hide-status') {
        closePanel();
      } else if (commandMatch.command === 'close-generic') {
        if (activePanel !== 'none') {
          closePanel();
        }
      } else if (commandMatch.command === 'clear-chat') {
        setMessages([userMsg, confirmationMsg]);
      } else if (commandMatch.command === 'end-chat') {
        await handleEndChat();
      }
      
      return;
    }

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
  }, [chatActive, activePanel, handleEndChat, finishListening, closePanel]);

  const handleOrbClick = useCallback(() => {
    if (orbState !== 'idle') return;

    if (!isSpeechRecognitionSupported()) {
      setChatActive(true);
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: 'Voice input is not supported in this browser. Please use the text input instead.',
          timestamp: new Date(),
        },
      ]);
      return;
    }

    setOrbState('listening');
    transcriptSentRef.current = false;

    const SpeechRecognitionClass = getSpeechRecognition();

    if (!SpeechRecognitionClass) {
      setOrbState('idle');
      return;
    }

    const recognition = new SpeechRecognitionClass();
    recognitionRef.current = recognition;

    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    
    recognition.onstart = () => {
      setOrbState('listening');

      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
      }

      listeningTimeoutRef.current = setTimeout(() => {
        if (recognitionRef.current) {
          recognitionRef.current.abort();
        }

        if (!transcriptSentRef.current) {
          setChatActive(true);
          setOrbState('idle');
          setMessages((prev) => [
            ...prev,
            {
              id: `a-${Date.now()}`,
              role: 'assistant',
              content: 'I did not catch that. Tap the orb and try again.',
              timestamp: new Date(),
            },
          ]);
        }
      }, 8000);
    };
    
    recognition.onresult = (event: any) => {
      if (transcriptSentRef.current) return;

      let transcript = '';
    
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcriptSegment = event.results[i][0].transcript;
        transcript += transcriptSegment;
    
        if (event.results[i].isFinal) {
          break;
        }
      }
    
      if (transcript.trim()) {
        transcriptSentRef.current = true;

        if (listeningTimeoutRef.current) {
          clearTimeout(listeningTimeoutRef.current);
        }

        handleSend(transcript.trim());
      }
    };
    
    recognition.onerror = (event: any) => {
      const errorCode = event.error;

      // Suppress error if we intentionally aborted speech recognition
      if (suppressNextSpeechErrorRef.current || errorCode === 'aborted') {
        suppressNextSpeechErrorRef.current = false;
        if (listeningTimeoutRef.current) {
          clearTimeout(listeningTimeoutRef.current);
        }
        return;
      }

      let errorMessage = 'Speech recognition failed. Please try again.';
    
      if (errorCode === 'no-speech') {
        errorMessage = 'No speech detected. Please speak clearly and try again.';
      } else if (errorCode === 'audio-capture') {
        errorMessage = 'Microphone not found or permission denied.';
      } else if (errorCode === 'not-allowed') {
        errorMessage = 'Microphone permission denied. Please enable it in your browser settings.';
      } else if (errorCode === 'network') {
        errorMessage = 'Network error during speech recognition.';
      }

      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
      }
    
      setChatActive(true);
      setOrbState('error');
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: errorMessage,
          timestamp: new Date(),
        },
      ]);
    
      setTimeout(() => {
        setOrbState('idle');
      }, 2000);
    };
    
    recognition.onend = () => {
      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
        listeningTimeoutRef.current = null;
      }

      if (!transcriptSentRef.current) {
        setOrbState('idle');
      }

      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
    };
    
    try {
      recognition.start();
    } catch (error) {
      console.error('Speech recognition start error:', error);
      
      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
      }
      
      setOrbState('idle');
    }
  }, [orbState, handleSend]);

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
              <span>{orbState === 'listening' ? 'Listening…' : 'Ask QMeet anything…'}</span>
            </div>
          )}
        </div>

        {/* Chat area: hidden when idle, 62% when active */}
        <div className={`chat-area ${chatActive ? 'chat-area-visible' : 'chat-area-hidden'}`}>
          <ChatPanel messages={messages} orbState={orbState} />
          <PromptBar onSend={handleSend} disabled={orbState === 'thinking'} />
        </div>
      </div>

      {/* Panel Overlays */}
      {activePanel === 'menu' && (
        <div className="panel-overlay">
          <div className="panel-content">
            <div className="panel-header">Menu</div>
            <div className="panel-body">
              <div className="panel-section">
                <div className="panel-section-title">Voice Commands</div>
                <p className="panel-section-text">
                  Say commands like "show settings", "show status", "close panel", "go home", "clear chat", or "end chat". You can also ask "what can you do?" for command help.
                </p>
              </div>
              <div className="panel-section">
                <div className="panel-section-title">Chat</div>
                <p className="panel-section-text">
                  Type or speak to chat with QMeet. Your messages will be sent to the AI backend.
                </p>
              </div>
              <button className="close-panel-btn" onClick={closePanel}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {activePanel === 'settings' && (
        <div className="panel-overlay">
          <div className="panel-content">
            <div className="panel-header">Settings</div>
            <div className="panel-body">
              <div className="panel-section">
                <div className="panel-section-title">Voice Settings</div>
                <p className="panel-section-text">
                  Microphone: Enabled · Language: English (US) · Recognition: Online
                </p>
              </div>
              <div className="panel-section">
                <div className="panel-section-title">Display</div>
                <p className="panel-section-text">
                  Theme: Dark · Resolution: 1024×600 · Interface: Optimized
                </p>
              </div>
              <div className="panel-section">
                <div className="panel-section-title">Backend</div>
                <p className="panel-section-text">
                  Status: {backendStatus?.ok ? 'Connected' : 'Disconnected'} · Provider: {backendStatus?.provider || 'Unknown'}
                </p>
              </div>
              <button className="close-panel-btn" onClick={closePanel}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
      
      {activePanel === 'status' && (
        <div className="panel-overlay">
          <div className="panel-content">
            <div className="panel-header">Status</div>
            <div className="panel-body">
              <div className="panel-section">
                <div className="panel-section-title">Current State</div>
                <p className="panel-section-text">
                  Orb State: {orbState.charAt(0).toUpperCase() + orbState.slice(1)} · Chat Active: {chatActive ? 'Yes' : 'No'}
                </p>
              </div>
              <div className="panel-section">
                <div className="panel-section-title">Backend Connection</div>
                <p className="panel-section-text">
                  {backendStatus?.ok ? 'Connected and ready' : 'Disconnected'}
                </p>
              </div>
              <div className="panel-section">
                <div className="panel-section-title">Messages</div>
                <p className="panel-section-text">
                  Total messages: {messages.length}
                </p>
              </div>
              <button className="close-panel-btn" onClick={closePanel}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
