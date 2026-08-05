import { QMEET_API_BASE_URL } from '../api';
import type {
  CommandMatch,
  FocusSessionCommandPayload,
} from '../commands';

export const SEMANTIC_FOCUS_LIFECYCLE_BRIDGE_VERSION = 'phase20d2b1';

const SEMANTIC_FOCUS_MODES = new Set([
  'general',
  'coding',
  'meeting',
  'planning',
  'research',
  'personal',
]);

type SemanticFocusMode = FocusSessionCommandPayload['mode'];

type SemanticLifecyclePayload = {
  ok?: unknown;
  bridgeVersion?: unknown;
  intent?: unknown;
  possibleMutation?: unknown;
  title?: unknown;
  objective?: unknown;
  objectiveSpecified?: unknown;
  mode?: unknown;
  forceEnd?: unknown;
  summaryRequested?: unknown;
  confidence?: unknown;
  reason?: unknown;
  message?: unknown;
  sourceTurnId?: unknown;
};

export function shouldPreflightSemanticFocusLifecycleBeforeCommandRouting(
  message: string,
): boolean {
  return looksLikeFocusTerminalLanguage(message);
}

/**
 * Deterministic safety gate for unambiguous Focus-terminal language.
 *
 * This is intentionally narrow: it does not replace semantic lifecycle
 * classification. It only prevents direct Focus completion/end statements
 * from reaching the generic task parser when the model classifier misses.
 */
