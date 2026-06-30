import { BackendStatus } from "./types";

export type ChatApiResponse = {
  reply: string;
  state: "idle" | "listening" | "thinking" | "speaking" | "error";
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
