/**
 * [INPUT]
 * - @/lib/api::getWsUrl (POS: WS URL builder)
 *
 * [OUTPUT]
 * - useVoiceAgentBridge: WebSocket-based voice agent bridge for server-side Agent execution
 *
 * [POS]
 * Voice Agent Bridge hook. Manages a single WebSocket to /ws/voice/session in agent_bridge mode.
 * Handles: mic audio → server STT → server Agent → streaming TTS audio playback.
 * Provides state for UI rendering (agent thinking, response text, tool use).
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { getWsUrl } from '@/lib/api';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import type { ToolApprovalRequest } from '@/store/chat/types';

export type AgentBridgeState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'listening'
  | 'agent_thinking'
  | 'agent_speaking'
  | 'error';

interface UseVoiceAgentBridgeOptions {
  enabled: boolean;
  agentId?: string;
  chatId?: string;
  keyterms?: string[];
  onError?: (error: string) => void;
  onAgentResponse?: (text: string, done: boolean) => void;
  onAgentToolUse?: (toolName: string) => void;
  onAgentTurnChange?: (state: 'thinking' | 'done', turnId: string) => void;
}

interface UseVoiceAgentBridgeReturn {
  state: AgentBridgeState;
  connect: () => void;
  disconnect: () => void;
  cancelTts: () => void;
  interimText: string;
  agentResponseText: string;
  agentToolName: string;
  audioLevel: number;
}

const AUDIO_CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    sampleRate: 48000,
    channelCount: 1,
  },
};

export function useVoiceAgentBridge(options: UseVoiceAgentBridgeOptions): UseVoiceAgentBridgeReturn {
  const { enabled, agentId, chatId, keyterms, onError, onAgentResponse, onAgentToolUse, onAgentTurnChange } = options;

  const [state, setState] = useState<AgentBridgeState>('disconnected');
  const [interimText, setInterimText] = useState('');
  const [agentResponseText, setAgentResponseText] = useState('');
  const [agentToolName, setAgentToolName] = useState('');
  const [audioLevel, setAudioLevel] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const ttsChunksRef = useRef<ArrayBuffer[]>([]);
  const ttsPlayQueueRef = useRef<Blob[]>([]);
  const ttsPlayingRef = useRef(false);
  const ttsAudioElementRef = useRef<HTMLAudioElement | null>(null);
  const ttsBlobUrlRef = useRef<string | null>(null);
  const responseAccumRef = useRef('');

  const stopTtsPlayback = useCallback(() => {
    if (ttsAudioElementRef.current) {
      ttsAudioElementRef.current.pause();
      ttsAudioElementRef.current.src = '';
      ttsAudioElementRef.current = null;
    }
    if (ttsBlobUrlRef.current) {
      URL.revokeObjectURL(ttsBlobUrlRef.current);
      ttsBlobUrlRef.current = null;
    }
    ttsChunksRef.current = [];
    ttsPlayQueueRef.current = [];
    ttsPlayingRef.current = false;
  }, []);

  const cleanup = useCallback(() => {
    if (levelTimerRef.current) {
      clearInterval(levelTimerRef.current);
      levelTimerRef.current = null;
    }
    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
      analyserRef.current = null;
    }
    stopTtsPlayback();
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
    }
    setAudioLevel(0);
    setInterimText('');
    setAgentResponseText('');
    setAgentToolName('');
    responseAccumRef.current = '';
  }, [stopTtsPlayback]);

  const startAudioLevelMonitor = useCallback(() => {
    if (!analyserRef.current) return;
    const analyser = analyserRef.current;
    const data = new Uint8Array(analyser.fftSize);

    levelTimerRef.current = setInterval(() => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const val = (data[i] - 128) / 128;
        sum += val * val;
      }
      const rms = Math.sqrt(sum / data.length);
      setAudioLevel(Math.min(1, rms * 4));
    }, 50);
  }, []);

  const connect = useCallback(() => {
    if (!enabled) return;
    cleanup();

    setState('connecting');

    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const base = getWsUrl('/ws/voice/session');
    const wsUrl = token ? `${base}?token=${encodeURIComponent(token)}` : base;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: 'config',
          mode: 'agent_bridge',
          agent_id: agentId ?? null,
          chat_id: chatId ?? null,
          keyterms: keyterms ?? [],
        }),
      );

      void navigator.mediaDevices
        .getUserMedia(AUDIO_CONSTRAINTS)
        .then((stream) => {
          if (wsRef.current !== ws) {
            stream.getTracks().forEach((t) => t.stop());
            return;
          }
          streamRef.current = stream;

          const actx = new AudioContext({ sampleRate: 48000 });
          audioContextRef.current = actx;
          const source = actx.createMediaStreamSource(stream);
          const analyser = actx.createAnalyser();
          analyser.fftSize = 256;
          source.connect(analyser);
          analyserRef.current = analyser;
          startAudioLevelMonitor();

          const recorder = new MediaRecorder(stream, {
            mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm',
          });
          recorderRef.current = recorder;

          recorder.ondataavailable = (e) => {
            if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) {
              void e.data.arrayBuffer().then((buf) => {
                if (ws.readyState === WebSocket.OPEN) {
                  ws.send(buf);
                }
              });
            }
          };

          recorder.start(100);
          setState('listening');
        })
        .catch((err) => {
          onError?.(`Microphone: ${err instanceof Error ? err.message : String(err)}`);
          setState('error');
        });
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        handleTtsAudio(event.data);
        return;
      }

      try {
        const msg = JSON.parse(event.data as string) as Record<string, unknown>;
        handleServerMessage(msg);
      } catch {
        /* ignore malformed */
      }
    };

    ws.onerror = () => {
      onError?.('Voice session connection error');
      setState('error');
    };

    ws.onclose = () => {
      cleanup();
      setState('disconnected');
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, agentId, chatId, keyterms, cleanup, startAudioLevelMonitor]);

  const handleTtsAudio = useCallback((buffer: ArrayBuffer) => {
    ttsChunksRef.current.push(buffer);
  }, []);

  const playNextInQueue = useCallback(() => {
    const blob = ttsPlayQueueRef.current.shift();
    if (!blob) {
      ttsPlayingRef.current = false;
      return;
    }

    ttsPlayingRef.current = true;

    if (ttsBlobUrlRef.current) {
      URL.revokeObjectURL(ttsBlobUrlRef.current);
    }

    const url = URL.createObjectURL(blob);
    ttsBlobUrlRef.current = url;

    const audio = new Audio(url);
    ttsAudioElementRef.current = audio;
    audio.onended = () => {
      if (ttsBlobUrlRef.current === url) {
        URL.revokeObjectURL(url);
        ttsBlobUrlRef.current = null;
      }
      ttsAudioElementRef.current = null;
      playNextInQueue();
    };
    audio.onerror = () => {
      ttsAudioElementRef.current = null;
      playNextInQueue();
    };
    void audio.play().catch(() => {
      ttsAudioElementRef.current = null;
      playNextInQueue();
    });
  }, []);

  const enqueueTtsSegment = useCallback(() => {
    const chunks = ttsChunksRef.current;
    ttsChunksRef.current = [];

    if (chunks.length === 0) return;

    const blob = new Blob(chunks, { type: 'audio/mpeg' });
    ttsPlayQueueRef.current.push(blob);

    if (!ttsPlayingRef.current) {
      playNextInQueue();
    }
  }, [playNextInQueue]);

  const handleServerMessage = useCallback(
    (msg: Record<string, unknown>) => {
      const type = msg.type as string;

      switch (type) {
        case 'stt_interim':
          setInterimText(msg.text as string);
          break;

        case 'stt_final':
          setInterimText('');
          break;

        case 'agent_thinking':
          setState('agent_thinking');
          responseAccumRef.current = '';
          setAgentResponseText('');
          setAgentToolName('');
          onAgentTurnChange?.('thinking', msg.turn_id as string);
          break;

        case 'agent_response': {
          const text = msg.text as string;
          const done = msg.done as boolean;
          responseAccumRef.current += text;
          setAgentResponseText(responseAccumRef.current);
          setState('agent_speaking');
          onAgentResponse?.(text, done);
          break;
        }

        case 'agent_tool_use':
          setAgentToolName(msg.tool_name as string);
          onAgentToolUse?.(msg.tool_name as string);
          break;

        case 'agent_done':
          setState('listening');
          onAgentTurnChange?.('done', msg.turn_id as string);
          break;

        case 'agent_error':
          setState('listening');
          onError?.(msg.message as string);
          break;

        case 'tts_start':
          ttsChunksRef.current = [];
          break;

        case 'tts_end':
          enqueueTtsSegment();
          break;

        case 'tool_approval_request': {
          const payload = msg.data as Record<string, unknown>;
          if (payload) {
            const { actionRequests, reviewConfigs, extensions } = payload as {
              actionRequests: Array<{
                action: string;
                args: Record<string, unknown>;
                description: string;
                domains?: string[];
                ptc_annotations?: Record<string, boolean>;
              }>;
              reviewConfigs?: Array<{
                allowedDecisions?: Array<'approve' | 'reject' | 'edit'>;
                domainApproval?: boolean;
              }>;
              extensions: {
                timeout: { seconds: number; expiresAt: number; behavior: 'deny' | 'allow' };
                approval: { requestId: string };
                displayMode: 'approval' | 'handover';
              };
            };
            const messageId = (msg.messageId as string) || '';
            const isBatch = actionRequests.length > 1;
            const batchId = isBatch ? extensions.approval.requestId : null;

            for (let i = 0; i < actionRequests.length; i++) {
              const action = actionRequests[i];
              const reviewConfig = reviewConfigs?.[i];
              const requestId = isBatch ? `${batchId}_${i}` : extensions.approval.requestId;
              const approvalRequest: ToolApprovalRequest = {
                requestId,
                toolName: action.action,
                toolInput: action.args,
                reason: action.description,
                timeoutSeconds: extensions.timeout.seconds,
                expiresAt: extensions.timeout.expiresAt,
                timeoutBehavior: extensions.timeout.behavior || 'deny',
                messageId,
                displayMode: extensions.displayMode,
                batchId: batchId || undefined,
                batchIndex: isBatch ? i : undefined,
                batchSize: isBatch ? actionRequests.length : undefined,
                chatId: chatId || '',
                actionMode: 'agent',
                domains: Array.isArray(action.domains) ? action.domains : undefined,
                domainApproval: reviewConfig?.domainApproval === true ? true : undefined,
                ptcAnnotations: action.ptc_annotations,
              };
              useToolApprovalStore.getState().addRequest(approvalRequest);
            }
          }
          setState('listening');
          break;
        }

        case 'approval_required':
          setState('listening');
          break;

        case 'error':
          onError?.(msg.message as string);
          break;
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    },
    [onAgentResponse, onAgentToolUse, onAgentTurnChange, onError, enqueueTtsSegment, chatId],
  );

  const disconnect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'close' }));
    }
    cleanup();
    setState('disconnected');
  }, [cleanup]);

  const cancelTts = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'tts_cancel' }));
    }
    stopTtsPlayback();
  }, [stopTtsPlayback]);

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return {
    state,
    connect,
    disconnect,
    cancelTts,
    interimText,
    agentResponseText,
    agentToolName,
    audioLevel,
  };
}
