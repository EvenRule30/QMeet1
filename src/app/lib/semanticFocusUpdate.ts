import { QMEET_API_BASE_URL } from '../api';
import type {
  CommandMatch,
  FocusSessionCommandPayload,
} from '../commands';

export const SEMANTIC_FOCUS_UPDATE_BRIDGE_VERSION = 'phase20d2a4c';

const SEMANTIC_FOCUS_MODES = new Set([
  'general',
  'coding',
  'meeting',
  'planning',
  'research',
  'personal',
]);

type SemanticFocusMode = FocusSessionCommandPayload['mode'];

type SemanticPreflightPayload = {
  ok?: unknown;
  bridgeVersion?: unknown;
  intent?: unknown;
  possibleUpdate?: unknown;
  title?: unknown;
  objective?: unknown;
  objectiveSpecified?: unknown;
  mode?: unknown;
  confidence?: unknown;
  reason?: unknown;
  message?: unknown;
  sourceTurnId?: unknown;
};

export type SemanticFocusUpdatePreflightOutcome =
  | {
      kind: 'update';
      commandMatch: CommandMatch;
      confidence: number;
      reason: string;
    }
  | {
      kind: 'not_update';
      confidence: number;
      reason: string;
    }
  | {
      kind: 'blocked';
      message: string;
      confidence: number;
      reason: string;
    }
  | {
      kind: 'unavailable';
      message: string;
      possibleUpdate: boolean;
      confidence: null;
      reason: string;
    };

