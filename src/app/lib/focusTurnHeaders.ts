import type { FocusToolResponse } from '../types';

const QMEET_TURN_HEADER = 'X-QMeet-Turn-Id';
const QMEET_CALENDAR_READ_INTENT_HEADER = 'X-QMeet-Calendar-Read-Intent';
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
let explicitCalendarReadPending = false;
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


type CommandIntentPayload = {
  intent?: unknown;
  action?: unknown;
  confidence?: unknown;
  frontendCommand?: unknown;
  payload?: unknown;
  reason?: unknown;
  [key: string]: unknown;
};

function normalizeCommandText(value: string): string {
  return value
    .trim()
    .replace(/[?!,;:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/[.]+$/g, '')
    .trim();
}

function extractNamedTaskCompletionTarget(message: string): string {
  const normalized = normalizeCommandText(message);
  const politePrefix =
    '(?:(?:please\\s+)?(?:can|could|would|will)\\s+you\\s+(?:please\\s+)?|please\\s+)?';
  const patterns = [
    new RegExp(
      `^${politePrefix}(?:mark|set|complete|finish)\\s+` +
        '(?:the\\s+)?(?:task\\s+)?(?:called|named|about)?\\s*' +
        '(.+?)\\s+(?:as\\s+)?(?:done|complete|completed|finished)$',
      'i',
    ),
  ];

  for (const pattern of patterns) {
    const match = normalized.match(pattern);
    if (!match?.[1]) continue;

    const target = match[1]
      .replace(/\s+task$/i, '')
      .replace(/^[\s'\"]+|[\s'\"]+$/g, '')
      .replace(/\s+/g, ' ')
      .trim();

    if (target) return target;
  }

  return '';
}

function normalizedAction(value: unknown): string {
  return typeof value === 'string'
    ? value.trim().toLowerCase().replace(/-/g, '_')
    : '';
}

export function repairNamedTaskCompletionResponse(
  message: string,
  value: unknown,
): CommandIntentPayload | null {
  if (!value || typeof value !== 'object') return null;

  const payload = value as CommandIntentPayload;
  if (
    normalizedAction(payload.intent) !== 'command' ||
    normalizedAction(payload.action) !== 'mark_task_done'
  ) {
    return null;
  }

  const target = extractNamedTaskCompletionTarget(message);
  if (!target) return null;

  const rawCommand =
    typeof payload.frontendCommand === 'string'
      ? payload.frontendCommand.trim()
      : '';
  const rawPayload =
    payload.payload && typeof payload.payload === 'object'
      ? (payload.payload as Record<string, unknown>)
      : {};
  const existingValue =
    typeof rawPayload.value === 'string' ? rawPayload.value.trim() : '';

  const targetKey = target.toLowerCase();
  const commandHasTarget = rawCommand.toLowerCase().includes(targetKey);
  const payloadHasTarget = existingValue.toLowerCase() === targetKey;

  if (commandHasTarget && payloadHasTarget) {
    return null;
  }

  return {
    ...payload,
    frontendCommand: `mark task ${target} done`,
    payload: {
      ...rawPayload,
      operation: 'complete_task',
      value: target,
    },
  };
}

async function readCommandMessage(request: Request): Promise<string> {
  try {
    const payload = (await request.clone().json()) as { message?: unknown };
    return typeof payload.message === 'string' ? payload.message.trim() : '';
  } catch {
    return '';
  }
}

async function repairCommandResponse(
  response: Response,
  message: string,
): Promise<Response> {
  if (!response.ok || !message) return response;

  try {
    const payload = (await response.clone().json()) as unknown;
    const repaired = repairNamedTaskCompletionResponse(message, payload);
    if (!repaired) return response;

    const headers = new Headers(response.headers);
    headers.delete('content-length');
    headers.delete('content-encoding');
    headers.set('content-type', 'application/json; charset=utf-8');
    headers.set('x-qmeet-client-command-repair', 'named-task-target');

    return new Response(JSON.stringify(repaired), {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  } catch {
    return response;
  }
}

export function beginExplicitCalendarRead(): void {
  explicitCalendarReadPending = true;
}

export function clearExplicitCalendarRead(): void {
  explicitCalendarReadPending = false;
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
    const commandMessage =
      path === '/api/command/interpret'
        ? await readCommandMessage(request)
        : '';

    if (!shouldAttachTurnId(request, path)) {
      const response = await originalFetch(request);
      return path === '/api/command/interpret'
        ? repairCommandResponse(response, commandMessage)
        : response;
    }

    const turnId = resolveTurnId(request, path);
    const headers = new Headers(request.headers);
    headers.set(QMEET_TURN_HEADER, turnId);

    const isExplicitCalendarRead =
      path === '/api/calendar/events' && explicitCalendarReadPending;

    if (path === '/api/calendar/events') {
      explicitCalendarReadPending = false;
      if (isExplicitCalendarRead) {
        headers.set(QMEET_CALENDAR_READ_INTENT_HEADER, 'explicit');
        latestCalendarFocusResponse = null;
      }
    }

    const response = await originalFetch(
      new Request(request, {
        headers,
      }),
    );

    if (isExplicitCalendarRead && response.ok) {
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

    return path === '/api/command/interpret'
      ? repairCommandResponse(response, commandMessage)
      : response;
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
