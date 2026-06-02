'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { getApiUrl } from '@/lib/api';
import { stripMarkdown } from '@/lib/utils/messageUtils';

export type TTSState = 'idle' | 'playing' | 'paused' | 'loading';
export type TTSMode = 'browser' | 'api';

interface UseTTSOptions {
  rate?: number;
  lang?: string;
  mode?: TTSMode;
  provider?: string;
}

interface UseTTSReturn {
  state: TTSState;
  speak: (text: string) => void;
  pause: () => void;
  resume: () => void;
  stop: () => void;
  toggle: (text: string) => void;
  supported: boolean;
}

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function buildRequestBody(text: string, provider?: string) {
  return JSON.stringify({
    text: text.slice(0, 10000),
    ...(provider && provider !== 'browser' ? { provider } : {}),
  });
}

const MSE_SUPPORTED =
  typeof window !== 'undefined' && 'MediaSource' in window && MediaSource.isTypeSupported('audio/mpeg');

// ---------------------------------------------------------------------------
// Browser TTS (SpeechSynthesis API)
// ---------------------------------------------------------------------------

function useBrowserTTS(options: UseTTSOptions): UseTTSReturn {
  const { rate = 1.0, lang } = options;
  const [state, setState] = useState<TTSState>('idle');
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    utteranceRef.current = null;
    setState('idle');
  }, [supported]);

  useEffect(() => {
    return () => {
      if (supported) window.speechSynthesis.cancel();
    };
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported) return;
      window.speechSynthesis.cancel();
      const cleaned = stripMarkdown(text);
      if (!cleaned) return;

      const utterance = new SpeechSynthesisUtterance(cleaned);
      utterance.rate = rate;
      if (lang) utterance.lang = lang;

      utterance.onstart = () => setState('playing');
      utterance.onend = () => {
        utteranceRef.current = null;
        setState('idle');
      };
      utterance.onerror = () => {
        utteranceRef.current = null;
        setState('idle');
      };

      utteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
    },
    [supported, rate, lang],
  );

  const pause = useCallback(() => {
    if (!supported || state !== 'playing') return;
    window.speechSynthesis.pause();
    setState('paused');
  }, [supported, state]);

  const resume = useCallback(() => {
    if (!supported || state !== 'paused') return;
    window.speechSynthesis.resume();
    setState('playing');
  }, [supported, state]);

  const toggle = useCallback(
    (text: string) => {
      if (state === 'playing') pause();
      else if (state === 'paused') resume();
      else speak(text);
    },
    [state, pause, resume, speak],
  );

  return { state, speak, pause, resume, stop, toggle, supported };
}

// ---------------------------------------------------------------------------
// API TTS (backend /api/tts with streaming + MSE fallback)
// ---------------------------------------------------------------------------

