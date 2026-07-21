import { useState } from 'react';

import type { Note } from '../types';

type NotesPanelProps = {
  notes: Note[];
  onSaveNote: (content: string) => Note | null;
  onDeleteNote: (noteId: string) => void;
  onClearNotes: () => void;
  onClose: () => void;
};

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

function StructuredNoteContent({ content }: { content: string }) {
  const lines = content.replace(/\r\n?/g, '\n').split('\n');

  return (
    <div className="note-structured-content">
      {lines.map((line, index) => {
        const bulletMatch = line.match(/^\s*[-*•]\s+(.+)$/);
        const numberedMatch = line.match(/^\s*(\d+)[.)]\s+(.+)$/);
        const key = `${index}-${line.slice(0, 20)}`;

        if (bulletMatch) {
          return (
            <div className="note-structured-row" key={key}>
              <span className="note-structured-marker" aria-hidden="true">
                •
              </span>
              <span>{bulletMatch[1]}</span>
            </div>
          );
        }

        if (numberedMatch) {
          return (
            <div className="note-structured-row" key={key}>
              <span className="note-structured-marker" aria-hidden="true">
                {numberedMatch[1]}.
              </span>
              <span>{numberedMatch[2]}</span>
            </div>
          );
        }

        if (!line.trim()) {
          return <div className="note-structured-gap" aria-hidden="true" key={key} />;
        }

        return <p key={key}>{line.trim()}</p>;
      })}
    </div>
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
                      <StructuredNoteContent content={note.content} />

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
