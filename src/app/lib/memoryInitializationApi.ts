export interface MemoryInitializationResponse {
  ok: boolean;
  initialized: boolean;
}

const API_BASE_URL =
  import.meta.env.VITE_QMEET_API_URL ?? 'http://localhost:8000';

export async function getMemoryInitialization(): Promise<MemoryInitializationResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/memory/initialization`,
  );

  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      text || `Memory initialization error: ${response.status}`,
    );
  }

  return response.json();
}
