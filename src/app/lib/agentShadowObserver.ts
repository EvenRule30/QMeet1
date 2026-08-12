import { QMEET_API_BASE_URL } from '../api';
import type { ActivePanel, Message } from '../types';


type ShadowConversationMessage = {
  role: 'user' | 'assistant' | 'tool';
  content: string;
};

type PendingCommandContext = {
  originalText: string;
  action: string;
  frontendCommand: string;
} | null;

type ActiveFocusProjectionContext = {
  id: string;
  title: string;
  goal: string;
  mode: string;
} | null;

export type AgentShadowObserverOptions = {
  userMessage: string;
  recentMessages: Message[];
  activePanel: ActivePanel;
  chatActive: boolean;
  calendarView: string;
  googleCalendarConnected: boolean;
  googleCalendarWriteEnabled: boolean;
  pendingCommand: PendingCommandContext;
  frontendFocusProjection: ActiveFocusProjectionContext;
};

export type LegacyShadowRouteObservation = {
  route: string;
  owner?: 'general_chat' | 'calendar' | 'search' | 'memory' | 'tasks' | 'notes' | 'focus' | 'device_ui' | 'visual' | 'other';
  action?: string;
  frontendCommand?: string;
  disposition?: 'conversation' | 'tool' | 'clarify';
  sequence?: number;
};

export type AgentShadowDecision = {
  turnOwner: string;
  focusRelevant: boolean;
  disposition: 'conversation' | 'tool' | 'clarify';
  proposedCapability: string;
  proposedAction: string;
  proposedArguments: Record<string, unknown>;
  responsePlan: string;
  confidence: number;
  reason: string;
};

export type AgentShadowResponse = {
  ok: boolean;
  mode: 'shadow';
  schemaVersion: string;
  turnId: string;
  decision: AgentShadowDecision;
};




export type PromotedConversationOwnershipHint = {
  source: 'agent-shadow';
  turnOwner: 'general_chat' | 'focus';
  focusRelevant: boolean;
  confidence: number;
  turnId: string;
};

const CONVERSATION_OWNERSHIP_MIN_CONFIDENCE = 0.9;
const CONVERSATION_OWNERSHIP_WAIT_MS = 900;

function waitForTimeout(milliseconds: number): Promise<null> {
  return new Promise((resolve) => {
    globalThis.setTimeout(() => resolve(null), milliseconds);
  });
}

export async function resolvePromotedConversationOwnership(options: {
  shadowTurn: Promise<AgentShadowResponse | null> | null;
  activeFocusId: string | null;
  timeoutMs?: number;
}): Promise<PromotedConversationOwnershipHint | null> {
  if (!options.shadowTurn) return null;

  const timeoutMs = Math.max(0, options.timeoutMs ?? CONVERSATION_OWNERSHIP_WAIT_MS);

  try {
    const shadow = await Promise.race([
      options.shadowTurn,
      waitForTimeout(timeoutMs),
    ]);
    if (!shadow?.decision) return null;

    const decision = shadow.decision;
    if (decision.disposition !== 'conversation') return null;
    if (decision.confidence < CONVERSATION_OWNERSHIP_MIN_CONFIDENCE) return null;

    if (decision.turnOwner === 'general_chat' && decision.focusRelevant === false) {
      return {
        source: 'agent-shadow',
        turnOwner: 'general_chat',
        focusRelevant: false,
        confidence: decision.confidence,
        turnId: shadow.turnId,
      };
    }

    if (
      decision.turnOwner === 'focus' &&
      decision.focusRelevant === true &&
      Boolean(options.activeFocusId)
    ) {
      return {
        source: 'agent-shadow',
        turnOwner: 'focus',
        focusRelevant: true,
        confidence: decision.confidence,
        turnId: shadow.turnId,
      };
    }

    return null;
  } catch (error) {
    console.warn(
      'Agent shadow conversation ownership was unavailable. Conversation heuristics remain authoritative.',
      error,
    );
    return null;
  }
}

export type ExplicitDeterministicRouteBeforeAgent = {
  kind: 'exact-command' | 'focus-mutation';
  reason: string;
};

