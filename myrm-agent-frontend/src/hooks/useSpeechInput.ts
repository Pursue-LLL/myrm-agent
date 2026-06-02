'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest, ApiError, getWsUrl } from '@/lib/api';

export type SpeechState = 'idle' | 'recording' | 'transcribing';
export type SpeechMode = 'toggle' | 'push-to-talk';
type SttBackend = 'server' | 'browser' | 'unknown';

interface TranscribeResult {
  text: string;
  language: string | null;
  duration: number | null;
}

interface UseSpeechInputOptions {
  onTranscript: (text: string) => void;
  onInterimTranscript?: (text: string) => void;
  onError?: (error: string) => void;
  maxDuration?: number;
  silenceTimeout?: number;
  silenceThreshold?: number;
  minDuration?: number;
  mode?: SpeechMode;
  enableSounds?: boolean;
  keyterms?: string[];
}

const PREFERRED_MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];

const SILENCE_CHECK_INTERVAL_MS = 100;
const DEFAULT_SILENCE_TIMEOUT_MS = 2000;
const DEFAULT_SILENCE_THRESHOLD = 0.01;
const DEFAULT_MIN_DURATION_MS = 500;

function getSupportedMimeType(): string {
  for (const mime of PREFERRED_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return '';
}

function getBrowserSpeechRecognition(): typeof SpeechRecognition | null {
  if (typeof window === 'undefined') return null;
  return (window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null) as typeof SpeechRecognition | null;
}

function playTone(frequency: number, endFrequency: number, duration: number) {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(frequency, ctx.currentTime);
    osc.frequency.linearRampToValueAtTime(endFrequency, ctx.currentTime + duration / 1000);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.linearRampToValueAtTime(0, ctx.currentTime + duration / 1000);
    osc.start();
    osc.stop(ctx.currentTime + duration / 1000);
    osc.onended = () => ctx.close();
  } catch {
    /* audio context unavailable */
  }
}

