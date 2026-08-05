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

export type NativeFocusUpdateInput = {
  title?: string;
  objective?: string;
  mode?: MemorySessionMode;
  sourceTurnId?: string;
};

export type NativeFocusEndInput = {
  disposition: 'ended' | 'completed';
  sourceTurnId?: string;
};

type NativeFocusOpenStatus = 'clarifying' | 'active' | 'waiting' | 'ready';
type NativeFocusTerminalStatus = 'inactive' | 'complete';

type NativeFocusState = {
  focusId: string;
  title: string;
  objective: string;
  status: NativeFocusOpenStatus;
  tags: string[];
  createdAt: string;
  updatedAt: string;
};

type NativeFocusClosedState = {
  focusId: string;
  title: string;
  objective: string;
  status: NativeFocusTerminalStatus;
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

type NativeFocusUpdateVerification = {
  focusIdentityPreserved: boolean;
  titleMatches: boolean;
  objectiveMatches: boolean;
  modeMatches: boolean;
  exactlyOneFocusOpen: boolean;
  updateEventsPersisted: boolean;
  openFocusIds: string[];
  details: string[];
};

type NativeFocusEndVerification = {
  focusIdentityPreserved: boolean;
  terminalStatusMatches: boolean;
  noFocusOpen: boolean;
  terminalEventPersisted: boolean;
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

export type NativeFocusUpdateResult = {
  ok: true;
  operation: 'update_focus';
  outcome: 'updated' | 'reused';
  verified: true;
  activeFocus: NativeFocusState;
  changedFields: Array<'title' | 'objective' | 'mode'>;
  sourceTurnId: string;
  verification: NativeFocusUpdateVerification;
  telemetryRecorded: boolean;
  message: string;
};

export type NativeFocusEndResult = {
  ok: true;
  operation: 'end_focus';
  outcome: 'ended' | 'completed' | 'reused';
  disposition: 'ended' | 'completed';
  verified: true;
  closedFocus: NativeFocusClosedState;
  sourceTurnId: string;
  verification: NativeFocusEndVerification;
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

class NativeFocusLifecycleClientError extends Error {
  readonly code: string;
  readonly status: number | null;

  constructor(
    name: string,
    message: string,
    options: { code?: string; status?: number | null } = {},
  ) {
    super(message);
    this.name = name;
    this.code = options.code ?? 'native_focus_lifecycle_failed';
    this.status = options.status ?? null;
  }
}

export class NativeFocusStartError extends NativeFocusLifecycleClientError {
  constructor(message: string, options: { code?: string; status?: number | null } = {}) {
    super('NativeFocusStartError', message, {
      code: options.code ?? 'native_focus_start_failed',
      status: options.status ?? null,
    });
  }
}

export class NativeFocusUpdateError extends NativeFocusLifecycleClientError {
  constructor(message: string, options: { code?: string; status?: number | null } = {}) {
    super('NativeFocusUpdateError', message, {
      code: options.code ?? 'native_focus_update_failed',
      status: options.status ?? null,
    });
  }
}

export class NativeFocusEndError extends NativeFocusLifecycleClientError {
  constructor(message: string, options: { code?: string; status?: number | null } = {}) {
    super('NativeFocusEndError', message, {
      code: options.code ?? 'native_focus_end_failed',
      status: options.status ?? null,
    });
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

function isChangedFieldArray(
  value: unknown,
): value is Array<'title' | 'objective' | 'mode'> {
  return (
    Array.isArray(value) &&
    value.every(
      (item) => item === 'title' || item === 'objective' || item === 'mode',
    )
  );
}

function isOpenFocusStatus(value: unknown): value is NativeFocusOpenStatus {
  return (
    value === 'clarifying' ||
    value === 'active' ||
    value === 'waiting' ||
    value === 'ready'
  );
}

function modeTags(tags: string[]): string[] {
  return tags.filter((rawTag) => rawTag.trim().toLowerCase().startsWith('mode:'));
}

function readModeTag(tags: string[]): MemorySessionMode | null {
  for (let index = tags.length - 1; index >= 0; index -= 1) {
    const normalized = tags[index].trim().toLowerCase();
    if (!normalized.startsWith('mode:')) continue;
    const mode = normalized.slice('mode:'.length);
    if (isMemorySessionMode(mode)) return mode;
  }
  return null;
}

function parseErrorPayload(
  value: unknown,
  fallbackCode: string,
  fallbackMessage: string,
): { code: string; message: string } {
  if (!value || typeof value !== 'object') {
    return { code: fallbackCode, message: fallbackMessage };
  }

  const payload = value as NativeFocusErrorPayload;
  if (typeof payload.detail === 'string' && payload.detail.trim()) {
    return { code: fallbackCode, message: payload.detail.trim() };
  }

  if (payload.detail && typeof payload.detail === 'object') {
    const code = normalizeText(payload.detail.code, fallbackCode);
    const message = normalizeText(payload.detail.message, fallbackMessage);
    return { code, message };
  }

  return {
    code: fallbackCode,
    message: normalizeText(payload.message, fallbackMessage),
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

  const storageCandidates = [window.localStorage, window.sessionStorage];
  const keys = [ACTIVE_SESSION_STORAGE_KEY, ACTIVE_SESSION_SESSION_STORAGE_KEY];

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

export function readVerifiedFocusProjection(): ActiveSession | null {
  return readStoredActiveSession();
}

function isNativeFocusState(value: unknown): value is NativeFocusState {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<NativeFocusState>;
  return (
    typeof candidate.focusId === 'string' &&
    Boolean(candidate.focusId.trim()) &&
    typeof candidate.title === 'string' &&
    Boolean(candidate.title.trim()) &&
    typeof candidate.objective === 'string' &&
    isOpenFocusStatus(candidate.status) &&
    isStringArray(candidate.tags) &&
    typeof candidate.createdAt === 'string' &&
    Boolean(candidate.createdAt.trim()) &&
    typeof candidate.updatedAt === 'string' &&
    Boolean(candidate.updatedAt.trim())
  );
}

function isNativeFocusClosedState(value: unknown): value is NativeFocusClosedState {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<NativeFocusClosedState>;
  return (
    typeof candidate.focusId === 'string' &&
    Boolean(candidate.focusId.trim()) &&
    typeof candidate.title === 'string' &&
    Boolean(candidate.title.trim()) &&
    typeof candidate.objective === 'string' &&
    (candidate.status === 'inactive' || candidate.status === 'complete') &&
    isStringArray(candidate.tags) &&
    typeof candidate.createdAt === 'string' &&
    Boolean(candidate.createdAt.trim()) &&
    typeof candidate.updatedAt === 'string' &&
    Boolean(candidate.updatedAt.trim())
  );
}

export function isVerifiedNativeFocusStartResult(
  value: unknown,
  expectedSourceTurnId: string,
): value is NativeFocusStartResult {
  if (!value || typeof value !== 'object') return false;

  const candidate = value as Partial<NativeFocusStartResult>;
  const verification = candidate.verification as
    | Partial<NativeFocusVerification>
    | undefined;
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
    isNativeFocusState(candidate.activeFocus) &&
    verification?.activeFocusMatches === true &&
    verification.exactlyOneFocusOpen === true &&
    verification.startEventPersisted === true &&
    verification.previousFocusesClosed === true &&
    isStringArray(openFocusIds) &&
    openFocusIds.length === 1 &&
    openFocusIds[0] === candidate.activeFocus.focusId
  );
}

export function isVerifiedNativeFocusUpdateResult(
  value: unknown,
  expectedSourceTurnId: string,
  expectedFocusId: string,
  requestedUpdate: NativeFocusUpdateInput,
): value is NativeFocusUpdateResult {
  if (!value || typeof value !== 'object') return false;

  const candidate = value as Partial<NativeFocusUpdateResult>;
  const verification = candidate.verification as
    | Partial<NativeFocusUpdateVerification>
    | undefined;
  const openFocusIds = verification?.openFocusIds;
  if (!isNativeFocusState(candidate.activeFocus)) return false;

  const hasTitle = Object.prototype.hasOwnProperty.call(requestedUpdate, 'title');
  const hasObjective = Object.prototype.hasOwnProperty.call(
    requestedUpdate,
    'objective',
  );
  const hasMode = Object.prototype.hasOwnProperty.call(requestedUpdate, 'mode');

  const requestedTitle = hasTitle ? normalizeText(requestedUpdate.title) : null;
  const requestedObjective = hasObjective
    ? normalizeText(requestedUpdate.objective)
    : null;
  const requestedMode = hasMode && isMemorySessionMode(requestedUpdate.mode)
    ? requestedUpdate.mode
    : null;
  const canonicalModeTags = modeTags(candidate.activeFocus.tags);

  return (
    candidate.ok === true &&
    candidate.operation === 'update_focus' &&
    (candidate.outcome === 'updated' || candidate.outcome === 'reused') &&
    candidate.verified === true &&
    candidate.sourceTurnId === expectedSourceTurnId &&
    candidate.activeFocus.focusId === expectedFocusId &&
    typeof candidate.message === 'string' &&
    Boolean(candidate.message.trim()) &&
    isChangedFieldArray(candidate.changedFields) &&
    verification?.focusIdentityPreserved === true &&
    verification.titleMatches === true &&
    verification.objectiveMatches === true &&
    verification.modeMatches === true &&
    verification.exactlyOneFocusOpen === true &&
    verification.updateEventsPersisted === true &&
    isStringArray(openFocusIds) &&
    openFocusIds.length === 1 &&
    openFocusIds[0] === expectedFocusId &&
    (!hasTitle || candidate.activeFocus.title === requestedTitle) &&
    (!hasObjective || candidate.activeFocus.objective === requestedObjective) &&
    (!hasMode ||
      (requestedMode !== null &&
        readModeTag(candidate.activeFocus.tags) === requestedMode &&
        canonicalModeTags.length === 1))
  );
}

export function isVerifiedNativeFocusEndResult(
  value: unknown,
  expectedSourceTurnId: string,
  expectedFocusId: string,
  expectedDisposition: 'ended' | 'completed',
): value is NativeFocusEndResult {
  if (!value || typeof value !== 'object') return false;

  const candidate = value as Partial<NativeFocusEndResult>;
  const verification = candidate.verification as
    | Partial<NativeFocusEndVerification>
    | undefined;
  const expectedStatus =
    expectedDisposition === 'completed' ? 'complete' : 'inactive';

  return (
    candidate.ok === true &&
    candidate.operation === 'end_focus' &&
    (candidate.outcome === expectedDisposition || candidate.outcome === 'reused') &&
    candidate.disposition === expectedDisposition &&
    candidate.verified === true &&
    candidate.sourceTurnId === expectedSourceTurnId &&
    typeof candidate.message === 'string' &&
    Boolean(candidate.message.trim()) &&
    isNativeFocusClosedState(candidate.closedFocus) &&
    candidate.closedFocus.focusId === expectedFocusId &&
    candidate.closedFocus.status === expectedStatus &&
    verification?.focusIdentityPreserved === true &&
    verification.terminalStatusMatches === true &&
    verification.noFocusOpen === true &&
    verification.terminalEventPersisted === true &&
    isStringArray(verification.openFocusIds) &&
    verification.openFocusIds.length === 0
  );
}

export function projectVerifiedFocusToActiveSession(
  result: NativeFocusStartResult | NativeFocusUpdateResult,
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

export function applyVerifiedFocusProjection(
  activeSession: ActiveSession | null,
): void {
  if (typeof window === 'undefined') return;

  if (activeSession === null) {
    try {
      window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
    } catch (error) {
      console.warn('Failed to clear the verified Focus local projection:', error);
    }
    try {
      window.sessionStorage.removeItem(ACTIVE_SESSION_SESSION_STORAGE_KEY);
    } catch (error) {
      console.warn('Failed to clear the verified Focus session projection:', error);
    }
  } else {
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
    const parsedError = parseErrorPayload(
      payload,
      'native_focus_start_failed',
      'The canonical Focus service did not verify the transition.',
    );
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

export async function updateNativeFocusVerified(
  input: NativeFocusUpdateInput,
): Promise<NativeFocusUpdateResult> {
  const activeProjection = readStoredActiveSession();
  if (!activeProjection) {
    throw new NativeFocusUpdateError(
      'No verified Focus display projection is available to identify the canonical Focus.',
      { code: 'no_active_focus_projection' },
    );
  }

  const hasTitle = Object.prototype.hasOwnProperty.call(input, 'title');
  const hasObjective = Object.prototype.hasOwnProperty.call(input, 'objective');
  const hasMode = Object.prototype.hasOwnProperty.call(input, 'mode');
  if (!hasTitle && !hasObjective && !hasMode) {
    throw new NativeFocusUpdateError('No Focus update fields were provided.', {
      code: 'missing_focus_update',
    });
  }

  const title = hasTitle ? normalizeText(input.title) : undefined;
  if (hasTitle && !title) {
    throw new NativeFocusUpdateError('A Focus title cannot be blank.', {
      code: 'invalid_focus_title',
    });
  }
  const objective = hasObjective ? normalizeText(input.objective) : undefined;
  const mode = hasMode && isMemorySessionMode(input.mode) ? input.mode : undefined;
  if (hasMode && !mode) {
    throw new NativeFocusUpdateError('The requested Focus mode is not supported.', {
      code: 'invalid_focus_mode',
    });
  }

  const normalizedInput: NativeFocusUpdateInput = {
    ...(hasTitle ? { title } : {}),
    ...(hasObjective ? { objective } : {}),
    ...(hasMode ? { mode } : {}),
  };
  const suppliedSourceTurnId = normalizeText(input.sourceTurnId);
  const sourceTurnId = suppliedSourceTurnId || createSourceTurnId();

  let response: Response;
  try {
    response = await fetch(`${QMEET_API_BASE_URL}/api/focus/lifecycle/update`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        [QMEET_TURN_HEADER]: sourceTurnId,
      },
      body: JSON.stringify({
        expectedFocusId: activeProjection.id,
        ...normalizedInput,
        sourceTurnId,
      }),
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message.trim() : '';
    throw new NativeFocusUpdateError(
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
    const parsedError = parseErrorPayload(
      payload,
      'native_focus_update_failed',
      'The canonical Focus service did not verify the update.',
    );
    throw new NativeFocusUpdateError(parsedError.message, {
      code: parsedError.code,
      status: response.status,
    });
  }

  if (
    !isVerifiedNativeFocusUpdateResult(
      payload,
      sourceTurnId,
      activeProjection.id,
      normalizedInput,
    )
  ) {
    throw new NativeFocusUpdateError(
      'The canonical Focus response did not prove that the update succeeded.',
      {
        code: 'client_verification_failed',
        status: response.status,
      },
    );
  }

  return payload;
}

export async function endNativeFocusVerified(
  input: NativeFocusEndInput,
): Promise<NativeFocusEndResult> {
  const activeProjection = readStoredActiveSession();
  if (!activeProjection) {
    throw new NativeFocusEndError(
      'No verified Focus display projection is available to identify the canonical Focus.',
      { code: 'no_active_focus_projection' },
    );
  }

  const disposition = input.disposition;
  if (disposition !== 'ended' && disposition !== 'completed') {
    throw new NativeFocusEndError('The requested Focus terminal state is invalid.', {
      code: 'invalid_focus_disposition',
    });
  }
  const suppliedSourceTurnId = normalizeText(input.sourceTurnId);
  const sourceTurnId = suppliedSourceTurnId || createSourceTurnId();

  let response: Response;
  try {
    response = await fetch(`${QMEET_API_BASE_URL}/api/focus/lifecycle/end`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        [QMEET_TURN_HEADER]: sourceTurnId,
      },
      body: JSON.stringify({
        expectedFocusId: activeProjection.id,
        disposition,
        sourceTurnId,
      }),
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message.trim() : '';
    throw new NativeFocusEndError(
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
    const parsedError = parseErrorPayload(
      payload,
      'native_focus_end_failed',
      'The canonical Focus service did not verify the terminal transition.',
    );
    throw new NativeFocusEndError(parsedError.message, {
      code: parsedError.code,
      status: response.status,
    });
  }

  if (
    !isVerifiedNativeFocusEndResult(
      payload,
      sourceTurnId,
      activeProjection.id,
      disposition,
    )
  ) {
    throw new NativeFocusEndError(
      'The canonical Focus response did not prove that the terminal transition succeeded.',
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

export function describeNativeFocusUpdateFailure(error: unknown): string {
  const reason =
    error instanceof Error && error.message.trim()
      ? ` ${error.message.trim()}`
      : '';

  return `I could not verify that the Focus update became canonical, so I will not claim it changed.${reason}`;
}


export function describeNativeFocusEndFailure(error: unknown): string {
  const reason =
    error instanceof Error && error.message.trim()
      ? ` ${error.message.trim()}`
      : '';

  return `I could not verify that the Focus reached its terminal canonical state, so I will not claim it ended.${reason}`;
}