const EXPLICIT_COMMAND_LEAD = /^(?:please\s+)?(?:open|show|display|bring\s+up|pull\s+up|close|hide|go|return|take|read|list|search|look\s+up|find|add|create|schedule|delete|remove|erase|edit|change|update|mark|complete|save|clear|start|begin|resume|restart|end|stop|finish|rename|retitle|set|turn|enable|disable|mute|unmute|increase|decrease|summarize|recap|prepare|wrap|link)\b/i;
const EXPLICIT_FOCUS_FIELD_ASSIGNMENT = /^(?:please\s+)?(?:(?:focus\s+)?(?:goal|objective|mode|title))\s*[:=]\s*\S/i;
const EXPLICIT_FOCUS_LIFECYCLE_COMMANDS = new Set([
  'start-focus-session',
  'update-focus-session',
  'resume-last-focus-session',
  'end-focus-session',
  'end-focus-with-summary',
]);

/**
 * Phase 21B agent-first routing inspects an exact local parse before asking the
 * model to own the turn, but parsing alone is not authority to execute it.
 * Bare aliases such as "health", "menu", or "status" remain contextual and
 * may be overridden by the agent. Explicit command syntax such as
 * "show status", "open menu", or "rename the focus ..." keeps the existing
 * deterministic route authoritative.
 */
export function resolveExplicitDeterministicRouteBeforeAgent(options: {
  userMessage: string;
  parsedCommand: string | null;
}): ExplicitDeterministicRouteBeforeAgent | null {
  const text = options.userMessage.trim();
  if (!text) return null;

  if (EXPLICIT_FOCUS_FIELD_ASSIGNMENT.test(text)) {
    return {
      kind: 'focus-mutation',
      reason: 'The user used an explicit Focus field assignment before agent-first ownership.',
    };
  }

  if (!options.parsedCommand || !EXPLICIT_COMMAND_LEAD.test(text)) {
    return null;
  }

  if (EXPLICIT_FOCUS_LIFECYCLE_COMMANDS.has(options.parsedCommand)) {
    return {
      kind: 'focus-mutation',
      reason: 'The user used explicit Focus lifecycle/update command syntax.',
    };
  }

  return {
    kind: 'exact-command',
    reason: 'The user used explicit deterministic command syntax.',
  };
}

export type PromotedSingleIntentDecision = {
  source: 'agent-shadow';
  turnOwner:
    | 'general_chat'
    | 'calendar'
    | 'search'
    | 'memory'
    | 'tasks'
    | 'notes'
    | 'focus'
    | 'device_ui'
    | 'visual';
  focusRelevant: boolean;
  disposition: 'conversation' | 'tool';
  proposedCapability: string;
  proposedAction: string;
  confidence: number;
  turnId: string;
};

const AGENT_FIRST_SINGLE_INTENT_MIN_CONFIDENCE = 0.9;
const AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 2500;
const PROMOTABLE_TOOL_OWNERS = new Set<PromotedSingleIntentDecision['turnOwner']>([
  'calendar',
  'search',
  'memory',
  'tasks',
  'notes',
  'focus',
  'device_ui',
  'visual',
]);

