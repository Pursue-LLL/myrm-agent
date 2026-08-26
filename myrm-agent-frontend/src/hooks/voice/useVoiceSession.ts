/**
 * [INPUT]
 * hooks/voice/useSpeechInput (POS: Speech-to-text input with multi-backend STT)
 * hooks/voice/useTTS (POS: Text-to-speech output with browser and API backends)
 * hooks/multimodal/useCameraInput (POS: Camera input manager with frame buffering)
 * hooks/multimodal/useVisionIntent (POS: Vision intent classifier with bilingual rules)
 * hooks/voice/useVoicePttListener (POS: Bridges Tauri PTT events to DOM, provides PttScreenContext type)
 *
 * [OUTPUT]
 * useVoiceSession: Full-duplex voice session with barge-in, concurrent STT/TTS,
 * queue-safe TTS insertion, vision fusion, and PTT screen context
 *
 * [POS]
 * Full-duplex voice session orchestrator. Manages concurrent listening + speaking with
 * automatic barge-in detection, queue-safe TTS insertion, and PTT screen context fusion (Tauri desktop).
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useSpeechInput, type SpeechMode } from './useSpeechInput';
import { useTTS, type TTSMode } from './useTTS';
import { useCameraInput } from '../multimodal/useCameraInput';
import { useVisionIntent } from '../multimodal/useVisionIntent';
import { useVoiceAgentBridge } from './useVoiceAgentBridge';
import { useRealtimeVoice } from './useRealtimeVoice';
import { useGeminiLiveVoice } from './useGeminiLiveVoice';
import type { VisualFrame } from '@/lib/vision/frameSelector';
import type { PttScreenContext } from './useVoicePttListener';

export type VoiceSessionState = 'inactive' | 'listening' | 'processing' | 'speaking' | 'paused';
export type VoiceSessionMode = 'audio_only' | 'agent_bridge' | 'openai_realtime' | 'gemini_live';

interface UseVoiceSessionOptions {
  enabled: boolean;
  cameraEnabled?: boolean;
  speechMode?: SpeechMode;
  ttsMode?: TTSMode;
  ttsProvider?: string;
  autoSend?: boolean;
  onSendMessage?: (text: string, visionFrames?: VisualFrame[]) => void;
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
  lastSpokenText: string | null;
  interimText: string;
  audioLevel: number;
  cameraState: ReturnType<typeof useCameraInput>['cameraState'];
  facingMode: ReturnType<typeof useCameraInput>['facingMode'];
  videoRef: ReturnType<typeof useCameraInput>['videoRef'];
  toggleFacing: () => void;
  ttsState: ReturnType<typeof useTTS>['state'];
  /** Current agent response text (agent_bridge mode) */
  agentResponseText: string;
  /** Current agent tool name being used (agent_bridge mode) */
  agentToolName: string;
}

const SENTENCE_END_PATTERN = /[.!?。！？\n]/;
const TERMINATOR_ONLY_PATTERN = /^[.!?。！？\s]+$/;

export function extractSpeakableSegments(text: string): string[] {
  const segments: string[] = [];
  let remaining = text;

  while (remaining.length > 0) {
    const match = SENTENCE_END_PATTERN.exec(remaining);
    if (match && match.index !== undefined) {
      const segment = remaining.slice(0, match.index + 1).trim();
      if (segment && !TERMINATOR_ONLY_PATTERN.test(segment)) {
        segments.push(segment);
      }
      remaining = remaining.slice(match.index + 1);
    } else {
      break;
    }
  }

  const tail = remaining.trim();
  if (tail && !TERMINATOR_ONLY_PATTERN.test(tail)) {
    segments.push(tail);
  }

  return segments;
}

