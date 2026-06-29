import { useEffect, useRef } from 'react';
import { Message, OrbState } from '../types';

interface ChatPanelProps {
  messages: Message[];
  orbState: OrbState;
}

export function ChatPanel({ messages, orbState }: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
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
            {msg.role === 'assistant' && (
              <div className="message-avatar">Q</div>
            )}
            <div className="message-bubble">
              <p>{msg.content}</p>
              <span className="message-time">
                {msg.timestamp.toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
          </div>
        ))}

        {orbState === 'thinking' && (
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
