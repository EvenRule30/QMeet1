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

type WindowWithNativeReadCapture = Window & {
  __qmeetNativeReadSurfaceCaptureInstalled__?: boolean;
  __qmeetPendingNativeReadSurface__?: PendingNativeReadSurface | null;
};

const COMMAND_INTERPRET_PATH = '/api/command/interpret';
const SURFACE_TTL_MS = 2_000;

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

function getCaptureWindow(): WindowWithNativeReadCapture | null {
  if (typeof window === 'undefined') return null;
  return window as WindowWithNativeReadCapture;
}

function captureResponseSurface(value: unknown) {
  const captureWindow = getCaptureWindow();
  if (!captureWindow) return;

  const surface = readResponseSurface(value);
  captureWindow.__qmeetPendingNativeReadSurface__ = surface
    ? {
        surface,
        capturedAt: Date.now(),
      }
    : null;
}

function getRequestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function isCommandInterpretRequest(input: RequestInfo | URL): boolean {
  if (typeof window === 'undefined') return false;

  try {
    const url = new URL(getRequestUrl(input), window.location.origin);
    return url.pathname === COMMAND_INTERPRET_PATH;
  } catch {
    return false;
  }
}

export function consumeNativeReadSurface(): NativeReadSurface | null {
  const captureWindow = getCaptureWindow();
  if (!captureWindow) return null;

  const captured = captureWindow.__qmeetPendingNativeReadSurface__ ?? null;
  captureWindow.__qmeetPendingNativeReadSurface__ = null;

  if (!captured) return null;
  if (Date.now() - captured.capturedAt > SURFACE_TTL_MS) return null;
  return captured.surface;
}

export function installNativeReadSurfaceCapture() {
  const captureWindow = getCaptureWindow();
  if (!captureWindow || typeof captureWindow.fetch !== 'function') {
    return;
  }
  if (captureWindow.__qmeetNativeReadSurfaceCaptureInstalled__) return;

  const originalFetch = captureWindow.fetch.bind(captureWindow);
  captureWindow.__qmeetNativeReadSurfaceCaptureInstalled__ = true;

  captureWindow.fetch = async (...args: Parameters<typeof fetch>) => {
    const response = await originalFetch(...args);

    if (!isCommandInterpretRequest(args[0])) {
      return response;
    }

    try {
      const responseBody = await response.clone().json();
      captureResponseSurface(responseBody);
    } catch {
      captureWindow.__qmeetPendingNativeReadSurface__ = null;
    }

    return response;
  };
}
