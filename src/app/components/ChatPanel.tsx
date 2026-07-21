import { ReactNode, useEffect, useRef } from 'react';

import { AssistantActivity, Message, OrbState } from '../types';

interface ChatPanelProps {
  messages: Message[];
  orbState: OrbState;
  activity?: AssistantActivity | null;
}

type TextBlock =
  | { type: 'paragraph'; lines: string[] }
  | { type: 'bullets'; items: string[] }
  | { type: 'ordered'; items: string[] }
  | { type: 'code'; lines: string[] };

function getToolLabel(message: Message): string {
  if (message.variant === 'error') return 'Needs attention';
  if (message.variant === 'notice') return 'Notice';
  if (message.variant === 'tool') return 'Tool update';

  return 'QMeet';
}

function renderInlineText(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const parts = text.split(/(\*\*[^*]+\*\*)/g);

  parts.forEach((part, index) => {
    if (!part) return;

    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      nodes.push(<strong key={`strong-${index}`}>{part.slice(2, -2)}</strong>);
      return;
    }

    nodes.push(<span key={`text-${index}`}>{part}</span>);
  });

  return nodes;
}

function parseMessageBlocks(content: string): TextBlock[] {
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  const blocks: TextBlock[] = [];
  let paragraph: string[] = [];
  let bullets: string[] = [];
  let ordered: string[] = [];
  let code: string[] | null = null;

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({ type: 'paragraph', lines: paragraph });
      paragraph = [];
    }
  };

  const flushBullets = () => {
    if (bullets.length > 0) {
      blocks.push({ type: 'bullets', items: bullets });
      bullets = [];
    }
  };

  const flushOrdered = () => {
    if (ordered.length > 0) {
      blocks.push({ type: 'ordered', items: ordered });
      ordered = [];
    }
  };

  const flushCode = () => {
    if (code) {
      blocks.push({ type: 'code', lines: code });
      code = null;
    }
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      flushParagraph();
      flushBullets();
      flushOrdered();
      if (code) {
        flushCode();
      } else {
        code = [];
      }
      return;
    }

    if (code) {
      code.push(line);
      return;
    }

    if (!trimmed) {
      flushParagraph();
      flushBullets();
      flushOrdered();
      return;
    }

    const bulletMatch = trimmed.match(/^[-*•]\s+(.+)$/);
    if (bulletMatch) {
      flushParagraph();
      flushOrdered();
      bullets.push(bulletMatch[1]);
      return;
    }

    const orderedMatch = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (orderedMatch) {
      flushParagraph();
      flushBullets();
      ordered.push(orderedMatch[1]);
      return;
    }

    flushBullets();
    flushOrdered();
    paragraph.push(trimmed.replace(/^#{1,4}\s+/, ''));
  });

  flushParagraph();
  flushBullets();
  flushOrdered();
  flushCode();

  if (blocks.length === 0 && content.trim()) {
    blocks.push({ type: 'paragraph', lines: [content.trim()] });
  }

  return blocks;
}

function FormattedMessageContent({ content }: { content: string }) {
  const blocks = parseMessageBlocks(content);

  return (
    <div className="message-content">
      {blocks.map((block, blockIndex) => {
        if (block.type === 'bullets') {
          return (
            <ul className="message-list" key={`bullets-${blockIndex}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`bullet-${blockIndex}-${itemIndex}`}>
                  {renderInlineText(item)}
                </li>
              ))}
            </ul>
          );
        }

        if (block.type === 'ordered') {
          return (
            <ol className="message-list" key={`ordered-${blockIndex}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`ordered-${blockIndex}-${itemIndex}`}>
                  {renderInlineText(item)}
                </li>
              ))}
            </ol>
          );
        }

        if (block.type === 'code') {
          return (
            <pre className="message-code" key={`code-${blockIndex}`}>
              <code>{block.lines.join('\n')}</code>
            </pre>
          );
        }

        return (
          <p className="message-paragraph" key={`paragraph-${blockIndex}`}>
            {block.lines.map((line, lineIndex) => (
              <span key={`line-${blockIndex}-${lineIndex}`}>
                {lineIndex > 0 && <br />}
                {renderInlineText(line)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function MessageFormattingStyles() {
  return (
    <style>{`
      .message-content {
        display: flex;
        flex-direction: column;
        gap: 0.42rem;
        line-height: 1.45;
        white-space: normal;
      }

      .message-content .message-paragraph {
        margin: 0;
      }

      .message-content .message-list {
        margin: 0;
        padding-left: 1.1rem;
      }

      .message-content .message-list li + li {
        margin-top: 0.22rem;
      }

      .message-content .message-code {
        margin: 0.15rem 0;
        padding: 0.55rem 0.65rem;
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 0.7rem;
        background: rgba(2, 6, 23, 0.46);
        overflow-x: auto;
        font-size: 0.78rem;
        line-height: 1.4;
      }

      .message-content strong {
        color: rgba(226, 232, 240, 0.98);
        font-weight: 700;
      }
    `}</style>
  );
}

export function ChatPanel({ messages, orbState, activity }: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, orbState, activity?.label, activity?.detail]);

  return (
    <div className="chat-panel">
      <MessageFormattingStyles />
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
            <div
              key={msg.id}
              className={`message message-${msg.role} message-${variant}`}
            >
              {msg.role === 'assistant' && (
                <div className="message-avatar">{isToolMessage ? '✓' : 'Q'}</div>
              )}

              <div className="message-bubble">
                {isToolMessage && (
                  <div className="message-tool-label">{getToolLabel(msg)}</div>
                )}

                <FormattedMessageContent content={msg.content} />

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
                <span />
                <span />
                <span />
              </div>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
