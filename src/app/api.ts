import {
  ActiveSessionUpdateRequest,
  ActiveSessionResponse,
  ActiveSessionReplaceRequest,
  ActiveSessionClearResponse,
  BackendStatus,
  CalendarAuthResetResponse,
  CalendarAuthStartResponse,
  CalendarBackendStatus,
  CalendarBackendView,
  CalendarCreateEventRequest,
  CalendarCreateEventResponse,
  CalendarDeleteEventResponse,
  CalendarEventsResponse,
  CalendarUpdateEventRequest,
  CalendarUpdateEventResponse,
  CommandIntentResponse,
  MemoryClearCompletedResponse,
  MemoryContextClearResponse,
  MemoryContextExportResponse,
  MemoryContextImportRequest,
  MemoryContextReplaceRequest,
  MemoryContextResponse,
  MemoryNoteCreateRequest,
  MemoryNoteDeleteResponse,
  MemoryNotesClearResponse,
  MemoryNotesReplaceRequest,
  MemoryNotesResponse,
  MemoryStatusResponse,
  MemoryTaskCreateRequest,
  MemoryTaskDeleteResponse,
  MemoryTasksReplaceRequest,
  MemoryTasksResponse,
  MemoryTaskUpdateRequest,
  RecentActionCreateRequest,
  RecentActionDeleteResponse,
  RecentActionsClearResponse,
  RecentActionsReplaceRequest,
  RecentActionsResponse,
  RecentFocusSessionsResponse,
  RecentFocusSessionsReplaceRequest,
  RecentFocusSessionsClearResponse,
  RecentFocusSessionDeleteResponse,
  VisualContextClearResponse,
  VisualContextReplaceRequest,
  VisualContextResponse,
  VisualContextUpdateRequest,
  VisualObservationCreateRequest,
  VisualObservationCreateResponse,
  VisualObservationDeleteResponse,
  VisualSnapshotAnalysisResponse,
  SearchResponse,
} from './types';

export type ChatApiResponse = {
  reply: string;
  state: 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';
};

