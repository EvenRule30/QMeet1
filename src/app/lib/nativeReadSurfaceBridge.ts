export type NativeReadSurface = 'tasks';

type PendingNativeReadSurface = {
  surface: NativeReadSurface;
  capturedAt: number;
};

type CommandInterpretPayload = {
  intent?: unknown;
  confidence?: unknown;
  frontendCommand?: unknown;
  payload?: unknown;
};

const SURFACE_TTL_MS = 2_000;
let pendingNativeReadSurface: PendingNativeReadSurface | null = null;

function normalizeSurface(value: unknown): NativeReadSurface | null {
  if (typeof value !== 'string') return null;
  return value.trim().toLowerCase() === 'tasks' ? 'tasks' : null;
}

function readResponseSurface(value: unknown): NativeReadSurface | null {
  if (!value || typeof value !== 'object') return null;

  const response = value as CommandInterpretPayload;
  if (response.intent !== 'command') return null;
  if (typeof response.confidence !== 'number' || response.confidence < 0.9) {
    return null;
  }
  if (
    typeof response.frontendCommand !== 'string' ||
    response.frontendCommand.trim().toLowerCase() !== 'read memory'
  ) {
    return null;
  }
  if (!response.payload || typeof response.payload !== 'object') return null;

  return normalizeSurface((response.payload as Record<string, unknown>).surface);
}

export function captureNativeReadSurface(value: unknown): void {
  const surface = readResponseSurface(value);
  pendingNativeReadSurface = surface
    ? {
        surface,
        capturedAt: Date.now(),
      }
    : null;
}

export function consumeNativeReadSurface(): NativeReadSurface | null {
  const captured = pendingNativeReadSurface;
  pendingNativeReadSurface = null;

  if (!captured) return null;
  if (Date.now() - captured.capturedAt > SURFACE_TTL_MS) return null;
  return captured.surface;
}
