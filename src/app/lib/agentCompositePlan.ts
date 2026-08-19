import { QMEET_API_BASE_URL } from '../api';
import type { ActivePanel, Message } from '../types';

export type AgentCompositeOwner =
  | 'calendar'
  | 'search'
  | 'memory'
  | 'tasks'
  | 'notes'
  | 'device_ui';

export type AgentCompositeStep = {
  stepId: string;
  turnOwner: AgentCompositeOwner;
  focusRelevant: boolean;
  disposition: 'tool';
  proposedCapability: string;
  proposedAction: string;
  proposedArguments: Record<string, unknown>;
  dependsOn: string[];
  reason: string;
};

export type AgentCompositePlan = {
  isComposite: boolean;
  steps: AgentCompositeStep[];
  executionPolicy: 'sequential-verified';
  confirmationPolicy: 'preserve-existing-capability-gates';
  failurePolicy: 'stop-before-dependent-step';
  responsePlan: string;
  confidence: number;
  reason: string;
};

export type AgentCompositePlanResponse = {
  ok: boolean;
  mode: 'shadow';
  schemaVersion: string;
  actionVocabularyVersion: string;
  planId: string;
  plan: AgentCompositePlan;
};

export type AgentCompositePlanObserverOptions = {
  userMessage: string;
  recentMessages: Message[];
  activePanel: ActivePanel;
  chatActive: boolean;
  calendarView: string;
  googleCalendarConnected: boolean;
  googleCalendarWriteEnabled: boolean;
  pendingCommand:
    | {
        originalText: string;
        action: string;
        frontendCommand: string;
      }
    | null;
  frontendFocusProjection:
    | {
        id: string;
        title: string;
        goal: string;
        mode: string;
      }
    | null;
};

const COMPOSITE_OWNERS = new Set<AgentCompositeOwner>([
  'calendar',
  'search',
  'memory',
  'tasks',
  'notes',
  'device_ui',
]);

const FORBIDDEN_IDENTITY_KEY =
  /(?:^|_)(?:id|eventid|event_id|taskid|task_id|focusid|focus_id)$/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function containsForbiddenIdentity(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some((item) => containsForbiddenIdentity(item));
  }
  if (!isRecord(value)) return false;

  return Object.entries(value).some(([key, child]) => {
    const normalizedKey = key.replace(/-/g, '_');
    return (
      FORBIDDEN_IDENTITY_KEY.test(normalizedKey) ||
      containsForbiddenIdentity(child)
    );
  });
}

function buildRecentConversation(
  messages: Message[],
): Array<{ role: 'user' | 'assistant' | 'tool'; content: string }> {
  return messages
    .slice(-12)
    .map((message) => {
      const content = message.content.trim();
      if (!content) return null;
      if (message.role === 'assistant' && message.variant === 'tool') {
        return { role: 'tool' as const, content };
      }
      return {
        role: message.role,
        content,
      };
    })
    .filter(
      (
        message,
      ): message is {
        role: 'user' | 'assistant' | 'tool';
        content: string;
      } => message !== null,
    );
}

function validateCompositeStep(
  value: unknown,
  index: number,
  earlierStepIds: Set<string>,
): AgentCompositeStep | null {
  if (!isRecord(value)) return null;

  const stepId = value.stepId;
  const owner = value.turnOwner;
  const focusRelevant = value.focusRelevant;
  const disposition = value.disposition;
  const proposedCapability = value.proposedCapability;
  const proposedAction = value.proposedAction;
  const proposedArguments = value.proposedArguments;
  const dependsOn = value.dependsOn;
  const reason = value.reason;

  if (typeof stepId !== 'string' || stepId !== `step-${index + 1}`) return null;
  if (
    typeof owner !== 'string' ||
    !COMPOSITE_OWNERS.has(owner as AgentCompositeOwner)
  ) {
    return null;
  }
  if (typeof focusRelevant !== 'boolean') return null;
  if (disposition !== 'tool') return null;
  if (
    typeof proposedCapability !== 'string' ||
    proposedCapability !== owner
  ) {
    return null;
  }
  if (typeof proposedAction !== 'string' || !proposedAction.trim()) return null;
  if (!isRecord(proposedArguments)) return null;
  if (containsForbiddenIdentity(proposedArguments)) return null;
  if (!Array.isArray(dependsOn)) return null;
  if (
    dependsOn.some(
      (dependency) =>
        typeof dependency !== 'string' || !earlierStepIds.has(dependency),
    )
  ) {
    return null;
  }
  if (typeof reason !== 'string') return null;

  return {
    stepId,
    turnOwner: owner as AgentCompositeOwner,
    focusRelevant,
    disposition: 'tool',
    proposedCapability,
    proposedAction,
    proposedArguments: { ...proposedArguments },
    dependsOn: [...dependsOn] as string[],
    reason,
  };
}