export type ChatStreamHandlers = {
  onStart?: () => void;
  onChunk: (text: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

const FALLBACK_API_BASE_URL = 'http://localhost:8000';

function normalizeApiBaseUrl(value: unknown): string {
  if (typeof value !== 'string') return FALLBACK_API_BASE_URL;
  const trimmedValue = value.trim();
  if (!trimmedValue) return FALLBACK_API_BASE_URL;
  return trimmedValue.replace(/\/+$/g, '');
}

export const QMEET_API_BASE_URL = normalizeApiBaseUrl(
  import.meta.env.VITE_QMEET_API_URL,
);

function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${QMEET_API_BASE_URL}${normalizedPath}`;
}

async function readErrorMessage(
  res: Response,
  fallbackMessage: string,
): Promise<string> {
  const text = await res.text();
  if (!text.trim()) return fallbackMessage;

  try {
    const parsed = JSON.parse(text) as {
      detail?: unknown;
      message?: unknown;
    };

    if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail;
    }

    if (typeof parsed.message === 'string' && parsed.message.trim()) {
      return parsed.message;
    }
  } catch {
    // Non-JSON error bodies are returned as-is below.
  }

  return text;
}

function fallbackWithStatus(fallbackMessage: string, status: number): string {
  const trimmedMessage = fallbackMessage.replace(/[.:\s]+$/g, '');
  return `${trimmedMessage}: ${status}`;
}

async function ensureOk(res: Response, fallbackMessage: string): Promise<void> {
  if (!res.ok) {
    throw new Error(
      await readErrorMessage(res, fallbackWithStatus(fallbackMessage, res.status)),
    );
  }
}

async function fetchJson<T>(
  path: string,
  init: RequestInit | undefined,
  fallbackMessage: string,
): Promise<T> {
  const res = await fetch(buildApiUrl(path), init);
  await ensureOk(res, fallbackMessage);
  return res.json();
}

export async function sendChatMessage(
  message: string,
): Promise<ChatApiResponse> {
  return fetchJson<ChatApiResponse>(
    '/api/chat',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message }),
    },
    'Backend error.',
  );
}

export async function getBackendStatus(): Promise<BackendStatus> {
  return fetchJson<BackendStatus>(
    '/api/status',
    undefined,
    'Backend status error.',
  );
}

export async function resetConversation(): Promise<void> {
  const res = await fetch(buildApiUrl('/api/reset'), {
    method: 'POST',
  });
  await ensureOk(res, 'Reset error.');
}

export async function interpretCommandIntent(
  message: string,
): Promise<CommandIntentResponse> {
  return fetchJson<CommandIntentResponse>(
    '/api/command/interpret',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message }),
    },
    'Command interpreter error.',
  );
}

export async function getCalendarStatus(): Promise<CalendarBackendStatus> {
  return fetchJson<CalendarBackendStatus>(
    '/api/calendar/status',
    undefined,
    'Calendar status error.',
  );
}

export async function startCalendarAuth(): Promise<CalendarAuthStartResponse> {
  return fetchJson<CalendarAuthStartResponse>(
    '/api/calendar/auth/start',
    { method: 'POST' },
    'Calendar auth start error.',
  );
}

export async function resetCalendarAuth(): Promise<CalendarAuthResetResponse> {
  return fetchJson<CalendarAuthResetResponse>(
    '/api/calendar/auth/reset',
    { method: 'POST' },
    'Calendar auth reset error.',
  );
}

export async function getCalendarEvents(
  view: CalendarBackendView = 'today',
): Promise<CalendarEventsResponse> {
  const params = new URLSearchParams({ view });
  return fetchJson<CalendarEventsResponse>(
    `/api/calendar/events?${params.toString()}`,
    undefined,
    'Calendar events error.',
  );
}

export async function createCalendarEvent(
  event: CalendarCreateEventRequest,
): Promise<CalendarCreateEventResponse> {
  return fetchJson<CalendarCreateEventResponse>(
    '/api/calendar/events',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(event),
    },
    'Calendar create event error.',
  );
}

export async function updateGoogleCalendarEvent(
  googleEventId: string,
  event: CalendarUpdateEventRequest,
): Promise<CalendarUpdateEventResponse> {
  const encodedId = encodeURIComponent(googleEventId);
  return fetchJson<CalendarUpdateEventResponse>(
    `/api/calendar/events/${encodedId}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(event),
    },
    'Calendar update event error.',
  );
}

export async function deleteGoogleCalendarEvent(
  googleEventId: string,
): Promise<CalendarDeleteEventResponse> {
  const encodedId = encodeURIComponent(googleEventId);
  return fetchJson<CalendarDeleteEventResponse>(
    `/api/calendar/events/${encodedId}`,
    { method: 'DELETE' },
    'Calendar delete event error.',
  );
}

export async function getMemoryStatus(): Promise<MemoryStatusResponse> {
  return fetchJson<MemoryStatusResponse>(
    '/api/memory/status',
    undefined,
    'Memory status error.',
  );
}

export async function getMemoryContext(): Promise<MemoryContextResponse> {
  return fetchJson<MemoryContextResponse>(
    '/api/memory/context',
    undefined,
    'Memory context error.',
  );
}

export async function getActiveSession(): Promise<ActiveSessionResponse> {
  return fetchJson<ActiveSessionResponse>(
    '/api/memory/session',
    undefined,
    'Active session error.',
  );
}

export async function replaceActiveSession(
  request: ActiveSessionReplaceRequest,
): Promise<ActiveSessionResponse> {
  return fetchJson<ActiveSessionResponse>(
    '/api/memory/session',
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Active session replace error.',
  );
}

export async function updateActiveSession(
  request: ActiveSessionUpdateRequest,
): Promise<ActiveSessionResponse> {
  return fetchJson<ActiveSessionResponse>(
    '/api/memory/session',
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Active session update error.',
  );
}

