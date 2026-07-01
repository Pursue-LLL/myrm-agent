/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: API request utilities)
 *
 * [OUTPUT]
 * - useRealtimeVoice: OpenAI Realtime WebRTC voice session hook
 *
 * [POS]
 * OpenAI Realtime API WebRTC integration. Connects browser directly to OpenAI
 * for sub-300ms voice latency via RTCPeerConnection. Falls back to agent_bridge
 * mode if WebRTC connection fails.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiRequest } from '@/lib/api';

export type RealtimeVoiceState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'error';

interface RealtimeTokenResponse {
  client_secret: string;
  model: string;
  voice: string;
  expires_at: number | null;
  instructions: string | null;
  tools: Array<{ type: string; name: string; description: string; parameters: Record<string, unknown> }>;
}

interface UseRealtimeVoiceOptions {
  enabled: boolean;
  agentId?: string;
  chatId?: string;
  voice?: string;
  model?: string;
  onTranscript?: (entry: { role: 'user' | 'assistant'; text: string }) => void;
  onToolCall?: (name: string, args: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  onFallback?: () => void;
  fallbackTimeoutMs?: number;
}

interface UseRealtimeVoiceReturn {
  state: RealtimeVoiceState;
  connect: () => void;
  disconnect: () => void;
  interimText: string;
  responseText: string;
}

const ICE_TIMEOUT_MS = 3000;
const OPENAI_REALTIME_OFFER_URL = 'https://api.openai.com/v1/realtime/calls';

export function useRealtimeVoice(options: UseRealtimeVoiceOptions): UseRealtimeVoiceReturn {
  const {
    enabled,
    agentId,
    chatId,
    voice,
    model,
    onTranscript,
    onToolCall,
    onError,
    onFallback,
    fallbackTimeoutMs = ICE_TIMEOUT_MS,
  } = options;

  const [state, setState] = useState<RealtimeVoiceState>('idle');
  const [interimText, setInterimText] = useState('');
  const [responseText, setResponseText] = useState('');

  const peerRef = useRef<RTCPeerConnection | null>(null);
  const channelRef = useRef<RTCDataChannel | null>(null);
  const mediaRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const closedRef = useRef(false);
  const transcriptBufferRef = useRef<Array<{ role: 'user' | 'assistant'; text: string }>>([]);
  const handleEventRef = useRef<(data: unknown) => void>(() => {});
  const responseActiveRef = useRef(false);
  const responsePendingRef = useRef(false);

  const cleanup = useCallback(() => {
    closedRef.current = true;
    responseActiveRef.current = false;
    responsePendingRef.current = false;
    channelRef.current?.close();
    channelRef.current = null;
    peerRef.current?.close();
    peerRef.current = null;
    mediaRef.current?.getTracks().forEach((t) => t.stop());
    mediaRef.current = null;
    if (audioRef.current) {
      audioRef.current.remove();
      audioRef.current = null;
    }
  }, []);

  const persistTranscript = useCallback(async () => {
    if (!chatId || transcriptBufferRef.current.length === 0) return;
    try {
      await apiRequest('/voice/realtime-transcript', {
        method: 'POST',
        body: JSON.stringify({
          chat_id: chatId,
          entries: transcriptBufferRef.current,
        }),
      });
    } catch {
      /* best-effort */
    }
    transcriptBufferRef.current = [];
  }, [chatId]);

  const executeToolCall = useCallback(
    async (name: string, callId: string, args: string) => {
      onToolCall?.(name, JSON.parse(args || '{}'));
      try {
        const resp = await apiRequest<{ result: unknown; error: string | null }>('/voice/realtime-tool-exec', {
          method: 'POST',
          body: JSON.stringify({
            tool_name: name,
            arguments: JSON.parse(args || '{}'),
            agent_id: agentId,
            chat_id: chatId,
          }),
        });
        return resp.error ? `Error: ${resp.error}` : JSON.stringify(resp.result);
      } catch (err) {
        return `Tool execution failed: ${err}`;
      }
    },
    [agentId, chatId, onToolCall],
  );

  const requestResponseCreate = useCallback(() => {
    if (responseActiveRef.current) {
      responsePendingRef.current = true;
      return;
    }
    responsePendingRef.current = false;
    const ch = channelRef.current;
    if (ch?.readyState === 'open') {
      ch.send(JSON.stringify({ type: 'response.create' }));
    }
  }, []);

  const flushPendingResponse = useCallback(() => {
    if (!responsePendingRef.current) return;
    responsePendingRef.current = false;
    requestResponseCreate();
  }, [requestResponseCreate]);

  const connect = useCallback(async () => {
    if (!enabled) return;
    closedRef.current = false;
    setState('connecting');
    setInterimText('');
    setResponseText('');
    transcriptBufferRef.current = [];

    try {
      const tokenResp = await apiRequest<RealtimeTokenResponse>('/voice/realtime-token', {
        method: 'POST',
        body: JSON.stringify({ agent_id: agentId, voice, model }),
      });

      if (!tokenResp.client_secret) {
        throw new Error('Failed to get realtime token');
      }

      const peer = new RTCPeerConnection();
      peerRef.current = peer;

      const audio = document.createElement('audio');
      audio.autoplay = true;
      audio.style.display = 'none';
      document.body.appendChild(audio);
      audioRef.current = audio;

      peer.addEventListener('track', (event) => {
        if (audio) {
          audio.srcObject = event.streams[0];
        }
      });

      const media = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      mediaRef.current = media;
      for (const track of media.getAudioTracks()) {
        peer.addTrack(track, media);
      }

      const channel = peer.createDataChannel('oai-events');
      channelRef.current = channel;

      channel.addEventListener('open', () => {
        if (!closedRef.current) setState('listening');
      });

      channel.addEventListener('message', (event) => {
        if (closedRef.current) return;
        handleEventRef.current(event.data);
      });

      const connectionTimeout = setTimeout(() => {
        if (peer.connectionState !== 'connected') {
          cleanup();
          setState('idle');
          onFallback?.();
        }
      }, fallbackTimeoutMs);

      peer.addEventListener('connectionstatechange', () => {
        if (peer.connectionState === 'connected') {
          clearTimeout(connectionTimeout);
        }
        if (peer.connectionState === 'failed' || peer.connectionState === 'closed') {
          if (!closedRef.current) {
            setState('error');
            onError?.('WebRTC connection lost');
          }
        }
      });

      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);

      const sdpResp = await fetch(OPENAI_REALTIME_OFFER_URL, {
        method: 'POST',
        body: offer.sdp,
        headers: {
          Authorization: `Bearer ${tokenResp.client_secret}`,
          'Content-Type': 'application/sdp',
        },
      });

      if (!sdpResp.ok) {
        throw new Error(`WebRTC SDP exchange failed: ${sdpResp.status}`);
      }

      const answerSdp = await sdpResp.text();
      await peer.setRemoteDescription({ type: 'answer', sdp: answerSdp });
    } catch (err) {
      cleanup();
      setState('idle');
      onError?.(err instanceof Error ? err.message : String(err));
      onFallback?.();
    }
  }, [enabled, agentId, voice, model, cleanup, fallbackTimeoutMs, onError, onFallback]);