export async function resolvePromotedSingleIntentDecision(options: {
  shadowTurn: Promise<AgentShadowResponse | null> | null;
  activeFocusId: string | null;
  timeoutMs?: number;
}): Promise<PromotedSingleIntentDecision | null> {
  if (!options.shadowTurn) return null;

  const timeoutMs = Math.max(
    0,
    options.timeoutMs ?? AGENT_FIRST_SINGLE_INTENT_WAIT_MS,
  );

  try {
    const shadow = await Promise.race([
      options.shadowTurn,
      waitForTimeout(timeoutMs),
    ]);
    if (!shadow?.decision) return null;

    const decision = shadow.decision;
    if (decision.confidence < AGENT_FIRST_SINGLE_INTENT_MIN_CONFIDENCE) {
      return null;
    }
    if (decision.disposition === 'clarify') return null;

    if (decision.disposition === 'conversation') {
      if (
        decision.turnOwner === 'general_chat' &&
        decision.focusRelevant === false
      ) {
        return {
          source: 'agent-shadow',
          turnOwner: 'general_chat',
          focusRelevant: false,
          disposition: 'conversation',
          proposedCapability: decision.proposedCapability,
          proposedAction: decision.proposedAction,
          confidence: decision.confidence,
          turnId: shadow.turnId,
        };
      }

      if (
        decision.turnOwner === 'focus' &&
        decision.focusRelevant === true &&
        Boolean(options.activeFocusId)
      ) {
        return {
          source: 'agent-shadow',
          turnOwner: 'focus',
          focusRelevant: true,
          disposition: 'conversation',
          proposedCapability: decision.proposedCapability,
          proposedAction: decision.proposedAction,
          confidence: decision.confidence,
          turnId: shadow.turnId,
        };
      }

      return null;
    }

    if (decision.disposition !== 'tool') return null;
    if (!PROMOTABLE_TOOL_OWNERS.has(decision.turnOwner as PromotedSingleIntentDecision['turnOwner'])) {
      return null;
    }
    if (!decision.proposedAction || decision.proposedAction === 'none') {
      return null;
    }
    if (decision.turnOwner === 'focus' && decision.focusRelevant !== true) {
      return null;
    }

    return {
      source: 'agent-shadow',
      turnOwner: decision.turnOwner as PromotedSingleIntentDecision['turnOwner'],
      focusRelevant: decision.focusRelevant,
      disposition: 'tool',
      proposedCapability: decision.proposedCapability,
      proposedAction: decision.proposedAction,
      confidence: decision.confidence,
      turnId: shadow.turnId,
    };
  } catch (error) {
    console.warn(
      'Agent-first single-intent ownership was unavailable. Existing deterministic routing remains authoritative.',
      error,
    );
    return null;
  }
}

export type AgentShadowFocusMutationGuardResult = {
  guarded: boolean;
  shadow: AgentShadowResponse | null;
  reason: string;
};

function normalizeLifecycleText(message: string): string {
  return message
    .trim()
    .toLowerCase()
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/\s+/g, ' ');
}

function hasExplicitFocusStartIntent(message: string): boolean {
  const text = normalizeLifecycleText(message);
  if (!text) return false;

  return /^(?:please\s+)?(?:start|begin|create|open)\s+(?:(?:a|the|my|our|new)\s+)*(?:focus(?:\s+session)?|session)(?:\b|:)/.test(text);
}

function hasExplicitFocusTitleUpdateIntent(message: string): boolean {
  const text = normalizeLifecycleText(message);
  if (!text) return false;

  return (
    /^(?:please\s+)?(?:rename|retitle)\s+(?:(?:the|my|our|current|active)\s+)*(?:focus(?:\s+session)?|session)(?:\s+title)?\b/.test(text) ||
    /^(?:please\s+)?(?:set|change|update|switch)\s+(?:(?:the|my|our|current|active)\s+)*(?:focus(?:\s+session)?|session)(?:\s+title)?\s+(?:to|as|on|about|around)\b/.test(text)
  );
}

export function shouldGuardInferredActiveFocusReplacement(options: {
  userMessage: string;
  semanticKind: string;
  mutationChangesTitle: boolean;
  activeFocusId: string | null;
}): AgentShadowFocusMutationGuardResult {
  const guardableReplacement =
    options.semanticKind === 'start' ||
    (options.semanticKind === 'update' && options.mutationChangesTitle);

  if (!guardableReplacement) {
    return {
      guarded: false,
      shadow: null,
      reason:
        'Goal, mode, objective, and typed Focus-context updates remain eligible for verified canonical execution.',
    };
  }

  if (!options.activeFocusId) {
    return {
      guarded: false,
      shadow: null,
      reason: 'There is no active Focus to protect from inferred replacement.',
    };
  }

  const explicitMutation =
    options.semanticKind === 'start'
      ? hasExplicitFocusStartIntent(options.userMessage)
      : hasExplicitFocusTitleUpdateIntent(options.userMessage);

  if (explicitMutation) {
    return {
      guarded: false,
      shadow: null,
      reason:
        'The user used explicit Focus lifecycle/title mutation language, so the verified canonical executor remains authoritative.',
    };
  }

  return {
    guarded: true,
    shadow: null,
    reason:
      'An active Focus cannot be started over or retitled from inferred content language alone. Explicit Focus mutation intent is required.',
  };
}

