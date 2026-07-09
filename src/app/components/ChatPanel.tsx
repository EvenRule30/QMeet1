import { useEffect, useRef } from 'react';
import { AssistantActivity, Message, OrbState } from '../types';

interface ChatPanelProps {
  messages: Message[];
  orbState: OrbState;
  activity?: AssistantActivity | null;
}

function getToolLabel(message: Message): string {
  if (message.variant === 'error') return 'Needs attention';
  if (message.variant === 'notice') return 'Notice';
  if (message.variant === 'tool') return 'Tool update';
  return 'QMeet';
}

export function ChatPanel({ messages, orbState, activity }: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, orbState, activity?.label, activity?.detail]);

  return (
    <div className="chat-panel">
      {activity && (
        <div className={`chat-activity-card chat-activity-${activity.kind}`}>
          <div className="chat-activity-pulse" />
          <div className="chat-activity-copy">
            <span className="chat-activity-label">{activity.label}</span>
            <span className="chat-activity-detail">{activity.detail}</span>
          </div>
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Tap the orb and speak, or type below.</p>
          </div>
        )}

        {messages.map((msg) => {
          const variant = msg.variant ?? 'normal';
          const isToolMessage = msg.role === 'assistant' && variant !== 'normal';

          return (
            <div key={msg.id} className={`message message-${msg.role} message-${variant}`}>
              {msg.role === 'assistant' && (
                <div className="message-avatar">{isToolMessage ? '✓' : 'Q'}</div>
              )}
              <div className="message-bubble">
                {isToolMessage && (
                  <div className="message-tool-label">{getToolLabel(msg)}</div>
                )}
                <p>{msg.content}</p>
                <span className="message-time">
                  {msg.timestamp.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </div>
            </div>
          );
        })}

        {orbState === 'thinking' && (
          <div className="message message-assistant message-notice">
            <div className="message-avatar">Q</div>
            <div className="message-bubble thinking-bubble">
              <div className="thinking-copy">Working</div>
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
