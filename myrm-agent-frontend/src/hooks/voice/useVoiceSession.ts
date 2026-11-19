/**
 * [INPUT]
 * hooks/voice/useSpeechInput (POS: Speech-to-text input with multi-backend STT)
 * hooks/voice/useTTS (POS: Text-to-speech output with browser and API backends)
 * hooks/voice/useLiveMeetingNotes (POS: In-meeting live notes session: transcript upload + rolling structured notes)
 * hooks/voice/session/usePttScreenContext (POS: PTT screen context fusion into outgoing voice messages)
 * hooks/voice/session/useSessionStateSync (POS: Mirrors the active transport's connection state into the session state)
 * hooks/voice/session/useSessionEvents (POS: Window event bridge: toggle / interrupt / replay in, state broadcast out)
 * hooks/voice/session/speakableSegments (POS: Pure sentence segmenter feeding the TTS queue)
 *
 * [OUTPUT]
 * useVoiceSession: Full-duplex voice session with barge-in, concurrent STT/TTS,
 * queue-safe TTS insertion, and PTT screen context
 * VoiceSessionState / VoiceSessionMode: Public session state and transport vocabulary
 *
 * [POS]
 * Full-duplex voice session orchestrator. Manages concurrent listening + speaking with
 * automatic barge-in detection and queue-safe TTS insertion; PTT context fusion, transport state sync
 * and window events live in hooks/voice/session/.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useSpeechInput, type SpeechMode } from './useSpeechInput';
import { useTTS, type TTSMode } from './useTTS';
import { useLiveMeetingNotes, type UseLiveMeetingNotesReturn } from './useLiveMeetingNotes';
import { useVoiceAgentBridge } from './useVoiceAgentBridge';
import { useRealtimeVoice } from './useRealtimeVoice';
import { useGeminiLiveVoice } from './useGeminiLiveVoice';
import { extractSpeakableSegments } from './session/speakableSegments';
import { useSessionEvents } from './session/useSessionEvents';
import { usePttScreenContext } from './session/usePttScreenContext';
import { useSessionStateSync } from './session/useSessionStateSync';
import type { VoiceSessionMode, VoiceSessionState } from './session/types';

export type { VoiceSessionMode, VoiceSessionState } from './session/types';

interface UseVoiceSessionOptions {
  enabled: boolean;
  speechMode?: SpeechMode;
  ttsMode?: TTSMode;
  ttsProvider?: string;
  autoSend?: boolean;
  /** Receives the transcript and the base64 screenshots (bare or as data URLs) that ride with it. */
  onSendMessage?: (text: string, visionFrames?: string[]) => void;
  onError?: (error: string) => void;
  keyterms?: string[];
  /** Enable full-duplex: keep mic open during TTS, auto-detect barge-in */
  fullDuplex?: boolean;
  /** Volume threshold for barge-in detection (0-1). Default: 0.06 */
  bargeInThreshold?: number;
  /** Duration in ms that voice must exceed threshold to trigger barge-in. Default: 300 */
  bargeInDurationMs?: number;
  /** Session mode: audio_only (default) or agent_bridge (server-side Agent) */
  mode?: VoiceSessionMode;
  /** Agent ID for agent_bridge mode */
  agentId?: string;
  /** Chat ID for agent_bridge mode */
  chatId?: string;
  /** Called when agent produces response text in agent_bridge mode */
  onAgentResponse?: (text: string, done: boolean) => void;
  /** Called when agent uses a tool in agent_bridge mode */
  onAgentToolUse?: (toolName: string) => void;
  /** Called when agent starts/ends a turn */
  onAgentTurnChange?: (state: 'thinking' | 'done', turnId: string) => void;
}

interface UseVoiceSessionReturn {
  sessionState: VoiceSessionState;
  isActive: boolean;
  startSession: () => void;
  stopSession: () => void;
  interruptTTS: () => void;
  speakResponse: (text: string, options?: { queue?: boolean }) => void;
  replayLastTTS: () => void;
  interimText: string;
  audioLevel: number;
  ttsState: ReturnType<typeof useTTS>['state'];
  /** Current agent response text (agent_bridge mode) */
  agentResponseText: string;
  /** Current agent tool name being used (agent_bridge mode) */
  agentToolName: string;
  /** Live in-meeting rolling structured notes (summary / decisions / action items) */
  liveNotes: UseLiveMeetingNotesReturn;
}

