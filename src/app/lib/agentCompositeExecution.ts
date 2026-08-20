import type { CommandMatch } from '../commands';
import type { PromotedSingleIntentDecision } from './agentShadowObserver';
import type {
  AgentCompositeInputBinding,
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

export type CompositeVerifiedBindings = {
  searchResultText?: string;
};

export type CompositeImmediateStepCandidate = {
  stepId: string;
  turnOwner: AgentCompositeStep['turnOwner'];
  focusRelevant: boolean;
  proposedCapability: string;
  proposedAction: string;
  proposedArguments: Record<string, unknown>;
  commandMatch: CommandMatch;
};

export type CompositePreflightStepCandidate = {
  stepId: string;
  turnOwner: AgentCompositeStep['turnOwner'];
  focusRelevant: boolean;
  proposedCapability: string;
  proposedAction: string;
  proposedArguments: Record<string, unknown>;
  inputBindings: AgentCompositeInputBinding[];
  commandMatch: CommandMatch | null;
};

export type CompositeImmediatePreflightFailureReason =
  | 'not-composite'
  | 'confidence-below-promotion-threshold'
  | 'dependency-not-yet-promoted'
  | 'unsupported-result-binding'
  | 'confirmation-pause-required'
  | 'unsupported-owner-or-action'
  | 'deterministic-validation-failed';

export type CompositeImmediatePreflight =
  | {
      ok: true;
      planId: string;
      confidence: number;
      candidates: CompositePreflightStepCandidate[];
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
  verifiedBindings?: CompositeVerifiedBindings;
};

export type CompositeImmediateExecutionResult = {
  ok: boolean;
  status: 'completed' | 'failed' | 'not-executed';
  planId: string | null;
  receipts: CompositeImmediateStepReceipt[];
  failedStepId: string | null;
  reason: string;
};

const COMPOSITE_IMMEDIATE_MIN_CONFIDENCE = 0.9;

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
  proposedArguments: Record<string, unknown> = step.proposedArguments,
): PromotedSingleIntentDecision {
  return {
    source: 'agent-shadow',
    turnOwner: step.turnOwner,
    focusRelevant: step.focusRelevant,
    disposition: 'tool',
    proposedCapability: step.proposedCapability,
    proposedAction: step.proposedAction,
    proposedArguments: { ...proposedArguments },
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
          focusRelevant: step.focusRelevant,
          proposedCapability: step.proposedCapability,
          proposedAction: step.proposedAction,
          proposedArguments: { ...step.proposedArguments },
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
          focusRelevant: step.focusRelevant,
          proposedCapability: step.proposedCapability,
          proposedAction: step.proposedAction,
          proposedArguments: { ...step.proposedArguments },
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
          focusRelevant: step.focusRelevant,
          proposedCapability: step.proposedCapability,
          proposedAction: step.proposedAction,
          proposedArguments: { ...step.proposedArguments },
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
          focusRelevant: step.focusRelevant,
          proposedCapability: step.proposedCapability,
          proposedAction: step.proposedAction,
          proposedArguments: { ...step.proposedArguments },
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
          focusRelevant: step.focusRelevant,
          proposedCapability: step.proposedCapability,
          proposedAction: step.proposedAction,
          proposedArguments: { ...step.proposedArguments },
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
          focusRelevant: step.focusRelevant,
          proposedCapability: step.proposedCapability,
          proposedAction: step.proposedAction,
          proposedArguments: { ...step.proposedArguments },
          commandMatch: resolved.commandMatch,
        }
      : null;
  }

  return null;
}

function isSupportedVerifiedResultBinding(
  step: AgentCompositeStep,
  binding: AgentCompositeInputBinding,
  priorSteps: Map<string, AgentCompositeStep>,
): boolean {
  if (step.turnOwner !== 'notes' || step.proposedAction !== 'save-note') {
    return false;
  }
  if (binding.targetArgument !== 'content') return false;
  if (binding.sourceField !== 'search.resultText') return false;
  if (Object.prototype.hasOwnProperty.call(step.proposedArguments, 'content')) {
    return false;
  }

  const sourceStep = priorSteps.get(binding.sourceStepId);
  return Boolean(
    sourceStep &&
      sourceStep.turnOwner === 'search' &&
      sourceStep.proposedCapability === 'search' &&
      sourceStep.proposedAction === 'run-search',
  );
}

function resolveBoundCandidate(
  candidate: CompositePreflightStepCandidate,
  receiptsByStepId: Map<string, CompositeImmediateStepReceipt>,
  confidence: number,
  planId: string,
): CompositeImmediateStepCandidate | null {
  if (candidate.inputBindings.length !== 1) return null;
  const binding = candidate.inputBindings[0];
  const sourceReceipt = receiptsByStepId.get(binding.sourceStepId);
  if (!sourceReceipt?.ok) return null;

  let boundValue = '';
  if (binding.sourceField === 'search.resultText') {
    boundValue = sourceReceipt.verifiedBindings?.searchResultText?.trim() ?? '';
  }
  if (!boundValue) return null;

  const boundArguments = {
    ...candidate.proposedArguments,
    [binding.targetArgument]: boundValue,
  };
  const decision: PromotedSingleIntentDecision = {
    source: 'agent-shadow',
    turnOwner: candidate.turnOwner,
    focusRelevant: candidate.focusRelevant,
    disposition: 'tool',
    proposedCapability: candidate.proposedCapability,
    proposedAction: candidate.proposedAction,
    proposedArguments: boundArguments,
    confidence,
    turnId: `${planId}:${candidate.stepId}:bound`,
  };

  if (
    candidate.turnOwner === 'notes' &&
    candidate.proposedAction === 'save-note'
  ) {
    const resolved = resolvePromotedNoteSaveToolCommand(decision);
    return resolved
      ? {
          stepId: candidate.stepId,
          turnOwner: candidate.turnOwner,
          focusRelevant: candidate.focusRelevant,
          proposedCapability: candidate.proposedCapability,
          proposedAction: candidate.proposedAction,
          proposedArguments: boundArguments,
          commandMatch: resolved.commandMatch,
        }
      : null;
  }

  return null;
}

