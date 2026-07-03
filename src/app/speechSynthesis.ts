export type SpeakTextOptions = {
  onStart?: () => void;
  onEnd?: () => void;
  onError?: (error?: unknown) => void;
  lang?: string;
  rate?: number;
  pitch?: number;
  volume?: number;
};

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

export function stopSpeaking(): void {
  if (!isSpeechSynthesisSupported()) return;
  window.speechSynthesis.cancel();
}

export function speakText(text: string, options: SpeakTextOptions = {}): boolean {
  const trimmed = text.trim();

  if (!trimmed || !isSpeechSynthesisSupported()) {
    return false;
  }

  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(trimmed);
  utterance.lang = options.lang ?? 'en-US';
  utterance.rate = options.rate ?? 1;
  utterance.pitch = options.pitch ?? 1;
  utterance.volume = options.volume ?? 1;

  utterance.onstart = () => {
    options.onStart?.();
  };

  utterance.onend = () => {
    options.onEnd?.();
  };

  utterance.onerror = (event) => {
    options.onError?.(event);
  };

  window.speechSynthesis.speak(utterance);
  return true;
}
