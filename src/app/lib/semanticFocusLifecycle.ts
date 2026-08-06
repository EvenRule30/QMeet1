import { QMEET_API_BASE_URL } from '../api';
import type { CommandMatch, FocusSessionMode } from '../commands';

export const SEMANTIC_FOCUS_LIFECYCLE_BRIDGE_VERSION = 'phase20d2b1';

const CONTEXT_REASON_PREFIX = 'phase20i-context:';
const SUPPORTED_MODES = new Set<FocusSessionMode>([
  'general',
  'coding',
  'meeting',
  'planning',
  'research',
  'personal',
]);

type SemanticLifecyclePayload = {
  ok?: unknown;
  bridgeVersion?: unknown;
  intent?: unknown;
  possibleMutation?: unknown;
  title?: unknown;
  objective?: unknown;
  objectiveSpecified?: unknown;
  mode?: unknown;
  confidence?: unknown;
  reason?: unknown;
  message?: unknown;
  sourceTurnId?: unknown;
  summaryRequired?: unknown;
};

type SemanticLifecycleMutationResult = {
  kind: 'update' | 'start' | 'end' | 'complete';
  commandMatch: CommandMatch;
  confidence: number;
  reason: string;
};

type SemanticLifecycleAcknowledgedResult = {
  kind: 'acknowledged';
  confidence: number;
  reason: string;
  message: string;
};

type SemanticLifecycleBlockedResult = {
  kind: 'blocked';
  confidence: number;
  reason: string;
  message: string;
  possibleMutation: true;
};

type SemanticLifecycleNoneResult = {
  kind: 'none';
  confidence: number;
  reason: string;
  possibleMutation: false;
};

type SemanticLifecycleUnavailableResult = {
  kind: 'unavailable';
  confidence: number;
  reason: string;
  message: string;
  possibleMutation: boolean;
};

export type SemanticFocusLifecycleResult =
  | SemanticLifecycleMutationResult
  | SemanticLifecycleAcknowledgedResult
  | SemanticLifecycleBlockedResult
  | SemanticLifecycleNoneResult
  | SemanticLifecycleUnavailableResult;

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

function normalizeMessage(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/\s+/g, ' ');
}

