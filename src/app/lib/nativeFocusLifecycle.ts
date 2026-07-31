import { QMEET_API_BASE_URL } from '../api';
import type { ActiveSession, MemorySessionMode } from '../types';
import { getActiveQMeetTurnId } from './focusTurnHeaders';

const ACTIVE_SESSION_STORAGE_KEY = 'qmeet-active-session';
const ACTIVE_SESSION_SESSION_STORAGE_KEY = 'qmeet-active-session-live';
const ACTIVE_SESSION_STATE_EVENT = 'qmeet-active-session-state';
const QMEET_TURN_HEADER = 'X-QMeet-Turn-Id';

export type NativeFocusStartInput = {
  title: string;
  objective?: string;
  mode?: MemorySessionMode;
  tags?: string[];
};

type NativeFocusOpenStatus = 'clarifying' | 'active' | 'waiting' | 'ready';

type NativeFocusState = {
  focusId: string;
  title: string;
  objective: string;
  status: NativeFocusOpenStatus;
  tags: string[];
  createdAt: string;
  updatedAt: string;
};

type NativeFocusVerification = {
  activeFocusMatches: boolean;
  exactlyOneFocusOpen: boolean;
  startEventPersisted: boolean;
  previousFocusesClosed: boolean;
  openFocusIds: string[];
  details: string[];
};

export type NativeFocusStartResult = {
  ok: true;
  operation: 'start_focus';
  outcome: 'started' | 'replaced' | 'reused';
  verified: true;
  activeFocus: NativeFocusState;
  previousFocusId: string;
  closedFocusIds: string[];
  sourceTurnId: string;
  verification: NativeFocusVerification;
  telemetryRecorded: boolean;
  message: string;
};

type NativeFocusErrorPayload = {
  detail?:
    | string
    | {
        code?: unknown;
        message?: unknown;
        verified?: unknown;
        successClaimAllowed?: unknown;
      };
  message?: unknown;
};

export class NativeFocusStartError extends Error {
  readonly code: string;
  readonly status: number | null;

  constructor(message: string, options: { code?: string; status?: number | null } = {}) {
    super(message);
    this.name = 'NativeFocusStartError';
    this.code = options.code ?? 'native_focus_start_failed';
    this.status = options.status ?? null;
  }
}

function createSourceTurnId(): string {
  const activeTurnId = getActiveQMeetTurnId()?.trim();
  if (activeTurnId) return activeTurnId;

  const randomPart =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID().replace(/-/g, '')
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;

  return `focus-turn-${randomPart}`;
}

function normalizeText(value: unknown, fallback = ''): string {
  if (typeof value !== 'string') return fallback;
  return value.replace(/\s+/g, ' ').trim();
}

function normalizeTags(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  const tags: string[] = [];
  const seen = new Set<string>();
  for (const rawTag of value) {
    const tag = normalizeText(rawTag).slice(0, 80);
    const key = tag.toLowerCase();
    if (!tag || seen.has(key)) continue;
    seen.add(key);
    tags.push(tag);
    if (tags.length >= 12) break;
  }
  return tags;
}