export function getDirectFocusTerminalCommandMatch(
  message: string,
): CommandMatch | null {
  const text = normalizeText(message).toLowerCase();
  if (!text) return null;

  if (/\b(?:don't|do not|never|cancel)\b/.test(text)) return null;

  // Compound summary + terminal requests still require two verified receipts.
  if (
    /\b(?:save|write|record|add|create)\b.{0,35}\b(?:summary|recap|note)\b/.test(
      text,
    )
  ) {
    return null;
  }

  if (!looksLikeFocusTerminalLanguage(text)) return null;

  const disposition = /\b(?:complete|completed|completing|finish|finished|finishing|done)\b/.test(
    text,
  )
    ? 'completed'
    : 'ended';

  return {
    command: 'end-focus-session',
    confirmation:
      disposition === 'completed' ? 'Completing Focus.' : 'Ending Focus.',
    payload: JSON.stringify({ disposition }),
    focusSession: {
      forceEnd: /\banyway\b/.test(text),
    },
  };
}

function looksLikeFocusTerminalLanguage(message: string): boolean {
  const text = normalizeText(message).toLowerCase();
  if (!text) return false;

  const focusTarget =
    String.raw`(?:(?:my|the|this|our)\s+)?(?:(?:current|active)\s+)?(?:focus(?:\s+session)?|session|work)`;
  const directFocusTerminalPattern = new RegExp(
    String.raw`\b(?:end|ended|ending|finish|finished|finishing|complete|completed|completing|close|closed|closing)\s+${focusTarget}\b|` +
      String.raw`\b(?:done|finished|complete|completed|over)\s+(?:with\s+)?${focusTarget}\b|` +
      String.raw`\b${focusTarget}\s+(?:is\s+|was\s+|has\s+been\s+|is\s+now\s+)?(?:done|finished|complete|completed|over)\b|` +
      String.raw`\bmark\s+${focusTarget}\s+(?:as\s+)?(?:done|finished|complete|completed)\b|` +
      String.raw`\bwrap(?:ped)?\s+up\s+${focusTarget}\b`,
    'i',
  );

  return directFocusTerminalPattern.test(text);
}

export function shouldRouteExactFocusLifecycleThroughSemanticPreflight(
  commandMatch: CommandMatch | null,
  originalMessage = '',
): boolean {
  if (
    commandMatch?.command === 'start-focus-session' ||
    commandMatch?.command === 'update-focus-session' ||
    commandMatch?.command === 'end-focus-session' ||
    commandMatch?.command === 'end-focus-with-summary'
  ) {
    return true;
  }

  // The legacy task parser can interpret phrases such as "I completed this
  // focus" as a task named "this focus". Defer only those task matches
  // whose original language clearly targets the Focus/session lifecycle.
  return (
    commandMatch?.command === 'mark-task-done' &&
    looksLikeFocusTerminalLanguage(originalMessage)
  );
}

export type SemanticFocusLifecyclePreflightOutcome =
  | {
      kind: 'update' | 'start' | 'end' | 'complete';
      commandMatch: CommandMatch;
      confidence: number;
      reason: string;
    }
  | {
      kind: 'not_lifecycle';
      confidence: number;
      reason: string;
    }
  | {
      kind: 'acknowledged';
      message: string;
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
      possibleMutation: boolean;
      confidence: null;
      reason: string;
    };

function createSourceTurnId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `focus-lifecycle-${crypto.randomUUID()}`;
  }
  return `focus-lifecycle-${Date.now()}-${Math.random().toString(16).slice(2)}`;
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

function looksLikePossibleLifecycleMutation(message: string): boolean {
  const text = message.toLowerCase().replace(/\s+/g, ' ').trim();
  if (!text || /\b(?:don't|do not|never|cancel)\b/.test(text)) return false;

  const updateReference =
    /\b(?:focus|session|goal|objective|mode|this work|current work|work i(?:'m| am) doing|what i(?:'m| am) working on)\b/.test(
      text,
    );
  const updateLanguage =
    /\b(?:rename|retitle|call|name|title|change|set|make|switch|update|should be|now called|turn .* into)\b/.test(
      text,
    );
  const explicitStart =
    /\b(?:start|begin|create|open|set|make|switch|change|move|turn)\b.{0,50}\b(?:focus|focus session|active focus|main focus)\b/.test(
      text,
    ) ||
    /\b(?:focus|focus session|active focus|main focus)\b.{0,35}\b(?:on|to|for|into|about)\b/.test(
      text,
    );
  const durableTransition =
    /\b(?:let(?:'s| us)|lets|i want to|i need to|we should|we need to)\s+(?:start|begin|work on|focus on|move on to|switch to)\b/.test(
      text,
    ) ||
    /\b(?:my|our)\s+next\s+(?:focus|priority|project)\s+is\b/.test(text) ||
    /\b(?:done|finished)\s+with\s+(?:this|that|it).{0,60}\b(?:work on|focus on|move to|switch to)\b/.test(
      text,
    );
  const terminalTransition =
    /\b(?:end|stop|close|leave|exit|finish|complete|wrap up|mark)\b.{0,55}\b(?:focus|session|focus mode|this work|current work)\b/.test(
      text,
    ) ||
    /\b(?:focus|session|work|goal|objective)\b.{0,40}\b(?:done|finished|complete|completed|over)\b/.test(
      text,
    );

  return (
    (updateReference && updateLanguage) ||
    explicitStart ||
    durableTransition ||
    terminalTransition
  );
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

function buildCommandMatch(
  payload: SemanticLifecyclePayload,
  intent: 'update' | 'start' | 'end' | 'complete',
): CommandMatch | null {
  const sourceTurnId = normalizeText(payload.sourceTurnId);

  if (intent === 'end' || intent === 'complete') {
    if (payload.summaryRequested === true) return null;
    const lifecyclePayload = JSON.stringify({
      sourceTurnId,
      disposition: intent === 'complete' ? 'completed' : 'ended',
    });
    return {
      command: 'end-focus-session',
      confirmation:
        intent === 'complete' ? 'Completing Focus.' : 'Ending Focus.',
      payload: lifecyclePayload,
      focusSession: {
        forceEnd: payload.forceEnd === true,
      },
    };
  }

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

  if (intent === 'start') {
    if (!focusSession.title) return null;
    return {
      command: 'start-focus-session',
      confirmation: 'Starting Focus.',
      focusSession,
    };
  }

  if (!hasChange) return null;
  return {
    command: 'update-focus-session',
    confirmation: 'Updating Focus.',
    ...(sourceTurnId ? { payload: sourceTurnId } : {}),
    focusSession,
  };
}

/**
 * Make one semantic lifecycle decision before general command/chat routing.
 * The result only selects a typed native command. Existing verified lifecycle
 * clients remain the sole mutation authority.
 */
export async function interpretSemanticFocusLifecycle(
  message: string,
): Promise<SemanticFocusLifecyclePreflightOutcome> {
  const cleanedMessage = normalizeText(message);
  if (!cleanedMessage) {
    return { kind: 'not_lifecycle', confidence: 1, reason: 'Empty message.' };
  }

  const sourceTurnId = createSourceTurnId();
  let response: Response;
  try {
    response = await fetch(
      `${QMEET_API_BASE_URL}/api/focus/lifecycle/semantic/interpret`,
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
      possibleMutation: looksLikePossibleLifecycleMutation(cleanedMessage),
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
    // Validation below safely handles an unreadable response body.
  }

  if (!response.ok) {
    const reason =
      parseErrorMessage(rawPayload) ||
      `The semantic Focus lifecycle endpoint returned HTTP ${response.status}.`;
    return {
      kind: 'unavailable',
      possibleMutation: looksLikePossibleLifecycleMutation(cleanedMessage),
      confidence: null,
      reason,
      message:
        'I could not safely interpret this possible Focus change, so the Focus was not changed.',
    };
  }

  if (!rawPayload || typeof rawPayload !== 'object') {
    return {
      kind: 'unavailable',
      possibleMutation: looksLikePossibleLifecycleMutation(cleanedMessage),
      confidence: null,
      reason: 'The semantic Focus lifecycle response was not an object.',
      message:
        'I could not safely interpret this possible Focus change, so the Focus was not changed.',
    };
  }

  const payload = rawPayload as SemanticLifecyclePayload;
  if (
    payload.ok !== true ||
    payload.bridgeVersion !== SEMANTIC_FOCUS_LIFECYCLE_BRIDGE_VERSION
  ) {
    return {
      kind: 'unavailable',
      possibleMutation: looksLikePossibleLifecycleMutation(cleanedMessage),
      confidence: null,
      reason: 'The semantic Focus lifecycle contract is missing or out of sync.',
      message:
        'The semantic Focus lifecycle bridge is out of sync, so the Focus was not changed. Restart both QMeet services after installing the complete Phase 20D2B1 files.',
    };
  }

  const confidence = normalizeConfidence(payload.confidence);
  const reason = normalizeText(payload.reason);

  if (payload.intent === 'not_lifecycle') {
    return { kind: 'not_lifecycle', confidence, reason };
  }

  if (payload.intent === 'cancelled') {
    return {
      kind: 'acknowledged',
      confidence,
      reason,
      message:
        normalizeText(payload.message) || 'Okay—no Focus change was made.',
    };
  }

  if (payload.intent === 'clarify') {
    return {
      kind: 'blocked',
      confidence,
      reason,
      message:
        normalizeText(payload.message) ||
        'I understood this as a possible Focus change, but I could not identify one safe update or new Focus. The Focus was not changed.',
    };
  }

  if (
    payload.intent === 'update' ||
    payload.intent === 'start' ||
    payload.intent === 'end' ||
    payload.intent === 'complete'
  ) {
    const commandMatch = buildCommandMatch(payload, payload.intent);
    if (commandMatch) {
      return {
        kind: payload.intent,
        commandMatch,
        confidence,
        reason,
      };
    }
    return {
      kind: 'blocked',
      confidence,
      reason: reason || 'The semantic lifecycle result contained no executable fields.',
      message:
        'I understood this as a Focus lifecycle change, but no specific safe operation was available to execute. The Focus was not changed.',
    };
  }

  return {
    kind: 'unavailable',
    possibleMutation: looksLikePossibleLifecycleMutation(cleanedMessage),
    confidence: null,
    reason: 'The semantic Focus lifecycle response used an unknown intent.',
    message:
      'I could not safely interpret this possible Focus change, so the Focus was not changed.',
  };
}
