'use client';

/**
 * [INPUT]
 * - Web Speech API (window.SpeechRecognition / window.webkitSpeechRecognition)
 *
 * [OUTPUT]
 * - useVoiceRecognition: React hook handling audio recording and real-time speech dictation
 *
 * [POS]
 * Extracted standalone hook for mobile quick capture voice-to-text dictation.
 */

import { useState, useRef, useCallback } from 'react';

export interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: (e: { results: Array<Array<{ transcript: string }>> }) => void;
  onerror: () => void;
  onend: () => void;
}

export interface UseVoiceRecognitionOptions {
  onTranscriptChunk?: (text: string) => void;
  onUnsupported?: () => void;
}

export function useVoiceRecognition(options: UseVoiceRecognitionOptions = {}) {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);

  const toggleRecognition = useCallback(() => {
    if (isListening) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setIsListening(false);
      return;
    }

    const SpeechRecognitionClass =
      (typeof window !== 'undefined' &&
        ((window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition ||
          (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition)) as
        | (new () => SpeechRecognitionInstance)
        | undefined;

    if (!SpeechRecognitionClass) {
      options.onUnsupported?.();
      return;
    }

    try {
      const recognition = new SpeechRecognitionClass();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = typeof navigator !== 'undefined' ? navigator.language || 'zh-CN' : 'zh-CN';

      recognition.onresult = (e) => {
        let text = '';
        for (let i = 0; i < e.results.length; i += 1) {
          text += e.results[i][0].transcript;
        }
        setTranscript(text);
        options.onTranscriptChunk?.(text);
      };

      recognition.onerror = () => {
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
      recognitionRef.current = recognition;
      setIsListening(true);
    } catch {
      setIsListening(false);
    }
  }, [isListening, options]);

  const resetTranscript = useCallback(() => {
    setTranscript('');
  }, []);

  const stopRecognition = useCallback(() => {
    if (recognitionRef.current && isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    }
  }, [isListening]);

  return {
    isListening,
    transcript,
    toggleRecognition,
    resetTranscript,
    stopRecognition,
  };
}
