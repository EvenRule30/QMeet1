import { Fragment, ReactNode, useEffect, useRef } from 'react';

import { AssistantActivity, Message, OrbState } from '../types';

interface ChatPanelProps {
  messages: Message[];
  orbState: OrbState;
  activity?: AssistantActivity | null;
}

type TextBlock =
  | { type: 'paragraph'; lines: string[] }
  | { type: 'bullet'; items: string[] }
  | { type: 'numbered'; items: string[] }
  | { type: 'code'; text: string }
  | { type: 'heading'; text: string }
  | { type: 'callout'; title: string; body: string };

function getToolLabel(message: Message): string {
  if (message.variant === 'error') return 'Needs attention';
  if (message.variant === 'notice') return 'Notice';
  if (message.variant === 'tool') return 'Tool update';
  return 'QMeet';
}

function formatMessageTime(timestamp: Message['timestamp']): string {
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '';

  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}

const STRUCTURED_SECTION_LABELS = [
  'Ended focus sessions',
  'Completed tasks',
  'New open tasks',
  'Current open tasks',
  'Notes saved',
  'Recent actions',
  'Tasks',
  'Still open',
  'Visual context',
  'Recent focus actions',
];

const STRUCTURED_SECTION_PATTERN = new RegExp(
  `\\s+((?:${STRUCTURED_SECTION_LABELS.join('|')}):)`,
  'gi',
);

function compactRecentActionPreview(value: string): string {
  return value
    .replace(/\s*\n+\s*(?:\d+[.)]|[-*])\s+/g, ' ')
    .replace(/\s+\d+[.)]\s+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function expandRecentActionsList(content: string): string {
  return content.replace(
    /(^|\s)(Recent actions:)\s+([\s\S]+?)(?=(?:\s+(?:Ended focus sessions|Completed tasks|New open tasks|Current open tasks|Notes saved|Tasks|Still open|Visual context|Recent focus actions):)|$)/gi,
    (_match, prefix: string, label: string, rawBody: string) => {
      const body = rawBody.trim().replace(/[.]$/, '');
      const items = body
        .split(/\s*;\s*/)
        .map(compactRecentActionPreview)
        .filter(Boolean);
      if (items.length < 2) {
        return `${prefix}${label} ${compactRecentActionPreview(rawBody)}`;
      }

      return `${prefix}${label}\n${items
        .map((item, index) => `${index + 1}. ${item}`)
        .join('\n')}`;
    },
  );
}

function normalizeAssistantText(content: string): string {
  return expandRecentActionsList(content)
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(
      /\s+(\*\*(?:Next step|Next steps|Try|Try saying|Options|Why|Tip|Goal|Focus|What I know|What I need|Open question):\*\*)/gi,
      '\n\n$1',
    )
    .replace(STRUCTURED_SECTION_PATTERN, '\n\n$1')
    .replace(/\s+(-\s+)/g, '\n$1')
    .replace(/\s+([1-9]\d?[.)]\s+)/g, '\n$1')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function stripMarkdownBold(value: string): string {
  return value.replace(/\*\*/g, '').trim();
}

function renderInlineText(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);

  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>;
    }

    return <Fragment key={`${part}-${index}`}>{part}</Fragment>;
  });
}

function flushParagraph(blocks: TextBlock[], paragraphLines: string[]) {
  const cleanLines = paragraphLines.map((line) => line.trim()).filter(Boolean);
  if (cleanLines.length > 0) {
    blocks.push({ type: 'paragraph', lines: cleanLines });
  }
  paragraphLines.length = 0;
}

