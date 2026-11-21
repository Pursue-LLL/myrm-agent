/**
 * [INPUT]
 * (no module dependencies)
 *
 * [OUTPUT]
 * VoiceSessionState: lifecycle state of one voice session
 * VoiceSessionMode: transport that carries the session (local STT/TTS, Agent bridge, OpenAI Realtime, Gemini Live)
 *
 * [POS]
 * Type vocabulary shared by the voice session orchestrator and its internal modules;
 * `useVoiceSession.ts` re-exports it as the public surface.
 */

export type VoiceSessionState = 'inactive' | 'listening' | 'processing' | 'speaking' | 'paused';
export type VoiceSessionMode = 'audio_only' | 'agent_bridge' | 'openai_realtime' | 'gemini_live';