  const handleServerEvent = useCallback(
    (data: unknown) => {
      let event: Record<string, unknown>;
      try {
        event = JSON.parse(String(data));
      } catch {
        return;
      }

      switch (event.type) {
        case 'conversation.item.input_audio_transcription.completed':
          if (event.transcript) {
            const text = String(event.transcript);
            setInterimText(text);
            onTranscript?.({ role: 'user', text });
            transcriptBufferRef.current.push({ role: 'user', text });
          }
          break;

        case 'response.audio_transcript.done':
          if (event.transcript) {
            const text = String(event.transcript);
            setResponseText(text);
            onTranscript?.({ role: 'assistant', text });
            transcriptBufferRef.current.push({ role: 'assistant', text });
          }
          break;

        case 'response.function_call_arguments.done': {
          const name = String(event.name || '');
          const callId = String(event.call_id || '');
          const args = String(event.arguments || '{}');
          if (callId) {
            void executeToolCall(name, callId, args).then((result) => {
              const ch = channelRef.current;
              if (ch?.readyState === 'open') {
                ch.send(
                  JSON.stringify({
                    type: 'conversation.item.create',
                    item: {
                      type: 'function_call_output',
                      call_id: callId,
                      output: result,
                    },
                  }),
                );
                requestResponseCreate();
              }
            });
          }
          break;
        }

        case 'input_audio_buffer.speech_started':
          setState('listening');
          break;

        case 'input_audio_buffer.speech_stopped':
          setState('thinking');
          break;

        case 'response.created':
          responseActiveRef.current = true;
          setState('thinking');
          break;

        case 'response.done':
        case 'response.cancelled':
          responseActiveRef.current = false;
          setState('listening');
          flushPendingResponse();
          break;

        case 'error':
          setState('error');
          onError?.(String((event.error as Record<string, unknown>)?.message || 'Realtime error'));
          break;
      }
    },
    [onTranscript, onError, executeToolCall, requestResponseCreate, flushPendingResponse],
  );

  handleEventRef.current = handleServerEvent;

  const disconnect = useCallback(() => {
    cleanup();
    void persistTranscript();
    setState('idle');
  }, [cleanup, persistTranscript]);

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return {
    state,
    connect,
    disconnect,
    interimText,
    responseText,
  };
}