export function useVoiceSession(options: UseVoiceSessionOptions): UseVoiceSessionReturn {
  const {
    enabled,
    speechMode = 'toggle',
    ttsMode = 'browser',
    ttsProvider,
    autoSend = true,
    onSendMessage,
    onError,
    keyterms,
    fullDuplex = true,
    bargeInThreshold = 0.06,
    bargeInDurationMs = 300,
    mode = 'audio_only',
    agentId,
    chatId,
    onAgentResponse,
    onAgentToolUse,
    onAgentTurnChange,
  } = options;

  const [sessionState, setSessionState] = useState<VoiceSessionState>('inactive');
  const [agentResponseText, _setAgentResponseText] = useState('');
  const [agentToolName, _setAgentToolName] = useState('');
  const sessionActiveRef = useRef(false);
  const pendingTTSRef = useRef<string[]>([]);
  const isSpeakingRef = useRef(false);

  // Barge-in detection state
  const bargeInStartRef = useRef(0);

  // F13 DoD: Last spoken TTS text cache for quick replay
  const lastSpokenTextRef = useRef<string | null>(null);

  const composeWithPttContext = usePttScreenContext(speechMode);

  const tts = useTTS({ mode: ttsMode, provider: ttsProvider });

  const liveNotes = useLiveMeetingNotes(chatId);

  const agentBridge = useVoiceAgentBridge({
    enabled: mode === 'agent_bridge',
    agentId,
    chatId,
    keyterms,
    onError,
    onSttFinal: liveNotes.ingest,
    onAgentResponse: useCallback(
      (text: string, done: boolean) => {
        onAgentResponse?.(text, done);
      },
      [onAgentResponse],
    ),
    onAgentToolUse,
    onAgentTurnChange,
  });

  const realtimeVoice = useRealtimeVoice({
    enabled: mode === 'openai_realtime',
    agentId,
    chatId,
    onTranscript: useCallback(
      (entry: { role: 'user' | 'assistant'; text: string }) => {
        if (entry.role === 'assistant') {
          onAgentResponse?.(entry.text, true);
        }
      },
      [onAgentResponse],
    ),
    onToolCall: useCallback(
      (name: string) => {
        onAgentToolUse?.(name);
      },
      [onAgentToolUse],
    ),
    onError,
    onFallback: useCallback(() => {
      onError?.('Realtime connection failed, please switch to Agent Bridge mode');
    }, [onError]),
  });

  const geminiLive = useGeminiLiveVoice({
    enabled: mode === 'gemini_live',
    agentId,
    chatId,
    model: undefined,
    onTranscript: useCallback(
      (entry: { role: 'user' | 'assistant'; text: string }) => {
        if (entry.role === 'assistant') {
          onAgentResponse?.(entry.text, true);
        }
      },
      [onAgentResponse],
    ),
    onToolCall: useCallback(
      (name: string) => {
        onAgentToolUse?.(name);
      },
      [onAgentToolUse],
    ),
    onError,
    onFallback: useCallback(() => {
      onError?.('Gemini Live connection failed, please switch to Agent Bridge mode');
    }, [onError]),
  });

  const handleTranscript = useCallback(
    async (text: string) => {
      if (!sessionActiveRef.current || !autoSend) {
        return;
      }

      if (mode === 'agent_bridge') {
        return;
      }

      if (fullDuplex && isSpeakingRef.current) {
        pendingTTSRef.current = [];
        isSpeakingRef.current = false;
        tts.stop();
      }

      setSessionState('processing');

      const { text: finalText, visionFrames } = await composeWithPttContext(text);
      onSendMessage?.(finalText, visionFrames);
    },
    [autoSend, fullDuplex, tts, onSendMessage, mode, composeWithPttContext],
  );

  const handleInterimTranscript = useCallback(() => {
    // no-op: interim text handled by useSpeechInput state
  }, []);

  const handleSpeechError = useCallback(
    (error: string) => {
      if (error === 'tooShort') {
        return;
      }
      onError?.(error);
    },
    [onError],
  );

  const speech = useSpeechInput({
    onTranscript: handleTranscript,
    onInterimTranscript: handleInterimTranscript,
    onError: handleSpeechError,
    mode: speechMode,
    keyterms,
  });

  // ── Barge-in detection via audio level ──
  useEffect(() => {
    if (!fullDuplex || !isSpeakingRef.current || !sessionActiveRef.current) {
      bargeInStartRef.current = 0;
      return;
    }

    if (speech.audioLevel > bargeInThreshold) {
      if (bargeInStartRef.current === 0) {
        bargeInStartRef.current = Date.now();
      } else if (Date.now() - bargeInStartRef.current >= bargeInDurationMs) {
        // Sustained voice detected during TTS → barge-in
        pendingTTSRef.current = [];
        isSpeakingRef.current = false;
        tts.stop();
        bargeInStartRef.current = 0;
        setSessionState('listening');
      }
    } else {
      bargeInStartRef.current = 0;
    }
  }, [speech.audioLevel, fullDuplex, bargeInThreshold, bargeInDurationMs, tts]);

  const speakNext = useCallback(() => {
    if (pendingTTSRef.current.length === 0) {
      isSpeakingRef.current = false;
      setSessionState((prev) => (prev === 'speaking' ? 'listening' : prev));
      // In half-duplex mode, restart recording after TTS finishes
      if (!fullDuplex && sessionActiveRef.current) {
        speech.startRecording();
      }
      return;
    }

    const segment = pendingTTSRef.current.shift();
    if (segment) {
      tts.speak(segment);
    }
  }, [tts, speech, fullDuplex]);

  const speakResponse = useCallback(
    (text: string, options?: { queue?: boolean }) => {
      if (!sessionActiveRef.current) {
        return;
      }

      lastSpokenTextRef.current = text;

      const segments = extractSpeakableSegments(text);
      if (segments.length === 0) {
        return;
      }

      // Queue insertion window: append to the pending queue without
      // interrupting an in-flight utterance (e.g. voice background task
      // completion announcements during an active agent response).
      if (options?.queue && isSpeakingRef.current) {
        pendingTTSRef.current.push(...segments);
        return;
      }

      pendingTTSRef.current = segments;
      isSpeakingRef.current = true;
      setSessionState('speaking');

      // In half-duplex mode, stop recording while TTS plays
      if (!fullDuplex && speech.state === 'recording') {
        speech.stopRecording();
      }
      // In full-duplex mode, keep recording (mic stays open for barge-in)

      speakNext();
    },
    [speech, speakNext, fullDuplex],
  );

  const replayLastTTS = useCallback(() => {
    if (!lastSpokenTextRef.current) {
      return;
    }
    speakResponse(lastSpokenTextRef.current);
  }, [speakResponse]);

  useEffect(() => {
    if (tts.state === 'idle' && isSpeakingRef.current) {
      speakNext();
    }
  }, [tts.state, speakNext]);

  const startSession = useCallback(() => {
    if (!enabled) {
      return;
    }

    sessionActiveRef.current = true;
    setSessionState('listening');

    if (mode === 'openai_realtime') {
      realtimeVoice.connect();
      return;
    }

    if (mode === 'gemini_live') {
      geminiLive.connect();
      return;
    }

    if (mode === 'agent_bridge') {
      agentBridge.connect();
      return;
    }

    speech.startRecording();
  }, [enabled, speech, mode, agentBridge, realtimeVoice, geminiLive]);

  const stopSession = useCallback(() => {
    // Publish/archive the in-meeting rolling notes when the session ends and reset
    // the live session so the next session starts fresh.
    void liveNotes.finalize();
    sessionActiveRef.current = false;
    pendingTTSRef.current = [];
    isSpeakingRef.current = false;
    bargeInStartRef.current = 0;

    if (mode === 'openai_realtime') {
      realtimeVoice.disconnect();
    } else if (mode === 'gemini_live') {
      geminiLive.disconnect();
    } else if (mode === 'agent_bridge') {
      agentBridge.disconnect();
    } else {
      if (speech.state === 'recording') {
        speech.stopRecording();
      }
      tts.stop();
    }

    setSessionState('inactive');
  }, [speech, tts, mode, agentBridge, realtimeVoice, geminiLive, liveNotes]);

  const interruptTTS = useCallback(() => {
    if (mode === 'openai_realtime' || mode === 'gemini_live') {
      // Realtime/Gemini Live: server-side VAD handles interruption natively
      return;
    }

    if (mode === 'agent_bridge') {
      agentBridge.cancelTts();
      if (sessionActiveRef.current) {
        setSessionState('listening');
      }
      return;
    }

    if (sessionState !== 'speaking') {
      return;
    }

    pendingTTSRef.current = [];
    isSpeakingRef.current = false;
    bargeInStartRef.current = 0;
    tts.stop();

    if (sessionActiveRef.current) {
      setSessionState('listening');
      if (!fullDuplex) {
        speech.startRecording();
      }
    }
  }, [sessionState, tts, speech, fullDuplex, mode, agentBridge]);

  useSessionStateSync({
    mode,
    agentBridgeState: agentBridge.state,
    realtimeState: realtimeVoice.state,
    geminiLiveState: geminiLive.state,
    sessionActiveRef,
    setSessionState,
  });

  useEffect(() => {
    return () => {
      sessionActiveRef.current = false;
      pendingTTSRef.current = [];
    };
  }, []);

  const isRealtime = mode === 'openai_realtime';
  const isGeminiLive = mode === 'gemini_live';
  const isAgentBridge = mode === 'agent_bridge';
  const audioLevel = isAgentBridge ? agentBridge.audioLevel : speech.audioLevel;

  useSessionEvents({
    sessionState,
    audioLevel,
    sessionActiveRef,
    startSession,
    stopSession,
    interruptTTS,
    replayLastTTS,
  });

  return {
    sessionState,
    isActive: sessionState !== 'inactive',
    startSession,
    stopSession,
    interruptTTS,
    speakResponse,
    replayLastTTS,
    interimText: isRealtime
      ? realtimeVoice.interimText
      : isGeminiLive
        ? geminiLive.interimText
        : isAgentBridge
          ? agentBridge.interimText
          : speech.interimText,
    audioLevel,
    ttsState: tts.state,
    agentResponseText: isRealtime
      ? realtimeVoice.responseText
      : isGeminiLive
        ? geminiLive.responseText
        : isAgentBridge
          ? agentBridge.agentResponseText
          : agentResponseText,
    agentToolName: isAgentBridge ? agentBridge.agentToolName : agentToolName,
    liveNotes,
  };
}
