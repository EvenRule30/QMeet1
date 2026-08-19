import type { CommandMatch, LocalCommand } from '../commands';
import type { PromotedSingleIntentDecision } from './agentShadowObserver';

const PROMOTED_DEVICE_UI_MIN_CONFIDENCE = 0.9;

export const PROMOTED_DEVICE_UI_ACTIONS = [
  'open-menu',
  'close-menu',
  'open-settings',
  'close-settings',
  'go-home',
  'show-status',
  'close-status',
  'hide-status',
  'voice-output-on',
  'voice-output-off',
  'voice-output-toggle',
  'voice-slower',
  'voice-faster',
  'voice-normal',
  'stop-speaking',
  'what-did-you-hear',
  'close-generic',
] as const;

export type PromotedDeviceUiAction =
  (typeof PROMOTED_DEVICE_UI_ACTIONS)[number];

export type PromotedDeviceUiToolCommand = {
  action: PromotedDeviceUiAction;
  commandMatch: CommandMatch;
};

const PROMOTED_DEVICE_UI_ACTION_SET = new Set<string>(
  PROMOTED_DEVICE_UI_ACTIONS,
);

const PROMOTED_DEVICE_UI_CONFIRMATIONS: Record<
  PromotedDeviceUiAction,
  string
> = {
  'open-menu': 'Opening menu.',
  'close-menu': 'Closing menu.',
  'open-settings': 'Opening settings.',
  'close-settings': 'Closing settings.',
  'go-home': 'Going home.',
  'show-status': 'Showing status.',
  'close-status': 'Closing status.',
  'hide-status': 'Hiding status.',
  'voice-output-on': 'Voice output enabled.',
  'voice-output-off': 'Voice output muted.',
  'voice-output-toggle': 'Toggling voice output.',
  'voice-slower': 'Speaking slower.',
  'voice-faster': 'Speaking faster.',
  'voice-normal': 'Voice speed reset to normal.',
  'stop-speaking': 'Speech stopped.',
  'what-did-you-hear': 'Checking the last heard transcript.',
  'close-generic': 'Closed.',
};

function hasNoProposedArguments(
  proposedArguments: Record<string, unknown>,
): boolean {
  return Object.keys(proposedArguments).length === 0;
}

function isPromotedDeviceUiAction(
  action: string,
): action is PromotedDeviceUiAction {
  return PROMOTED_DEVICE_UI_ACTION_SET.has(action);
}

/**
 * True when the unified agent has explicitly claimed Device/UI tool ownership.
 *
 * This intentionally does not inspect focusRelevant. Active Focus is advisory
 * context for a Device/UI-owned turn and cannot veto a separate capability
 * owner. The stricter resolver below still validates action, arguments, and
 * confidence before anything can execute.
 */
export function isPromotedDeviceUiToolDecision(
  decision: PromotedSingleIntentDecision | null,
): boolean {
  return Boolean(
    decision &&
      decision.disposition === 'tool' &&
      decision.turnOwner === 'device_ui' &&
      decision.proposedCapability === 'device_ui',
  );
}

/**
 * Translate one validated unified-agent Device/UI proposal into the same
 * CommandMatch consumed by QMeet's existing deterministic frontend executor.
 *
 * The model never supplies a frontend command string or arbitrary arguments.
 * Only the reversible Phase 21E action allowlist is accepted. Session-wide or
 * destructive controls such as clear-chat, end-chat, and cancel-action remain
 * on their pre-existing guarded paths.
 */
export function resolvePromotedDeviceUiToolCommand(
  decision: PromotedSingleIntentDecision | null,
): PromotedDeviceUiToolCommand | null {
  if (!isPromotedDeviceUiToolDecision(decision) || !decision) {
    return null;
  }

  if (decision.confidence < PROMOTED_DEVICE_UI_MIN_CONFIDENCE) {
    return null;
  }

  if (!hasNoProposedArguments(decision.proposedArguments)) {
    return null;
  }

  if (!isPromotedDeviceUiAction(decision.proposedAction)) {
    return null;
  }

  const action = decision.proposedAction;
  return {
    action,
    commandMatch: {
      command: action as LocalCommand,
      confirmation: PROMOTED_DEVICE_UI_CONFIRMATIONS[action],
    },
  };
}
