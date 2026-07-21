import { Fragment, type ReactNode, useState } from 'react';

import type { Note } from '../types';

type NotesPanelProps = {
  notes: Note[];
  onSaveNote: (content: string) => Note | null;
  onDeleteNote: (noteId: string) => void;
  onClearNotes: () => void;
  onClose: () => void;
};

type NoteBlock =
  | { type: 'paragraph'; text: string }
  | { type: 'bullet'; items: string[] }
  | { type: 'numbered'; items: Array<{ marker: string; text: string }> }
  | { type: 'code'; text: string }
  | { type: 'heading'; level: 1 | 2 | 3; text: string }
  | { type: 'callout'; title: string; body: string };

function formatNoteTime(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return 'Saved note';
  }

  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function normalizeNoteText(content: string): string {
  return content
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t]+(?=[-*•]\s+\S)/g, '\n')
    .replace(/[ \t]+(?=\d+[.)]\s+\S)/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function parseNoteBlocks(content: string): NoteBlock[] {
  const lines = normalizeNoteText(content).split('\n');
  const blocks: NoteBlock[] = [];
  let lineIndex = 0;

  while (lineIndex < lines.length) {
    const rawLine = lines[lineIndex];
    const line = rawLine.trim();

    if (!line) {
      lineIndex += 1;
      continue;
    }

    if (/^```/.test(line)) {
      const codeLines: string[] = [];
      lineIndex += 1;

      while (lineIndex < lines.length && !/^```/.test(lines[lineIndex].trim())) {
        codeLines.push(lines[lineIndex]);
        lineIndex += 1;
      }

      if (lineIndex < lines.length) {
        lineIndex += 1;
      }

      blocks.push({ type: 'code', text: codeLines.join('\n') });
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length as 1 | 2 | 3,
        text: headingMatch[2].trim(),
      });
      lineIndex += 1;
      continue;
    }

    const calloutMatch = line.match(/^\*\*([^*\n]{1,60}):\*\*\s*(.*)$/);
    if (calloutMatch) {
      blocks.push({
        type: 'callout',
        title: calloutMatch[1].trim(),
        body: calloutMatch[2].trim(),
      });
      lineIndex += 1;
      continue;
    }

    if (/^[-*•]\s+/.test(line)) {
      const items: string[] = [];

      while (lineIndex < lines.length) {
        const bulletMatch = lines[lineIndex].trim().match(/^[-*•]\s+(.+)$/);
        if (!bulletMatch) break;
        items.push(bulletMatch[1].trim());
        lineIndex += 1;
      }

      blocks.push({ type: 'bullet', items });
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const items: Array<{ marker: string; text: string }> = [];

      while (lineIndex < lines.length) {
        const numberedMatch = lines[lineIndex].trim().match(/^(\d+)[.)]\s+(.+)$/);
        if (!numberedMatch) break;
        items.push({ marker: `${numberedMatch[1]}.`, text: numberedMatch[2].trim() });
        lineIndex += 1;
      }

      blocks.push({ type: 'numbered', items });
      continue;
    }

    const paragraphLines = [line];
    lineIndex += 1;

    while (lineIndex < lines.length) {
      const nextLine = lines[lineIndex].trim();
      if (
        !nextLine ||
        /^```/.test(nextLine) ||
        /^(#{1,3})\s+/.test(nextLine) ||
        /^[-*•]\s+/.test(nextLine) ||
        /^\d+[.)]\s+/.test(nextLine) ||
        /^\*\*([^*\n]{1,60}):\*\*/.test(nextLine)
      ) {
        break;
      }

      paragraphLines.push(nextLine);
      lineIndex += 1;
    }

    blocks.push({ type: 'paragraph', text: paragraphLines.join(' ') });
  }

  return blocks;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const tokenPattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_)/g;
  const parts = text.split(tokenPattern).filter((part) => part.length > 0);

  return parts.map((part, index) => {
    const key = `${index}-${part.slice(0, 18)}`;

    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={key}>{part.slice(1, -1)}</code>;
    }

    if (
      (part.startsWith('**') && part.endsWith('**')) ||
      (part.startsWith('__') && part.endsWith('__'))
    ) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }

    if (
      (part.startsWith('*') && part.endsWith('*')) ||
      (part.startsWith('_') && part.endsWith('_'))
    ) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }

    return <Fragment key={key}>{part}</Fragment>;
  });
}

function FormattedNoteContent({ content }: { content: string }) {
  const blocks = parseNoteBlocks(content);

  return (
    <div className="note-formatted-content">
      {blocks.map((block, index) => {
        const key = `${block.type}-${index}`;

        if (block.type === 'heading') {
          const HeadingTag = `h${block.level + 2}` as 'h3' | 'h4' | 'h5';
          return (
            <HeadingTag className="note-formatted-heading" key={key}>
              {renderInlineMarkdown(block.text)}
            </HeadingTag>
          );
        }

        if (block.type === 'callout') {
          return (
            <div className="note-formatted-callout" key={key}>
              <strong>{block.title}:</strong>
              {block.body ? <span>{renderInlineMarkdown(` ${block.body}`)}</span> : null}
            </div>
          );
        }

        if (block.type === 'bullet') {
          return (
            <div className="note-formatted-list" key={key}>
              {block.items.map((item, itemIndex) => (
                <div className="note-formatted-list-row" key={`${key}-${itemIndex}`}>
                  <span className="note-formatted-marker" aria-hidden="true">
                    •
                  </span>
                  <span className="note-formatted-list-text">
                    {renderInlineMarkdown(item)}
                  </span>
                </div>
              ))}
            </div>
          );
        }

        if (block.type === 'numbered') {
          return (
            <div className="note-formatted-list" key={key}>
              {block.items.map((item, itemIndex) => (
                <div className="note-formatted-list-row" key={`${key}-${itemIndex}`}>
                  <span className="note-formatted-marker" aria-hidden="true">
                    {item.marker}
                  </span>
                  <span className="note-formatted-list-text">
                    {renderInlineMarkdown(item.text)}
                  </span>
                </div>
              ))}
            </div>
          );
        }

        if (block.type === 'code') {
          return (
            <pre className="note-formatted-code-block" key={key}>
              <code>{block.text}</code>
            </pre>
          );
        }

        return (
          <p className="note-formatted-paragraph" key={key}>
            {renderInlineMarkdown(block.text)}
          </p>
        );
      })}
    </div>
  );
}

function NoteFormattingStyles() {
  return (
    <style>{`
      .notes-overlay .note-formatted-content {
        display: flex;
        min-width: 0;
        flex-direction: column;
        gap: 8px;
        overflow-wrap: anywhere;
      }

      .notes-overlay .note-formatted-paragraph,
      .notes-overlay .note-formatted-heading,
      .notes-overlay .note-formatted-callout,
      .notes-overlay .note-formatted-code-block {
        margin: 0;
      }

      .notes-overlay .note-formatted-heading {
        color: rgba(255, 255, 255, 0.96);
        font-size: 0.94rem;
        font-weight: 750;
        line-height: 1.3;
        letter-spacing: 0.01em;
      }

      .notes-overlay .note-formatted-paragraph,
      .notes-overlay .note-formatted-list-text,
      .notes-overlay .note-formatted-callout {
        color: rgba(255, 255, 255, 0.86);
        font-size: 0.82rem;
        line-height: 1.48;
      }

      .notes-overlay .note-formatted-content strong {
        color: rgba(255, 255, 255, 0.98);
        font-weight: 750;
      }

      .notes-overlay .note-formatted-content em {
        color: rgba(255, 255, 255, 0.9);
      }

      .notes-overlay .note-formatted-content code {
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 5px;
        background: rgba(10, 8, 22, 0.42);
        padding: 1px 5px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.78rem;
      }

      .notes-overlay .note-formatted-list {
        display: flex;
        flex-direction: column;
        gap: 5px;
      }

      .notes-overlay .note-formatted-list-row {
        display: grid;
        grid-template-columns: 22px minmax(0, 1fr);
        align-items: start;
        gap: 4px;
      }

      .notes-overlay .note-formatted-marker {
        color: rgba(203, 179, 255, 0.92);
        font-size: 0.8rem;
        font-weight: 750;
        line-height: 1.48;
        text-align: right;
      }

      .notes-overlay .note-formatted-callout {
        border-left: 2px solid rgba(190, 153, 255, 0.72);
        border-radius: 0 7px 7px 0;
        background: rgba(137, 93, 214, 0.1);
        padding: 7px 9px;
      }

      .notes-overlay .note-formatted-code-block {
        max-width: 100%;
        overflow-x: auto;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        background: rgba(8, 7, 18, 0.58);
        padding: 9px 10px;
        white-space: pre-wrap;
        word-break: break-word;
      }

      .notes-overlay .note-formatted-code-block code {
        border: 0;
        background: transparent;
        padding: 0;
        color: rgba(255, 255, 255, 0.88);
      }
    `}</style>
  );
}

export function NotesPanel({
  notes,
  onSaveNote,
  onDeleteNote,
  onClearNotes,
  onClose,
}: NotesPanelProps) {
  const [draft, setDraft] = useState('');

  const handleSave = () => {
    const saved = onSaveNote(draft);

    if (saved) {
      setDraft('');
    }
  };

  return (
    <div className="panel-overlay notes-overlay">
      <NoteFormattingStyles />

      <section
        className="panel-content notes-panel"
        role="dialog"
        aria-labelledby="notes-panel-title"
        onClick={(event) => event.stopPropagation()}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <div className="panel-header" id="notes-panel-title">
          Notes
        </div>

        <div className="panel-body notes-panel-body">
          <div className="panel-section notes-compose-section">
            <div className="panel-section-title">New Note</div>

            <div className="note-input-section">
              <textarea
                className="note-input"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Write a note, or say: note that buy milk"
              />

              <div className="note-action-row">
                <button
                  className="panel-action-btn"
                  onClick={handleSave}
                  disabled={!draft.trim()}
                >
                  Save Note
                </button>

                <button
                  className="panel-action-btn panel-action-btn-danger"
                  onClick={onClearNotes}
                  disabled={notes.length === 0}
                >
                  Clear All
                </button>
              </div>
            </div>
          </div>

          <div className="panel-section notes-list-section">
            <div className="panel-section-title">Saved Notes</div>

            <div className="notes-scroll-area">
              {notes.length === 0 ? (
                <p className="notes-empty">No saved notes yet.</p>
              ) : (
                <div className="notes-list">
                  {notes.map((note) => (
                    <article className="note-item" key={note.id}>
                      <FormattedNoteContent content={note.content} />

                      <div className="note-footer">
                        <span className="note-time">{formatNoteTime(note.createdAt)}</span>
                        <button
                          className="note-delete-btn"
                          onClick={() => onDeleteNote(note.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="panel-section notes-help-section">
            <div className="panel-section-title">Voice Commands</div>
            <p className="panel-section-text">
              Try “note that buy milk,” “read my notes,” “delete last note,” or
              “close notes.”
            </p>
          </div>
        </div>

        <div className="notes-panel-footer">
          <button className="close-panel-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </section>
    </div>
  );
}
