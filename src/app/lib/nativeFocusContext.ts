import { QMEET_API_BASE_URL } from '../api';
import type { ActiveSession } from '../types';
import {
  applyVerifiedFocusProjection,
  readVerifiedFocusProjection,
} from './nativeFocusLifecycle';

export type FocusContextField =
  | 'requirements'
  | 'constraints'
  | 'preferences'
  | 'decisions'
  | 'knownFacts';
export type NativeFocusContextState = {
  focusId: string;
  title: string;
  objective: string;
  status: 'clarifying' | 'active' | 'waiting' | 'ready';
  requirements: string[];
  constraints: string[];
  preferences: string[];
  decisions: string[];
  knownFacts: string[];
  updatedAt: string;
};

type NativeFocusContextVerification = {
  activeFocusMatches?: unknown;
  objectivePreserved?: unknown;
  contextPersisted?: unknown;
  sourceTurnUnique?: unknown;
};
type NativeFocusContextPayload = {
  ok?: unknown;
  operation?: unknown;
  outcome?: unknown;
  verified?: unknown;
  focusId?: unknown;
  focusTitle?: unknown;
  field?: unknown;
  value?: unknown;
  canonicalValue?: unknown;
  sourceTurnId?: unknown;
  updatedAt?: unknown;
  focusContext?: unknown;
  verification?: unknown;
  message?: unknown;
};
export type VerifiedNativeFocusContextResult = {
  ok: true;
  operation: 'add_focus_context';
  outcome: 'added' | 'reused';
  verified: true;
  focusId: string;
  focusTitle: string;
  field: FocusContextField;
  value: string;
  canonicalValue: string;
  sourceTurnId: string;
  updatedAt: string;
  focusContext: NativeFocusContextState;
  message: string;
};

export class NativeFocusContextClientError extends Error {
  code: string;
  constructor(message: string, code = 'native_focus_context_failed') {
    super(message);
    this.name = 'NativeFocusContextClientError';
    this.code = code;
  }
}

