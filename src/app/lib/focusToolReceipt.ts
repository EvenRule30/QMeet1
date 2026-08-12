import type { CommandMatch } from '../commands';

const GENERIC_FOCUS_REUSED_PREFIX = 'focus already matches:';

function clean(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

/**
 * Keep canonical verification authoritative while making a verified no-op
 * receipt precise enough for the UI and post-tool continuation model.
 *
 * The backend historically returns "Focus already matches: <title>." for any
 * reused update, even when the requested field was the goal or mode. We only
 * refine that already-verified success message; this function never infers or
 * performs a state change.
 */
export function normalizeVerifiedFocusToolReceipt(
  commandMatch: CommandMatch,
  receipt: string,
): string {
  if (commandMatch.command !== 'update-focus-session') return receipt;

  const normalizedReceipt = clean(receipt);
  if (!normalizedReceipt.toLowerCase().startsWith(GENERIC_FOCUS_REUSED_PREFIX)) {
    return receipt;
  }

  const focusSession = commandMatch.focusSession;
  if (!focusSession) return receipt;

  const title = clean(focusSession.title);
  const goal = clean(focusSession.goal);
  const mode = clean(focusSession.mode);
  const requested = [
    title ? 'title' : '',
    goal ? 'goal' : '',
    mode ? 'mode' : '',
  ].filter(Boolean);

  if (requested.length === 1 && goal) {
    return `Focus goal already matches: ${goal}.`;
  }
  if (requested.length === 1 && title) {
    return `Focus title already matches: ${title}.`;
  }
  if (requested.length === 1 && mode) {
    return `Focus mode already matches: ${mode}.`;
  }
  if (requested.length > 1) {
    return `Focus already matches the requested ${requested.join(' and ')}.`;
  }

  return receipt;
}
