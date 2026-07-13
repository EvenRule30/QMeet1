import { Dispatch, SetStateAction, useCallback, useEffect, useRef, useState } from 'react';
import { OrbState } from '../types';
import { speakText, stopSpeaking } from '../speechSynthesis';

const VOICE_OUTPUT_STORAGE_KEY = 'qmeet-voice-output-enabled';
const SPEECH_RATE_STORAGE_KEY = 'qmeet-speech-rate';

function clampSpeechRate(rate: number): number {
  return Math.min(1.35, Math.max(0.75, rate));
}

function readStoredVoiceOutputEnabled(): boolean {
  if (typeof window === 'undefined') return true;

  try {
    const storedValue = window.localStorage.getItem(VOICE_OUTPUT_STORAGE_KEY);

    if (storedValue === 'false') return false;
    if (storedValue === 'true') return true;

    return true;
  } catch {
    return true;
  }
}

function readStoredSpeechRate(): number {
  if (typeof window === 'undefined') return 1;

  try {
    const storedValue = window.localStorage.getItem(SPEECH_RATE_STORAGE_KEY);
    if (!storedValue) return 1;

    const parsedRate = Number(storedValue);
    return Number.isFinite(parsedRate) ? clampSpeechRate(parsedRate) : 1;
  } catch {
    return 1;
  }
}

type UseSpeechOutputOptions = {
  setOrbState: Dispatch<SetStateAction<OrbState>>;
};

export function useSpeechOutput({ setOrbState }: UseSpeechOutputOptions) {
  const [voiceOutputEnabled, setVoiceOutputEnabled] = useState(readStoredVoiceOutputEnabled);
  const [speechRate, setSpeechRate] = useState(readStoredSpeechRate);
  const speechTokenRef = useRef(0);

  const stopCurrentSpeech = useCallback(() => {
    speechTokenRef.current += 1;
    stopSpeaking();
  }, []);

  const speakAssistantText = useCallback((text: string, options: { enabled?: boolean; rate?: number } = {}) => {
    const trimmed = text.trim();
    const shouldSpeak = options.enabled ?? voiceOutputEnabled;
    const rate = options.rate ?? speechRate;

    if (!trimmed || !shouldSpeak) {
      setOrbState('idle');
      return;
    }

    const speechToken = speechTokenRef.current + 1;
    speechTokenRef.current = speechToken;

    const didStart = speakText(trimmed, {
      rate,
      onStart: () => {
        if (speechTokenRef.current === speechToken) {
          setOrbState('speaking');
        }
      },
      onEnd: () => {
        if (speechTokenRef.current === speechToken) {
          setOrbState('idle');
        }
      },
      onError: () => {
        if (speechTokenRef.current === speechToken) {
          setOrbState('idle');
        }
      },
    });

    if (!didStart) {
      setOrbState('idle');
    }
  }, [setOrbState, speechRate, voiceOutputEnabled]);

  const setVoiceOutput = useCallback((enabled: boolean) => {
    if (!enabled) {
      stopCurrentSpeech();
    }
    setVoiceOutputEnabled(enabled);
  }, [stopCurrentSpeech]);

  const adjustSpeechRate = useCallback((nextRate: number) => {
    const clampedRate = clampSpeechRate(nextRate);
    setSpeechRate(clampedRate);
    return clampedRate;
  }, []);

  useEffect(() => {
    return () => {
      stopSpeaking();
    };
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(VOICE_OUTPUT_STORAGE_KEY, String(voiceOutputEnabled));
    } catch (error) {
      console.error('Failed to save voice output setting:', error);
    }
  }, [voiceOutputEnabled]);

  useEffect(() => {
    try {
      window.localStorage.setItem(SPEECH_RATE_STORAGE_KEY, String(speechRate));
    } catch (error) {
      console.error('Failed to save speech rate setting:', error);
    }
  }, [speechRate]);

  return {
    voiceOutputEnabled,
    speechRate,
    stopCurrentSpeech,
    speakAssistantText,
    setVoiceOutput,
    adjustSpeechRate,
  };
}
