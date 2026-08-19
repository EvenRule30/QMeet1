import type { CommandMatch } from '../commands';
import type { PromotedSingleIntentDecision } from './agentShadowObserver';
import type {
  AgentCompositePlanResponse,
  AgentCompositeStep,
} from './agentCompositePlan';
import {
  resolvePromotedCalendarReadToolCommand,
  resolvePromotedNoteReadToolCommand,
  resolvePromotedNoteSaveToolCommand,
  resolvePromotedSearchToolCommand,
  resolvePromotedTaskCreateToolCommand,
  resolvePromotedTaskReadToolCommand,
} from './agentToolPromotion';

export type CompositeImmediateStepCandidate = {
  stepId: string;
  turnOwner: AgentCompositeStep['turnOwner'];
  proposedAction: string;
  commandMatch: CommandMatch;
};

export type CompositeImmediatePreflightFailureReason =
  | 'not-composite'
  | 'dependency-not-yet-promoted'
  | 'confirmation-pause-required'
  | 'unsupported-owner-or-action'
  | 'deterministic-validation-failed';

export type CompositeImmediatePreflight =
  | {
      ok: true;
      planId: string;
      candidates: CompositeImmediateStepCandidate[];
    }
  | {
      ok: false;
      planId: string | null;
      reason: CompositeImmediatePreflightFailureReason;
      stepId: string | null;
      detail: string;
    };

export type CompositeImmediateStepReceipt = {
  stepId: string;
  ok: boolean;
  toolResult: string;
  toolContext?: string;
};

export type CompositeImmediateExecutionResult = {
  ok: boolean;
  status: 'completed' | 'failed' | 'not-executed';
  planId: string | null;
  receipts: CompositeImmediateStepReceipt[];
  failedStepId: string | null;
  reason: string;
};

const CONFIRMATION_PAUSE_ACTIONS = new Set([
  'add-calendar-event',
  'edit-last-event',
  'delete-calendar-event',
  'delete-last-event',
  'clear-calendar',
  'mark-task-done',
  'delete-task',
]);

function toPromotedAtomicDecision(
  plan: AgentCompositePlanResponse,
  step: AgentCompositeStep,
): PromotedSingleIntentDecision {
  return {
    source: 'agent-shadow',
    turnOwner: step.turnOwner,
    focusRelevant: step.focusRelevant,
    disposition: 'tool',
    proposedCapability: step.proposedCapability,
    proposedAction: step.proposedAction,
    proposedArguments: { ...step.proposedArguments },
    confidence: plan.plan.confidence,
    turnId: `${plan.planId}:${step.stepId}`,
  };
}

function resolveImmediateCandidate(
  plan: AgentCompositePlanResponse,
  step: AgentCompositeStep,
): CompositeImmediateStepCandidate | null {
  const decision = toPromotedAtomicDecision(plan, step);

  if (step.turnOwner === 'search' && step.proposedAction === 'run-search') {
    const resolved = resolvePromotedSearchToolCommand(decision);
    return resolved
      ? {
          stepId: step.stepId,
          turnOwner: step.turnOwner,
          proposedAction: step.proposedAction,
          commandMatch: resolved.commandMatch,
        }
      : null;
  }

  if (step.turnOwner === 'tasks' && step.proposedAction === 'remember-task') {
    const resolved = resolvePromotedTaskCreateToolCommand(decision);
    return resolved
      ? {
          stepId: step.stepId,
          turnOwner: step.turnOwner,
          proposedAction: step.proposedAction,
          commandMatch: resolved.commandMatch,
        }
      : null;
  }

  if (step.turnOwner === 'tasks' && step.proposedAction === 'read-memory') {
    const resolved = resolvePromotedTaskReadToolCommand(decision);
    return resolved
      ? {
          stepId: step.stepId,
          turnOwner: step.turnOwner,
          proposedAction: step.proposedAction,
          commandMatch: resolved.commandMatch,
        }
      : null;
  }

  if (step.turnOwner === 'notes' && step.proposedAction === 'save-note') {
    const resolved = resolvePromotedNoteSaveToolCommand(decision);
    return resolved
      ? {
          stepId: step.stepId,
          turnOwner: step.turnOwner,
          proposedAction: step.proposedAction,
          commandMatch: resolved.commandMatch,
        }
      : null;
  }

  if (step.turnOwner === 'notes' && step.proposedAction === 'read-notes') {
    const resolved = resolvePromotedNoteReadToolCommand(decision);
    return resolved
      ? {
          stepId: step.stepId,
          turnOwner: step.turnOwner,
          proposedAction: step.proposedAction,
          commandMatch: resolved.commandMatch,
        }
      : null;
  }

  if (step.turnOwner === 'calendar' && step.proposedAction === 'read-calendar') {
    const resolved = resolvePromotedCalendarReadToolCommand(decision);
    return resolved
      ? {
          stepId: step.stepId,
          turnOwner: step.turnOwner,
          proposedAction: step.proposedAction,
          commandMatch: resolved.commandMatch,
        }
      : null;
  }

  return null;
}