/**
 * Phase 21G2C preflights the whole plan before any step can run.
 *
 * Immediate steps must pass their existing single-intent validators now.
 * A dependent step is allowed only for the one Phase 21G2C typed binding:
 * verified Search resultText -> Notes save-note content. The bound Notes
 * command is revalidated only after the source receipt exists.
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

  if (plan.plan.confidence < COMPOSITE_IMMEDIATE_MIN_CONFIDENCE) {
    return {
      ok: false,
      planId: plan.planId,
      reason: 'confidence-below-promotion-threshold',
      stepId: null,
      detail:
        'The composite plan did not meet the live promotion confidence threshold.',
    };
  }

  const candidates: CompositePreflightStepCandidate[] = [];
  const priorSteps = new Map<string, AgentCompositeStep>();

  for (const step of plan.plan.steps) {
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

    if (step.dependsOn.length > 0 || step.inputBindings.length > 0) {
      if (
        step.dependsOn.length !== 1 ||
        step.inputBindings.length !== 1 ||
        step.dependsOn[0] !== step.inputBindings[0].sourceStepId ||
        !isSupportedVerifiedResultBinding(
          step,
          step.inputBindings[0],
          priorSteps,
        )
      ) {
        return {
          ok: false,
          planId: plan.planId,
          reason: 'unsupported-result-binding',
          stepId: step.stepId,
          detail:
            'The dependent step did not use the promoted verified Search resultText to Notes content binding.',
        };
      }

      candidates.push({
        stepId: step.stepId,
        turnOwner: step.turnOwner,
        focusRelevant: step.focusRelevant,
        proposedCapability: step.proposedCapability,
        proposedAction: step.proposedAction,
        proposedArguments: { ...step.proposedArguments },
        inputBindings: [...step.inputBindings],
        commandMatch: null,
      });
      priorSteps.set(step.stepId, step);
      continue;
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
          : 'This owner/action is not in the Phase 21G2C execution allowlist.',
      };
    }

    candidates.push({
      ...candidate,
      inputBindings: [],
    });
    priorSteps.set(step.stepId, step);
  }

  return {
    ok: true,
    planId: plan.planId,
    confidence: plan.plan.confidence,
    candidates,
  };
}

/**
 * Coordination primitive for G2C.
 *
 * This function owns ordering, verified-result binding, and stop behavior. The
 * supplied executor still runs every resolved CommandMatch through QMeet's
 * existing canonical command path and returns a verified receipt.
 */
export async function executePreflightedCompositeImmediatePlan(options: {
  preflight: CompositeImmediatePreflight;
  executeStep: (
    candidate: CompositeImmediateStepCandidate,
  ) => Promise<CompositeImmediateStepReceipt>;
}): Promise<CompositeImmediateExecutionResult> {
  const preflight = options.preflight;
  if (preflight.ok === false) {
    return {
      ok: false,
      status: 'not-executed',
      planId: preflight.planId,
      receipts: [],
      failedStepId: preflight.stepId,
      reason: preflight.detail,
    };
  }

  const receipts: CompositeImmediateStepReceipt[] = [];
  const receiptsByStepId = new Map<string, CompositeImmediateStepReceipt>();

  for (const plannedCandidate of preflight.candidates) {
    const candidate = plannedCandidate.commandMatch
      ? {
          stepId: plannedCandidate.stepId,
          turnOwner: plannedCandidate.turnOwner,
          focusRelevant: plannedCandidate.focusRelevant,
          proposedCapability: plannedCandidate.proposedCapability,
          proposedAction: plannedCandidate.proposedAction,
          proposedArguments: { ...plannedCandidate.proposedArguments },
          commandMatch: plannedCandidate.commandMatch,
        }
      : resolveBoundCandidate(
          plannedCandidate,
          receiptsByStepId,
          preflight.confidence,
          preflight.planId,
        );

    if (!candidate) {
      return {
        ok: false,
        status: 'failed',
        planId: preflight.planId,
        receipts,
        failedStepId: plannedCandidate.stepId,
        reason:
          'A dependent composite step could not bind one required value from its verified source receipt.',
      };
    }

    let receipt: CompositeImmediateStepReceipt;
    try {
      receipt = await options.executeStep(candidate);
    } catch (error) {
      return {
        ok: false,
        status: 'failed',
        planId: preflight.planId,
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
        planId: preflight.planId,
        receipts,
        failedStepId: candidate.stepId,
        reason:
          'An atomic step did not return one matching successful verified receipt.',
      };
    }

    receipts.push(receipt);
    receiptsByStepId.set(receipt.stepId, receipt);
  }

  return {
    ok: true,
    status: 'completed',
    planId: preflight.planId,
    receipts,
    failedStepId: null,
    reason:
      'Every atomic step returned one successful verified receipt in plan order, including any downstream step bound only from an earlier verified receipt.',
  };
}