function useApiTTS(options: UseTTSOptions): UseTTSReturn {
  const { provider } = options;
  const [state, setState] = useState<TTSState>('idle');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const mediaSourceRef = useRef<MediaSource | null>(null);

  const cleanup = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute('src');
      audioRef.current.load();
      audioRef.current = null;
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
    if (mediaSourceRef.current?.readyState === 'open') {
      try {
        mediaSourceRef.current.endOfStream();
      } catch {
        /* already ended */
      }
    }
    mediaSourceRef.current = null;
  }, []);

  const stop = useCallback(() => {
    cleanup();
    setState('idle');
  }, [cleanup]);

  useEffect(() => stop, [stop]);

  const speakStream = useCallback(
    async (cleaned: string, controller: AbortController) => {
      const mediaSource = new MediaSource();
      mediaSourceRef.current = mediaSource;
      const audio = new Audio();
      audioRef.current = audio;
      audio.src = URL.createObjectURL(mediaSource);
      blobUrlRef.current = audio.src;

      await new Promise<void>((resolve) => {
        mediaSource.addEventListener('sourceopen', () => resolve(), { once: true });
      });

      const sourceBuffer = mediaSource.addSourceBuffer('audio/mpeg');
      const queue: Uint8Array[] = [];
      let feeding = false;

      const feedBuffer = () => {
        if (feeding || !queue.length || sourceBuffer.updating) return;
        feeding = true;
        const chunk = queue.shift()!;
        try {
          sourceBuffer.appendBuffer(chunk as unknown as BufferSource);
        } catch {
          feeding = false;
          return;
        }
      };

      sourceBuffer.addEventListener('updateend', () => {
        feeding = false;
        if (queue.length) feedBuffer();
      });

      const resp = await fetch(getApiUrl('/tts/synthesize-stream'), {
        method: 'POST',
        headers: getAuthHeaders(),
        body: buildRequestBody(cleaned, provider),
        signal: controller.signal,
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`TTS stream error ${resp.status}`);
      }

      audio.onplay = () => setState('playing');
      audio.onended = () => {
        stop();
      };
      audio.onerror = () => {
        stop();
      };

      const reader = resp.body.getReader();
      let started = false;

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!value?.length) continue;

        queue.push(value);
        feedBuffer();

        if (!started) {
          started = true;
          audio.play().catch(() => {
            stop();
          });
        }
      }

      // Wait for SourceBuffer to flush remaining data
      if (queue.length || sourceBuffer.updating) {
        await new Promise<void>((resolve) => {
          const check = () => {
            if (!queue.length && !sourceBuffer.updating) {
              resolve();
            } else {
              feedBuffer();
              sourceBuffer.addEventListener('updateend', check, { once: true });
            }
          };
          check();
        });
      }

      if (mediaSource.readyState === 'open') {
        mediaSource.endOfStream();
      }
    },
    [provider, stop],
  );

  const speakFull = useCallback(
    async (cleaned: string, controller: AbortController) => {
      const resp = await fetch(getApiUrl('/tts/synthesize'), {
        method: 'POST',
        headers: getAuthHeaders(),
        body: buildRequestBody(cleaned, provider),
        signal: controller.signal,
      });

      if (!resp.ok) {
        throw new Error(`TTS API error ${resp.status}`);
      }

      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      blobUrlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onplay = () => setState('playing');
      const done = () => {
        if (blobUrlRef.current === url) {
          URL.revokeObjectURL(url);
          blobUrlRef.current = null;
        }
        audioRef.current = null;
        setState('idle');
      };
      audio.onended = done;
      audio.onerror = done;

      await audio.play();
    },
    [provider],
  );

  const speak = useCallback(
    async (text: string) => {
      stop();
      const cleaned = stripMarkdown(text);
      if (!cleaned) return;

      setState('loading');
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        if (MSE_SUPPORTED) {
          await speakStream(cleaned, controller);
        } else {
          await speakFull(cleaned, controller);
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        console.error('TTS API speak failed:', err);
        setState('idle');
      }
    },
    [stop, speakStream, speakFull],
  );

  const pause = useCallback(() => {
    if (state !== 'playing' || !audioRef.current) return;
    audioRef.current.pause();
    setState('paused');
  }, [state]);

  const resume = useCallback(() => {
    if (state !== 'paused' || !audioRef.current) return;
    audioRef.current.play();
    setState('playing');
  }, [state]);

  const toggle = useCallback(
    (text: string) => {
      if (state === 'playing') pause();
      else if (state === 'paused') resume();
      else speak(text);
    },
    [state, pause, resume, speak],
  );

  return { state, speak, pause, resume, stop, toggle, supported: true };
}

// ---------------------------------------------------------------------------
// Main hook
// ---------------------------------------------------------------------------

export function useTTS(options: UseTTSOptions = {}): UseTTSReturn {
  const mode = options.mode ?? 'browser';
  const browserTTS = useBrowserTTS(options);
  const apiTTS = useApiTTS(options);
  return mode === 'api' ? apiTTS : browserTTS;
}