/**
 * Phase 21G2A deliberately preflights the whole plan before any step can run.
 *
 * Only dependency-free atomic steps whose existing single-intent validators
 * produce a CommandMatch are eligible. This prevents a plan from partially
 * mutating state before discovering that a later step requires confirmation or
 * untyped result binding.
 */
export function preflightCompositeImmediatePlan(
  plan: AgentCompositePlanResponse | null,
): CompositeImmediatePreflight {
  if (!plan?.plan.isComposite) {
    return {
      ok: false,
      planId: plan?.planId ?? null,
      reason: 'not-composite',
      stepId: null,
      detail: 'The observed turn did not contain a validated composite plan.',
    };
  }

  const candidates: CompositeImmediateStepCandidate[] = [];

  for (const step of plan.plan.steps) {
    if (step.dependsOn.length > 0) {
      return {
        ok: false,
        planId: plan.planId,
        reason: 'dependency-not-yet-promoted',
        stepId: step.stepId,
        detail:
          'Phase 21G2A does not execute dependent steps because verified result binding is not typed yet.',
      };
    }

    if (CONFIRMATION_PAUSE_ACTIONS.has(step.proposedAction)) {
      return {
        ok: false,
        planId: plan.planId,
        reason: 'confirmation-pause-required',
        stepId: step.stepId,
        detail:
          'This atomic action must preserve its existing user-confirmation pause before execution.',
      };
    }

    const candidate = resolveImmediateCandidate(plan, step);
    if (!candidate) {
      const potentiallySupportedOwner = new Set([
        'search',
        'tasks',
        'notes',
        'calendar',
      ]).has(step.turnOwner);

      return {
        ok: false,
        planId: plan.planId,
        reason: potentiallySupportedOwner
          ? 'deterministic-validation-failed'
          : 'unsupported-owner-or-action',
        stepId: step.stepId,
        detail: potentiallySupportedOwner
          ? 'The atomic proposal did not pass its existing single-intent deterministic validator.'
          : 'This owner/action is not in the Phase 21G2A immediate execution allowlist.',
      };
    }

    candidates.push(candidate);
  }

  return {
    ok: true,
    planId: plan.planId,
    candidates,
  };
}

/**
 * Coordination primitive for G2B.
 *
 * This function owns only ordering and stop behavior. The supplied executor must
 * run each CommandMatch through QMeet's existing canonical command path and
 * return a verified receipt. G2A itself never writes state.
 */
export async function executePreflightedCompositeImmediatePlan(options: {
  preflight: CompositeImmediatePreflight;
  executeStep: (
    candidate: CompositeImmediateStepCandidate,
  ) => Promise<CompositeImmediateStepReceipt>;
}): Promise<CompositeImmediateExecutionResult> {
  if (!options.preflight.ok) {
    return {
      ok: false,
      status: 'not-executed',
      planId: options.preflight.planId,
      receipts: [],
      failedStepId: options.preflight.stepId,
      reason: options.preflight.detail,
    };
  }

  const receipts: CompositeImmediateStepReceipt[] = [];

  for (const candidate of options.preflight.candidates) {
    let receipt: CompositeImmediateStepReceipt;
    try {
      receipt = await options.executeStep(candidate);
    } catch (error) {
      return {
        ok: false,
        status: 'failed',
        planId: options.preflight.planId,
        receipts,
        failedStepId: candidate.stepId,
        reason:
          error instanceof Error
            ? error.message
            : 'The composite atomic executor failed.',
      };
    }

    if (
      receipt.stepId !== candidate.stepId ||
      receipt.ok !== true ||
      !receipt.toolResult.trim()
    ) {
      return {
        ok: false,
        status: 'failed',
        planId: options.preflight.planId,
        receipts,
        failedStepId: candidate.stepId,
        reason:
          'An atomic step did not return one matching successful verified receipt.',
      };
    }

    receipts.push(receipt);
  }

  return {
    ok: true,
    status: 'completed',
    planId: options.preflight.planId,
    receipts,
    failedStepId: null,
    reason:
      'Every preflighted atomic step returned one successful verified receipt in plan order.',
  };
}
