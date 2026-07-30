export * from './memoryCore';

import { handleMemoryCommand as handleMemoryCommandCore } from './memoryCore';
import {
  formatOpenTasksReadout,
  readStoredMemoryTasks,
} from '../lib/memoryReadSurface';
import { consumeNativeReadSurface } from '../lib/nativeReadSurfaceBridge';

export function handleMemoryCommand(
  commandMatch: Parameters<typeof handleMemoryCommandCore>[0],
  deps: Parameters<typeof handleMemoryCommandCore>[1],
): ReturnType<typeof handleMemoryCommandCore> {
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

  return handleMemoryCommandCore(commandMatch, deps);
}
