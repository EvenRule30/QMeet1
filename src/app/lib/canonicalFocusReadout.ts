import { QMEET_API_BASE_URL } from '../api';
import type { MemorySessionMode } from '../types';
import { readVerifiedFocusProjection } from './nativeFocusLifecycle';

type CanonicalFocusReadState = {
  focusId?: unknown;
  title?: unknown;
  objective?: unknown;
  nextAction?: unknown;
  status?: unknown;
  tags?: unknown;
};

type CanonicalFocusReadResponse = {
  ok?: unknown;
  state?: unknown;
};

const OPEN_FOCUS_STATUSES = new Set(['clarifying', 'active', 'waiting', 'ready']);
const MEMORY_SESSION_MODES = new Set<MemorySessionMode>([
  'coding',
  'meeting',
  'planning',
  'research',
  'personal',
  'general',
]);

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

function normalizeState(value: unknown): CanonicalFocusReadState | null {
  return value && typeof value === 'object'
    ? (value as CanonicalFocusReadState)
    : null;
}

function modeFromTags(tags: unknown): MemorySessionMode | null {
  if (!Array.isArray(tags)) return null;
  for (const rawTag of tags) {
    const tag = normalizeText(rawTag);
    if (!tag.toLowerCase().startsWith('mode:')) continue;
    const candidate = tag.slice('mode:'.length).trim().toLowerCase() as MemorySessionMode;
    if (MEMORY_SESSION_MODES.has(candidate)) return candidate;
  }
  return null;
}

function resolveMode(state: CanonicalFocusReadState): MemorySessionMode {
  const taggedMode = modeFromTags(state.tags);
  if (taggedMode) return taggedMode;

  const projection = readVerifiedFocusProjection();
  const focusId = normalizeText(state.focusId);
  if (projection?.id === focusId) return projection.mode;
  return 'general';
}

export function formatCanonicalFocusReadout(state: CanonicalFocusReadState): string {
  const focusId = normalizeText(state.focusId);
  const status = normalizeText(state.status).toLowerCase();
  if (!focusId || !OPEN_FOCUS_STATUSES.has(status)) {
    return 'No active Focus is currently running.';
  }

  const title = normalizeText(state.title) || 'Focus session';
  const objective = normalizeText(state.objective);
  const nextAction = normalizeText(state.nextAction);
  const mode = resolveMode(state);

  const parts = [`Current focus: ${title}.`, `Mode: ${mode}.`];
  parts.push(objective ? `Goal: ${objective}.` : 'No goal has been set yet.');
  if (nextAction) {
    parts.push(`Next step: ${nextAction}.`);
  }
  return parts.join(' ');
}

export async function readCanonicalFocusReadout(): Promise<string> {
  const response = await fetch(`${QMEET_API_BASE_URL}/api/focus/state`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });

  let payload: CanonicalFocusReadResponse | null = null;
  try {
    payload = (await response.json()) as CanonicalFocusReadResponse;
  } catch {
    // Validation below turns an unreadable body into a safe fallback error.
  }

  if (!response.ok || payload?.ok !== true) {
    throw new Error('The canonical Focus state could not be read.');
  }

  const state = normalizeState(payload.state);
  if (!state) {
    throw new Error('The canonical Focus response did not include a valid state.');
  }

  return formatCanonicalFocusReadout(state);
}