export async function clearActiveSession(): Promise<ActiveSessionClearResponse> {
  return fetchJson<ActiveSessionClearResponse>(
    '/api/memory/session',
    { method: 'DELETE' },
    'Active session clear error.',
  );
}


export async function getRecentFocusSessions(): Promise<RecentFocusSessionsResponse> {
  return fetchJson<RecentFocusSessionsResponse>(
    '/api/memory/sessions/recent',
    undefined,
    'Recent focus sessions error.',
  );
}

export async function replaceRecentFocusSessions(
  request: RecentFocusSessionsReplaceRequest,
): Promise<RecentFocusSessionsResponse> {
  return fetchJson<RecentFocusSessionsResponse>(
    '/api/memory/sessions/recent',
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Recent focus sessions replace error.',
  );
}

export async function clearRecentFocusSessions(): Promise<RecentFocusSessionsClearResponse> {
  return fetchJson<RecentFocusSessionsClearResponse>(
    '/api/memory/sessions/recent/clear',
    { method: 'POST' },
    'Recent focus sessions clear error.',
  );
}

export async function deleteRecentFocusSessionById(
  sessionId: string,
): Promise<RecentFocusSessionDeleteResponse> {
  const encodedId = encodeURIComponent(sessionId);
  return fetchJson<RecentFocusSessionDeleteResponse>(
    `/api/memory/sessions/recent/${encodedId}`,
    { method: 'DELETE' },
    'Recent focus session delete error.',
  );
}


export async function getVisualContext(): Promise<VisualContextResponse> {
  return fetchJson(
    '/api/memory/visual',
    undefined,
    'Visual context error.',
  );
}

export async function replaceVisualContext(
  request: VisualContextReplaceRequest,
): Promise<VisualContextResponse> {
  return fetchJson(
    '/api/memory/visual',
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Visual context replace error.',
  );
}

export async function updateVisualContext(
  request: VisualContextUpdateRequest,
): Promise<VisualContextResponse> {
  return fetchJson(
    '/api/memory/visual',
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Visual context update error.',
  );
}

export async function createVisualObservation(
  request: VisualObservationCreateRequest,
): Promise<VisualObservationCreateResponse> {
  return fetchJson(
    '/api/memory/visual/observations',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Visual observation create error.',
  );
}

export async function clearVisualContext(): Promise<VisualContextClearResponse> {
  return fetchJson(
    '/api/memory/visual/clear',
    { method: 'POST' },
    'Visual context clear error.',
  );
}

export async function deleteVisualObservationById(
  observationId: string,
): Promise<VisualObservationDeleteResponse> {
  const encodedId = encodeURIComponent(observationId);
  return fetchJson(
    `/api/memory/visual/observations/${encodedId}`,
    { method: 'DELETE' },
    'Visual observation delete error.',
  );
}

export async function analyzeVisualSnapshot(
  snapshot: Blob,
): Promise<VisualSnapshotAnalysisResponse> {
  const contentType = snapshot.type || 'image/jpeg';
  const res = await fetch(buildApiUrl('/api/visual/analyze-snapshot'), {
    method: 'POST',
    headers: {
      'Content-Type': contentType,
    },
    body: snapshot,
  });

  await ensureOk(res, 'Visual snapshot analysis error.');
  return res.json();
}

export async function replaceMemoryContext(
  request: MemoryContextReplaceRequest,
): Promise<MemoryContextResponse> {
  return fetchJson<MemoryContextResponse>(
    '/api/memory/context',
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Memory context replace error.',
  );
}

export async function exportMemoryContext(): Promise<MemoryContextExportResponse> {
  return fetchJson<MemoryContextExportResponse>(
    '/api/memory/export',
    undefined,
    'Memory export error.',
  );
}

export async function importMemoryContext(
  request: MemoryContextImportRequest,
): Promise<MemoryContextResponse> {
  return fetchJson<MemoryContextResponse>(
    '/api/memory/import',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Memory import error.',
  );
}

export async function clearAllMemoryContext(): Promise<MemoryContextClearResponse> {
  return fetchJson<MemoryContextClearResponse>(
    '/api/memory/clear',
    { method: 'POST' },
    'Memory clear error.',
  );
}

