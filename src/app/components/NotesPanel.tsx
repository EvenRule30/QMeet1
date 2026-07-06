import { useState, useEffect } from 'react';

interface Note {
  id: string;
  content: string;
  timestamp: Date;
}

interface NotesPanelProps {
  onClose: () => void;
  clearVersion: number;
}

export function NotesPanel({ onClose, clearVersion }: NotesPanelProps) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [newNoteContent, setNewNoteContent] = useState('');
  const [initialClearVersion, setInitialClearVersion] = useState(clearVersion);

  useEffect(() => {
    const stored = localStorage.getItem('qmeet-notes');
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setNotes(parsed.map((n: any) => ({ ...n, timestamp: new Date(n.timestamp) })));
      } catch (error) {
        console.error('Failed to load notes from localStorage:', error);
      }
    }
  }, []);

  useEffect(() => {
    if (clearVersion > initialClearVersion) {
      setNotes([]);
      setInitialClearVersion(clearVersion);
    }
  }, [clearVersion, initialClearVersion]);

  const saveNotes = (updatedNotes: Note[]) => {
    setNotes(updatedNotes);
    localStorage.setItem('qmeet-notes', JSON.stringify(updatedNotes));
  };

  const handleAddNote = () => {
    const trimmed = newNoteContent.trim();
    if (!trimmed) return;

    const newNote: Note = {
      id: `note-${Date.now()}`,
      content: trimmed,
      timestamp: new Date(),
    };

    saveNotes([newNote, ...notes]);
    setNewNoteContent('');
  };

  const handleDeleteNote = (id: string) => {
    saveNotes(notes.filter((note) => note.id !== id));
  };

  const handleClearAll = () => {
    saveNotes([]);
  };

  const formatTime = (date: Date) => {
    return new Date(date).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  };

  return (
    <div className="panel-overlay">
      <div className="panel-content notes-panel">
        <div className="panel-header">Notes</div>
        <div className="panel-body notes-panel-body">
          <div className="note-input-section">
            <textarea
              className="note-input"
              placeholder="Type a note..."
              value={newNoteContent}
              onChange={(e) => setNewNoteContent(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && e.ctrlKey) {
                  handleAddNote();
                }
              }}
            />
            <div className="note-action-row">
              <button
                className="panel-action-btn"
                onClick={handleAddNote}
                disabled={!newNoteContent.trim()}
              >
                Save Note
              </button>
              {notes.length > 0 && (
                <button className="panel-action-btn panel-action-btn-danger" onClick={handleClearAll}>
                  Clear All
                </button>
              )}
            </div>
          </div>

          <div className="notes-list-section">
            {notes.length === 0 ? (
              <p className="notes-empty">No notes yet. Create one to get started.</p>
            ) : (
              <div className="notes-list">
                {notes.map((note) => (
                  <div key={note.id} className="note-item">
                    <div className="note-content">{note.content}</div>
                    <div className="note-footer">
                      <span className="note-time">{formatTime(note.timestamp)}</span>
                      <button
                        className="note-delete-btn"
                        onClick={() => handleDeleteNote(note.id)}
                        aria-label="Delete note"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button className="close-panel-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