const CONTEXT_FIELDS = new Set<FocusContextField>([
  'requirements',
  'constraints',
  'preferences',
  'decisions',
  'knownFacts',
]);

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}
function normalizeStringList(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const items = value.map(normalizeText);
  if (items.some((item) => !item)) return null;
  return items;
}
function normalizeContextState(value: unknown): NativeFocusContextState | null {
  if (!value || typeof value !== 'object') return null;
  const envelope = value as Record<string, unknown>;
  const record =
    envelope.state && typeof envelope.state === 'object'
      ? (envelope.state as Record<string, unknown>)
      : envelope;
  const focusId = normalizeText(record.focusId);
  const title = normalizeText(record.title);
  const objective = normalizeText(record.objective);
  const status = record.status;
  const requirements = normalizeStringList(record.requirements);
  const constraints = normalizeStringList(record.constraints);
  const preferences = normalizeStringList(record.preferences);
  const decisions = normalizeStringList(record.decisions);
  const knownFacts = normalizeStringList(record.knownFacts);
  const updatedAt = normalizeText(record.updatedAt);
  if (
    !focusId ||
    !title ||
    !updatedAt ||
    !['clarifying', 'active', 'waiting', 'ready'].includes(String(status)) ||
    requirements === null ||
    constraints === null ||
    preferences === null ||
    decisions === null ||
    knownFacts === null
  ) {
    return null;
  }
  return {
    focusId,
    title,
    objective,
    status: status as NativeFocusContextState['status'],
    requirements,
    constraints,
    preferences,
    decisions,
    knownFacts,
    updatedAt,
  };
}
function containsExact(values: string[], target: string): boolean {
  const expected = target.toLocaleLowerCase();
  return values.some((value) => value.toLocaleLowerCase() === expected);
}
function parseErrorPayload(payload: unknown): { code: string; message: string } {
  if (!payload || typeof payload !== 'object') {
    return {
      code: 'native_focus_context_failed',
      message: 'The Focus context request failed.',
    };
  }
  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  if (detail && typeof detail === 'object') {
    const detailRecord = detail as Record<string, unknown>;
    return {
      code: normalizeText(detailRecord.code) || 'native_focus_context_failed',
      message:
        normalizeText(detailRecord.message) || 'The Focus context request failed.',
    };
  }
  return {
    code: normalizeText(record.code) || 'native_focus_context_failed',
    message: normalizeText(record.message) || 'The Focus context request failed.',
  };
}
function createSourceTurnId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `focus-context-${crypto.randomUUID()}`;
  }
  return `focus-context-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
export async function addNativeFocusContextVerified(input: {
  expectedFocusId: string;
  expectedObjective: string;
  field: FocusContextField;
  value: string;
  sourceTurnId?: string;
}): Promise<VerifiedNativeFocusContextResult> {
  const expectedFocusId = normalizeText(input.expectedFocusId);
  const expectedObjective = normalizeText(input.expectedObjective);
  const value = normalizeText(input.value);
  if (!expectedFocusId) {
    throw new NativeFocusContextClientError(
      'No verified active Focus is available for this context.',
      'missing_focus',
    );
  }
  if (!CONTEXT_FIELDS.has(input.field) || !value) {
    throw new NativeFocusContextClientError(
      'The Focus context field or value was invalid.',
      'invalid_context',
    );
  }
  const sourceTurnId = normalizeText(input.sourceTurnId) || createSourceTurnId();
  let response: Response;
  try {
    response = await fetch(`${QMEET_API_BASE_URL}/api/focus/lifecycle/context`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'x-qmeet-turn-id': sourceTurnId,
      },
      body: JSON.stringify({
        expectedFocusId,
        expectedObjective,
        field: input.field,
        value,
        sourceTurnId,
      }),
    });
  } catch (error) {
    throw new NativeFocusContextClientError(
      error instanceof Error && error.message.trim()
        ? error.message
        : 'The native Focus context endpoint was unavailable.',
      'endpoint_unavailable',
    );
  }
  let rawPayload: unknown = null;
  try {
    rawPayload = await response.json();
  } catch {
    // Validation below handles unreadable responses safely.
  }
  if (!response.ok) {
    const parsed = parseErrorPayload(rawPayload);
    throw new NativeFocusContextClientError(parsed.message, parsed.code);
  }
  if (!rawPayload || typeof rawPayload !== 'object') {
    throw new NativeFocusContextClientError(
      'The canonical Focus context response was not an object.',
      'invalid_response',
    );
  }
  const payload = rawPayload as NativeFocusContextPayload;
  const verification = payload.verification as NativeFocusContextVerification | null;
  const focusContext = normalizeContextState(payload.focusContext);
  const outcome = payload.outcome;
  const field = normalizeText(payload.field) as FocusContextField;
  const resultValue = normalizeText(payload.value);
  const canonicalValue = normalizeText(payload.canonicalValue);
  const resultFocusId = normalizeText(payload.focusId);
  const resultSourceTurnId = normalizeText(payload.sourceTurnId);
  const updatedAt = normalizeText(payload.updatedAt);
  const message = normalizeText(payload.message);
  const contextValues = focusContext?.[input.field];
  const valid =
    payload.ok === true &&
    payload.operation === 'add_focus_context' &&
    (outcome === 'added' || outcome === 'reused') &&
    payload.verified === true &&
    resultFocusId === expectedFocusId &&
    field === input.field &&
    resultValue === value &&
    Boolean(canonicalValue) &&
    resultSourceTurnId === sourceTurnId &&
    Boolean(updatedAt) &&
    Boolean(message) &&
    focusContext !== null &&
    focusContext.focusId === expectedFocusId &&
    focusContext.objective === expectedObjective &&
    Array.isArray(contextValues) &&
    containsExact(contextValues, canonicalValue) &&
    verification?.activeFocusMatches === true &&
    verification.objectivePreserved === true &&
    verification.contextPersisted === true &&
    verification.sourceTurnUnique === true;
  if (!valid || !focusContext || (outcome !== 'added' && outcome !== 'reused')) {
    throw new NativeFocusContextClientError(
      'The canonical response did not prove that the canonical Focus context item was persisted without replacing the objective.',
      'verification_failed',
    );
  }
  return {
    ok: true,
    operation: 'add_focus_context',
    outcome,
    verified: true,
    focusId: resultFocusId,
    focusTitle: normalizeText(payload.focusTitle),
    field,
    value: resultValue,
    canonicalValue,
    sourceTurnId: resultSourceTurnId,
    updatedAt,
    focusContext,
    message,
  };
}
export function applyVerifiedFocusContextProjection(
  result: VerifiedNativeFocusContextResult,
): ActiveSession {
  const current = readVerifiedFocusProjection();
  if (!current || current.id !== result.focusId) {
    throw new NativeFocusContextClientError(
      'The displayed Focus changed before its verified context could be projected.',
      'stale_projection',
    );
  }
  if (current.goal.trim() !== result.focusContext.objective) {
    throw new NativeFocusContextClientError(
      'The verified Focus objective no longer matches the displayed projection.',
      'objective_projection_mismatch',
    );
  }
  const next: ActiveSession = {
    ...current,
    updatedAt: result.updatedAt,
  };
  applyVerifiedFocusProjection(next);
  return next;
}
export async function readNativeFocusContext(
  expectedFocusId: string,
): Promise<NativeFocusContextState> {
  const normalizedFocusId = normalizeText(expectedFocusId);
  if (!normalizedFocusId) {
    throw new NativeFocusContextClientError(
      'A Focus ID is required to read canonical context.',
      'missing_focus',
    );
  }
  let response: Response;
  try {
    response = await fetch(`${QMEET_API_BASE_URL}/api/focus/state`, {
      headers: { Accept: 'application/json' },
    });
  } catch (error) {
    throw new NativeFocusContextClientError(
      error instanceof Error && error.message.trim()
        ? error.message
        : 'The canonical Focus state endpoint was unavailable.',
      'endpoint_unavailable',
    );
  }
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // Validation below reports an unreadable response.
  }
  if (!response.ok) {
    const parsed = parseErrorPayload(payload);
    throw new NativeFocusContextClientError(parsed.message, parsed.code);
  }
  const context = normalizeContextState(payload);
  if (!context || context.focusId !== normalizedFocusId) {
    throw new NativeFocusContextClientError(
      'The canonical Focus context did not match the active Focus.',
      'stale_focus',
    );
  }
  return context;
}
function section(label: string, values: string[]): string {
  if (values.length === 0) return '';
  return `${label}:\n${values.map((value) => `• ${value}`).join('\n')}`;
}
export function appendNativeFocusContextToSummary(
  summary: string,
  context: NativeFocusContextState,
): string {
  const sections = [
    section('Requirements', context.requirements),
    section('Constraints', context.constraints),
    section('Preferences', context.preferences),
    section('Decisions', context.decisions),
    section('Known details', context.knownFacts),
  ].filter(Boolean);
  if (sections.length === 0) return summary.trim();
  return `${summary.trim()}\n\nFocus context:\n\n${sections.join('\n\n')}`;
}
export function buildNativeFocusContextTaskTitles(
  context: NativeFocusContextState,
): string[] {
  const titles: string[] = [];
  for (const value of context.constraints) {
    titles.push(`Check the plan against this constraint: ${value}`);
  }
  for (const value of context.requirements) {
    titles.push(`Make sure the result includes: ${value}`);
  }
  for (const value of context.preferences) {
    titles.push(`Find an option that matches this preference: ${value}`);
  }
  for (const value of context.knownFacts) {
    titles.push(`Use this known detail in the plan: ${value}`);
  }
  for (const value of context.decisions) {
    titles.push(`Carry out the decision: ${value}`);
  }
  return titles;
}
export function describeNativeFocusContextFailure(error: unknown): string {
  const detail =
    error instanceof Error && error.message.trim()
      ? ` ${error.message.trim()}`
      : '';
  return (
    'I could not verify that this detail was added to the canonical Focus without replacing its objective, ' +
    `so I will not claim it was saved.${detail}`
  );
}