function parseFormattedBlocks(content: string): TextBlock[] {
  const normalized = normalizeAssistantText(content);
  if (!normalized) return [];

  const lines = normalized.split('\n');
  const blocks: TextBlock[] = [];
  const paragraphLines: string[] = [];
  let codeLines: string[] | null = null;
  let bulletItems: string[] = [];
  let numberedItems: string[] = [];
  let lastNumberedValue: number | null = null;

  const flushBullets = () => {
    if (bulletItems.length > 0) {
      blocks.push({ type: 'bullet', items: bulletItems });
      bulletItems = [];
    }
  };

  const flushNumbered = () => {
    if (numberedItems.length > 0) {
      blocks.push({ type: 'numbered', items: numberedItems });
      numberedItems = [];
    }
    lastNumberedValue = null;
  };

  const flushLists = () => {
    flushBullets();
    flushNumbered();
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      flushParagraph(blocks, paragraphLines);
      flushLists();

      if (codeLines === null) {
        codeLines = [];
      } else {
        blocks.push({ type: 'code', text: codeLines.join('\n') });
        codeLines = null;
      }
      continue;
    }

    if (codeLines !== null) {
      codeLines.push(line);
      continue;
    }

    if (!trimmed) {
      flushParagraph(blocks, paragraphLines);
      flushLists();
      continue;
    }

    const headingMatch = trimmed.match(/^#{1,3}\s+(.+)$/);
    if (headingMatch) {
      flushParagraph(blocks, paragraphLines);
      flushLists();
      blocks.push({ type: 'heading', text: stripMarkdownBold(headingMatch[1]) });
      continue;
    }

    const calloutMatch = trimmed.match(
      /^\*\*(Next step|Next steps|Try|Try saying|Options|Why|Tip|Goal|Focus|What I know|What I need|Open question):\*\*\s*(.*)$/i,
    );
    if (calloutMatch) {
      flushParagraph(blocks, paragraphLines);
      flushLists();
      blocks.push({
        type: 'callout',
        title: calloutMatch[1],
        body: calloutMatch[2].trim(),
      });
      continue;
    }

    const bulletMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (bulletMatch) {
      flushParagraph(blocks, paragraphLines);
      flushNumbered();
      bulletItems.push(bulletMatch[1].trim());
      continue;
    }

    const numberedMatch = trimmed.match(/^(\d+)[.)]\s+(.+)$/);
    if (numberedMatch) {
      flushParagraph(blocks, paragraphLines);
      flushBullets();
      const numberedValue = Number.parseInt(numberedMatch[1], 10);
      if (
        numberedItems.length > 0 &&
        lastNumberedValue !== null &&
        numberedValue <= lastNumberedValue
      ) {
        flushNumbered();
      }

      numberedItems.push(numberedMatch[2].trim());
      lastNumberedValue = numberedValue;
      continue;
    }

    flushLists();
    paragraphLines.push(trimmed);
  }

  if (codeLines !== null && codeLines.length > 0) {
    blocks.push({ type: 'code', text: codeLines.join('\n') });
  }

  flushParagraph(blocks, paragraphLines);
  flushLists();
  return blocks;
}

function MessageListBlock({
  items,
  ordered = false,
  blockIndex,
}: {
  items: string[];
  ordered?: boolean;
  blockIndex: number;
}) {
  return (
    <div className="message-list-block" role="list">
      {items.map((item, itemIndex) => (
        <div
          className="message-list-row"
          key={`${ordered ? 'numbered' : 'bullet'}-${blockIndex}-${itemIndex}`}
          role="listitem"
        >
          <span className="message-list-marker">
            {ordered ? `${itemIndex + 1}.` : '•'}
          </span>
          <span className="message-list-text">{renderInlineText(item)}</span>
        </div>
      ))}
    </div>
  );
}

function FormattedMessageContent({ content }: { content: string }) {
  const blocks = parseFormattedBlocks(content);

  if (blocks.length === 0) {
    return <p className="message-text">{content}</p>;
  }

  return (
    <div className="message-formatted-content">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          return (
            <p className="message-heading" key={`heading-${index}`}>
              {renderInlineText(block.text)}
            </p>
          );
        }

        if (block.type === 'callout') {
          return (
            <div className="message-callout" key={`callout-${index}`}>
              <strong>{block.title}</strong>
              {block.body ? <span>{renderInlineText(` ${block.body}`)}</span> : null}
            </div>
          );
        }

        if (block.type === 'bullet') {
          return <MessageListBlock blockIndex={index} items={block.items} />;
        }
        if (block.type === 'numbered') {
          return <MessageListBlock blockIndex={index} items={block.items} ordered />;
        }

        if (block.type === 'code') {
          return (
            <pre className="message-code" key={`code-${index}`}>
              <code>{block.text}</code>
            </pre>
          );
        }

        return block.lines.map((line, lineIndex) => (
          <p className="message-text" key={`paragraph-${index}-${lineIndex}`}>
            {renderInlineText(line)}
          </p>
        ));
      })}
    </div>
  );
}

