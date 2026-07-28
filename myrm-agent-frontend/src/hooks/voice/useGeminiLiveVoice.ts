/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: API request utilities)
 *
 * [OUTPUT]
 * - useGeminiLiveVoice: Gemini Live WebSocket voice session hook
 *
 * [POS]
 * Gemini Multimodal Live API WebSocket integration. Connects browser directly
 * to Google for sub-300ms voice latency via WebSocket + AudioWorklet.
 * Supports video multimodal input (camera frames as JPEG).
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiRequest } from '@/lib/api';

export type GeminiLiveState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'error';

interface GeminiFunctionDeclaration {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

interface GeminiLiveTokenResponse {
  ws_url: string;
  model: string;
  instructions: string | null;
  tools: GeminiFunctionDeclaration[];
}

interface UseGeminiLiveVoiceOptions {
  enabled: boolean;
  agentId?: string;
  chatId?: string;
  model?: string;
  onTranscript?: (entry: { role: 'user' | 'assistant'; text: string }) => void;
  onToolCall?: (name: string, args: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  onFallback?: () => void;
  getVideoFrame?: () => string | null;
}

interface UseGeminiLiveVoiceReturn {
  state: GeminiLiveState;
  connect: () => void;
  disconnect: () => void;
  interimText: string;
  responseText: string;
}

const CONNECT_TIMEOUT_MS = 5000;
const AUDIO_SAMPLE_RATE_INPUT = 16000;
const AUDIO_SAMPLE_RATE_OUTPUT = 24000;
const VIDEO_FRAME_INTERVAL_MS = 1000;

export function useGeminiLiveVoice(options: UseGeminiLiveVoiceOptions): UseGeminiLiveVoiceReturn {
  const { enabled, agentId, chatId, model, onTranscript, onError, onFallback, onToolCall, getVideoFrame } = options;

  const [state, setState] = useState<GeminiLiveState>('idle');
  const [interimText, setInterimText] = useState('');
  const [responseText, setResponseText] = useState('');

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const mediaRef = useRef<MediaStream | null>(null);
  const closedRef = useRef(false);
  const transcriptBufferRef = useRef<Array<{ role: 'user' | 'assistant'; text: string }>>([]);
  const audioQueueRef = useRef<ArrayBuffer[]>([]);
  const nextPlayTimeRef = useRef(0);
  const videoIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const cleanup = useCallback(() => {
    closedRef.current = true;
    if (videoIntervalRef.current) {
      clearInterval(videoIntervalRef.current);
      videoIntervalRef.current = null;
    }
    wsRef.current?.close();
    wsRef.current = null;
    processorNodeRef.current?.disconnect();
    processorNodeRef.current = null;
    void audioCtxRef.current?.close();
    audioCtxRef.current = null;
    mediaRef.current?.getTracks().forEach((t) => t.stop());
    mediaRef.current = null;
    audioQueueRef.current = [];
    nextPlayTimeRef.current = 0;
  }, []);

  const scheduleAudioChunk = useCallback((pcmData: ArrayBuffer) => {
    const ctx = audioCtxRef.current;
    if (!ctx || ctx.state === 'closed') return;

    const samples = new Int16Array(pcmData);
    const float32 = new Float32Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      float32[i] = samples[i] / 32768;
    }

    const buffer = ctx.createBuffer(1, float32.length, AUDIO_SAMPLE_RATE_OUTPUT);
    buffer.copyToChannel(float32, 0);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    const startTime = Math.max(now, nextPlayTimeRef.current);
    source.start(startTime);
    nextPlayTimeRef.current = startTime + buffer.duration;
  }, []);

  const processAudioQueue = useCallback(() => {
    while (audioQueueRef.current.length > 0) {
      const chunk = audioQueueRef.current.shift()!;
      scheduleAudioChunk(chunk);
    }
  }, [scheduleAudioChunk]);

  const sendVideoFrame = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !getVideoFrame) return;

