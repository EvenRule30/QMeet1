import { useCallback, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { Message, OrbState } from '../types';
import { normalizeSpokenQMeet } from '../commands';
import { getSpeechRecognition, isSpeechRecognitionSupported } from '../speechRecognition';

type FinalTranscriptHandler = (rawTranscript: string, normalizedTranscript: string) => void;

type UseSpeechRecognitionControllerOptions = {
  setOrbState: Dispatch<SetStateAction<OrbState>>;
  setChatActive: Dispatch<SetStateAction<boolean>>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
};

export function useSpeechRecognitionController({
  setOrbState,
  setChatActive,
  setMessages,
}: UseSpeechRecognitionControllerOptions) {
  const [listeningTranscript, setListeningTranscript] = useState('');
  const recognitionRef = useRef<any | null>(null);
  const transcriptSentRef = useRef(false);
  const listeningTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suppressNextSpeechErrorRef = useRef(false);

  const finishListening = useCallback(() => {
    if (listeningTimeoutRef.current) {
      clearTimeout(listeningTimeoutRef.current);
      listeningTimeoutRef.current = null;
    }

    if (recognitionRef.current) {
      try {
        suppressNextSpeechErrorRef.current = true;
        recognitionRef.current.abort();
      } catch (error) {
        console.error('Error aborting recognition:', error);
      }

      recognitionRef.current = null;
    }

    transcriptSentRef.current = false;
    setListeningTranscript('');
    setOrbState('idle');
  }, [setOrbState]);

  const startListening = useCallback((onFinalTranscript: FinalTranscriptHandler) => {
    if (!isSpeechRecognitionSupported()) {
      setChatActive(true);
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: 'Voice input is not supported in this browser. Please use the text input instead.',
          timestamp: new Date(),
        },
      ]);
      return;
    }

    setOrbState('listening');
    transcriptSentRef.current = false;
    setListeningTranscript('');

    const SpeechRecognitionClass = getSpeechRecognition();

    if (!SpeechRecognitionClass) {
      setOrbState('idle');
      return;
    }

    const recognition = new SpeechRecognitionClass();
    recognitionRef.current = recognition;

    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setOrbState('listening');

      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
      }

      listeningTimeoutRef.current = setTimeout(() => {
        if (recognitionRef.current) {
          recognitionRef.current.abort();
        }

        if (!transcriptSentRef.current) {
          setListeningTranscript('');
          setChatActive(true);
          setOrbState('idle');
          setMessages((prev) => [
            ...prev,
            {
              id: `a-${Date.now()}`,
              role: 'assistant',
              content: 'I did not catch that. Tap the orb and try again.',
              timestamp: new Date(),
            },
          ]);
        }
      }, 8000);
    };

    recognition.onresult = (event: any) => {
      let interimTranscript = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0]?.transcript ?? '';

        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      const previewText = (finalTranscript || interimTranscript).trim();
      if (previewText) {
        setListeningTranscript(previewText);
      }

      if (finalTranscript.trim()) {
        if (transcriptSentRef.current) return;
        transcriptSentRef.current = true;

        if (listeningTimeoutRef.current) {
          clearTimeout(listeningTimeoutRef.current);
          listeningTimeoutRef.current = null;
        }

        const rawTranscript = finalTranscript.trim();
        const normalizedTranscript = normalizeSpokenQMeet(rawTranscript);

        // Clear the visible listening preview immediately so the UI does not keep
        // showing "Heard: Listening..." while QMeet is parsing the command.
        setListeningTranscript('');
        setOrbState('thinking');

        onFinalTranscript(rawTranscript, normalizedTranscript);
      }
    };

    recognition.onerror = (event: any) => {
      const errorCode = event.error;

      if (suppressNextSpeechErrorRef.current || errorCode === 'aborted') {
        suppressNextSpeechErrorRef.current = false;
        if (listeningTimeoutRef.current) {
          clearTimeout(listeningTimeoutRef.current);
          listeningTimeoutRef.current = null;
        }
        setListeningTranscript('');
        return;
      }

      let errorMessage = 'Speech recognition failed. Please try again.';

      if (errorCode === 'no-speech') {
        errorMessage = 'No speech detected. Please speak clearly and try again.';
      } else if (errorCode === 'audio-capture') {
        errorMessage = 'Microphone not found or permission denied.';
      } else if (errorCode === 'not-allowed') {
        errorMessage = 'Microphone permission denied. Please enable it in your browser settings.';
      } else if (errorCode === 'network') {
        errorMessage = 'Network error during speech recognition.';
      }

      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
        listeningTimeoutRef.current = null;
      }

      setListeningTranscript('');
      setChatActive(true);
      setOrbState('error');
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: errorMessage,
          timestamp: new Date(),
        },
      ]);

      setTimeout(() => {
        setOrbState('idle');
      }, 2000);
    };

    recognition.onend = () => {
      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
        listeningTimeoutRef.current = null;
      }

      if (!transcriptSentRef.current) {
        setListeningTranscript('');
        setOrbState('idle');
      } else {
        window.setTimeout(() => {
          setListeningTranscript('');
        }, 300);
      }

      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
    };

    try {
      recognition.start();
    } catch (error) {
      console.error('Speech recognition start error:', error);

      if (listeningTimeoutRef.current) {
        clearTimeout(listeningTimeoutRef.current);
        listeningTimeoutRef.current = null;
      }

      setListeningTranscript('');
      setOrbState('idle');
    }
  }, [setChatActive, setMessages, setOrbState]);

  return {
    listeningTranscript,
    finishListening,
    startListening,
    voiceInputSupported: isSpeechRecognitionSupported(),
  };
}
