/**
 * [INPUT]
 * hooks/voice/tts/types (POS: Type vocabulary shared by the TTS engines and the useTTS facade)
 * hooks/voice/tts/useBrowserTTS (POS: Browser TTS engine on the SpeechSynthesis API)
 * hooks/voice/tts/useApiTTS (POS: API TTS engine on the backend synthesis endpoints)
 *
 * [OUTPUT]
 * useTTS: Text-to-speech output with browser and API backends
 * TTSMode: Engine selector accepted by useTTS
 *
 * [POS]
 * Text-to-speech output with browser and API backends. Runs both engines on every render (the hook order stays
 * fixed), exposes the one the mode selects and adds `toggle` (speak, pause or resume by its state); the engines
 * live in hooks/voice/tts/.
 */

'use client';

import { useCallback } from 'react';
import { useApiTTS } from './tts/useApiTTS';
import { useBrowserTTS } from './tts/useBrowserTTS';
import type { UseTTSOptions, UseTTSReturn } from './tts/types';

export type { TTSMode } from './tts/types';

export function useTTS(options: UseTTSOptions = {}): UseTTSReturn {
  const browserTTS = useBrowserTTS();
  const apiTTS = useApiTTS(options);
  const engine = options.mode === 'api' ? apiTTS : browserTTS;
  const { state, speak, pause, resume } = engine;

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

  return { ...engine, toggle };
}
