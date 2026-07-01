declare global {
  interface Window {
    SpeechRecognition: typeof SpeechRecognition;
    webkitSpeechRecognition: typeof SpeechRecognition;
  }
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
  interpretation?: object;
  emma?: XMLDocument;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  readonly isFinal: boolean;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  readonly transcript: string;
  readonly confidence: number;
}

declare class SpeechRecognition extends EventTarget {
  grammars: SpeechGrammarList;
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  serviceURI: string;

  abort(): void;
  start(): void;
  stop(): void;

  onaudiostart: ((this: SpeechRecognition, ev: Event) => any) | null;
  onstart: ((this: SpeechRecognition, ev: Event) => any) | null;
  onend: ((this: SpeechRecognition, ev: Event) => any) | null;
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => any) | null;
  onnomatch: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => any) | null;
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => any) | null;
  onsoundend: ((this: SpeechRecognition, ev: Event) => any) | null;
}

declare class SpeechGrammarList {
  readonly length: number;
  item(index: number): SpeechGrammar;
  addFromURI(src: string, weight?: number): void;
  addFromString(string: string, weight?: number): void;
  [index: number]: SpeechGrammar;
}

declare class SpeechGrammar {
  src: string;
  weight: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: SpeechRecognitionErrorCode;
  readonly isTrusted: boolean;
}

type SpeechRecognitionErrorCode =
  | 'network'
  | 'aborted'
  | 'service-not-allowed'
  | 'bad-grammar'
  | 'no-speech'
  | 'audio-capture'
  | 'not-allowed';

export function getSpeechRecognition(): typeof SpeechRecognition | null {
  const SpeechRecognitionClass =
    (typeof window !== 'undefined' && window.SpeechRecognition) ||
    (typeof window !== 'undefined' && window.webkitSpeechRecognition);
  
    return SpeechRecognitionClass || null;
}

export function isSpeechRecognitionSupported(): boolean {
  return getSpeechRecognition() !== null;
}