// Compatibility export for the first guarded-veto slice. The live safety
// decision is now deterministic and does not wait for or trust a shadow-model
// response. Shadow remains observational for comparison and future promotion.
export async function shouldGuardInferredSemanticFocusMutationWithShadow(options: {
  shadowTurn: Promise<AgentShadowResponse | null> | null;
  userMessage: string;
  semanticKind: string;
  mutationChangesTitle: boolean;
  activeFocusId: string | null;
  observedFocusId?: string | null;
  exactLifecycleClaimed?: boolean;
}): Promise<AgentShadowFocusMutationGuardResult> {
  return shouldGuardInferredActiveFocusReplacement({
    userMessage: options.userMessage,
    semanticKind: options.semanticKind,
    mutationChangesTitle: options.mutationChangesTitle,
    activeFocusId: options.activeFocusId,
  });
}

function buildRecentConversation(messages: Message[]): ShadowConversationMessage[] {
  return messages
    .slice(-12)
    .map((message): ShadowConversationMessage | null => {
      const content = message.content.trim();
      if (!content) return null;

      if (message.role === 'assistant' && message.variant === 'tool') {
        return { role: 'tool', content };
      }

      return {
        role: message.role,
        content,
      };
    })
    .filter(
      (message): message is ShadowConversationMessage => message !== null,
    );
}

export async function observeAgentShadowTurn(
  options: AgentShadowObserverOptions,
): Promise<AgentShadowResponse | null> {
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
      observationPoint: 'frontend-pre-route',
      calendarView: options.calendarView,
      googleCalendarConnected: options.googleCalendarConnected,
      googleCalendarWriteEnabled: options.googleCalendarWriteEnabled,
      pendingCommand: options.pendingCommand,
      frontendFocusProjection: options.frontendFocusProjection,
    },
  };

  try {
    const response = await fetch(`${QMEET_API_BASE_URL}/api/agent/shadow/decide`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      console.warn(
        `Agent shadow observation failed with HTTP ${response.status}. Existing routing remains authoritative.`,
      );
      return null;
    }

    const payload = (await response.json()) as AgentShadowResponse;
    if (!payload?.ok || payload.mode !== 'shadow' || !payload.turnId) {
      console.warn(
        'Agent shadow observation returned an unexpected payload. Existing routing remains authoritative.',
      );
      return null;
    }

    console.debug('[QMeet agent shadow]', {
      turnId: payload.turnId,
      owner: payload.decision?.turnOwner,
      focusRelevant: payload.decision?.focusRelevant,
      disposition: payload.decision?.disposition,
      proposedAction: payload.decision?.proposedAction,
      confidence: payload.decision?.confidence,
    });
    return payload;
  } catch (error) {
    console.warn(
      'Agent shadow observation was unavailable. Existing routing remains authoritative.',
      error,
    );
    return null;
  }
}

export async function reportAgentShadowLegacyRoute(
  shadowTurn: Promise<AgentShadowResponse | null> | null,
  observation: LegacyShadowRouteObservation,
): Promise<void> {
  if (!shadowTurn) return;

  const route = observation.route.trim();
  if (!route) return;

  try {
    const shadow = await shadowTurn;
    if (!shadow?.turnId) return;

    const response = await fetch(`${QMEET_API_BASE_URL}/api/agent/shadow/compare`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        turnId: shadow.turnId,
        legacyObservation: {
          route,
          owner: observation.owner,
          action: observation.action?.trim() ?? '',
          frontendCommand: observation.frontendCommand?.trim() ?? '',
          disposition: observation.disposition,
          sequence: observation.sequence ?? 0,
        },
      }),
    });

    if (!response.ok) {
      console.warn(
        `Agent shadow comparison failed with HTTP ${response.status}. Existing routing remains authoritative.`,
      );
      return;
    }

    const payload = (await response.json()) as {
      ok?: boolean;
      foundDecision?: boolean;
      comparison?: {
        disagreementSummary?: string;
      };
    };

    if (!payload?.ok || payload.foundDecision === false) return;

    if (payload.comparison?.disagreementSummary) {
      console.debug('[QMeet agent shadow disagreement]', {
        turnId: shadow.turnId,
        route,
        summary: payload.comparison.disagreementSummary,
      });
    }
  } catch (error) {
    console.warn(
      'Agent shadow comparison was unavailable. Existing routing remains authoritative.',
      error,
    );
  }
}