function normalizeConfidence(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function createSourceTurnId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `focus-turn-${crypto.randomUUID().replace(/-/g, '')}`;
  }
  return `focus-turn-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function parseMode(value: unknown): FocusSessionMode | undefined {
  const normalized = normalizeText(value) as FocusSessionMode;
  return SUPPORTED_MODES.has(normalized) ? normalized : undefined;
}

function contextEnvelopeFromReason(
  reason: string,
): { contextField: string; contextValue: string } | null {
  if (!reason.startsWith(CONTEXT_REASON_PREFIX)) return null;
  const remainder = reason.slice(CONTEXT_REASON_PREFIX.length);
  const separator = remainder.indexOf(':');
  if (separator <= 0) return null;
  const contextField = remainder.slice(0, separator).trim();
  const contextValue = remainder.slice(separator + 1).trim();
  if (
    ![
      'requirements',
      'constraints',
      'preferences',
      'decisions',
      'knownFacts',
    ].includes(contextField) ||
    !contextValue
  ) {
    return null;
  }
  return { contextField, contextValue };
}

function looksLikeFocusContextStatement(message: string): boolean {
  const text = normalizeMessage(message);
  if (!text) return false;
  if (
    /\b(?:focus|focus session|session|goal|objective|mode)\b/.test(text) &&
    /\b(?:start|begin|create|open|resume|restart|end|stop|finish|complete|rename|retitle|replace|switch|move|change|update|set|clear|remove|make)\b/.test(
      text,
    )
  ) {
    return false;
  }
  if (
    /\b(?:let(?:'s| us)|lets|i want to|i need to|we should|we need to)\s+(?:start|begin|work on|focus on|move on to|switch to)\b/.test(
      text,
    )
  ) {
    return false;
  }
  return (
    /^(?:i|we)\s+(?:really\s+)?(?:want|prefer|would like|would rather|like)\s+.+/.test(
      text,
    ) ||
    /^(?:i|we)\s+have\s+.+\b(?:available|free|minutes?|hours?|days?|weeks?|months?|weekends?)\b/.test(
      text,
    ) ||
    /^(?:i am|i'm|we are|we're)\s+(?:only\s+)?available\s+.+/.test(text) ||
    /\b(?:under|below|within|at most|no more than|less than|maximum|max|budget|cost|spend|deadline|must not|cannot|can't|avoid)\b/.test(
      text,
    ) ||
    /^(?:keep|limit|cap|stay|fit)\b/.test(text) ||
    /^(?:i|we)(?:'ve| have)?\s+decided\b/.test(text) ||
    /^(?:it|this|the result|the plan)\s+(?:needs|has)\s+to\b/.test(text) ||
    /^(?:the|our|my)\s+(?:trip|project|meeting|deadline|date|schedule|budget|dates?)\s+(?:is|are|has|starts|ends)\b/.test(
      text,
    )
  );
}

function looksLikeExplicitLifecycleMutation(message: string): boolean {
  const text = normalizeMessage(message);
  if (!text) return false;
  return Boolean(
    /\b(?:start|begin|create|open|resume|restart|end|finish|complete|rename|retitle|replace|switch|move|change|update|set|clear|remove|make)\b.{0,70}\b(?:focus|focus session|session|goal|objective|mode)\b/.test(
      text,
    ) ||
      /\b(?:focus|focus session|session|goal|objective|mode)\b.{0,55}\b(?:to|as|into|is|should be|called|named)\b/.test(
        text,
      ) ||
      /\b(?:let(?:'s| us)|lets|i want to|i need to|we should|we need to)\s+(?:start|begin|work on|focus on|move on to|switch to)\b/.test(
        text,
      ) ||
      /\b(?:my|our)\s+next\s+(?:focus|priority|project)\s+is\b/.test(text) ||
      /\b(?:cancel|ignore|discard)\s+(?:that|the|this)?\s*(?:focus|session)?\s*(?:change|update|rename|start|replacement)\b/.test(
        text,
      ),
  );
}

function looksLikeFocusTerminalLanguage(message: string): boolean {
  const text = normalizeMessage(message).replace(/[.!?]+$/g, '').trim();
  const focusTarget = /\b(?:focus(?:\s+session)?|session|work)\b/.test(text);
  const focusReference = focusTarget;
  const terminalLanguage =
    /\b(?:end|ended|stop|stopped|close|closed|complete|completed|finish|finished|mark)\b/.test(text);
  const hasDirectTerminalLanguage = focusTarget && terminalLanguage;
  const hasReferencedTerminalLanguage = focusReference && terminalLanguage;
  const directFocusTerminalPattern =
    hasDirectTerminalLanguage && hasReferencedTerminalLanguage
      ? /^(?:please\s+)?(?:(?:end|ended|stop|stopped|close|closed|complete|completed|finish|finished)\s+(?:(?:my|the|this|current|active)\s+)?(?:focus(?:\s+session)?|session|work)|mark\s+(?:(?:my|the|this|current|active)\s+)?(?:focus(?:\s+session)?|session|work)\s+(?:as\s+)?complete)(?:\s+anyway)?$/
      : /$a/;
  return directFocusTerminalPattern.test(text);
}

export function shouldRouteDirectFocusTerminalLanguageBeforeSemanticPreflight(message: string): boolean {
  return looksLikeFocusTerminalLanguage(message);
}

// Phase 20D compatibility exports. These names all describe the same direct
// terminal safety boundary and intentionally delegate to one detector.
export function shouldRouteDirectFocusTerminalLanguageBeforeCommandRouting(message: string): boolean {
  return looksLikeFocusTerminalLanguage(message);
}

export function shouldRouteDirectFocusTerminalBeforeSemanticPreflight(message: string): boolean {
  return looksLikeFocusTerminalLanguage(message);
}

export function shouldRouteDirectFocusTerminalBeforeCommandRouting(message: string): boolean {
  return looksLikeFocusTerminalLanguage(message);
}

export function shouldRouteDirectFocusTerminalLanguageBeforeCommandParsing(message: string): boolean {
  return looksLikeFocusTerminalLanguage(message);
}

export function shouldRouteDirectFocusTerminalBeforeCommandParsing(message: string): boolean {
  return looksLikeFocusTerminalLanguage(message);
}

export function shouldRouteDirectFocusTerminalLanguageBeforeInterpreter(message: string): boolean {
  return looksLikeFocusTerminalLanguage(message);
}

export function shouldRouteDirectFocusTerminalBeforeInterpreter(message: string): boolean {
  return looksLikeFocusTerminalLanguage(message);
}

function terminalDisposition(message: string): 'ended' | 'completed' | null {
  if (!looksLikeFocusTerminalLanguage(message)) return null;
  const text = normalizeMessage(message).replace(/[.!?]+$/g, '').trim();
  if (
    /^(?:please\s+)?(?:complete|completed|finish|finished|mark)\s+(?:(?:my|the|this|current|active)\s+)?(?:focus(?:\s+session)?|session|work)(?:\s+anyway)?$/.test(
      text,
    ) ||
    /^(?:please\s+)?mark\s+(?:(?:my|the|this|current|active)\s+)?(?:focus(?:\s+session)?|session|work)\s+(?:as\s+)?complete(?:\s+anyway)?$/.test(
      text,
    )
  ) {
    return 'completed';
  }
  if (
    /^(?:please\s+)?(?:end|ended|stop|stopped|close|closed)\s+(?:(?:my|the|this|current|active)\s+)?(?:focus(?:\s+session)?|session|work)(?:\s+anyway)?$/.test(
      text,
    )
  ) {
    return 'ended';
  }
  return null;
}

export function getDirectFocusTerminalCommandMatch(message: string): CommandMatch | null {
  const disposition = terminalDisposition(message);
  if (!disposition) return null;
  const forceEnd = /\banyway\b/i.test(message);
  return {
    command: 'end-focus-session',
    confirmation:
      disposition === 'completed' ? 'Completed focus session.' : 'Ended focus session.',
    payload: JSON.stringify({
      sourceTurnId: createSourceTurnId(),
      disposition,
    }),
    focusSession: { forceEnd },
  };
}

export function shouldPreflightSemanticFocusLifecycleBeforeCommandRouting(
  message: string,
): boolean {
  return (
    looksLikeFocusContextStatement(message) ||
    looksLikeExplicitLifecycleMutation(message)
  );
}

export function shouldRouteExactFocusLifecycleThroughSemanticPreflight(
  commandMatch: CommandMatch | null,
  originalMessage: string,
): boolean {
  if (
    commandMatch?.command === 'mark-task-done' &&
    looksLikeFocusTerminalLanguage(originalMessage)
  ) {
    return true;
  }
  return (
    commandMatch?.command === 'start-focus-session' ||
    commandMatch?.command === 'update-focus-session' ||
    commandMatch?.command === 'resume-last-focus-session' ||
    commandMatch?.command === 'end-focus-session' ||
    commandMatch?.command === 'end-focus-with-summary'
  );
}

function buildMutationResult(
  payload: SemanticLifecyclePayload,
  sourceTurnId: string,
): SemanticLifecycleMutationResult | null {
  const reason = normalizeText(payload.reason);
  const confidence = normalizeConfidence(payload.confidence);
  if (payload.intent === 'end' || payload.intent === 'complete') {
    const disposition = payload.intent === 'complete' ? 'completed' : 'ended';
    return {
      kind: payload.intent,
      confidence,
      reason,
      commandMatch: {
        command: 'end-focus-session',
        confirmation:
          disposition === 'completed'
            ? 'Completed focus session.'
            : 'Ended focus session.',
        payload: JSON.stringify({ sourceTurnId, disposition }),
      },
    };
  }
  const contextEnvelope = contextEnvelopeFromReason(reason);
  if (payload.intent === 'update' && contextEnvelope) {
    return {
      kind: 'update',
      confidence,
      reason,
      commandMatch: {
        command: 'update-focus-session',
        confirmation: 'Updated focus session.',
        payload: JSON.stringify({
          sourceTurnId,
          ...contextEnvelope,
        }),
      },
    };
  }
  if (payload.intent !== 'update' && payload.intent !== 'start') return null;

  const title = normalizeText(payload.title);
  const objective = normalizeText(payload.objective);
  const objectiveSpecified = payload.objectiveSpecified === true;
  const mode = parseMode(payload.mode);
  const focusSession = {
    ...(title ? { title } : {}),
    ...(objectiveSpecified ? { goal: objective } : {}),
    ...(mode ? { mode } : {}),
  };
  if (payload.intent === 'start' && !title) return null;
  if (
    payload.intent === 'update' &&
    !title &&
    !objectiveSpecified &&
    !mode
  ) {
    return null;
  }
  if (payload.intent === 'start') {
    return {
      kind: 'start',
      confidence,
      reason,
      commandMatch: {
        command: 'start-focus-session',
        confirmation: 'Started focus session.',
        focusSession,
        payload: sourceTurnId,
      },
    };
  }
  return {
    kind: 'update',
    confidence,
    reason,
    commandMatch: {
      command: 'update-focus-session',
      confirmation: 'Updated focus session.',
      focusSession,
      payload: sourceTurnId,
    },
  };
}

export async function interpretSemanticFocusLifecycle(
  message: string,
): Promise<SemanticFocusLifecycleResult> {
  const cleaned = normalizeText(message);
  const sourceTurnId = createSourceTurnId();
  const possibleMutation =
    looksLikeFocusContextStatement(cleaned) ||
    looksLikeExplicitLifecycleMutation(cleaned);
  if (!cleaned) {
    return {
      kind: 'none',
      confidence: 1,
      reason: 'The message was empty.',
      possibleMutation: false,
    };
  }

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
        body: JSON.stringify({ message: cleaned, sourceTurnId }),
      },
    );
  } catch (error) {
    return {
      kind: 'unavailable',
      confidence: 0,
      reason:
        error instanceof Error ? error.message : 'Semantic Focus lifecycle endpoint unavailable.',
      message:
        'I could not verify the requested Focus change, so no Focus change was made.',
      possibleMutation,
    };
  }

  let rawPayload: unknown = null;
  try {
    rawPayload = await response.json();
  } catch {
    // The safe unavailable result below handles unreadable responses.
  }
  if (!response.ok || !rawPayload || typeof rawPayload !== 'object') {
    const record = rawPayload as Record<string, unknown> | null;
    const detail =
      record?.detail && typeof record.detail === 'object'
        ? (record.detail as Record<string, unknown>)
        : null;
    return {
      kind: 'unavailable',
      confidence: 0,
      reason:
        normalizeText(detail?.message) ||
        normalizeText(record?.message) ||
        `Semantic Focus lifecycle request failed with status ${response.status}.`,
      message:
        'I could not verify the requested Focus change, so no Focus change was made.',
      possibleMutation,
    };
  }

  const payload = rawPayload as SemanticLifecyclePayload;
  if (
    payload.ok !== true ||
    payload.bridgeVersion !== SEMANTIC_FOCUS_LIFECYCLE_BRIDGE_VERSION
  ) {
    return {
      kind: 'unavailable',
      confidence: 0,
      reason: 'The semantic Focus lifecycle contract is missing or out of sync.',
      message:
        'The semantic Focus lifecycle bridge is out of sync, so no Focus change was made. Restart both QMeet services after installing the complete files.',
      possibleMutation,
    };
  }

  const confidence = normalizeConfidence(payload.confidence);
  const reason = normalizeText(payload.reason);
  const messageText = normalizeText(payload.message);
  if (
    (payload.intent === 'end' || payload.intent === 'complete') &&
    payload.summaryRequired === true
  ) {
    return {
      kind: 'blocked',
      confidence,
      reason,
      message:
        messageText ||
        'Save the Focus summary first, then end or complete the Focus.',
      possibleMutation: true,
    };
  }

  const mutation = buildMutationResult(
    payload,
    normalizeText(payload.sourceTurnId) || sourceTurnId,
  );
  if (mutation) return mutation;

  if (payload.intent === 'cancelled') {
    return {
      kind: 'acknowledged',
      confidence,
      reason,
      message: messageText || 'Okay—no Focus change was made.',
    };
  }
  if (payload.intent === 'clarify') {
    return {
      kind: 'blocked',
      confidence,
      reason,
      message:
        messageText ||
        'I understood this as a possible Focus change, but I could not identify one safe lifecycle operation. The Focus was not changed.',
      possibleMutation: true,
    };
  }
  if (payload.intent === 'not_lifecycle') {
    return {
      kind: 'none',
      confidence,
      reason,
      possibleMutation: false,
    };
  }
  return {
    kind: 'unavailable',
    confidence,
    reason: reason || 'The semantic Focus lifecycle response used an unknown intent.',
    message:
      'I could not safely interpret this possible Focus change, so no Focus change was made.',
    possibleMutation,
  };
}
