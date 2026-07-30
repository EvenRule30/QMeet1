export * from './apiCore';

import { interpretCommandIntent as interpretCommandIntentCore } from './apiCore';
import type { CommandIntentResponse } from './types';
import { captureNativeReadSurface } from './lib/nativeReadSurfaceBridge';

export async function interpretCommandIntent(
  message: string,
): Promise<CommandIntentResponse> {
  const response = await interpretCommandIntentCore(message);
  captureNativeReadSurface(response);
  return response;
}