function createSourceTurnId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `focus-semantic-${crypto.randomUUID()}`;
  }
  return `focus-semantic-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

function normalizeConfidence(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.max(0, Math.min(value, 1))
    : 0;
}

function isSemanticFocusMode(value: unknown): value is SemanticFocusMode {
  return (
    typeof value === 'string' &&
    SEMANTIC_FOCUS_MODES.has(value.trim().toLowerCase())
  );
}

/**
 * Safety-only fallback used when the dedicated semantic endpoint is unavailable.
 * It never authorizes execution; it only prevents likely mutation language from
 * falling through to normal chat and producing unsupported success wording.
 */
function looksLikePossibleFocusUpdate(message: string): boolean {
  const text = message.toLowerCase().replace(/\s+/g, ' ').trim();
  if (!text || /\b(?:don't|do not|never|cancel|stop)\b/.test(text)) return false;

  const focusReference =
    /\b(?:focus|session|goal|objective|mode|this work|current work|work i(?:'m| am) doing|what i(?:'m| am) working on)\b/.test(
      text,
    );
  const changeLanguage =
    /\b(?:rename|retitle|call|name|title|change|set|make|switch|update|should be|now called|turn .* into)\b/.test(
      text,
    );
  return focusReference && changeLanguage;
}

function parseErrorMessage(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '';
  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  if (typeof detail === 'string') return detail.trim();
  if (detail && typeof detail === 'object') {
    const message = (detail as Record<string, unknown>).message;
    if (typeof message === 'string') return message.trim();
  }
  const message = record.message;
  return typeof message === 'string' ? message.trim() : '';
}

function buildUpdateMatch(payload: SemanticPreflightPayload): CommandMatch | null {
  const focusSession: FocusSessionCommandPayload = {};
  let hasChange = false;

  const title = normalizeText(payload.title);
  if (title) {
    focusSession.title = title;
    hasChange = true;
  }

  if (payload.objectiveSpecified === true) {
    if (typeof payload.objective !== 'string') return null;
    focusSession.goal = normalizeText(payload.objective);
    hasChange = true;
  }

  if (payload.mode !== null && payload.mode !== undefined) {
    if (!isSemanticFocusMode(payload.mode)) return null;
    focusSession.mode = payload.mode.trim().toLowerCase() as SemanticFocusMode;
    hasChange = true;
  }

  if (!hasChange) return null;

  const sourceTurnId = normalizeText(payload.sourceTurnId);
  return {
    command: 'update-focus-session',
    confirmation: 'Updating Focus.',
    ...(sourceTurnId ? { payload: sourceTurnId } : {}),
    focusSession,
  };
}

/**
 * Ask the lifecycle surface—not chat or the general command interpreter—whether
 * the natural sentence is a current-Focus title, goal, or mode update.
 *
 * An UPDATE result is still only an interpretation. App.tsx sends the typed
 * CommandMatch through the existing verified /api/focus/lifecycle/update path.
 */
export async function interpretSemanticFocusUpdate(
  message: string,
): Promise<SemanticFocusUpdatePreflightOutcome> {
  const cleanedMessage = normalizeText(message);
  if (!cleanedMessage) {
    return { kind: 'not_update', confidence: 1, reason: 'Empty message.' };
  }

  const sourceTurnId = createSourceTurnId();
  let response: Response;
  try {
    response = await fetch(
      `${QMEET_API_BASE_URL}/api/focus/lifecycle/semantic-update/interpret`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'x-qmeet-turn-id': sourceTurnId,
        },
        body: JSON.stringify({
          message: cleanedMessage,
          sourceTurnId,
        }),
      },
    );
  } catch (error) {
    const reason = error instanceof Error ? error.message.trim() : '';
    return {
      kind: 'unavailable',
      possibleUpdate: looksLikePossibleFocusUpdate(cleanedMessage),
      confidence: null,
      reason: reason || 'The semantic Focus lifecycle endpoint was unavailable.',
      message:
        'I could not safely interpret this possible Focus change, so the Focus was not changed.',
    };
  }

  let rawPayload: unknown = null;
  try {
    rawPayload = await response.json();
  } catch {
    // Validation below converts unreadable responses into a safe unavailable result.
  }

  if (!response.ok) {
    const reason =
      parseErrorMessage(rawPayload) ||
      `The semantic Focus lifecycle endpoint returned HTTP ${response.status}.`;
    return {
      kind: 'unavailable',
      possibleUpdate: looksLikePossibleFocusUpdate(cleanedMessage),
      confidence: null,
      reason,
      message:
        'I could not safely interpret this possible Focus change, so the Focus was not changed.',
    };
  }

  if (!rawPayload || typeof rawPayload !== 'object') {
    return {
      kind: 'unavailable',
      possibleUpdate: looksLikePossibleFocusUpdate(cleanedMessage),
      confidence: null,
      reason: 'The semantic Focus lifecycle response was not an object.',
      message:
        'I could not safely interpret this possible Focus change, so the Focus was not changed.',
    };
  }

  const payload = rawPayload as SemanticPreflightPayload;
  if (
    payload.ok !== true ||
    payload.bridgeVersion !== SEMANTIC_FOCUS_UPDATE_BRIDGE_VERSION
  ) {
    return {
      kind: 'unavailable',
      possibleUpdate: looksLikePossibleFocusUpdate(cleanedMessage),
      confidence: null,
      reason: 'The semantic Focus lifecycle contract is missing or out of sync.',
      message:
        'The semantic Focus update bridge is out of sync, so the Focus was not changed. Restart both QMeet services after installing the complete Phase 20D2A4C files.',
    };
  }

  const confidence = normalizeConfidence(payload.confidence);
  const reason = normalizeText(payload.reason);

  if (payload.intent === 'not_update') {
    return { kind: 'not_update', confidence, reason };
  }

  if (payload.intent === 'clarify') {
    return {
      kind: 'blocked',
      confidence,
      reason,
      message:
        normalizeText(payload.message) ||
        'I understood this as a possible Focus change, but I could not identify one specific update safely. The Focus was not changed.',
    };
  }

  if (payload.intent === 'update') {
    const commandMatch = buildUpdateMatch(payload);
    if (commandMatch) {
      return { kind: 'update', commandMatch, confidence, reason };
    }
    return {
      kind: 'blocked',
      confidence,
      reason: reason || 'The semantic update contained no executable fields.',
      message:
        'I understood this as a Focus update, but no specific title, goal, or mode value was safe to execute. The Focus was not changed.',
    };
  }

  return {
    kind: 'unavailable',
    possibleUpdate: looksLikePossibleFocusUpdate(cleanedMessage),
    confidence: null,
    reason: 'The semantic Focus lifecycle response used an unknown intent.',
    message:
      'I could not safely interpret this possible Focus change, so the Focus was not changed.',
  };
}
