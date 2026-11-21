/**
 * [INPUT]
 * (no module dependencies)
 *
 * [OUTPUT]
 * TTSState: playback state of one TTS engine
 * TTSMode: engine that voices the text (browser SpeechSynthesis or the backend API)
 * UseTTSOptions / UseTTSReturn: options and controls shared by both engines and the useTTS facade
 *
 * [POS]
 * Type vocabulary shared by the TTS engines and the useTTS facade;
 * `useTTS.ts` re-exports `TTSMode` as the public surface.
 */

export type TTSState = 'idle' | 'playing' | 'paused' | 'loading';
export type TTSMode = 'browser' | 'api';

export interface UseTTSOptions {
  rate?: number;
  lang?: string;
  mode?: TTSMode;
  provider?: string;
}

export interface UseTTSReturn {
  state: TTSState;
  speak: (text: string) => void;
  pause: () => void;
  resume: () => void;
  stop: () => void;
  toggle: (text: string) => void;
  supported: boolean;
}