function isMemorySessionMode(value: unknown): value is MemorySessionMode {
  return (
    value === 'general' ||
    value === 'coding' ||
    value === 'meeting' ||
    value === 'planning' ||
    value === 'research' ||
    value === 'personal'
  );
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isOpenFocusStatus(value: unknown): value is NativeFocusOpenStatus {
  return (
    value === 'clarifying' ||
    value === 'active' ||
    value === 'waiting' ||
    value === 'ready'
  );
}

function readModeTag(tags: string[]): MemorySessionMode | null {
  for (const rawTag of tags) {
    const normalized = rawTag.trim().toLowerCase();
    if (!normalized.startsWith('mode:')) continue;
    const mode = normalized.slice('mode:'.length);
    if (isMemorySessionMode(mode)) return mode;
  }
  return null;
}

function parseErrorPayload(value: unknown): { code: string; message: string } {
  if (!value || typeof value !== 'object') {
    return {
      code: 'native_focus_start_failed',
      message: 'The canonical Focus service returned an unreadable error.',
    };
  }

  const payload = value as NativeFocusErrorPayload;
  if (typeof payload.detail === 'string' && payload.detail.trim()) {
    return {
      code: 'native_focus_start_failed',
      message: payload.detail.trim(),
    };
  }

  if (payload.detail && typeof payload.detail === 'object') {
    const code = normalizeText(payload.detail.code, 'native_focus_start_failed');
    const message = normalizeText(
      payload.detail.message,
      'The canonical Focus service did not verify the transition.',
    );
    return { code, message };
  }

  return {
    code: 'native_focus_start_failed',
    message: normalizeText(
      payload.message,
      'The canonical Focus service did not verify the transition.',
    ),
  };
}

function normalizeStoredActiveSession(value: unknown): ActiveSession | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<ActiveSession>;
  if (
    typeof candidate.id !== 'string' ||
    !candidate.id.trim() ||
    typeof candidate.title !== 'string' ||
    !candidate.title.trim()
  ) {
    return null;
  }

  const now = new Date().toISOString();
  return {
    id: candidate.id.trim(),
    title: candidate.title.trim(),
    mode: isMemorySessionMode(candidate.mode) ? candidate.mode : 'general',
    goal: typeof candidate.goal === 'string' ? candidate.goal : '',
    startedAt:
      typeof candidate.startedAt === 'string' && candidate.startedAt.trim()
        ? candidate.startedAt
        : now,
    updatedAt:
      typeof candidate.updatedAt === 'string' && candidate.updatedAt.trim()
        ? candidate.updatedAt
        : now,
    pinnedNoteIds: isStringArray(candidate.pinnedNoteIds)
      ? [...candidate.pinnedNoteIds]
      : [],
    linkedTaskIds: isStringArray(candidate.linkedTaskIds)
      ? [...candidate.linkedTaskIds]
      : [],
    summary:
      typeof candidate.summary === 'string' || candidate.summary === null
        ? candidate.summary
        : undefined,
  };
}

function readStoredActiveSession(): ActiveSession | null {
  if (typeof window === 'undefined') return null;

  const storageCandidates = [
    window.localStorage,
    window.sessionStorage,
  ];
  const keys = [
    ACTIVE_SESSION_STORAGE_KEY,
    ACTIVE_SESSION_SESSION_STORAGE_KEY,
  ];

  for (let index = 0; index < storageCandidates.length; index += 1) {
    try {
      const rawValue = storageCandidates[index].getItem(keys[index]);
      if (!rawValue) continue;
      const normalized = normalizeStoredActiveSession(JSON.parse(rawValue));
      if (normalized) return normalized;
    } catch (error) {
      console.warn('Failed to read the existing Focus display projection:', error);
    }
  }

  return null;
}

export function isVerifiedNativeFocusStartResult(
  value: unknown,
  expectedSourceTurnId: string,
): value is NativeFocusStartResult {
  if (!value || typeof value !== 'object') return false;

  const candidate = value as Partial<NativeFocusStartResult>;
  const activeFocus = candidate.activeFocus as Partial<NativeFocusState> | undefined;
  const verification = candidate.verification as Partial<NativeFocusVerification> | undefined;
  const openFocusIds = verification?.openFocusIds;

  return (
    candidate.ok === true &&
    candidate.operation === 'start_focus' &&
    (candidate.outcome === 'started' ||
      candidate.outcome === 'replaced' ||
      candidate.outcome === 'reused') &&
    candidate.verified === true &&
    candidate.sourceTurnId === expectedSourceTurnId &&
    typeof candidate.message === 'string' &&
    Boolean(candidate.message.trim()) &&
    typeof activeFocus?.focusId === 'string' &&
    Boolean(activeFocus.focusId.trim()) &&
    typeof activeFocus.title === 'string' &&
    Boolean(activeFocus.title.trim()) &&
    isOpenFocusStatus(activeFocus.status) &&
    isStringArray(activeFocus.tags) &&
    verification?.activeFocusMatches === true &&
    verification.exactlyOneFocusOpen === true &&
    verification.startEventPersisted === true &&
    verification.previousFocusesClosed === true &&
    isStringArray(openFocusIds) &&
    openFocusIds.length === 1 &&
    openFocusIds[0] === activeFocus.focusId
  );
}

