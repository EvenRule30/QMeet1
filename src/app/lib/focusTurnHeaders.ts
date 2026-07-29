import type { FocusToolResponse } from '../types';

const QMEET_TURN_HEADER = 'X-QMeet-Turn-Id';
const TURN_LINK_WINDOW_MS = 60_000;

const TURN_START_PATHS = new Set([
  '/api/command/interpret',
]);

const TURN_FOLLOW_UP_PATHS = new Set([
  '/api/chat',
  '/api/chat/stream',
  '/api/search',
  '/api/calendar/events',
]);

type ActiveTurn = {
  id: string;
  startedAt: number;
  linkedPaths: Set<string>;
};

let activeTurn: ActiveTurn | null = null;
let interceptorInstalled = false;
let latestCalendarFocusResponse: {
  turnId: string;
  response: FocusToolResponse;
} | null = null;

function createTurnId(): string {
  const randomPart =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID().replace(/-/g, '')
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;

  return `focus-turn-${randomPart}`;
}

function getRequestPath(request: Request): string {
  try {
    return new URL(request.url, window.location.origin).pathname;
  } catch {
    return '';
  }
}

function isFresh(turn: ActiveTurn): boolean {
  return Date.now() - turn.startedAt <= TURN_LINK_WINDOW_MS;
}

function rememberSuppliedTurnId(turnId: string, path: string): void {
  activeTurn = {
    id: turnId,
    startedAt: Date.now(),
    linkedPaths: new Set(
      TURN_FOLLOW_UP_PATHS.has(path) ? [path] : [],
    ),
  };
}

function startTurn(): string {
  const turnId = createTurnId();
  activeTurn = {
    id: turnId,
    startedAt: Date.now(),
    linkedPaths: new Set<string>(),
  };
  return turnId;
}

function resolveTurnId(request: Request, path: string): string {
  const suppliedTurnId = request.headers.get(QMEET_TURN_HEADER)?.trim();

  if (suppliedTurnId) {
    rememberSuppliedTurnId(suppliedTurnId, path);
    return suppliedTurnId;
  }

  if (TURN_START_PATHS.has(path)) {
    return startTurn();
  }

  if (
    TURN_FOLLOW_UP_PATHS.has(path) &&
    activeTurn &&
    isFresh(activeTurn) &&
    !activeTurn.linkedPaths.has(path)
  ) {
    activeTurn.linkedPaths.add(path);
    return activeTurn.id;
  }

  const turnId = startTurn();
  activeTurn?.linkedPaths.add(path);
  return turnId;
}

function shouldAttachTurnId(request: Request, path: string): boolean {
  const method = request.method.toUpperCase();

  if (path === '/api/calendar/events') {
    return method === 'GET';
  }

  if (method !== 'POST') {
    return false;
  }

  return TURN_START_PATHS.has(path) || TURN_FOLLOW_UP_PATHS.has(path);
}

function isFocusToolResponse(value: unknown): value is FocusToolResponse {
  if (!value || typeof value !== 'object') return false;

  const candidate = value as Partial<FocusToolResponse>;
  return (
    typeof candidate.text === 'string' &&
    typeof candidate.tool === 'string' &&
    Array.isArray(candidate.citations) &&
    typeof candidate.sourceTurnId === 'string' &&
    candidate.responseSource === 'focus-tool-guarded'
  );
}

export function installQMeetFocusTurnHeaders(): void {
  if (interceptorInstalled || typeof window === 'undefined') {
    return;
  }

  interceptorInstalled = true;
  const originalFetch = window.fetch.bind(window);

  window.fetch = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const request = new Request(input, init);
    const path = getRequestPath(request);

    if (!shouldAttachTurnId(request, path)) {
      return originalFetch(request);
    }

    const turnId = resolveTurnId(request, path);
    const headers = new Headers(request.headers);
    headers.set(QMEET_TURN_HEADER, turnId);

    if (path === '/api/calendar/events') {
      latestCalendarFocusResponse = null;
    }

    const response = await originalFetch(
      new Request(request, {
        headers,
      }),
    );

    if (path === '/api/calendar/events' && response.ok) {
      try {
        const payload = (await response.clone().json()) as {
          focusResponse?: unknown;
        };
        if (isFocusToolResponse(payload.focusResponse)) {
          latestCalendarFocusResponse = {
            turnId,
            response: payload.focusResponse,
          };
        }
      } catch {
        latestCalendarFocusResponse = null;
      }
    }

    return response;
  };
}

export function getActiveQMeetTurnId(): string | null {
  if (!activeTurn || !isFresh(activeTurn)) {
    return null;
  }

  return activeTurn.id;
}

export function consumeLatestCalendarFocusResponse(): FocusToolResponse | null {
  if (!latestCalendarFocusResponse) return null;

  const activeTurnId = getActiveQMeetTurnId();
  const stored = latestCalendarFocusResponse;
  latestCalendarFocusResponse = null;

  return activeTurnId === stored.turnId ? stored.response : null;
}
