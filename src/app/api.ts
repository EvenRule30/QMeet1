import { BackendStatus, CommandIntentResponse } from "./types";

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
