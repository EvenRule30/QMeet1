import { NotesPanel } from '../components/NotesPanel';
import type { Note } from '../types';

type NotesOverlayProps = {
  notes: Note[];
  onSaveNote: (content: string) => Note | null;
  onDeleteNote: (noteId: string) => void;
  onClearNotes: () => void;
  onClose: () => void;
};

export function NotesOverlay({
  notes,
  onSaveNote,
  onDeleteNote,
  onClearNotes,
  onClose,
}: NotesOverlayProps) {
  return (
    <NotesPanel
      notes={notes}
      onSaveNote={onSaveNote}
      onDeleteNote={onDeleteNote}
      onClearNotes={onClearNotes}
      onClose={onClose}
    />
  );
}