export function projectVerifiedFocusToActiveSession(
  result: NativeFocusStartResult,
  requestedMode?: MemorySessionMode,
): ActiveSession {
  const activeFocus = result.activeFocus;
  const tags = normalizeTags(activeFocus.tags);
  const mode =
    (isMemorySessionMode(requestedMode) ? requestedMode : null) ??
    readModeTag(tags) ??
    'general';
  const now = new Date().toISOString();
  const existingProjection = readStoredActiveSession();
  const canPreserveCompatibilityFields =
    existingProjection?.id === activeFocus.focusId;

  return {
    id: activeFocus.focusId,
    title: normalizeText(activeFocus.title, 'Focus session'),
    mode,
    goal: normalizeText(activeFocus.objective),
    startedAt: normalizeText(activeFocus.createdAt, now),
    updatedAt: normalizeText(activeFocus.updatedAt, now),
    pinnedNoteIds: canPreserveCompatibilityFields
      ? [...existingProjection.pinnedNoteIds]
      : [],
    linkedTaskIds: canPreserveCompatibilityFields
      ? [...existingProjection.linkedTaskIds]
      : [],
    ...(canPreserveCompatibilityFields && existingProjection.summary !== undefined
      ? { summary: existingProjection.summary }
      : {}),
  };
}

export function applyVerifiedFocusProjection(activeSession: ActiveSession): void {
  if (typeof window === 'undefined') return;

  const serializedSession = JSON.stringify(activeSession);
  try {
    window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, serializedSession);
  } catch (error) {
    console.warn('Failed to save the verified Focus local projection:', error);
  }

  try {
    window.sessionStorage.setItem(
      ACTIVE_SESSION_SESSION_STORAGE_KEY,
      serializedSession,
    );
  } catch (error) {
    console.warn('Failed to save the verified Focus session projection:', error);
  }

  window.dispatchEvent(
    new CustomEvent(ACTIVE_SESSION_STATE_EVENT, {
      detail: { activeSession },
    }),
  );
}

export async function startNativeFocusVerified(
  input: NativeFocusStartInput,
): Promise<NativeFocusStartResult> {
  const title = normalizeText(input.title);
  if (!title) {
    throw new NativeFocusStartError('A Focus title is required.', {
      code: 'missing_focus_title',
    });
  }

  const sourceTurnId = createSourceTurnId();
  let response: Response;
  try {
    response = await fetch(`${QMEET_API_BASE_URL}/api/focus/lifecycle/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        [QMEET_TURN_HEADER]: sourceTurnId,
      },
      body: JSON.stringify({
        title,
        objective: normalizeText(input.objective),
        mode: isMemorySessionMode(input.mode) ? input.mode : '',
        tags: normalizeTags(input.tags),
        sourceTurnId,
      }),
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message.trim() : '';
    throw new NativeFocusStartError(
      reason
        ? `The canonical Focus service could not be reached: ${reason}`
        : 'The canonical Focus service could not be reached.',
      { code: 'focus_service_unavailable' },
    );
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // The validation below turns an unreadable success body into a blocked result.
  }

  if (!response.ok) {
    const parsedError = parseErrorPayload(payload);
    throw new NativeFocusStartError(parsedError.message, {
      code: parsedError.code,
      status: response.status,
    });
  }

  if (!isVerifiedNativeFocusStartResult(payload, sourceTurnId)) {
    throw new NativeFocusStartError(
      'The canonical Focus response did not prove that the transition succeeded.',
      {
        code: 'client_verification_failed',
        status: response.status,
      },
    );
  }

  return payload;
}

export function describeNativeFocusStartFailure(error: unknown): string {
  const reason =
    error instanceof Error && error.message.trim()
      ? ` ${error.message.trim()}`
      : '';

  return `I could not verify that the new Focus became canonical, so I will not claim it started.${reason}`;
}
