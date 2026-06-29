import { useState, useRef, useEffect, useCallback } from "react";
import "./App.css";

// ─── Types ────────────────────────────────────────────────────────────────────

type OrbState = "idle" | "listening" | "thinking" | "speaking" | "error";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

// ─── Mock responses (replace with FastAPI calls) ──────────────────────────────

const MOCK_RESPONSES: { match: RegExp; reply: string }[] = [
  {
    match: /\b(hi|hello|hey)\b/i,
    reply: "Hello! I'm QMeet, your intelligent AI assistant. I'm ready to help with scheduling, questions, or anything else on your mind.",
  },
  {
    match: /meeting|schedule|calendar|book/i,
    reply: "I can help with that. Based on the shared calendar, Thursday at 2:00 PM and Friday at 10:30 AM both look clear. I can send invites automatically once you confirm a time — which works best?",
  },
  {
    match: /weather|temperature|forecast/i,
    reply: "Currently 19°C and partly cloudy at your location. The forecast shows clear skies by 3 PM — ideal if you were planning an outdoor session.",
  },
  {
    match: /who are you|what are you|your name/i,
    reply: "I'm QMeet — an embedded AI assistant designed for collaborative workspaces. I handle scheduling, answer questions, summarize notes, and connect to your team's tools.",
  },
  {
    match: /time|clock/i,
    reply: `The current time is ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.`,
  },
];

function getMockResponse(input: string): string {
  const match = MOCK_RESPONSES.find((r) => r.match.test(input));
  return match?.reply ??
    "I'm processing your request. In the live deployment, this response would come from the QMeet FastAPI backend via WebSocket. Feel free to ask about meetings, the weather, or who I am.";
}

// ─── Orb Component ────────────────────────────────────────────────────────────

interface OrbProps {
  state: OrbState;
  active: boolean;
}

function Orb({ state, active }: OrbProps) {
  return (
    <div className={`orb-container orb-${state} ${active ? "orb-active" : "orb-idle-pos"}`}>
      {/* Outermost ambient halo */}
      <div className="orb-halo" />

      {/* Sphere — rendered first so orbital dots stack above it */}
      <div className="orb-sphere">
        <div className="orb-gradient" />
        <div className="orb-gloss" />
      </div>
      <div className="orb-depth" />

      {/* Orbital dot rings — rendered last so they are always on top */}
      <div className="orb-orbital-wrap">
        <div className="orbit-group orbit-group-1">
          <div className="od" />
          <div className="od" />
          <div className="od" />
        </div>
        <div className="orbit-group orbit-group-2">
          <div className="od" />
          <div className="od" />
          <div className="od" />
        </div>
      </div>
    </div>
  );
}

// ─── TopStatusBar Component ───────────────────────────────────────────────────

interface TopStatusBarProps {
  orbState: OrbState;
  chatActive: boolean;
  onEnd: () => void;
}

function TopStatusBar({ orbState, chatActive, onEnd }: TopStatusBarProps) {
  const [time, setTime] = useState(() => new Date());

  useEffect(() => {
    const ticker = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(ticker);
  }, []);

  const stateLabel: Record<OrbState, string> = {
    idle: "Idle",
    listening: "Listening",
    thinking: "Processing",
    speaking: "Responding",
    error: "Error",
  };

  return (
    <div className="status-bar">
      <div className="status-left">
        <span className="status-logo">QMeet</span>
        <span className="status-divider">|</span>
        <span className={`status-state state-${orbState}`}>
          {stateLabel[orbState]}
        </span>
      </div>
      <div className="status-right">
        <span className="status-time">
          {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
        {chatActive && (
          <button className="end-btn" onClick={onEnd} aria-label="End conversation">
            {/* X icon */}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
              strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
            End
          </button>
        )}
        <div className="connection-indicator">
          <div className="conn-dot" />
          <span className="conn-label">Connected</span>
        </div>
      </div>
    </div>
  );
}

// ─── ChatPanel Component ──────────────────────────────────────────────────────

interface ChatPanelProps {
  messages: Message[];
  orbState: OrbState;
}

function ChatPanel({ messages, orbState }: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, orbState]);

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Conversation will appear here…</p>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`message message-${msg.role}`}>
            {msg.role === "assistant" && (
              <div className="message-avatar">Q</div>
            )}
            <div className="message-bubble">
              <p>{msg.content}</p>
              <span className="message-time">
                {msg.timestamp.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
          </div>
        ))}

        {orbState === "thinking" && (
          <div className="message message-assistant">
            <div className="message-avatar">Q</div>
            <div className="message-bubble thinking-bubble">
              <div className="thinking-dots">
                <span /><span /><span />
              </div>
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  );
}