function MessageFormattingStyles() {
  return (
    <style>{`
      .message-formatted-content {
        display: flex;
        flex-direction: column;
        gap: 0.42rem;
        min-width: 0;
      }
      .message-formatted-content .message-text,
      .message-formatted-content .message-heading {
        margin: 0;
        line-height: 1.48;
      }

      .message-formatted-content .message-heading {
        font-weight: 800;
        letter-spacing: 0.02em;
      }

      .message-callout {
        border: 1px solid rgba(82, 210, 255, 0.22);
        border-radius: 0.7rem;
        background: rgba(18, 67, 106, 0.18);
        padding: 0.52rem 0.62rem;
        line-height: 1.45;
      }
      .message-callout strong {
        margin-right: 0.2rem;
      }

      .message-list-block {
        display: flex;
        flex-direction: column;
        gap: 0.28rem;
        margin: 0.04rem 0 0.1rem;
        padding: 0;
      }

      .message-list-row {
        display: grid;
        grid-template-columns: 1.45rem minmax(0, 1fr);
        column-gap: 0.34rem;
        align-items: start;
        min-width: 0;
      }
      .message-list-marker {
        color: rgba(178, 232, 255, 0.9);
        font-weight: 800;
        line-height: 1.48;
        text-align: right;
        white-space: nowrap;
      }

      .message-list-text {
        line-height: 1.48;
        min-width: 0;
      }
      .message-list-text code,
      .message-formatted-content .message-text code,
      .message-callout code {
        border: 1px solid rgba(114, 178, 255, 0.2);
        border-radius: 0.32rem;
        background: rgba(6, 17, 38, 0.56);
        padding: 0.05rem 0.28rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        font-size: 0.94em;
      }
      .message-code {
        margin: 0.1rem 0 0.12rem;
        border: 1px solid rgba(114, 178, 255, 0.18);
        border-radius: 0.72rem;
        background: rgba(3, 10, 25, 0.62);
        padding: 0.7rem 0.78rem;
        overflow-x: auto;
        white-space: pre;
        line-height: 1.48;
      }

      .message-code code {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        font-size: 0.92em;
      }
    `}</style>
  );
}

export function ChatPanel({ messages, orbState, activity }: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, orbState, activity?.label, activity?.detail]);

  return (
    <div className="chat-panel">
      <MessageFormattingStyles />
      <div className="chat-messages">
        {activity && (
          <div className="message message-assistant message-activity">
            <div className="message-avatar">Q</div>
            <div className="message-bubble thinking-bubble">
              <p className="message-text">
                <strong>{activity.label}</strong>
                {activity.detail ? ` ${activity.detail}` : ''}
              </p>
            </div>
          </div>
        )}

        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Tap the orb and speak, or type below.</p>
          </div>
        )}

        {messages.map((msg) => {
          const variant = msg.variant ?? 'normal';
          const isAssistant = msg.role === 'assistant';
          const isToolMessage = isAssistant && variant !== 'normal';
          const timeText = formatMessageTime(msg.timestamp);
          return (
            <div
              className={`message message-${msg.role} message-${variant}`}
              key={msg.id}
            >
              {isAssistant && (
                <div className="message-avatar">{isToolMessage ? '✓' : 'Q'}</div>
              )}
              <div className="message-bubble">
                {isToolMessage && (
                  <p className="message-tool-label">{getToolLabel(msg)}</p>
                )}
                <FormattedMessageContent content={msg.content} />
                {timeText && <span className="message-time">{timeText}</span>}
              </div>
            </div>
          );
        })}

        {orbState === 'thinking' && (
          <div className="message message-assistant">
            <div className="message-avatar">Q</div>
            <div className="message-bubble thinking-bubble">
              <div className="thinking-dots" aria-label="QMeet is thinking">
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
