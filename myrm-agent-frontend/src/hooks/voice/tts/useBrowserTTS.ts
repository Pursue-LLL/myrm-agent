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
 * without browser support every control is a no-op. The speech queue is page-wide: `speak`
 * takes it over whenever there is something to say, while stop, unmount and utterance
 * events only concern the instance that owns the current utterance, so a row that is not
 * speaking cannot cut off another by stopping, unmounting or having nothing to say.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { stripMarkdown } from '@/lib/utils/messageUtils';
import type { TTSEngine, TTSState } from './types';

export function useBrowserTTS(): TTSEngine {
  const [state, setState] = useState<TTSState>('idle');
  // The utterance this instance owns until it ends or is replaced. The speech queue is page-wide (every message row
  // has an instance), so ownership decides whether a `cancel()` or an utterance event concerns this instance at all.
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const stop = useCallback(() => {
    if (!supported || !utteranceRef.current) {
      return;
    }
    utteranceRef.current = null;
    window.speechSynthesis.cancel();
    setState('idle');
  }, [supported]);

  // Unmounting ends what this instance voices and nothing else.
  useEffect(() => stop, [stop]);

  const speak = useCallback(
    (text: string) => {
      if (!supported) {
        return;
      }
      const cleaned = stripMarkdown(text);
      if (!cleaned) {
        return;
      }

      const utterance = new SpeechSynthesisUtterance(cleaned);
      const finish = () => {
        if (utteranceRef.current === utterance) {
          utteranceRef.current = null;
          setState('idle');
        }
      };
      utterance.onstart = () => {
        if (utteranceRef.current === utterance) {
          setState('playing');
        }
      };
      utterance.onend = finish;
      utterance.onerror = finish;

      // Claim before cancelling: the utterance being interrupted reports its error after `cancel()` has returned, and
      // by then it must no longer be this instance's.
      utteranceRef.current = utterance;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    },
    [supported],
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

  return { state, speak, pause, resume, stop, supported };
}
