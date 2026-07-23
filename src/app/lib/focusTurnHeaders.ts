const QMEET_TURN_HEADER = 'X-QMeet-Turn-Id';
const TURN_LINK_WINDOW_MS = 60_000;

const TURN_START_PATHS = new Set([
  '/api/command/interpret',
]);

const TURN_FOLLOW_UP_PATHS = new Set([
  '/api/chat',
  '/api/chat/stream',
  '/api/search',
]);

type ActiveTurn = {
  id: string;
  startedAt: number;
  linkedPaths: Set<string>;
};

let activeTurn: ActiveTurn | null = null;
let interceptorInstalled = false;

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
  if (request.method.toUpperCase() !== 'POST') {
    return false;
  }

  return TURN_START_PATHS.has(path) || TURN_FOLLOW_UP_PATHS.has(path);
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

    const headers = new Headers(request.headers);
    headers.set(QMEET_TURN_HEADER, resolveTurnId(request, path));

    return originalFetch(
      new Request(request, {
        headers,
      }),
    );
  };
}

export function getActiveQMeetTurnId(): string | null {
  if (!activeTurn || !isFresh(activeTurn)) {
    return null;
  }

  return activeTurn.id;
}
