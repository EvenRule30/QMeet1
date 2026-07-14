import type { Dispatch, SetStateAction } from 'react';
import type { OrbState } from '../types';
import type { CommandMatch } from '../commands';

export type VoiceCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
  confirmationSpeechRate?: number;
};

export function handleVoiceCommand(
  commandMatch: CommandMatch,
  deps: {
    voiceOutputEnabled: boolean;
    speechRate: number;
    previousLastHeardTranscript: string;
    previousLastNormalizedTranscript: string;
    previousLastLocalCommand: string;
    setVoiceOutput: (enabled: boolean) => void;
    adjustSpeechRate: (nextRate: number) => number;
    stopCurrentSpeech: () => void;
    cancelActiveResponse: () => void;
    finishListening: () => void;
    setShowThinkingBubble: Dispatch<SetStateAction<boolean>>;
    setOrbState: Dispatch<SetStateAction<OrbState>>;
  },
): VoiceCommandResult {
  switch (commandMatch.command) {
    case 'voice-output-on':
      deps.setVoiceOutput(true);
      return { handled: true, shouldSpeakConfirmation: true };

    case 'voice-output-off':
      deps.setVoiceOutput(false);
      return { handled: true, shouldSpeakConfirmation: false };

    case 'voice-output-toggle': {
      const nextEnabled = !deps.voiceOutputEnabled;
      deps.setVoiceOutput(nextEnabled);
      return {
        handled: true,
        confirmationContent: nextEnabled ? 'Voice output enabled.' : 'Voice output muted.',
        shouldSpeakConfirmation: nextEnabled,
      };
    }

    case 'voice-slower': {
      const confirmationSpeechRate = deps.adjustSpeechRate(deps.speechRate - 0.15);
      return {
        handled: true,
        confirmationContent: `Speaking slower. Voice speed is now ${confirmationSpeechRate.toFixed(2)}×.`,
        confirmationSpeechRate,
      };
    }

    case 'voice-faster': {
      const confirmationSpeechRate = deps.adjustSpeechRate(deps.speechRate + 0.15);
      return {
        handled: true,
        confirmationContent: `Speaking faster. Voice speed is now ${confirmationSpeechRate.toFixed(2)}×.`,
        confirmationSpeechRate,
      };
    }

    case 'voice-normal': {
      const confirmationSpeechRate = deps.adjustSpeechRate(1);
      return {
        handled: true,
        confirmationContent: 'Voice speed reset to normal.',
        confirmationSpeechRate,
      };
    }

    case 'stop-speaking':
      deps.stopCurrentSpeech();
      deps.setOrbState('idle');
      return { handled: true, shouldSpeakConfirmation: false };

    case 'cancel-action':
      deps.stopCurrentSpeech();
      deps.cancelActiveResponse();
      deps.finishListening();
      deps.setShowThinkingBubble(false);
      deps.setOrbState('idle');
      return {
        handled: true,
        confirmationContent: 'Cancelled.',
        shouldSpeakConfirmation: false,
      };

    case 'what-did-you-hear':
      return {
        handled: true,
        confirmationContent: deps.previousLastHeardTranscript
          ? `I last heard: "${deps.previousLastHeardTranscript}". Normalized as: "${deps.previousLastNormalizedTranscript || deps.previousLastHeardTranscript}". Last local command: ${deps.previousLastLocalCommand}.`
          : 'I have not heard a voice transcript yet.',
      };

    default:
      return { handled: false };
  }
}
