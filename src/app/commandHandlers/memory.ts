import type { ActivePanel, MemoryTask } from '../types';
import type { CommandMatch } from '../commands';

export type MemoryCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
};

export function handleMemoryCommand(
  commandMatch: CommandMatch,
  deps: {
    voiceOutputEnabled: boolean;
    setActivePanel: (panel: ActivePanel) => void;
    closePanel: () => void;
    getMemoryReadout: () => string;
    saveMemoryTask: (title: string) => MemoryTask | null;
    markMemoryTaskDone: (
      lookup?: string,
      operation?: 'complete' | 'delete',
    ) => MemoryTask | null;
    clearCompletedTasks: () => number;
  },
): MemoryCommandResult {
  switch (commandMatch.command) {
    case 'open-memory':
      deps.setActivePanel('memory');
      return { handled: true };

    case 'close-memory':
      deps.closePanel();
      return { handled: true };

    case 'read-memory':
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: deps.getMemoryReadout(),
        shouldSpeakConfirmation:
          deps.voiceOutputEnabled,
      };

    case 'remember-task': {
      const savedTask = deps.saveMemoryTask(
        commandMatch.payload ?? '',
      );
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: savedTask
          ? `Saved task: ${savedTask.title}.`
          : 'I did not catch the task text.',
        shouldSpeakConfirmation:
          deps.voiceOutputEnabled,
      };
    }

    case 'mark-task-done': {
      const completedTask = deps.markMemoryTaskDone(
        commandMatch.payload,
      );
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: completedTask
          ? `Marked task done: ${completedTask.title}.`
          : commandMatch.payload
            ? `I could not find an open task matching "${commandMatch.payload}".`
            : 'No open tasks to complete.',
        shouldSpeakConfirmation:
          deps.voiceOutputEnabled,
      };
    }

    case 'delete-last-task': {
      const deletedTask = deps.markMemoryTaskDone(
        undefined,
        'delete',
      );
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: deletedTask
          ? `Deleted task: ${deletedTask.title}.`
          : 'No tasks to delete.',
        shouldSpeakConfirmation:
          deps.voiceOutputEnabled,
      };
    }

    case 'clear-done-tasks': {
      const removedCount =
        deps.clearCompletedTasks();
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent:
          removedCount > 0
            ? `Cleared ${removedCount} completed task${
                removedCount === 1 ? '' : 's'
              }.`
            : 'No completed tasks to clear.',
        shouldSpeakConfirmation:
          deps.voiceOutputEnabled,
      };
    }

    default:
      return { handled: false };
  }
}
