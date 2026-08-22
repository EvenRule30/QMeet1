export * from './memoryCore';
import { handleMemoryCommand as handleMemoryCommandCore } from './memoryCore';
import {
  formatFocusTaskReadout,
  formatOpenTasksReadout,
  readStoredMemoryTasks,
} from '../lib/memoryReadSurface';
import { consumeNativeReadSurface } from '../lib/nativeReadSurfaceBridge';
import { readCanonicalFocusReadout } from '../lib/canonicalFocusReadout';
import type { Note } from '../types';
import {
  addNativeFocusContextVerified,
  appendNativeFocusContextToSummary,
  applyVerifiedFocusContextProjection,
  describeNativeFocusContextFailure,
  readNativeFocusContext,
  type FocusContextField,
} from '../lib/nativeFocusContext';
import {
  applyVerifiedCalendarFocusPrepProjection,
  describeNativeCalendarFocusPrepFailure,
  prepareNextCalendarFocusVerified,
} from '../lib/nativeCalendarFocusPrep';
import {
  applyVerifiedFocusProjection,
  describeNativeFocusEndFailure,
  describeNativeFocusResumeFailure,
  describeNativeFocusStartFailure,
  describeNativeFocusUpdateFailure,
  endNativeFocusVerified,
  projectVerifiedFocusToActiveSession,
  readVerifiedFocusProjection,
  resumeNativeFocusVerified,
  startNativeFocusVerified,
  updateNativeFocusVerified,
} from '../lib/nativeFocusLifecycle';
import {
  applyVerifiedFocusSummaryProjection,
  describeNativeFocusSummaryFailure,
  saveNativeFocusSummaryVerified,
} from '../lib/nativeFocusSummary';
import {
  applyVerifiedFocusTaskProjection,
  buildContextAwareNativeFocusTaskTitles,
  buildNativeMeetingFollowUpTaskTitles,
  createNativeFocusTasksVerified,
  describeNativeFocusTasksFailure,
} from '../lib/nativeFocusTasks';

export const NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION = 'phase20i';

type MemoryCommandName = Parameters<typeof handleMemoryCommandCore>[0]['command'];
const RETIRED_LEGACY_FOCUS_OWNERSHIP_COMMANDS = new Set<MemoryCommandName>([
  'start-focus-session',
  'update-focus-session',
  'resume-last-focus-session',
  'end-focus-session',
  'end-focus-with-summary',
  'wrap-up-meeting-focus',
  'save-focus-summary',
  'focus-to-tasks',
  'create-meeting-follow-up-tasks',
  'prepare-calendar-focus',
]);

type NativeFocusSummaryDeps = Parameters<typeof handleMemoryCommandCore>[1] & {
  saveNote: (content: string) => Note | null;
  deleteNote: (noteId: string) => Note | null | void;
};

type NativeFocusEndCommandEnvelope = {
  sourceTurnId?: unknown;
  disposition?: unknown;
};

function parseNativeFocusEndCommand(payload: string | undefined): {
  sourceTurnId?: string;
  disposition: 'ended' | 'completed';
} {
  if (!payload?.trim()) return { disposition: 'ended' };
  try {
    const parsed = JSON.parse(payload) as NativeFocusEndCommandEnvelope;
    const sourceTurnId =
      typeof parsed.sourceTurnId === 'string'
        ? parsed.sourceTurnId.trim()
        : '';
    const disposition =
      parsed.disposition === 'completed' ? 'completed' : 'ended';
    return {
      disposition,
      ...(sourceTurnId ? { sourceTurnId } : {}),
    };
  } catch {
    return { disposition: 'ended' };
  }
}

type NativeFocusContextCommandEnvelope = {
  sourceTurnId?: unknown;
  contextField?: unknown;
  contextValue?: unknown;
};