    const frame = getVideoFrame();
    if (!frame) return;

    const base64Data = frame.replace(/^data:image\/jpeg;base64,/, '');
    ws.send(
      JSON.stringify({
        realtimeInput: {
          mediaChunks: [{ mimeType: 'image/jpeg', data: base64Data }],
        },
      }),
    );
  }, [getVideoFrame]);

  const persistTranscript = useCallback(async () => {
    if (!chatId || transcriptBufferRef.current.length === 0) return;
    try {
      await apiRequest('/voice/realtime-transcript', {
        method: 'POST',
        body: JSON.stringify({ chat_id: chatId, entries: transcriptBufferRef.current }),
      });
    } catch {
      /* best-effort */
    }
    transcriptBufferRef.current = [];
  }, [chatId]);

  const executeToolCall = useCallback(
    async (name: string, args: Record<string, unknown>, _callId: string) => {
      onToolCall?.(name, args);
      try {
        const resp = await apiRequest<{ result: unknown; error: string | null }>('/voice/realtime-tool-exec', {
          method: 'POST',
          body: JSON.stringify({ tool_name: name, arguments: args, agent_id: agentId, chat_id: chatId }),
        });
        return resp.error ? `Error: ${resp.error}` : JSON.stringify(resp.result);
      } catch (err) {
        return `Tool execution failed: ${err}`;
      }
    },
    [agentId, chatId, onToolCall],
  );

  const startAudioCapture = useCallback(() => {
    const media = mediaRef.current;
    const ws = wsRef.current;
    const audioCtx = audioCtxRef.current;
    if (!media || !ws || !audioCtx) return;

    const source = audioCtx.createMediaStreamSource(media);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (e) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      const inputData = e.inputBuffer.getChannelData(0);

      const ratio = audioCtx.sampleRate / AUDIO_SAMPLE_RATE_INPUT;
      const outputLength = Math.floor(inputData.length / ratio);
      const pcm16 = new Int16Array(outputLength);

      for (let i = 0; i < outputLength; i++) {
        const sample = inputData[Math.floor(i * ratio)];
        pcm16[i] = Math.max(-32768, Math.min(32767, Math.floor(sample * 32768)));
      }

      const base64 = btoa(String.fromCharCode(...new Uint8Array(pcm16.buffer)));
      ws.send(
        JSON.stringify({
          realtimeInput: {
            mediaChunks: [{ mimeType: 'audio/pcm;rate=16000', data: base64 }],
          },
        }),
      );
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);
    processorNodeRef.current = processor;
  }, []);

  const handleServerMessage = useCallback(
    async (data: unknown) => {
      let msg: Record<string, unknown>;
      try {
        if (data instanceof Blob) {
          const text = await data.text();
          msg = JSON.parse(text);
        } else {
          msg = JSON.parse(String(data));
        }
      } catch {
        return;
      }

      if (msg.setupComplete) {
        setState('listening');
        startAudioCapture();
        if (getVideoFrame) {
          videoIntervalRef.current = setInterval(sendVideoFrame, VIDEO_FRAME_INTERVAL_MS);
        }
        return;
      }

      const serverContent = msg.serverContent as Record<string, unknown> | undefined;
      if (serverContent) {
        const parts = (serverContent.modelTurn as Record<string, unknown>)?.parts as
          Array<Record<string, unknown>> | undefined;
        if (parts) {
          for (const part of parts) {
            if (part.inlineData) {
              const inlineData = part.inlineData as Record<string, string>;
              if (inlineData.mimeType?.startsWith('audio/')) {
                const audioBytes = Uint8Array.from(atob(inlineData.data), (c) => c.charCodeAt(0));
                audioQueueRef.current.push(audioBytes.buffer);
                processAudioQueue();
                setState('speaking');
              }
            }
            if (typeof part.text === 'string' && part.text) {
              setResponseText(part.text);
              onTranscript?.({ role: 'assistant', text: part.text });
              transcriptBufferRef.current.push({ role: 'assistant', text: part.text });
            }
          }
        }
        if (serverContent.turnComplete) {
          setState('listening');
        }
      }

      const toolCall = msg.toolCall as Record<string, unknown> | undefined;
      if (toolCall) {
        const functionCalls = toolCall.functionCalls as Array<Record<string, unknown>> | undefined;
        if (functionCalls) {
          setState('thinking');
          const responses: Array<Record<string, unknown>> = [];
          for (const fc of functionCalls) {
            const name = String(fc.name || '');
            const id = String(fc.id || '');
            const args = (fc.args || {}) as Record<string, unknown>;
            const result = await executeToolCall(name, args, id);
            responses.push({ id, name, response: { result } });
          }
          wsRef.current?.send(JSON.stringify({ toolResponse: { functionResponses: responses } }));
        }
      }

      const transcription = msg.serverContent as Record<string, unknown> | undefined;
      if (transcription?.inputTranscription) {
        const text = String(transcription.inputTranscription);
        setInterimText(text);
        setState('thinking');
        onTranscript?.({ role: 'user', text });
        transcriptBufferRef.current.push({ role: 'user', text });
      }
    },
    [onTranscript, executeToolCall, processAudioQueue, getVideoFrame, sendVideoFrame, startAudioCapture],
  );

  const connect = useCallback(async () => {
    if (!enabled) return;
    closedRef.current = false;
    setState('connecting');
    setInterimText('');
    setResponseText('');
    transcriptBufferRef.current = [];
    audioQueueRef.current = [];

    try {
      const tokenResp = await apiRequest<GeminiLiveTokenResponse>('/voice/gemini-live-token', {
        method: 'POST',
        body: JSON.stringify({ agent_id: agentId, model }),
      });

      if (!tokenResp.ws_url) {
        throw new Error('Failed to get Gemini Live token');
      }

      const audioCtx = new AudioContext({ sampleRate: AUDIO_SAMPLE_RATE_OUTPUT });
      audioCtxRef.current = audioCtx;

      const media = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: AUDIO_SAMPLE_RATE_INPUT, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      mediaRef.current = media;

      const ws = new WebSocket(tokenResp.ws_url);
      wsRef.current = ws;

      const connectTimeout = setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN) {
          cleanup();
          setState('idle');
          onFallback?.();
        }
      }, CONNECT_TIMEOUT_MS);

      ws.addEventListener('open', () => {
        clearTimeout(connectTimeout);
        const setupPayload: Record<string, unknown> = {
          model: `models/${tokenResp.model}`,
          generationConfig: {
            responseModalities: ['AUDIO'],
            speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: 'Aoede' } } },
          },
        };
        if (tokenResp.instructions) {
          setupPayload.systemInstruction = { parts: [{ text: tokenResp.instructions }] };
        }
        if (tokenResp.tools && tokenResp.tools.length > 0) {
          setupPayload.tools = [
            {
              functionDeclarations: tokenResp.tools.map((t) => ({
                name: t.name,
                description: t.description,
                parameters: t.parameters,
              })),
            },
          ];
        }
        ws.send(JSON.stringify({ setup: setupPayload }));
      });

      ws.addEventListener('message', (event) => {
        if (closedRef.current) return;
        void handleServerMessage(event.data);
      });

      ws.addEventListener('close', () => {
        if (!closedRef.current) {
          setState('idle');
        }
      });

      ws.addEventListener('error', () => {
        if (!closedRef.current) {
          cleanup();
          setState('idle');
          onError?.('Gemini Live WebSocket error');
          onFallback?.();
        }
      });
    } catch (err) {
      cleanup();
      setState('idle');
      onError?.(err instanceof Error ? err.message : String(err));
      onFallback?.();
    }
  }, [enabled, agentId, model, cleanup, onError, onFallback, handleServerMessage]);

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

  return { state, connect, disconnect, interimText, responseText };
}
