/**
 * [INPUT]
 * hooks/voice/tts/types (POS: Type vocabulary shared by the TTS engines and the useTTS facade)
 * lib/utils/messageUtils::stripMarkdown (POS: Message text cleanup and formatting toolkit)
 *
 * [OUTPUT]
 * useBrowserTTS: Text-to-speech engine on the browser SpeechSynthesis API
 *
 * [POS]
 * Browser TTS engine. Voices markdown-stripped text through `window.speechSynthesis`;
 * without browser support every control is a no-op.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { stripMarkdown } from '@/lib/utils/messageUtils';
import type { TTSState, UseTTSOptions, UseTTSReturn } from './types';

export function useBrowserTTS(options: UseTTSOptions): UseTTSReturn {
  const { rate = 1.0, lang } = options;
  const [state, setState] = useState<TTSState>('idle');
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const stop = useCallback(() => {
    if (!supported) {
      return;
    }
    window.speechSynthesis.cancel();
    utteranceRef.current = null;
    setState('idle');
  }, [supported]);

  useEffect(() => {
    return () => {
      if (supported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported) {
        return;
      }
      window.speechSynthesis.cancel();
      const cleaned = stripMarkdown(text);
      if (!cleaned) {
        return;
      }

      const utterance = new SpeechSynthesisUtterance(cleaned);
      utterance.rate = rate;
      if (lang) {
        utterance.lang = lang;
      }

      utterance.onstart = () => setState('playing');
      utterance.onend = () => {
        utteranceRef.current = null;
        setState('idle');
      };
      utterance.onerror = () => {
        utteranceRef.current = null;
        setState('idle');
      };

      utteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
    },
    [supported, rate, lang],
  );

  const pause = useCallback(() => {
    if (!supported || state !== 'playing') {
      return;
    }
    window.speechSynthesis.pause();
    setState('paused');
  }, [supported, state]);

  const resume = useCallback(() => {
    if (!supported || state !== 'paused') {
      return;
    }
    window.speechSynthesis.resume();
    setState('playing');
  }, [supported, state]);

  const toggle = useCallback(
    (text: string) => {
      if (state === 'playing') {
        pause();
      } else if (state === 'paused') {
        resume();
      } else {
        speak(text);
      }
    },
    [state, pause, resume, speak],
  );

  return { state, speak, pause, resume, stop, toggle, supported };
}