function parseNativeFocusContextCommand(
  payload: string | undefined,
): {
  sourceTurnId?: string;
  field: FocusContextField;
  value: string;
} | null {
  if (!payload?.trim()) return null;
  try {
    const parsed = JSON.parse(payload) as NativeFocusContextCommandEnvelope;
    const field =
      typeof parsed.contextField === 'string'
        ? parsed.contextField.trim()
        : '';
    const value =
      typeof parsed.contextValue === 'string'
        ? parsed.contextValue.replace(/\s+/g, ' ').trim()
        : '';
    const sourceTurnId =
      typeof parsed.sourceTurnId === 'string'
        ? parsed.sourceTurnId.trim()
        : '';
    if (
      ![
        'requirements',
        'constraints',
        'preferences',
        'decisions',
        'knownFacts',
      ].includes(field) ||
      !value
    ) {
      return null;
    }
    return {
      field: field as FocusContextField,
      value,
      ...(sourceTurnId ? { sourceTurnId } : {}),
    };
  } catch {
    return null;
  }
}

function hasSavedFocusSummary(
  activeSession: NonNullable<ReturnType<typeof readVerifiedFocusProjection>>,
): boolean {
  return (
    activeSession.pinnedNoteIds.length > 0 ||
    Boolean(activeSession.summary?.trim())
  );
}

function shouldGuardNativeFocusEnd(
  activeSession: NonNullable<ReturnType<typeof readVerifiedFocusProjection>>,
): boolean {
  if (hasSavedFocusSummary(activeSession)) return false;
  return (
    Boolean(activeSession.goal.trim()) ||
    activeSession.linkedTaskIds.length > 0 ||
    activeSession.title.trim().toLowerCase() !== 'focus session'
  );
}

function describeNativeFocusEndGuard(
  activeSession: NonNullable<ReturnType<typeof readVerifiedFocusProjection>>,
  disposition: 'ended' | 'completed',
): string {
  const linkedTaskIds = new Set(activeSession.linkedTaskIds);
  const linkedTasks = readStoredMemoryTasks().filter((task) =>
    linkedTaskIds.has(task.id),
  );
  const openTaskCount = linkedTasks.filter((task) => !task.completedAt).length;
  const completedTaskCount = linkedTasks.length - openTaskCount;
  const goalText = activeSession.goal
    ? ` Goal: ${activeSession.goal}.`
    : '';
  const taskText = linkedTasks.length
    ? ` It has ${linkedTasks.length} linked task${
        linkedTasks.length === 1 ? '' : 's'
      } (${openTaskCount} open, ${completedTaskCount} done).`
    : '';
  const terminalInstruction =
    disposition === 'completed'
      ? 'say "complete Focus anyway" to complete it without saving'
      : 'say "end Focus anyway" to end it without saving';
  return `You have an active Focus with no saved summary note: ${activeSession.title}.${goalText}${taskText} Save the Focus summary first, ${terminalInstruction}, or say "cancel" to keep it running.`;
}

function describeRetiredLegacyLifecycleBlock(command: MemoryCommandName): string {
  if (command === 'wrap-up-meeting-focus') {
    return (
      'I kept the meeting Focus open because meeting wrap-up still combines summary saving, ' +
      'follow-up task creation, and Focus completion without one verified transaction. ' +
      'Save the meeting summary, create follow-up tasks, and complete the Focus as separate verified actions.'
    );
  }
  return (
    'I blocked a retired legacy Focus lifecycle path because it did not reach the verified native executor. ' +
    'No Focus change was made.'
  );
}

