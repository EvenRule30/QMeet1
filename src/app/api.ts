import { BackendStatus, CalendarAuthResetResponse, CalendarAuthStartResponse, CalendarBackendStatus, CalendarBackendView, CalendarCreateEventRequest, CalendarCreateEventResponse, CalendarDeleteEventResponse, CalendarEventsResponse, CalendarUpdateEventRequest, CalendarUpdateEventResponse, CommandIntentResponse, MemoryStatusResponse, MemoryTaskCreateRequest, MemoryTaskDeleteResponse, MemoryTaskUpdateRequest, MemoryTasksReplaceRequest, MemoryTasksResponse, MemoryClearCompletedResponse, MemoryContextReplaceRequest, MemoryContextResponse, RecentActionCreateRequest, RecentActionDeleteResponse, RecentActionsClearResponse, RecentActionsReplaceRequest, RecentActionsResponse, SearchResponse } from "./types";

export type ChatApiResponse = {
  reply: string;
  state: "idle" | "listening" | "thinking" | "speaking" | "error";
};

export type ChatStreamHandlers = {
  onStart?: () => void;
  onChunk: (text: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

const API_BASE_URL =
  import.meta.env.VITE_QMEET_API_URL ?? "http://localhost:8000";

export async function sendChatMessage(message: string): Promise<ChatApiResponse> {
  const res = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Backend error: ${res.status}`);
  }

  return res.json();
}

export async function getBackendStatus(): Promise<BackendStatus> {
  const res = await fetch(`${API_BASE_URL}/api/status`);

  if (!res.ok) {
    throw new Error(`Backend status error: ${res.status}`);
  }

  return res.json();
}

export async function resetConversation(): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/reset`, {
    method: "POST",
  });

  if (!res.ok) {
    throw new Error(`Reset error: ${res.status}`);
  }
}


export async function interpretCommandIntent(message: string): Promise<CommandIntentResponse> {
  const res = await fetch(`${API_BASE_URL}/api/command/interpret`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Command interpreter error: ${res.status}`);
  }

  return res.json();
}


export async function getCalendarStatus(): Promise<CalendarBackendStatus> {
  const res = await fetch(`${API_BASE_URL}/api/calendar/status`);

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Calendar status error: ${res.status}`);
  }

  return res.json();
}

export async function startCalendarAuth(): Promise<CalendarAuthStartResponse> {
  const res = await fetch(`${API_BASE_URL}/api/calendar/auth/start`, {
    method: "POST",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Calendar auth start error: ${res.status}`);
  }

  return res.json();
}

export async function resetCalendarAuth(): Promise<CalendarAuthResetResponse> {
  const res = await fetch(`${API_BASE_URL}/api/calendar/auth/reset`, {
    method: "POST",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Calendar auth reset error: ${res.status}`);
  }

  return res.json();
}