export function useSpeechInput({
  onTranscript,
  onInterimTranscript,
  onError,
  maxDuration = 60,
  silenceTimeout = DEFAULT_SILENCE_TIMEOUT_MS,
  silenceThreshold = DEFAULT_SILENCE_THRESHOLD,
  minDuration = DEFAULT_MIN_DURATION_MS,
  mode = 'toggle',
  enableSounds = false,
  keyterms,
}: UseSpeechInputOptions) {
  const [state, setState] = useState<SpeechState>('idle');
  const [elapsed, setElapsed] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [interimText, setInterimText] = useState('');

  const sttBackendRef = useRef<SttBackend>('unknown');
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef(0);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const silenceStartRef = useRef(0);
  const animFrameRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = 0;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        /* ignore */
      }
      recognitionRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close();
      } catch {
        /* ignore */
      }
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
    silenceStartRef.current = 0;
    setElapsed(0);
    setAudioLevel(0);
    setInterimText('');
  }, []);

  useEffect(() => cleanup, [cleanup]);

  // ── Audio analysis (silence detection + volume level) ──

  const adaptiveThresholdRef = useRef(silenceThreshold);
  const CALIBRATION_MS = 500;
  const CALIBRATION_MARGIN = 2.5;

  const setupAudioAnalysis = useCallback(
    (stream: MediaStream) => {
      try {
        const ctx = new AudioContext();
        audioContextRef.current = ctx;
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.3;
        source.connect(analyser);
        analyserRef.current = analyser;

        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        const calibrationStart = Date.now();
        let calibrationSamples: number[] = [];
        let calibrated = false;
        adaptiveThresholdRef.current = silenceThreshold;

        const tick = () => {
          if (!analyserRef.current) return;
          analyser.getByteFrequencyData(dataArray);

          let sum = 0;
          for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i] * dataArray[i];
          }
          const rms = Math.sqrt(sum / dataArray.length) / 255;
          setAudioLevel(rms);

          if (!calibrated && Date.now() - calibrationStart < CALIBRATION_MS) {
            calibrationSamples.push(rms);
            animFrameRef.current = requestAnimationFrame(tick);
            return;
          }

          if (!calibrated) {
            calibrated = true;
            if (calibrationSamples.length > 0) {
              const avgNoise = calibrationSamples.reduce((a, b) => a + b, 0) / calibrationSamples.length;
              adaptiveThresholdRef.current = Math.max(silenceThreshold, avgNoise * CALIBRATION_MARGIN);
            }
            calibrationSamples = [];
          }

          const threshold = adaptiveThresholdRef.current;

          if (rms < threshold) {
            if (!silenceStartRef.current) {
              silenceStartRef.current = Date.now();
            } else if (Date.now() - silenceStartRef.current > silenceTimeout) {
              const elapsedMs = Date.now() - startTimeRef.current;
              if (elapsedMs > minDuration && stateRef.current === 'recording') {
                stopRecording();
                return;
              }
            }
          } else {
            silenceStartRef.current = 0;
          }

          animFrameRef.current = requestAnimationFrame(tick);
        };

        animFrameRef.current = requestAnimationFrame(tick);
      } catch {
        /* AudioContext unavailable */
      }
    },
    [silenceThreshold, silenceTimeout, minDuration],
  );

  // ── WebSocket streaming STT (Deepgram via backend proxy) ──

  const startStreamingSTT = useCallback(
    (stream: MediaStream) => {
      const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
      const base = getWsUrl('/ws/stt/stream');
      const wsUrl = token ? `${base}?token=${encodeURIComponent(token)}` : base;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ keyterms: keyterms ?? [] }));

        const mimeType = getSupportedMimeType();
        if (!mimeType) return;

        const recorder = new MediaRecorder(stream, { mimeType, audioBitsPerSecond: 64000 });
        recorderRef.current = recorder;

        recorder.ondataavailable = (e) => {
          if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) {
            ws.send(e.data);
          }
        };

        recorder.onstop = () => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'close' }));
          }
        };

        recorder.start(SILENCE_CHECK_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string) as {
            type: string;
            text?: string;
            is_final?: boolean;
            message?: string;
            fallback?: string;
          };
          if (data.type === 'transcript' && data.text) {
            if (data.is_final) {
              setInterimText('');
              onTranscript(data.text);
            } else {
              setInterimText(data.text);
              onInterimTranscript?.(data.text);
            }
          } else if (data.type === 'info' && data.fallback === 'batch') {
            sttBackendRef.current = 'server';
          } else if (data.type === 'error') {
            onError?.(data.message ?? 'STT error');
          }
        } catch {
          /* ignore malformed messages */
        }
      };

      ws.onerror = () => {
        wsRef.current = null;
        onError?.('STT streaming connection failed');
      };

      ws.onclose = (event) => {
        wsRef.current = null;
        if (stateRef.current === 'recording') {
          if (recorderRef.current?.state === 'recording') {
            recorderRef.current.stop();
          }
          cleanup();

          if (event.code !== 1000) {
            sttBackendRef.current = 'server';
          }
          setState('idle');
        }
      };
    },
    [keyterms, onTranscript, onInterimTranscript, onError, cleanup],
  );

  // ── Server-side STT (MediaRecorder → upload) ──

  const transcribeViaServer = useCallback(
    async (blob: Blob) => {
      setState('transcribing');
      try {
        const formData = new FormData();
        const ext = blob.type.includes('webm') ? 'webm' : blob.type.includes('ogg') ? 'ogg' : 'mp4';
        formData.append('file', blob, `recording.${ext}`);

        const result = await apiRequest<TranscribeResult>('/stt/transcribe', {
          method: 'POST',
          body: formData,
        });
        if (result.text) {
          sttBackendRef.current = 'server';
          onTranscript(result.text);
        }
      } catch (err) {
        if (err instanceof ApiError && err.code === 400) {
          sttBackendRef.current = 'browser';
          onError?.('STT not configured, switching to browser speech recognition');
        } else {
          const msg = err instanceof Error ? err.message : 'Transcription failed';
          onError?.(msg);
        }
      } finally {
        setState('idle');
      }
    },
    [onTranscript, onError],
  );

  const startServerRecording = useCallback(
    async (stream: MediaStream, useStreaming: boolean) => {
      if (useStreaming) {
        startStreamingSTT(stream);
        return;
      }

      const mimeType = getSupportedMimeType();
      if (!mimeType) {
        onError?.('Browser does not support audio recording');
        return;
      }

      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        cleanup();
        if (blob.size > 1024) {
          transcribeViaServer(blob);
        } else {
          setState('idle');
        }
      };

      recorder.start(250);
    },
    [onError, cleanup, transcribeViaServer, startStreamingSTT],
  );

  // ── Browser-native STT (Web Speech API) ──

  const startBrowserRecording = useCallback(() => {
    const SRConstructor = getBrowserSpeechRecognition();
    if (!SRConstructor) {
      onError?.('Browser speech recognition not supported');
      return;
    }

    const recognition = new SRConstructor();
    recognitionRef.current = recognition;
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = navigator.language || 'zh-CN';

    let finalText = '';

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalText += event.results[i][0].transcript;
        }
      }
    };

    recognition.onend = () => {
      cleanup();
      if (finalText.trim()) {
        onTranscript(finalText.trim());
      }
      setState('idle');
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      cleanup();
      if (event.error !== 'aborted' && event.error !== 'no-speech') {
        onError?.(`Speech recognition error: ${event.error}`);
      }
      setState('idle');
    };

    recognition.start();
  }, [onTranscript, onError, cleanup]);

  // ── Unified start/stop ──

  const stopRecording = useCallback(() => {
    const elapsedMs = Date.now() - startTimeRef.current;
    if (elapsedMs < minDuration && startTimeRef.current > 0) {
      cleanup();
      onError?.('tooShort');
      setState('idle');
      return;
    }

    if (enableSounds) playTone(880, 440, 150);

    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.stop();
    }
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
  }, [minDuration, enableSounds, cleanup, onError]);

  const startRecording = useCallback(async () => {
    if (stateRef.current !== 'idle') return;

    try {
      setState('recording');
      startTimeRef.current = Date.now();
      silenceStartRef.current = 0;

      if (enableSounds) playTone(440, 880, 150);

      if (sttBackendRef.current === 'browser') {
        startBrowserRecording();
      } else {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRef.current = stream;
        setupAudioAnalysis(stream);

        const useStreaming = (keyterms != null && keyterms.length > 0) || sttBackendRef.current === 'unknown';
        await startServerRecording(stream, useStreaming);
      }

      timerRef.current = setInterval(() => {
        const secs = Math.floor((Date.now() - startTimeRef.current) / 1000);
        setElapsed(secs);
        if (secs >= maxDuration) {
          stopRecording();
        }
      }, 200);
    } catch {
      cleanup();
      onError?.('Microphone access denied');
      setState('idle');
    }
  }, [
    maxDuration,
    enableSounds,
    keyterms,
    onError,
    cleanup,
    startServerRecording,
    startBrowserRecording,
    setupAudioAnalysis,
    stopRecording,
  ]);

  const toggle = useCallback(() => {
    if (state === 'recording') {
      stopRecording();
    } else if (state === 'idle') {
      startRecording();
    }
  }, [state, startRecording, stopRecording]);

  // ── Push-to-talk handlers ──

  const onPointerDown = useCallback(() => {
    if (mode === 'push-to-talk') {
      startRecording();
    }
  }, [mode, startRecording]);

  const onPointerUp = useCallback(() => {
    if (mode === 'push-to-talk' && stateRef.current === 'recording') {
      stopRecording();
    }
  }, [mode, stopRecording]);

  const isSupported = useMemo(() => {
    if (typeof window === 'undefined') return false;
    const hasMediaRecorder = !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined';
    const hasSpeechRecognition = !!getBrowserSpeechRecognition();
    return hasMediaRecorder || hasSpeechRecognition;
  }, []);

  return {
    state,
    elapsed,
    audioLevel,
    interimText,
    toggle,
    startRecording,
    stopRecording,
    onPointerDown,
    onPointerUp,
    isSupported,
    mode,
  };
}
