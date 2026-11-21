'use client';

/**
 * [INPUT]
 * hooks/voice/useVoiceAgentBridge::AgentBridgeState (POS: Connection state of the server-side Agent WebSocket bridge)
 * hooks/voice/useRealtimeVoice::RealtimeVoiceState (POS: Connection state of the OpenAI Realtime WebRTC session)
 * hooks/voice/useGeminiLiveVoice::GeminiLiveState (POS: Connection state of the Gemini Live WebSocket session)
 * hooks/voice/session/types (POS: Voice session state and mode vocabulary)
 *
 * [OUTPUT]
 * useSessionStateSync: Mirrors the connection state of the transport that owns the current mode into the session state
 *
 * [POS]
 * Keeps the session state in step with the active transport (Agent bridge, OpenAI Realtime or Gemini Live).
 * A transport that drops while the session is running ends the session.
 */

import { useEffect, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import type { AgentBridgeState } from '../useVoiceAgentBridge';
import type { RealtimeVoiceState } from '../useRealtimeVoice';
import type { GeminiLiveState } from '../useGeminiLiveVoice';
import type { VoiceSessionMode, VoiceSessionState } from './types';

interface UseSessionStateSyncOptions {
  mode: VoiceSessionMode;
  agentBridgeState: AgentBridgeState;
  realtimeState: RealtimeVoiceState;
  geminiLiveState: GeminiLiveState;
  /** True while a session is running; cleared here when the transport drops. */
  sessionActiveRef: MutableRefObject<boolean>;
  setSessionState: Dispatch<SetStateAction<VoiceSessionState>>;
}

export function useSessionStateSync({
  mode,
  agentBridgeState,
  realtimeState,
  geminiLiveState,
  sessionActiveRef,
  setSessionState,
}: UseSessionStateSyncOptions): void {
  // Sync agent bridge state → session state
  useEffect(() => {
    if (mode !== 'agent_bridge') {
      return;
    }
    switch (agentBridgeState) {
      case 'listening':
        setSessionState('listening');
        break;
      case 'agent_thinking':
        setSessionState('processing');
        break;
      case 'agent_speaking':
        setSessionState('speaking');
        break;
      case 'disconnected':
        if (sessionActiveRef.current) {
          sessionActiveRef.current = false;
          setSessionState('inactive');
        }
        break;
    }
  }, [mode, agentBridgeState, sessionActiveRef, setSessionState]);

  // Sync realtime voice state → session state
  useEffect(() => {
    if (mode !== 'openai_realtime') {
      return;
    }
    switch (realtimeState) {
      case 'connecting':
        setSessionState('listening');
        break;
      case 'listening':
        setSessionState('listening');
        break;
      case 'thinking':
        setSessionState('processing');
        break;
      case 'speaking':
        setSessionState('speaking');
        break;
      case 'error':
      case 'idle':
        if (sessionActiveRef.current) {
          sessionActiveRef.current = false;
          setSessionState('inactive');
        }
        break;
    }
  }, [mode, realtimeState, sessionActiveRef, setSessionState]);

  // Sync Gemini Live state → session state
  useEffect(() => {
    if (mode !== 'gemini_live') {
      return;
    }
    switch (geminiLiveState) {
      case 'connecting':
      case 'listening':
        setSessionState('listening');
        break;
      case 'thinking':
        setSessionState('processing');
        break;
      case 'speaking':
        setSessionState('speaking');
        break;
      case 'error':
      case 'idle':
        if (sessionActiveRef.current) {
          sessionActiveRef.current = false;
          setSessionState('inactive');
        }
        break;
    }
  }, [mode, geminiLiveState, sessionActiveRef, setSessionState]);
}
