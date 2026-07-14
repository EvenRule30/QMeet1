import type { ActivePanel, Note } from '../types';
import type { CommandMatch } from '../commands';

export type NotesCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
};

export function handleNotesCommand(
  commandMatch: CommandMatch,
  deps: {
    voiceOutputEnabled: boolean;
    setActivePanel: (panel: ActivePanel) => void;
    closePanel: () => void;
    saveNote: (content: string) => Note | null;
    deleteLastNote: () => Note | null;
    clearNotes: () => void;
    getNotesReadout: () => string;
  },
): NotesCommandResult {
  switch (commandMatch.command) {
    case 'open-notes':
    case 'new-note':
      deps.setActivePanel('notes');
      return { handled: true };

    case 'save-note': {
      const savedNote = deps.saveNote(commandMatch.payload ?? '');
      deps.setActivePanel('notes');
      return {
        handled: true,
        confirmationContent: savedNote ? 'Saved note.' : 'I did not catch the note text.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-notes':
      deps.setActivePanel('notes');
      return {
        handled: true,
        confirmationContent: deps.getNotesReadout(),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };

    case 'delete-last-note': {
      const deletedNote = deps.deleteLastNote();
      deps.setActivePanel('notes');
      return {
        handled: true,
        confirmationContent: deletedNote ? 'Deleted the last note.' : 'No notes to delete.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'close-notes':
      deps.closePanel();
      return { handled: true };

    case 'clear-notes':
      deps.clearNotes();
      return { handled: true };

    default:
      return { handled: false };
  }
}
