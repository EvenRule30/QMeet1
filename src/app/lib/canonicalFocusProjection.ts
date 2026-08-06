import { QMEET_API_BASE_URL } from '../api';
import type {
  ActiveSession,
  MemorySessionMode,
  RecentFocusSession,
} from '../types';

const ACTIVE_SESSION_STORAGE_KEY = 'qmeet-active-session';
const ACTIVE_SESSION_SESSION_STORAGE_KEY = 'qmeet-active-session-live';
const ACTIVE_SESSION_STATE_EVENT = 'qmeet-active-session-state';

const OPEN_CANONICAL_FOCUS_STATUSES = new Set([
  'clarifying',
  'active',
  'waiting',
  'ready',
]);

type CanonicalFocusStatus =
  | 'inactive'
  | 'clarifying'
  | 'active'
  | 'waiting'
  | 'ready'
  | 'complete';

export type CanonicalFocusState = {
  focusId: string;
  title: string;
  objective: string;
  status: CanonicalFocusStatus;
  createdAt: string;
  updatedAt: string;
};

type CanonicalFocusStateResponse = {
  ok: boolean;
  state: CanonicalFocusState;
  linkedTaskIds: string[];
  eventCount: number;
};

type CanonicalFocusSnapshot = {
  state: CanonicalFocusState;
  linkedTaskIds: string[];
};

type FocusProjectionSource = Pick<
  ActiveSession,
  | 'id'
  | 'title'
  | 'mode'
  | 'goal'
  | 'startedAt'
  | 'pinnedNoteIds'
  | 'summary'
>;

function normalizeText(value: string): string {
  return value.replace(/\s+/g, ' ').trim().toLocaleLowerCase();
}

function normalizeLinkedTaskIds(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  const linkedTaskIds: string[] = [];
  const seen = new Set<string>();
  for (const item of value) {
    const taskId = typeof item === 'string' ? item.trim() : '';
    if (!taskId || seen.has(taskId)) continue;
    linkedTaskIds.push(taskId);
    seen.add(taskId);
  }

  return linkedTaskIds;
}

function isCanonicalFocusOpen(state: CanonicalFocusState): boolean {
  return (
    Boolean(state.focusId.trim()) &&
    OPEN_CANONICAL_FOCUS_STATUSES.has(state.status)
  );
}

function sessionsAreEqual(
  first: ActiveSession | null,
  second: ActiveSession | null,
): boolean {
  return JSON.stringify(first) === JSON.stringify(second);
}

function findExactProjectionSource(
  focusId: string,
  currentSession: ActiveSession | null,
  recentSessions: RecentFocusSession[],
): FocusProjectionSource | null {
  if (currentSession?.id === focusId) {
    return currentSession;
  }

  return recentSessions.find((session) => session.id === focusId) ?? null;
}

function inferProjectionMode(
  state: CanonicalFocusState,
  currentSession: ActiveSession | null,
): MemorySessionMode {
  if (!currentSession) return 'general';

  const sameTitle =
    normalizeText(currentSession.title) === normalizeText(state.title);
  const sameGoal =
    Boolean(state.objective.trim()) &&
    normalizeText(currentSession.goal) === normalizeText(state.objective);

  return sameTitle || sameGoal ? currentSession.mode : 'general';
}

export function buildCanonicalActiveSessionProjection(
  state: CanonicalFocusState,
  currentSession: ActiveSession | null,
  recentSessions: RecentFocusSession[] = [],
  canonicalLinkedTaskIds: string[] = [],
): ActiveSession | null {
  if (!isCanonicalFocusOpen(state)) {
    return null;
  }

  const exactSource = findExactProjectionSource(
    state.focusId,
    currentSession,
    recentSessions,
  );
  const now = new Date().toISOString();
  const title = state.title.trim() || exactSource?.title.trim() || 'Focus session';
  const goal = state.objective.trim() || exactSource?.goal.trim() || '';

  return {
    id: state.focusId.trim(),
    title,
    mode: exactSource?.mode ?? inferProjectionMode(state, currentSession),
    goal,
    startedAt: state.createdAt.trim() || exactSource?.startedAt || now,
    updatedAt: state.updatedAt.trim() || now,
    pinnedNoteIds: exactSource?.pinnedNoteIds ?? [],
    linkedTaskIds: normalizeLinkedTaskIds(canonicalLinkedTaskIds),
    ...(exactSource?.summary !== undefined
      ? { summary: exactSource.summary }
      : {}),
  };
}

function applyActiveSessionProjection(activeSession: ActiveSession | null) {
  if (typeof window === 'undefined') return;

  try {
    if (activeSession) {
      const serializedSession = JSON.stringify(activeSession);
      window.localStorage.setItem(
        ACTIVE_SESSION_STORAGE_KEY,
        serializedSession,
      );
      window.sessionStorage.setItem(
        ACTIVE_SESSION_SESSION_STORAGE_KEY,
        serializedSession,
      );
    } else {
      window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
      window.sessionStorage.removeItem(ACTIVE_SESSION_SESSION_STORAGE_KEY);
    }
  } catch (error) {
    console.warn('Canonical Focus projection storage update failed:', error);
  }

  window.dispatchEvent(
    new CustomEvent(ACTIVE_SESSION_STATE_EVENT, {
      detail: { activeSession },
    }),
  );
}

async function readCanonicalFocusState(): Promise<CanonicalFocusSnapshot> {
  const response = await fetch(`${QMEET_API_BASE_URL}/api/focus/state`, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(
      `Canonical Focus state request failed with status ${response.status}.`,
    );
  }

  const payload = (await response.json()) as CanonicalFocusStateResponse;
  if (
    !payload.ok ||
    !payload.state ||
    !Array.isArray(payload.linkedTaskIds)
  ) {
    throw new Error('Canonical Focus state response was invalid.');
  }

  return {
    state: payload.state,
    linkedTaskIds: normalizeLinkedTaskIds(payload.linkedTaskIds),
  };
}

export async function reconcileCanonicalFocusProjection(
  currentSession: ActiveSession | null,
  recentSessions: RecentFocusSession[] = [],
): Promise<ActiveSession | null> {
  const canonicalSnapshot = await readCanonicalFocusState();
  const nextSession = buildCanonicalActiveSessionProjection(
    canonicalSnapshot.state,
    currentSession,
    recentSessions,
    canonicalSnapshot.linkedTaskIds,
  );

  if (sessionsAreEqual(currentSession, nextSession)) {
    return currentSession;
  }

  applyActiveSessionProjection(nextSession);
  return nextSession;
}
