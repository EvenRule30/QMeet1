export * from './memoryCore';

import { handleMemoryCommand as handleMemoryCommandCore } from './memoryCore';
import {
  formatOpenTasksReadout,
  readStoredMemoryTasks,
} from '../lib/memoryReadSurface';
import { consumeNativeReadSurface } from '../lib/nativeReadSurfaceBridge';
import {
  applyVerifiedFocusProjection,
  describeNativeFocusStartFailure,
  describeNativeFocusUpdateFailure,
  projectVerifiedFocusToActiveSession,
  startNativeFocusVerified,
  updateNativeFocusVerified,
} from '../lib/nativeFocusLifecycle';

export async function handleMemoryCommand(
  commandMatch: Parameters<typeof handleMemoryCommandCore>[0],
  deps: Parameters<typeof handleMemoryCommandCore>[1],
): Promise<ReturnType<typeof handleMemoryCommandCore>> {
  const nativeReadSurface =
    commandMatch.command === 'read-memory'
      ? consumeNativeReadSurface()
      : null;
  if (nativeReadSurface === 'tasks') {
    deps.setActivePanel('memory');
    return {
      handled: true,
      confirmationContent: formatOpenTasksReadout(readStoredMemoryTasks()),
      shouldSpeakConfirmation: deps.voiceOutputEnabled,
    };
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

  return handleMemoryCommandCore(commandMatch, deps);
}
