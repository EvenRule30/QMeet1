import type {
  CompositeConfirmationPause,
  CompositeImmediateStepReceipt,
  CompositeResumablePreflight,
  CompositeResumableStepCandidate,
} from './agentCompositeExecution';

export const PENDING_COMPOSITE_RESUME_VERSION = 'phase21g3a-v1' as const;

export type PendingCompositeResume = {
  version: typeof PENDING_COMPOSITE_RESUME_VERSION;
  originalUserText: string;
  preflight: Extract<CompositeResumablePreflight, { ok: true }>;
  pause: CompositeConfirmationPause;
};

/**
 * G3A pending state carries only orchestration metadata.
 *
 * Canonical Calendar event identity must continue to live in App's existing
 * pending Calendar target refs after authoritative target resolution. This
 * object must never become a second event/task/Focus identity authority.
 */
export function createPendingCompositeResume(options: {
  originalUserText: string;
  preflight: CompositeResumablePreflight;
  pause: CompositeConfirmationPause;
}): PendingCompositeResume | null {
  const originalUserText = options.originalUserText.trim();
  if (!originalUserText || options.preflight.ok === false) return null;

  const pause = options.pause;
  const pausedCandidate =
    options.preflight.candidates[pause.pausedStepIndex] ?? null;

  if (
    pause.planId !== options.preflight.planId ||
    !pausedCandidate ||
    pausedCandidate.confirmationMode !== 'required' ||
    pausedCandidate.stepId !== pause.pausedStepId ||
    pausedCandidate.proposedAction !== pause.expectedAction
  ) {
    return null;
  }

  return {
    version: PENDING_COMPOSITE_RESUME_VERSION,
    originalUserText,
    preflight: options.preflight,
    pause: {
      ...pause,
      receiptsBeforePause: [...pause.receiptsBeforePause],
    },
  };
}

export function getPendingCompositePausedCandidate(
  pending: PendingCompositeResume | null,
): CompositeResumableStepCandidate | null {
  if (!pending) return null;
  const candidate =
    pending.preflight.candidates[pending.pause.pausedStepIndex] ?? null;
  if (!candidate) return null;
  if (candidate.confirmationMode !== 'required') return null;
  if (candidate.stepId !== pending.pause.pausedStepId) return null;
  if (candidate.proposedAction !== pending.pause.expectedAction) return null;
  return candidate;
}

export function matchesPendingCompositeConfirmationAction(
  pending: PendingCompositeResume | null,
  action: string,
): boolean {
  const candidate = getPendingCompositePausedCandidate(pending);
  return Boolean(candidate && candidate.proposedAction === action);
}

export function validatePendingCompositeConfirmedReceipt(
  pending: PendingCompositeResume | null,
  receipt: CompositeImmediateStepReceipt | null,
): boolean {
  if (!pending || !receipt) return false;
  return Boolean(
    receipt.stepId === pending.pause.pausedStepId &&
      receipt.ok === true &&
      receipt.toolResult.trim(),
  );
}
