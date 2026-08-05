import { QMEET_API_BASE_URL } from '../api';
import type { ActiveSession, Note } from '../types';
import {
  applyVerifiedFocusProjection,
  readVerifiedFocusProjection,
} from './nativeFocusLifecycle';

export const NATIVE_FOCUS_SUMMARY_OWNERSHIP_VERSION = 'phase20e2a';

type NativeFocusSummaryVerification = {
  activeFocusMatches?: unknown;
  notePersisted?: unknown;
  relationshipPersisted?: unknown;
  sourceTurnUnique?: unknown;
  details?: unknown;
};

type NativeFocusSummaryPayload = {
  ok?: unknown;
  operation?: unknown;
  outcome?: unknown;
  verified?: unknown;
  focusId?: unknown;
  focusTitle?: unknown;
  summary?: unknown;
  note?: unknown;
  receiptId?: unknown;
  sourceTurnId?: unknown;
  verification?: unknown;
  message?: unknown;
};

export type VerifiedNativeFocusSummaryResult = {
  ok: true;
  operation: 'save_focus_summary';
  outcome: 'saved' | 'reused';
  verified: true;
  focusId: string;
  focusTitle: string;
  summary: string;
  note: Note;
  receiptId: string;
  sourceTurnId: string;
  message: string;
};

export class NativeFocusSummaryClientError extends Error {
  code: string;

  constructor(message: string, code = 'native_focus_summary_failed') {
    super(message);
    this.name = 'NativeFocusSummaryClientError';
    this.code = code;
  }
}

function createSourceTurnId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `focus-summary-${crypto.randomUUID()}`;
  }
  return `focus-summary-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function isNote(value: unknown): value is Note {
  if (!value || typeof value !== 'object') return false;
  const note = value as Partial<Note>;
  return (
    typeof note.id === 'string' &&
    Boolean(note.id.trim()) &&
    typeof note.content === 'string' &&
    Boolean(note.content.trim()) &&
    typeof note.createdAt === 'string' &&
    Boolean(note.createdAt.trim())
  );
}

function parseErrorPayload(payload: unknown): { code: string; message: string } {
  if (!payload || typeof payload !== 'object') {
    return {
      code: 'native_focus_summary_failed',
      message: 'The Focus summary request failed.',
    };
  }
  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  if (detail && typeof detail === 'object') {
    const detailRecord = detail as Record<string, unknown>;
    return {
      code: normalizeText(detailRecord.code) || 'native_focus_summary_failed',
      message:
        normalizeText(detailRecord.message) || 'The Focus summary request failed.',
    };
  }
  return {
    code: normalizeText(record.code) || 'native_focus_summary_failed',
    message: normalizeText(record.message) || 'The Focus summary request failed.',
  };
}

function validatePayload(
  rawPayload: unknown,
  expectedFocusId: string,
  expectedNote: Note,
  expectedSourceTurnId: string,
): VerifiedNativeFocusSummaryResult {
  if (!rawPayload || typeof rawPayload !== 'object') {
    throw new NativeFocusSummaryClientError(
      'The canonical Focus summary response was not an object.',
      'invalid_response',
    );
  }
  const payload = rawPayload as NativeFocusSummaryPayload;
  const verification = payload.verification as NativeFocusSummaryVerification | null;
  const note = payload.note;
  const outcome = payload.outcome;
  const focusId = normalizeText(payload.focusId);
  const sourceTurnId = normalizeText(payload.sourceTurnId);
  const summary = normalizeText(payload.summary);
  const receiptId = normalizeText(payload.receiptId);
  const message = normalizeText(payload.message);

  const valid =
    payload.ok === true &&
    payload.operation === 'save_focus_summary' &&
    (outcome === 'saved' || outcome === 'reused') &&
    payload.verified === true &&
    focusId === expectedFocusId &&
    sourceTurnId === expectedSourceTurnId &&
    isNote(note) &&
    note.id === expectedNote.id &&
    note.content === expectedNote.content &&
    note.createdAt === expectedNote.createdAt &&
    summary === expectedNote.content &&
    Boolean(receiptId) &&
    Boolean(message) &&
    verification?.activeFocusMatches === true &&
    verification?.notePersisted === true &&
    verification?.relationshipPersisted === true &&
    verification?.sourceTurnUnique === true;

  if (!valid || !isNote(note) || (outcome !== 'saved' && outcome !== 'reused')) {
    throw new NativeFocusSummaryClientError(
      'The canonical Focus summary response did not prove that the Note and Focus relationship were persisted.',
      'verification_failed',
    );
  }

  return {
    ok: true,
    operation: 'save_focus_summary',
    outcome,
    verified: true,
    focusId,
    focusTitle: normalizeText(payload.focusTitle),
    summary,
    note,
    receiptId,
    sourceTurnId,
    message,
  };
}

export async function saveNativeFocusSummaryVerified(input: {
  expectedFocusId: string;
  note: Note;
  sourceTurnId?: string;
}): Promise<VerifiedNativeFocusSummaryResult> {
  const expectedFocusId = input.expectedFocusId.trim();
  if (!expectedFocusId) {
    throw new NativeFocusSummaryClientError(
      'No verified active Focus is available for this summary.',
      'missing_focus',
    );
  }
  const sourceTurnId = input.sourceTurnId?.trim() || createSourceTurnId();
  let response: Response;
  try {
    response = await fetch(`${QMEET_API_BASE_URL}/api/focus/lifecycle/summary`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'x-qmeet-turn-id': sourceTurnId,
      },
      body: JSON.stringify({
        expectedFocusId,
        note: input.note,
        sourceTurnId,
      }),
    });
  } catch (error) {
    throw new NativeFocusSummaryClientError(
      error instanceof Error && error.message.trim()
        ? error.message
        : 'The native Focus summary endpoint was unavailable.',
      'endpoint_unavailable',
    );
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Validation below reports an unreadable response safely.
  }

  if (!response.ok) {
    const parsed = parseErrorPayload(payload);
    throw new NativeFocusSummaryClientError(parsed.message, parsed.code);
  }
  return validatePayload(payload, expectedFocusId, input.note, sourceTurnId);
}

export function applyVerifiedFocusSummaryProjection(
  result: VerifiedNativeFocusSummaryResult,
): ActiveSession {
  const current = readVerifiedFocusProjection();
  if (!current || current.id !== result.focusId) {
    throw new NativeFocusSummaryClientError(
      'The displayed Focus changed before its verified summary could be projected.',
      'stale_projection',
    );
  }
  const next: ActiveSession = {
    ...current,
    summary: result.summary,
    pinnedNoteIds: [
      result.note.id,
      ...current.pinnedNoteIds.filter((id) => id !== result.note.id),
    ],
    updatedAt: result.note.createdAt,
  };
  applyVerifiedFocusProjection(next);
  return next;
}

export function describeNativeFocusSummaryFailure(error: unknown): string {
  const detail =
    error instanceof Error && error.message.trim()
      ? ` ${error.message.trim()}`
      : '';
  return (
    'I could not verify that the Focus summary Note and its canonical relationship were saved, ' +
    `so I will not claim it succeeded.${detail}`
  );
}