// ─── PromptBar Component ──────────────────────────────────────────────────────

interface PromptBarProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

function PromptBar({ onSend, disabled }: PromptBarProps) {
  const [input, setInput] = useState("");

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput("");
  }, [input, disabled, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="prompt-bar">
      <input
        className="prompt-input"
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask QMeet…"
        disabled={disabled}
        autoComplete="off"
      />
      <button
        className={`send-btn${disabled || !input.trim() ? " send-disabled" : ""}`}
        onClick={handleSend}
        disabled={disabled || !input.trim()}
        aria-label="Send message"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
          strokeLinecap="round" strokeLinejoin="round">
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </div>
  );
}

// ─── AgentScreen Component ────────────────────────────────────────────────────

function AgentScreen() {
  const [chatActive, setChatActive] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [messages, setMessages] = useState<Message[]>([]);

  // Return to idle state — clears conversation and resets layout
  const handleEndChat = useCallback(() => {
    setOrbState("idle");
    setChatActive(false);
    setMessages([]);
  }, []);

  // BACKEND HOOK ─────────────────────────────────────────────────────────────
  // Replace this function body with WebSocket / FastAPI fetch:
  //
  //   const ws = useRef<WebSocket | null>(null);
  //   // Connect: ws.current = new WebSocket("ws://localhost:8000/ws/chat");
  //   // Send:    ws.current.send(JSON.stringify({ message: text }));
  //   // Receive: ws.current.onmessage = (e) => { ... append assistant msg ... };
  //
  //   Or with REST:
  //   const res = await fetch("http://localhost:8000/api/chat", {
  //     method: "POST",
  //     headers: { "Content-Type": "application/json" },
  //     body: JSON.stringify({ message: text }),
  //   });
  //   const data = await res.json();  // { reply: "..." }
  // ──────────────────────────────────────────────────────────────────────────
  const handleSend = useCallback(async (text: string) => {
    if (!chatActive) setChatActive(true);

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setOrbState("thinking");

    // Simulated latency — remove when wiring real backend
    await new Promise((r) => setTimeout(r, 900 + Math.random() * 700));

    setOrbState("speaking");
    const assistantMsg: Message = {
      id: `a-${Date.now()}`,
      role: "assistant",
      content: getMockResponse(text),
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMsg]);

    // Simulated speaking duration — remove when wiring real backend
    await new Promise((r) => setTimeout(r, 2000));
    setOrbState("idle");
  }, [chatActive]);

  // Tap orb in idle mode to start listening
  // BACKEND HOOK: trigger STT / voice capture stream here
  const handleOrbClick = useCallback(() => {
    if (chatActive) return;
    setOrbState("listening");
    // Replace with real voice callback
    setTimeout(() => {
      setChatActive(true);
      setOrbState("idle");
    }, 1600);
  }, [chatActive]);

  return (
    <div className="agent-screen">
      <TopStatusBar orbState={orbState} chatActive={chatActive} onEnd={handleEndChat} />

      <div className="agent-body">
        {/* ── Orb area (full width idle → 38% active) ── */}
        <div
          className={`orb-area${chatActive ? " orb-area-active" : ""}`}
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

        {/* ── Chat area (hidden → 62% active) ── */}
        <div className={`chat-area ${chatActive ? "chat-area-visible" : "chat-area-hidden"}`}>
          <ChatPanel messages={messages} orbState={orbState} />
          <PromptBar onSend={handleSend} disabled={orbState === "thinking"} />
        </div>
      </div>
    </div>
  );
}

// ─── App Entry Point ──────────────────────────────────────────────────────────

export default function App() {
  return <AgentScreen />;
}
