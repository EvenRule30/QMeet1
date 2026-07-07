import { useState } from 'react';
import { Note } from '../types';

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
    <div className="panel-overlay">
      <div className="panel-content notes-panel">
        <div className="panel-header">Notes</div>

        <div className="panel-body notes-panel-body">
          <div className="panel-section">
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

            {notes.length === 0 ? (
              <p className="notes-empty">No saved notes yet.</p>
            ) : (
              <div className="notes-list">
                {notes.map((note) => (
                  <div className="note-item" key={note.id}>
                    <div className="note-content">{note.content}</div>

                    <div className="note-footer">
                      <span className="note-time">{formatNoteTime(note.createdAt)}</span>

                      <button
                        className="note-delete-btn"
                        onClick={() => onDeleteNote(note.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="panel-section">
            <div className="panel-section-title">Voice Commands</div>
            <p className="panel-section-text">
              Try “note that buy milk,” “remember that test the tablet UI,” “read my notes,”
              “delete last note,” “clear notes,” or “close notes.”
            </p>
          </div>

          <button className="close-panel-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