export async function getCalendarEvents(view: CalendarBackendView = "today"): Promise<CalendarEventsResponse> {
  const params = new URLSearchParams({ view });
  const res = await fetch(`${API_BASE_URL}/api/calendar/events?${params.toString()}`);

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Calendar events error: ${res.status}`);
  }

  return res.json();
}


export async function createCalendarEvent(event: CalendarCreateEventRequest): Promise<CalendarCreateEventResponse> {
  const res = await fetch(`${API_BASE_URL}/api/calendar/events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(event),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Calendar create event error: ${res.status}`);
  }

  return res.json();
}




export async function updateGoogleCalendarEvent(
  googleEventId: string,
  event: CalendarUpdateEventRequest
): Promise<CalendarUpdateEventResponse> {
  const encodedId = encodeURIComponent(googleEventId);
  const res = await fetch(`${API_BASE_URL}/api/calendar/events/${encodedId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(event),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Calendar update event error: ${res.status}`);
  }

  return res.json();
}

export async function deleteGoogleCalendarEvent(googleEventId: string): Promise<CalendarDeleteEventResponse> {
  const encodedId = encodeURIComponent(googleEventId);
  const res = await fetch(`${API_BASE_URL}/api/calendar/events/${encodedId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Calendar delete event error: ${res.status}`);
  }

  return res.json();
}


export async function getMemoryStatus(): Promise<MemoryStatusResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/status`);

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Memory status error: ${res.status}`);
  }

  return res.json();
}

export async function getMemoryContext(): Promise<MemoryContextResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/context`);

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Memory context error: ${res.status}`);
  }

  return res.json();
}

export async function replaceMemoryContext(request: MemoryContextReplaceRequest): Promise<MemoryContextResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/context`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Memory context replace error: ${res.status}`);
  }

  return res.json();
}

export async function getMemoryTasks(): Promise<MemoryTasksResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/tasks`);

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Memory tasks error: ${res.status}`);
  }

  return res.json();
}

export async function replaceMemoryTasks(request: MemoryTasksReplaceRequest): Promise<MemoryTasksResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/tasks`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Memory replace error: ${res.status}`);
  }

  return res.json();
}

export async function createMemoryTask(request: MemoryTaskCreateRequest): Promise<MemoryTasksResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/tasks`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Memory create error: ${res.status}`);
  }

  return res.json();
}

export async function updateMemoryTask(taskId: string, request: MemoryTaskUpdateRequest): Promise<MemoryTasksResponse> {
  const encodedId = encodeURIComponent(taskId);
  const res = await fetch(`${API_BASE_URL}/api/memory/tasks/${encodedId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Memory update error: ${res.status}`);
  }

  return res.json();
}

export async function deleteMemoryTaskById(taskId: string): Promise<MemoryTaskDeleteResponse> {
  const encodedId = encodeURIComponent(taskId);
  const res = await fetch(`${API_BASE_URL}/api/memory/tasks/${encodedId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Memory delete error: ${res.status}`);
  }

  return res.json();
}

export async function clearCompletedMemoryTasks(): Promise<MemoryClearCompletedResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/tasks/clear-completed`, {
    method: "POST",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Memory clear completed error: ${res.status}`);
  }

  return res.json();
}


export async function getRecentActions(): Promise<RecentActionsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/actions`);

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Recent actions error: ${res.status}`);
  }

  return res.json();
}

export async function replaceRecentActions(request: RecentActionsReplaceRequest): Promise<RecentActionsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/actions`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Recent actions replace error: ${res.status}`);
  }

  return res.json();
}

export async function createRecentAction(request: RecentActionCreateRequest): Promise<RecentActionsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/actions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Recent action create error: ${res.status}`);
  }

  return res.json();
}

export async function deleteRecentActionById(actionId: string): Promise<RecentActionDeleteResponse> {
  const encodedId = encodeURIComponent(actionId);
  const res = await fetch(`${API_BASE_URL}/api/memory/actions/${encodedId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Recent action delete error: ${res.status}`);
  }

  return res.json();
}

export async function clearRecentActions(): Promise<RecentActionsClearResponse> {
  const res = await fetch(`${API_BASE_URL}/api/memory/actions/clear`, {
    method: "POST",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Recent actions clear error: ${res.status}`);
  }

  return res.json();
}


export async function searchWeb(query: string): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE_URL}/api/search`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Web search error: ${res.status}`);
  }

  return res.json();
}

export async function streamChatMessage(
  message: string,
  handlers: ChatStreamHandlers,
  options: { signal?: AbortSignal } = {}
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message }),
    signal: options.signal,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Streaming backend error: ${res.status}`);
  }

  if (!res.body) {
    throw new Error("Streaming response body was empty.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();

  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();

    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const rawEvent of events) {
      const lines = rawEvent.split("\n");
      const eventLine = lines.find((line) => line.startsWith("event:"));
      const dataLine = lines.find((line) => line.startsWith("data:"));

      const event = eventLine?.replace("event:", "").trim();
      const dataRaw = dataLine?.replace("data:", "").trim();

      if (!event || !dataRaw) continue;

      const data = JSON.parse(dataRaw);

      if (event === "start") {
        handlers.onStart?.();
      }

      if (event === "chunk") {
        handlers.onChunk(data.text ?? "");
      }

      if (event === "done") {
        handlers.onDone?.();
      }

      if (event === "error") {
        handlers.onError?.(data.message ?? "Streaming error.");
      }
    }
  }
}