export async function handleMemoryCommand(
  commandMatch: Parameters<typeof handleMemoryCommandCore>[0],
  deps: NativeFocusSummaryDeps,
): Promise<ReturnType<typeof handleMemoryCommandCore>> {
  const nativeReadSurface =
    commandMatch.command === 'read-memory'
      ? consumeNativeReadSurface()
      : null;

  if (commandMatch.command === 'read-memory') {
    const tasks = readStoredMemoryTasks();
    const activeSession = readVerifiedFocusProjection();
    deps.setActivePanel('memory');
    return {
      handled: true,
      confirmationContent: activeSession
        ? formatFocusTaskReadout(activeSession, tasks)
        : formatOpenTasksReadout(tasks),
      shouldSpeakConfirmation: deps.voiceOutputEnabled,
    };
  }

  if (nativeReadSurface === 'tasks') {
    deps.setActivePanel('memory');
    return {
      handled: true,
      confirmationContent: formatOpenTasksReadout(readStoredMemoryTasks()),
      shouldSpeakConfirmation: deps.voiceOutputEnabled,
    };
  }

  if (commandMatch.command === 'read-focus-session') {
    deps.setActivePanel('memory');
    try {
      return {
        handled: true,
        confirmationContent: await readCanonicalFocusReadout(),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    } catch (error) {
      console.warn(
        'Canonical Focus readout unavailable; falling back to the verified display projection:',
        error,
      );
      const fallbackResult = handleMemoryCommandCore(commandMatch, deps);
      return fallbackResult;
    }
  }

  if (commandMatch.command === 'start-focus-session') {
    const requestedTitle =
      commandMatch.focusSession?.title?.trim() ||
      commandMatch.payload?.trim() ||
      'Focus session';
    const requestedMode = commandMatch.focusSession?.mode;
    try {
      const result = await startNativeFocusVerified({
        title: requestedTitle,
        objective: commandMatch.focusSession?.goal?.trim() || '',
        mode: requestedMode,
      });
      const activeSession = projectVerifiedFocusToActiveSession(
        result,
        requestedMode,
      );
      applyVerifiedFocusProjection(activeSession);
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: result.message,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    } catch (error) {
      console.error('Verified native Focus start failed:', error);
      return {
        handled: true,
        confirmationContent: describeNativeFocusStartFailure(error),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
  }

  if (commandMatch.command === 'update-focus-session') {
    const contextCommand = parseNativeFocusContextCommand(commandMatch.payload);
    if (contextCommand) {
      const activeSession = readVerifiedFocusProjection();
      deps.setActivePanel('memory');
      if (!activeSession) {
        return {
          handled: true,
          confirmationContent:
            'No active Focus is currently running. Start a Focus first, then I can save that detail.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }
      try {
        const result = await addNativeFocusContextVerified({
          expectedFocusId: activeSession.id,
          expectedObjective: activeSession.goal,
          field: contextCommand.field,
          value: contextCommand.value,
          sourceTurnId: contextCommand.sourceTurnId,
        });
        try {
          applyVerifiedFocusContextProjection(result);
        } catch (error) {
          console.error('Verified Focus context projection was stale:', error);
          return {
            handled: true,
            confirmationContent:
              `${result.message} The canonical receipt is saved, but the visible Focus changed before its timestamp could be refreshed.`,
            shouldSpeakConfirmation: deps.voiceOutputEnabled,
          };
        }
        return {
          handled: true,
          confirmationContent: result.message,
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      } catch (error) {
        console.error('Verified native Focus context failed:', error);
        return {
          handled: true,
          confirmationContent: describeNativeFocusContextFailure(error),
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }
    }

    const payload = commandMatch.focusSession ?? {};
    const hasTitle = typeof payload.title === 'string';
    const hasObjective = typeof payload.goal === 'string';
    const hasMode = typeof payload.mode === 'string';
    try {
      const result = await updateNativeFocusVerified({
        ...(hasTitle ? { title: payload.title } : {}),
        ...(hasObjective ? { objective: payload.goal } : {}),
        ...(hasMode ? { mode: payload.mode } : {}),
        ...(commandMatch.payload ? { sourceTurnId: commandMatch.payload } : {}),
      });
      const activeSession = projectVerifiedFocusToActiveSession(
        result,
        hasMode ? payload.mode : undefined,
      );
      applyVerifiedFocusProjection(activeSession);
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: result.message,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    } catch (error) {
      console.error('Verified native Focus update failed:', error);
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: describeNativeFocusUpdateFailure(error),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
  }

  if (commandMatch.command === 'resume-last-focus-session') {
    const requestedMode = commandMatch.focusSession?.mode;
    try {
      const result = await resumeNativeFocusVerified({
        ...(requestedMode ? { mode: requestedMode } : {}),
      });
      const activeSession = projectVerifiedFocusToActiveSession(
        result,
        requestedMode,
      );
      applyVerifiedFocusProjection(activeSession);
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: result.message,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    } catch (error) {
      console.error('Verified native Focus resume failed:', error);
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: describeNativeFocusResumeFailure(error),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
  }

  if (commandMatch.command === 'prepare-calendar-focus') {
    deps.setActivePanel('calendar');
    try {
      const result = await prepareNextCalendarFocusVerified();
      try {
        applyVerifiedCalendarFocusPrepProjection(result);
      } catch (error) {
        console.error(
          'Verified calendar Focus projection could not be refreshed:',
          error,
        );
        return {
          handled: true,
          confirmationContent:
            `${result.message} The canonical combined receipt is saved, but the visible Focus changed before its projection could be refreshed.`,
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: result.message,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    } catch (error) {
      console.error('Verified native calendar Focus preparation failed:', error);
      return {
        handled: true,
        confirmationContent: describeNativeCalendarFocusPrepFailure(error),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
  }

  if (commandMatch.command === 'focus-to-tasks') {
    const activeSession = readVerifiedFocusProjection();
    deps.setActivePanel('memory');
    if (!activeSession) {
      return {
        handled: true,
        confirmationContent:
          'No active Focus is currently running. Start a Focus first, then I can create linked tasks.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
    const taskTitles = await buildContextAwareNativeFocusTaskTitles(activeSession);
    try {
      const result = await createNativeFocusTasksVerified({
        expectedFocusId: activeSession.id,
        taskTitles,
      });
      try {
        applyVerifiedFocusTaskProjection(result);
      } catch (error) {
        console.error('Verified Focus task projection was stale:', error);
        return {
          handled: true,
          confirmationContent:
            `${result.message} The canonical receipt is saved, but the visible Focus changed before its task projection could be refreshed.`,
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }
      return {
        handled: true,
        confirmationContent: result.message,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    } catch (error) {
      console.error('Verified native Focus task linking failed:', error);
      return {
        handled: true,
        confirmationContent: describeNativeFocusTasksFailure(error),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
  }

  if (commandMatch.command === 'create-meeting-follow-up-tasks') {
    const activeSession = readVerifiedFocusProjection();
    deps.setActivePanel('memory');
    if (!activeSession) {
      return {
        handled: true,
        confirmationContent:
          'No active Focus is currently running. Start or prepare a meeting Focus first, then I can create verified follow-up tasks.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
    const taskTitles = buildNativeMeetingFollowUpTaskTitles(activeSession);
    try {
      const result = await createNativeFocusTasksVerified({
        expectedFocusId: activeSession.id,
        taskTitles,
      });
      try {
        applyVerifiedFocusTaskProjection(result);
      } catch (error) {
        console.error(
          'Verified meeting follow-up task projection was stale:',
          error,
        );
        return {
          handled: true,
          confirmationContent:
            `${result.message} The canonical receipt is saved, but the visible Focus changed before its task projection could be refreshed.`,
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }
      return {
        handled: true,
        confirmationContent: result.message,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    } catch (error) {
      console.error(
        'Verified native meeting follow-up task linking failed:',
        error,
      );
      return {
        handled: true,
        confirmationContent: describeNativeFocusTasksFailure(error),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
  }

  if (commandMatch.command === 'save-focus-summary') {
    const activeSession = readVerifiedFocusProjection();
    if (!activeSession) {
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent:
          'No active Focus is currently running. Start a Focus first, then I can save its summary.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
    const summaryRead = await handleMemoryCommandCore(
      {
        ...commandMatch,
        command: 'summarize-focus-session',
      },
      deps,
    );
    let summary = summaryRead.confirmationContent?.trim() ?? '';
    if (!summary || !summaryRead.handled) {
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent:
          'I could not build a Focus summary, so no Note or Focus relationship was changed.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
    try {
      const context = await readNativeFocusContext(activeSession.id);
      summary = appendNativeFocusContextToSummary(summary, context);
    } catch (error) {
      console.warn(
        'Canonical Focus context was unavailable while building the summary; saving the verified base summary:',
        error,
      );
    }
    const note = deps.saveNote(summary);
    if (!note) {
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent:
          'I could not stage the Focus summary Note, so no canonical summary receipt was created.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
    let result;
    try {
      result = await saveNativeFocusSummaryVerified({
        expectedFocusId: activeSession.id,
        note,
      });
    } catch (error) {
      deps.deleteNote(note.id);
      console.error('Verified native Focus summary failed:', error);
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: describeNativeFocusSummaryFailure(error),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
    try {
      applyVerifiedFocusSummaryProjection(result);
    } catch (error) {
      console.error('Verified Focus summary projection was stale:', error);
      deps.setActivePanel('notes');
      return {
        handled: true,
        confirmationContent:
          `${result.message} The visible Focus changed before its verified summary relationship could be projected; refresh Memory to reconcile the display.`,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
    deps.setActivePanel('notes');
    return {
      handled: true,
      confirmationContent: result.message,
      shouldSpeakConfirmation: deps.voiceOutputEnabled,
    };
  }

  if (commandMatch.command === 'end-focus-with-summary') {
    deps.setActivePanel('memory');
    return {
      handled: true,
      confirmationContent:
        'I kept the Focus open because saving a summary and ending it still require separate verified receipts. Save the Focus summary first, then end the Focus, or say "end Focus anyway".',
      shouldSpeakConfirmation: deps.voiceOutputEnabled,
    };
  }

  if (commandMatch.command === 'end-focus-session') {
    const activeSession = readVerifiedFocusProjection();
    deps.setActivePanel('memory');
    if (!activeSession) {
      return {
        handled: true,
        confirmationContent: 'No active Focus is currently running.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
    const endCommand = parseNativeFocusEndCommand(commandMatch.payload);
    const forceEnd = Boolean(commandMatch.focusSession?.forceEnd);
    if (!forceEnd && shouldGuardNativeFocusEnd(activeSession)) {
      return {
        handled: true,
        confirmationContent: describeNativeFocusEndGuard(
          activeSession,
          endCommand.disposition,
        ),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
    try {
      const result = await endNativeFocusVerified({
        disposition: endCommand.disposition,
        ...(endCommand.sourceTurnId
          ? { sourceTurnId: endCommand.sourceTurnId }
          : {}),
      });
      applyVerifiedFocusProjection(null);
      return {
        handled: true,
        confirmationContent: result.message,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    } catch (error) {
      console.error('Verified native Focus terminal transition failed:', error);
      return {
        handled: true,
        confirmationContent: describeNativeFocusEndFailure(error),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }
  }

  if (RETIRED_LEGACY_FOCUS_OWNERSHIP_COMMANDS.has(commandMatch.command)) {
    console.error(
      'Retired legacy Focus ownership command reached the memoryCore fallback:',
      commandMatch.command,
    );
    deps.setActivePanel('memory');
    return {
      handled: true,
      confirmationContent: describeRetiredLegacyLifecycleBlock(
        commandMatch.command,
      ),
      shouldSpeakConfirmation: deps.voiceOutputEnabled,
    };
  }

  return handleMemoryCommandCore(commandMatch, deps);
}