export function useVoiceSession(options: UseVoiceSessionOptions): UseVoiceSessionReturn {
  const {
    enabled,
    cameraEnabled = false,
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

  const { classify } = useVisionIntent();

  // PTT 屏幕上下文：Rust 端在 PTT 按下时异步截图后发射 voice-ptt-context DOM 事件
  const pttScreenContextRef = useRef<PttScreenContext | null>(null);
  const pttPendingPromiseRef = useRef<{ resolve: (ctx: PttScreenContext | null) => void } | null>(null);

  useEffect(() => {
    const handlePttStart = () => {
      pttScreenContextRef.current = null;
    };

    const handlePttContext = (e: Event) => {
      const detail = (e as CustomEvent<PttScreenContext>).detail;
      if (detail?.screenshot || detail?.extractedText) {
        pttScreenContextRef.current = detail;
        if (pttPendingPromiseRef.current) {
          pttPendingPromiseRef.current.resolve(detail);
          pttPendingPromiseRef.current = null;
        }
      }
    };

    window.addEventListener('voice-ptt-start', handlePttStart);
    window.addEventListener('voice-ptt-context', handlePttContext);
    return () => {
      window.removeEventListener('voice-ptt-start', handlePttStart);
      window.removeEventListener('voice-ptt-context', handlePttContext);
    };
  }, []);

  const tts = useTTS({ mode: ttsMode, provider: ttsProvider });

  const agentBridge = useVoiceAgentBridge({
    enabled: mode === 'agent_bridge',
    agentId,
    chatId,
    keyterms,
    onError,
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
    getVideoFrame: cameraEnabled
      ? () => {
          const frame = camera.captureSnapshot();
          return frame?.base64 ? `data:image/jpeg;base64,${frame.base64}` : null;
        }
      : undefined,
  });

  const camera = useCameraInput({
    onError: (err) => onError?.(`Camera: ${err}`),
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

      let visionFrames: VisualFrame[] | undefined;
      let finalText = text;

      if (cameraEnabled && camera.cameraState === 'active') {
        const intent = classify(text);
        if (intent.needsVision) {
          visionFrames = camera.getFramesForSpeech();
        }
      }

      // PTT 屏幕上下文汇聚屏障锁（Barrier Sync）：
      // 若当前处于 PTT 模式且截图仍在传输，等待最多 250ms 汇聚窗口
      let pttCtx = pttScreenContextRef.current;
      if (!pttCtx && speechMode === 'push-to-talk') {
        pttCtx = await new Promise<PttScreenContext | null>((resolve) => {
          const timer = setTimeout(() => {
            pttPendingPromiseRef.current = null;
            resolve(null);
          }, 250);
          pttPendingPromiseRef.current = {
            resolve: (ctx) => {
              clearTimeout(timer);
              resolve(ctx);
            },
          };
        });
      }
      pttScreenContextRef.current = null;

      if (pttCtx && Date.now() - pttCtx.timestamp < 30_000) {
        if (pttCtx.screenshot) {
          const screenFrame: VisualFrame = {
            id: `ptt-screen-${pttCtx.timestamp}`,
            base64: pttCtx.screenshot,
            width: 0,
            height: 0,
            timestamp: pttCtx.timestamp,
          };
          visionFrames = visionFrames ? [...visionFrames, screenFrame] : [screenFrame];
        }

        const contextParts: string[] = [];
        if (pttCtx.windowTitle) {
          contextParts.push(`[Active Window: ${pttCtx.windowTitle}]`);
        }
        if (pttCtx.extractedText) {
          contextParts.push(`[Screen Text: ${pttCtx.extractedText.slice(0, 2000)}]`);
        }
        if (contextParts.length > 0) {
          finalText = `${contextParts.join('\n')}\n\n${text}`;
        }
      }

      onSendMessage?.(finalText, visionFrames);
    },
    [autoSend, fullDuplex, tts, cameraEnabled, camera, classify, onSendMessage, mode, speechMode],
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

    const segment = pendingTTSRef.current.shift()!;
    tts.speak(segment);
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
      if (cameraEnabled) {
        void camera.startCamera();
      }
      geminiLive.connect();
      return;
    }

    if (mode === 'agent_bridge') {
      agentBridge.connect();
      return;
    }

    if (cameraEnabled) {
      void camera.startCamera();
    }

    speech.startRecording();
  }, [enabled, cameraEnabled, camera, speech, mode, agentBridge, realtimeVoice, geminiLive]);

  const stopSession = useCallback(() => {
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
    camera.stopCamera();

    setSessionState('inactive');
  }, [speech, tts, camera, mode, agentBridge, realtimeVoice, geminiLive]);

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

  // Sync agent bridge state → session state
  useEffect(() => {
    if (mode !== 'agent_bridge') {
      return;
    }
    const bridgeState = agentBridge.state;
    switch (bridgeState) {
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
  }, [mode, agentBridge.state]);

  // Sync realtime voice state → session state
  useEffect(() => {
    if (mode !== 'openai_realtime') {
      return;
    }
    const rtState = realtimeVoice.state;
    switch (rtState) {
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
  }, [mode, realtimeVoice.state]);

  // Sync Gemini Live state → session state
  useEffect(() => {
    if (mode !== 'gemini_live') {
      return;
    }
    const glState = geminiLive.state;
    switch (glState) {
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
  }, [mode, geminiLive.state]);

  useEffect(() => {
    return () => {
      sessionActiveRef.current = false;
      pendingTTSRef.current = [];
    };
  }, []);

  // External event bus listeners (from Tauri Pet companion or global shortcuts)
  useEffect(() => {
    const handleToggle = () => {
      if (sessionActiveRef.current) {
        stopSession();
      } else {
        startSession();
      }
    };

    const handleInterrupt = () => {
      interruptTTS();
    };

    const handleReplay = () => {
      replayLastTTS();
    };

    window.addEventListener('myrm-voice-toggle', handleToggle);
    window.addEventListener('myrm-voice-interrupt', handleInterrupt);
    window.addEventListener('myrm-voice-replay', handleReplay);

    return () => {
      window.removeEventListener('myrm-voice-toggle', handleToggle);
      window.removeEventListener('myrm-voice-interrupt', handleInterrupt);
      window.removeEventListener('myrm-voice-replay', handleReplay);
    };
  }, [startSession, stopSession, interruptTTS, replayLastTTS]);

  const isRealtime = mode === 'openai_realtime';
  const isGeminiLive = mode === 'gemini_live';
  const isAgentBridge = mode === 'agent_bridge';
  const currentAudioLevel = isAgentBridge ? agentBridge.audioLevel : speech.audioLevel;

  // Broadcast unified voice state for satellites / companion / Pet overlay
  useEffect(() => {
    const mappedState =
      sessionState === 'inactive'
        ? 'idle'
        : sessionState === 'speaking'
          ? 'speaking'
          : sessionState === 'processing'
            ? 'processing'
            : 'listening';

    window.dispatchEvent(
      new CustomEvent('myrm-voice-state-update', {
        detail: {
          voiceState: mappedState,
          audioLevel: currentAudioLevel,
        },
      }),
    );
  }, [sessionState, currentAudioLevel]);

  return {
    sessionState,
    isActive: sessionState !== 'inactive',
    startSession,
    stopSession,
    interruptTTS,
    speakResponse,
    replayLastTTS,
    lastSpokenText: lastSpokenTextRef.current,
    interimText: isRealtime
      ? realtimeVoice.interimText
      : isGeminiLive
        ? geminiLive.interimText
        : isAgentBridge
          ? agentBridge.interimText
          : speech.interimText,
    audioLevel: isAgentBridge ? agentBridge.audioLevel : speech.audioLevel,
    cameraState: camera.cameraState,
    facingMode: camera.facingMode,
    videoRef: camera.videoRef,
    toggleFacing: camera.toggleFacing,
    ttsState: tts.state,
    agentResponseText: isRealtime
      ? realtimeVoice.responseText
      : isGeminiLive
        ? geminiLive.responseText
        : isAgentBridge
          ? agentBridge.agentResponseText
          : agentResponseText,
    agentToolName: isAgentBridge ? agentBridge.agentToolName : agentToolName,
  };
}