export async function getMemoryTasks(): Promise<MemoryTasksResponse> {
  return fetchJson<MemoryTasksResponse>(
    '/api/memory/tasks',
    undefined,
    'Memory tasks error.',
  );
}

export async function replaceMemoryTasks(
  request: MemoryTasksReplaceRequest,
): Promise<MemoryTasksResponse> {
  return fetchJson<MemoryTasksResponse>(
    '/api/memory/tasks',
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Memory replace error.',
  );
}

export async function createMemoryTask(
  request: MemoryTaskCreateRequest,
): Promise<MemoryTasksResponse> {
  return fetchJson<MemoryTasksResponse>(
    '/api/memory/tasks',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Memory create error.',
  );
}

export async function updateMemoryTask(
  taskId: string,
  request: MemoryTaskUpdateRequest,
): Promise<MemoryTasksResponse> {
  const encodedId = encodeURIComponent(taskId);
  return fetchJson<MemoryTasksResponse>(
    `/api/memory/tasks/${encodedId}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Memory update error.',
  );
}

export async function deleteMemoryTaskById(
  taskId: string,
): Promise<MemoryTaskDeleteResponse> {
  const encodedId = encodeURIComponent(taskId);
  return fetchJson<MemoryTaskDeleteResponse>(
    `/api/memory/tasks/${encodedId}`,
    { method: 'DELETE' },
    'Memory delete error.',
  );
}

export async function clearCompletedMemoryTasks(): Promise<MemoryClearCompletedResponse> {
  return fetchJson<MemoryClearCompletedResponse>(
    '/api/memory/tasks/clear-completed',
    { method: 'POST' },
    'Memory clear completed error.',
  );
}

export async function getMemoryNotes(): Promise<MemoryNotesResponse> {
  return fetchJson<MemoryNotesResponse>(
    '/api/memory/notes',
    undefined,
    'Memory notes error.',
  );
}

export async function replaceMemoryNotes(
  request: MemoryNotesReplaceRequest,
): Promise<MemoryNotesResponse> {
  return fetchJson<MemoryNotesResponse>(
    '/api/memory/notes',
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Memory notes replace error.',
  );
}

export async function createMemoryNote(
  request: MemoryNoteCreateRequest,
): Promise<MemoryNotesResponse> {
  return fetchJson<MemoryNotesResponse>(
    '/api/memory/notes',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Memory note create error.',
  );
}

export async function deleteMemoryNote(
  noteId: string,
): Promise<MemoryNoteDeleteResponse> {
  const encodedId = encodeURIComponent(noteId);
  return fetchJson<MemoryNoteDeleteResponse>(
    `/api/memory/notes/${encodedId}`,
    { method: 'DELETE' },
    'Memory note delete error.',
  );
}

export async function clearMemoryNotes(): Promise<MemoryNotesClearResponse> {
  return fetchJson<MemoryNotesClearResponse>(
    '/api/memory/notes/clear',
    { method: 'POST' },
    'Memory notes clear error.',
  );
}

export async function getRecentActions(): Promise<RecentActionsResponse> {
  return fetchJson<RecentActionsResponse>(
    '/api/memory/actions',
    undefined,
    'Recent actions error.',
  );
}

export async function replaceRecentActions(
  request: RecentActionsReplaceRequest,
): Promise<RecentActionsResponse> {
  return fetchJson<RecentActionsResponse>(
    '/api/memory/actions',
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Recent actions replace error.',
  );
}

export async function createRecentAction(
  request: RecentActionCreateRequest,
): Promise<RecentActionsResponse> {
  return fetchJson<RecentActionsResponse>(
    '/api/memory/actions',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    },
    'Recent action create error.',
  );
}

export async function deleteRecentActionById(
  actionId: string,
): Promise<RecentActionDeleteResponse> {
  const encodedId = encodeURIComponent(actionId);
  return fetchJson<RecentActionDeleteResponse>(
    `/api/memory/actions/${encodedId}`,
    { method: 'DELETE' },
    'Recent action delete error.',
  );
}

export async function clearRecentActions(): Promise<RecentActionsClearResponse> {
  return fetchJson<RecentActionsClearResponse>(
    '/api/memory/actions/clear',
    { method: 'POST' },
    'Recent actions clear error.',
  );
}

export async function searchWeb(query: string): Promise<SearchResponse> {
  return fetchJson<SearchResponse>(
    '/api/search',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    },
    'Web search error.',
  );
}

type StreamEventPayload = Record<string, unknown>;

type ParsedServerSentEvent = {
  event: string;
  data: string;
};

function parseServerSentEvent(rawEvent: string): ParsedServerSentEvent | null {
  const lines = rawEvent.split('\n');
  let event = 'message';
  const dataLines: string[] = [];

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();

    if (!line || line.startsWith(':')) {
      continue;
    }

    const separatorIndex = line.indexOf(':');
    const field = separatorIndex === -1 ? line : line.slice(0, separatorIndex);
    let value = separatorIndex === -1 ? '' : line.slice(separatorIndex + 1);

    if (value.startsWith(' ')) {
      value = value.slice(1);
    }

    if (field === 'event') {
      event = value.trim() || 'message';
      continue;
    }

    if (field === 'data') {
      dataLines.push(value);
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event,
    data: dataLines.join('\n'),
  };
}

function parseStreamEventPayload(
  eventName: string,
  dataRaw: string,
): StreamEventPayload {
  try {
    const parsed = JSON.parse(dataRaw) as unknown;
    return parsed && typeof parsed === 'object'
      ? (parsed as StreamEventPayload)
      : {};
  } catch {
    throw new Error(`Malformed streaming event from backend: ${eventName}.`);
  }
}

function getStringPayloadValue(
  payload: StreamEventPayload,
  key: string,
): string {
  const value = payload[key];
  return typeof value === 'string' ? value : '';
}

export async function streamChatMessage(
  message: string,
  handlers: ChatStreamHandlers,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const res = await fetch(buildApiUrl('/api/chat/stream'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ message }),
    signal: options.signal,
  });

  await ensureOk(res, 'Streaming backend error.');

  if (!res.body) {
    throw new Error('Streaming response body was empty.');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let terminalEventSeen = false;

  const processRawEvent = (rawEvent: string) => {
    const parsedEvent = parseServerSentEvent(rawEvent);
    if (!parsedEvent || terminalEventSeen) return;

    const data = parseStreamEventPayload(parsedEvent.event, parsedEvent.data);

    if (parsedEvent.event === 'start') {
      handlers.onStart?.();
      return;
    }

    if (parsedEvent.event === 'chunk') {
      handlers.onChunk(getStringPayloadValue(data, 'text'));
      return;
    }

    if (parsedEvent.event === 'done') {
      terminalEventSeen = true;
      handlers.onDone?.();
      return;
    }

    if (parsedEvent.event === 'error') {
      terminalEventSeen = true;
      handlers.onError?.(
        getStringPayloadValue(data, 'message') || 'Streaming error.',
      );
    }
  };

  const processBufferedEvents = () => {
    let boundaryIndex = buffer.indexOf('\n\n');

    while (boundaryIndex !== -1) {
      const rawEvent = buffer.slice(0, boundaryIndex);
      buffer = buffer.slice(boundaryIndex + 2);
      processRawEvent(rawEvent);
      boundaryIndex = buffer.indexOf('\n\n');
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder
        .decode(value, { stream: true })
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n');

      processBufferedEvents();
    }

    buffer += decoder.decode().replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    processBufferedEvents();

    const finalBufferedEvent = buffer.trim();
    if (finalBufferedEvent) {
      processRawEvent(finalBufferedEvent);
    }

    if (!terminalEventSeen && !options.signal?.aborted) {
      throw new Error(
        'Streaming connection closed before QMeet finished the response.',
      );
    }
  } finally {
    reader.releaseLock();
  }
}