export function validateAgentCompositePlanResponse(
  value: unknown,
): AgentCompositePlanResponse | null {
  if (!isRecord(value)) return null;
  if (value.ok !== true || value.mode !== 'shadow') return null;
  if (typeof value.schemaVersion !== 'string' || !value.schemaVersion) {
    return null;
  }
  if (
    typeof value.actionVocabularyVersion !== 'string' ||
    !value.actionVocabularyVersion
  ) {
    return null;
  }
  if (typeof value.planId !== 'string' || !value.planId) return null;
  if (!isRecord(value.plan)) return null;

  const rawPlan = value.plan;
  if (typeof rawPlan.isComposite !== 'boolean') return null;
  if (!Array.isArray(rawPlan.steps)) return null;
  if (rawPlan.executionPolicy !== 'sequential-verified') return null;
  if (
    rawPlan.confirmationPolicy !== 'preserve-existing-capability-gates'
  ) {
    return null;
  }
  if (rawPlan.failurePolicy !== 'stop-before-dependent-step') return null;
  if (typeof rawPlan.responsePlan !== 'string') return null;
  if (
    typeof rawPlan.confidence !== 'number' ||
    !Number.isFinite(rawPlan.confidence) ||
    rawPlan.confidence < 0 ||
    rawPlan.confidence > 1
  ) {
    return null;
  }
  if (typeof rawPlan.reason !== 'string') return null;

  if (!rawPlan.isComposite) {
    if (rawPlan.steps.length !== 0) return null;
  } else if (rawPlan.steps.length < 2 || rawPlan.steps.length > 4) {
    return null;
  }

  const earlierStepIds = new Set<string>();
  const steps: AgentCompositeStep[] = [];
  for (let index = 0; index < rawPlan.steps.length; index += 1) {
    const step = validateCompositeStep(
      rawPlan.steps[index],
      index,
      earlierStepIds,
    );
    if (!step) return null;
    steps.push(step);
    earlierStepIds.add(step.stepId);
  }

  return {
    ok: true,
    mode: 'shadow',
    schemaVersion: value.schemaVersion,
    actionVocabularyVersion: value.actionVocabularyVersion,
    planId: value.planId,
    plan: {
      isComposite: rawPlan.isComposite,
      steps,
      executionPolicy: 'sequential-verified',
      confirmationPolicy: 'preserve-existing-capability-gates',
      failurePolicy: 'stop-before-dependent-step',
      responsePlan: rawPlan.responsePlan,
      confidence: rawPlan.confidence,
      reason: rawPlan.reason,
    },
  };
}

export async function observeAgentCompositePlan(
  options: AgentCompositePlanObserverOptions,
): Promise<AgentCompositePlanResponse | null> {
  const userMessage = options.userMessage.trim();
  if (!userMessage) return null;

  const requestBody = {
    userMessage,
    recentConversation: buildRecentConversation(options.recentMessages),
    uiState: {
      activePanel: options.activePanel,
      chatActive: options.chatActive,
    },
    clientContext: {
      observationPoint: 'frontend-pre-route-composite',
      calendarView: options.calendarView,
      googleCalendarConnected: options.googleCalendarConnected,
      googleCalendarWriteEnabled: options.googleCalendarWriteEnabled,
      pendingCommand: options.pendingCommand,
      frontendFocusProjection: options.frontendFocusProjection,
    },
  };

  try {
    const response = await fetch(
      `${QMEET_API_BASE_URL}/api/agent/shadow/plan`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      },
    );

    if (!response.ok) {
      console.warn(
        `Agent composite planning failed with HTTP ${response.status}. Single-intent routing remains authoritative.`,
      );
      return null;
    }

    const parsed = validateAgentCompositePlanResponse(await response.json());
    if (!parsed) {
      console.warn(
        'Agent composite planning returned an invalid payload. Single-intent routing remains authoritative.',
      );
      return null;
    }

    console.debug('[QMeet composite plan]', {
      planId: parsed.planId,
      isComposite: parsed.plan.isComposite,
      steps: parsed.plan.steps.map((step) => ({
        stepId: step.stepId,
        owner: step.turnOwner,
        action: step.proposedAction,
        dependsOn: step.dependsOn,
      })),
      confidence: parsed.plan.confidence,
    });

    return parsed;
  } catch (error) {
    console.warn(
      'Agent composite planning was unavailable. Single-intent routing remains authoritative.',
      error,
    );
    return null;
  }
}
