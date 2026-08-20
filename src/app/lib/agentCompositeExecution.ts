import type { CommandMatch } from '../commands';
import type { PromotedSingleIntentDecision } from './agentShadowObserver';
import type {
  AgentCompositeInputBinding,
  AgentCompositePlanResponse,
  AgentCompositeStep,
} from './agentCompositePlan';
import {
  resolvePromotedCalendarCreateToolCommand,
  resolvePromotedCalendarDeleteToolCommand,
  resolvePromotedCalendarEditToolCommand,
  resolvePromotedCalendarReadToolCommand,
  resolvePromotedNoteReadToolCommand,
  resolvePromotedNoteSaveToolCommand,
  resolvePromotedSearchToolCommand,
  resolvePromotedTaskCreateToolCommand,
  resolvePromotedTaskReadToolCommand,
  type PromotedCalendarEditTargetCriteria,
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

export type CompositeConfirmationMode = 'none' | 'required';

export type CompositeResumableStepCandidate =
  CompositePreflightStepCandidate & {
    confirmationMode: CompositeConfirmationMode;
    calendarEditTargetCriteria?: PromotedCalendarEditTargetCriteria;
  };

export type CompositeResumablePreflightFailureReason =
  | CompositeImmediatePreflightFailureReason
  | 'unsupported-confirmation-action'
  | 'confirmation-step-cannot-depend-on-result';

export type CompositeResumablePreflight =
  | {
      ok: true;
      planId: string;
      confidence: number;
      candidates: CompositeResumableStepCandidate[];
    }
  | {
      ok: false;
      planId: string | null;
      reason: CompositeResumablePreflightFailureReason;
      stepId: string | null;
      detail: string;
    };

export type CompositeConfirmationPause = {
  planId: string;
  pausedStepId: string;
  pausedStepIndex: number;
  expectedAction: string;
  receiptsBeforePause: CompositeImmediateStepReceipt[];
};

export type CompositeResumableExecutionResult = {
  ok: boolean;
  status: 'completed' | 'failed' | 'not-executed' | 'paused';
  planId: string | null;
  receipts: CompositeImmediateStepReceipt[];
  failedStepId: string | null;
  reason: string;
  pause?: CompositeConfirmationPause;
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

const G3A_RESUMABLE_CONFIRMATION_ACTIONS = new Set([
  'add-calendar-event',
  'edit-last-event',
  'delete-calendar-event',
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

function resolveResumableConfirmationCandidate(
  plan: AgentCompositePlanResponse,
  step: AgentCompositeStep,
): CompositeResumableStepCandidate | null {
  const decision = toPromotedAtomicDecision(plan, step);

  if (
    step.turnOwner === 'calendar' &&
    step.proposedAction === 'add-calendar-event'
  ) {
    const resolved = resolvePromotedCalendarCreateToolCommand(decision);
    return resolved
      ? {
          stepId: step.stepId,
          turnOwner: step.turnOwner,
          focusRelevant: step.focusRelevant,
          proposedCapability: step.proposedCapability,
          proposedAction: step.proposedAction,
          proposedArguments: { ...step.proposedArguments },
          inputBindings: [],
          commandMatch: resolved.commandMatch,
          confirmationMode: 'required',
        }
      : null;
  }

  if (
    step.turnOwner === 'calendar' &&
    step.proposedAction === 'delete-calendar-event'
  ) {
    const resolved = resolvePromotedCalendarDeleteToolCommand(decision);
    return resolved
      ? {
          stepId: step.stepId,
          turnOwner: step.turnOwner,
          focusRelevant: step.focusRelevant,
          proposedCapability: step.proposedCapability,
          proposedAction: step.proposedAction,
          proposedArguments: { ...step.proposedArguments },
          inputBindings: [],
          commandMatch: resolved.commandMatch,
          confirmationMode: 'required',
        }
      : null;
  }

  if (
    step.turnOwner === 'calendar' &&
    step.proposedAction === 'edit-last-event'
  ) {
    const resolved = resolvePromotedCalendarEditToolCommand(decision);
    return resolved
      ? {
          stepId: step.stepId,
          turnOwner: step.turnOwner,
          focusRelevant: step.focusRelevant,
          proposedCapability: step.proposedCapability,
          proposedAction: step.proposedAction,
          proposedArguments: { ...step.proposedArguments },
          inputBindings: [],
          commandMatch: resolved.commandMatch,
          confirmationMode: 'required',
          calendarEditTargetCriteria: resolved.target,
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

/**
 * Phase 21G3A additive preflight for resumable composites.
 *
 * This does NOT replace preflightCompositeImmediatePlan(), so Phase 21G2C live
 * behavior remains unchanged until App explicitly promotes the resumable path.
 *
 * G3A promotes only Calendar create, targeted edit, and targeted delete as
 * confirmation-pausing candidates. Existing Calendar validators still build the
 * command proposal; App remains responsible for canonical target resolution,
 * identity locking, user confirmation, and mutation execution.
 */
export function preflightCompositeResumablePlan(
  plan: AgentCompositePlanResponse | null,
): CompositeResumablePreflight {
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
        'The composite plan did not meet the resumable promotion confidence threshold.',
    };
  }

  const candidates: CompositeResumableStepCandidate[] = [];
  const priorSteps = new Map<string, AgentCompositeStep>();

  for (const step of plan.plan.steps) {
    if (G3A_RESUMABLE_CONFIRMATION_ACTIONS.has(step.proposedAction)) {
      if (step.dependsOn.length > 0 || step.inputBindings.length > 0) {
        return {
          ok: false,
          planId: plan.planId,
          reason: 'confirmation-step-cannot-depend-on-result',
          stepId: step.stepId,
          detail:
            'Phase 21G3A does not pause on a Calendar mutation whose executable arguments still depend on an earlier verified result.',
        };
      }

      const confirmationCandidate =
        resolveResumableConfirmationCandidate(plan, step);
      if (!confirmationCandidate) {
        return {
          ok: false,
          planId: plan.planId,
          reason: 'deterministic-validation-failed',
          stepId: step.stepId,
          detail:
            'The Calendar mutation did not pass its existing single-intent deterministic validator.',
        };
      }

      candidates.push(confirmationCandidate);
      priorSteps.set(step.stepId, step);
      continue;
    }

    if (CONFIRMATION_PAUSE_ACTIONS.has(step.proposedAction)) {
      return {
        ok: false,
        planId: plan.planId,
        reason: 'unsupported-confirmation-action',
        stepId: step.stepId,
        detail:
          'This confirmation-pausing action is not in the Phase 21G3A resumable allowlist.',
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
        confirmationMode: 'none',
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
          : 'This owner/action is not in the Phase 21G3A resumable execution allowlist.',
      };
    }

    candidates.push({
      ...candidate,
      inputBindings: [],
      confirmationMode: 'none',
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

async function executeResumableCandidates(options: {
  preflight: Extract<CompositeResumablePreflight, { ok: true }>;
  startIndex: number;
  initialReceipts: CompositeImmediateStepReceipt[];
  executeStep: (
    candidate: CompositeImmediateStepCandidate,
  ) => Promise<CompositeImmediateStepReceipt>;
}): Promise<CompositeResumableExecutionResult> {
  const receipts = [...options.initialReceipts];
  const receiptsByStepId = new Map<string, CompositeImmediateStepReceipt>(
    receipts.map((receipt) => [receipt.stepId, receipt]),
  );

  for (
    let index = options.startIndex;
    index < options.preflight.candidates.length;
    index += 1
  ) {
    const plannedCandidate = options.preflight.candidates[index];

    if (plannedCandidate.confirmationMode === 'required') {
      if (!plannedCandidate.commandMatch) {
        return {
          ok: false,
          status: 'failed',
          planId: options.preflight.planId,
          receipts,
          failedStepId: plannedCandidate.stepId,
          reason:
            'A confirmation-pausing composite step lost its validated CommandMatch before the pause.',
        };
      }

      return {
        ok: false,
        status: 'paused',
        planId: options.preflight.planId,
        receipts,
        failedStepId: null,
        reason:
          'Composite execution paused before a Calendar mutation that requires the existing user-confirmation gate.',
        pause: {
          planId: options.preflight.planId,
          pausedStepId: plannedCandidate.stepId,
          pausedStepIndex: index,
          expectedAction: plannedCandidate.proposedAction,
          receiptsBeforePause: [...receipts],
        },
      };
    }

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
          options.preflight.confidence,
          options.preflight.planId,
        );

    if (!candidate) {
      return {
        ok: false,
        status: 'failed',
        planId: options.preflight.planId,
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
        planId: options.preflight.planId,
        receipts,
        failedStepId: candidate.stepId,
        reason:
          error instanceof Error
            ? error.message
            : 'The resumable composite atomic executor failed.',
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
    receiptsByStepId.set(receipt.stepId, receipt);
  }

  return {
    ok: true,
    status: 'completed',
    planId: options.preflight.planId,
    receipts,
    failedStepId: null,
    reason:
      'Every resumable composite step returned one successful verified receipt in plan order.',
  };
}

export async function executePreflightedCompositeResumablePlan(options: {
  preflight: CompositeResumablePreflight;
  executeStep: (
    candidate: CompositeImmediateStepCandidate,
  ) => Promise<CompositeImmediateStepReceipt>;
}): Promise<CompositeResumableExecutionResult> {
  if (options.preflight.ok === false) {
    return {
      ok: false,
      status: 'not-executed',
      planId: options.preflight.planId,
      receipts: [],
      failedStepId: options.preflight.stepId,
      reason: options.preflight.detail,
    };
  }

  return executeResumableCandidates({
    preflight: options.preflight,
    startIndex: 0,
    initialReceipts: [],
    executeStep: options.executeStep,
  });
}

/**
 * Resume only after App's existing confirmation/canonical executor has produced
 * one verified receipt for the exact paused step. G3A never fabricates that
 * receipt and never owns Calendar target identity.
 */
export async function resumePreflightedCompositeAfterConfirmation(options: {
  preflight: CompositeResumablePreflight;
  pause: CompositeConfirmationPause;
  confirmedReceipt: CompositeImmediateStepReceipt;
  executeStep: (
    candidate: CompositeImmediateStepCandidate,
  ) => Promise<CompositeImmediateStepReceipt>;
}): Promise<CompositeResumableExecutionResult> {
  if (options.preflight.ok === false) {
    return {
      ok: false,
      status: 'not-executed',
      planId: options.preflight.planId,
      receipts: [],
      failedStepId: options.preflight.stepId,
      reason: options.preflight.detail,
    };
  }

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
    return {
      ok: false,
      status: 'failed',
      planId: options.preflight.planId,
      receipts: [...pause.receiptsBeforePause],
      failedStepId: pause.pausedStepId,
      reason:
        'The pending composite confirmation checkpoint no longer matches the preflighted paused step.',
    };
  }

  const confirmedReceipt = options.confirmedReceipt;
  if (
    confirmedReceipt.stepId !== pause.pausedStepId ||
    confirmedReceipt.ok !== true ||
    !confirmedReceipt.toolResult.trim()
  ) {
    return {
      ok: false,
      status: 'failed',
      planId: options.preflight.planId,
      receipts: [...pause.receiptsBeforePause],
      failedStepId: pause.pausedStepId,
      reason:
        'The confirmed mutation did not produce one successful verified receipt for the exact paused composite step.',
    };
  }

  return executeResumableCandidates({
    preflight: options.preflight,
    startIndex: pause.pausedStepIndex + 1,
    initialReceipts: [
      ...pause.receiptsBeforePause,
      confirmedReceipt,
    ],
    executeStep: options.executeStep,
  });
}

