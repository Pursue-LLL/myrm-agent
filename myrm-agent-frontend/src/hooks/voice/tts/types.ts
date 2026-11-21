/**
 * [INPUT]
 * (no module dependencies)
 *
 * [OUTPUT]
 * TTSState: playback state of one TTS engine
 * TTSMode: engine that voices the text (browser SpeechSynthesis or the backend API)
 * TTSEngine: controls every engine exposes
 * UseTTSOptions: engine selector and provider accepted by useTTS
 * UseTTSReturn: what useTTS returns, the engine's controls plus toggle
 *
 * [POS]
 * Type vocabulary shared by the TTS engines and the useTTS facade;
 * `useTTS.ts` re-exports `TTSMode` as the public surface.
 */

export type TTSState = 'idle' | 'playing' | 'paused' | 'loading';
export type TTSMode = 'browser' | 'api';

export interface UseTTSOptions {
  mode?: TTSMode;
  provider?: string;
}

export interface TTSEngine {
  state: TTSState;
  speak: (text: string) => void;
  pause: () => void;
  resume: () => void;
  stop: () => void;
  supported: boolean;
}

export interface UseTTSReturn extends TTSEngine {
  toggle: (text: string) => void;
}
