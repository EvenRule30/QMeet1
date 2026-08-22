export type MemoryUiContextTarget = 'focus' | 'tasks';

const MEMORY_UI_CONTEXT_STORAGE_KEY = 'qmeet-memory-ui-context';
export const MEMORY_UI_CONTEXT_EVENT = 'qmeet-memory-ui-context';

type MemoryUiContextEventDetail = {
  target: MemoryUiContextTarget;
};

function isMemoryUiContextTarget(value: unknown): value is MemoryUiContextTarget {
  return value === 'focus' || value === 'tasks';
}

export function rememberMemoryUiContext(target: MemoryUiContextTarget): void {
  if (typeof window === 'undefined') return;

  try {
    window.sessionStorage.setItem(MEMORY_UI_CONTEXT_STORAGE_KEY, target);
  } catch {
    // Session storage can be unavailable in restricted browser contexts.
  }

  window.dispatchEvent(
    new CustomEvent<MemoryUiContextEventDetail>(MEMORY_UI_CONTEXT_EVENT, {
      detail: { target },
    }),
  );
}

export function consumeMemoryUiContext(): MemoryUiContextTarget | null {
  if (typeof window === 'undefined') return null;

  try {
    const stored = window.sessionStorage.getItem(MEMORY_UI_CONTEXT_STORAGE_KEY);
    window.sessionStorage.removeItem(MEMORY_UI_CONTEXT_STORAGE_KEY);
    return isMemoryUiContextTarget(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function readMemoryUiContextEventTarget(
  event: Event,
): MemoryUiContextTarget | null {
  const detail = (event as CustomEvent<MemoryUiContextEventDetail>).detail;
  return isMemoryUiContextTarget(detail?.target) ? detail.target : null;
}
