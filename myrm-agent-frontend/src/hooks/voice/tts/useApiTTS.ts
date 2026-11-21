/**
 * [INPUT]
 * hooks/voice/tts/types (POS: Type vocabulary shared by the TTS engines and the useTTS facade)
 * lib/api::getApiUrl (POS: Frontend API access layer: request base URL, timeout and error normalisation)
 * lib/utils/toast::toast (POS: unified toast wrapper)
 * lib/utils/messageUtils::stripMarkdown (POS: Message text cleanup and formatting toolkit)
 *
 * [OUTPUT]
 * useApiTTS: Text-to-speech engine on the backend synthesis endpoints
 *
 * [POS]
 * API TTS engine. Streams `/tts/synthesize-stream` into a MediaSource buffer, falls back to the one-shot
 * `/tts/synthesize` blob when MediaSource cannot play MP3, and reports a failed synthesis through a toast.
 * Only one API instance speaks at a time: starting speech stops whichever instance (message row) was speaking.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { getApiUrl } from '@/lib/api';
import { toast } from '@/lib/utils/toast';
import { stripMarkdown } from '@/lib/utils/messageUtils';
import type { TTSEngine, TTSState, UseTTSOptions } from './types';

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

class TtsRequestError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`TTS request failed with status ${status}`);
    this.name = 'TtsRequestError';
    this.status = status;
  }
}

// Audio elements do not queue behind one another and every message row mounts its own engine, so this slot is what
// keeps two rows from speaking at once: an engine that starts speaking stops the one holding it. A stop only touches
// the stopped engine's own audio and request, so stopping a holder that has already finished is harmless.
let speakerStop: (() => void) | null = null;

export function useApiTTS(options: UseTTSOptions): TTSEngine {
  const { provider } = options;
  const tVoice = useTranslations('voice');
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

  // Unmounting ends what this instance voices and gives up its place as the speaker.
  useEffect(
    () => () => {
      stop();
      if (speakerStop === stop) {
        speakerStop = null;
      }
    },
    [stop],
  );

  const notifyTtsFailure = useCallback(
    (status: number) => {
      if (status === 503) {
        toast.error(tVoice('edgeTtsUnavailableTitle'), {
          description: tVoice('edgeTtsUnavailableDesc'),
        });
        return;
      }
      toast.error(tVoice('ttsPlaybackFailedTitle'), {
        description: tVoice('ttsPlaybackFailedDesc'),
      });
    },
    [tVoice],
  );

  const assertTtsResponseOk = useCallback(async (resp: Response): Promise<void> => {
    if (resp.ok) {
      return;
    }
    throw new TtsRequestError(resp.status);
  }, []);

  const speakStream = useCallback(
    async (cleaned: string, controller: AbortController) => {
      const resp = await fetch(getApiUrl('/tts/synthesize-stream'), {
        method: 'POST',
        headers: getAuthHeaders(),
        body: buildRequestBody(cleaned, provider),
        signal: controller.signal,
      });

      await assertTtsResponseOk(resp);
      if (!resp.body) {
        throw new TtsRequestError(resp.status);
      }

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
      const feeder = { busy: false };

      const feedBuffer = () => {
        if (feeder.busy || !queue.length || sourceBuffer.updating) {
          return;
        }
        feeder.busy = true;
        const chunk = queue.shift();
        try {
          sourceBuffer.appendBuffer(chunk as unknown as BufferSource);
        } catch {
          feeder.busy = false;
          return;
        }
      };

      sourceBuffer.addEventListener('updateend', () => {
        feeder.busy = false;
        if (queue.length) {
          feedBuffer();
        }
      });

      audio.onplay = () => setState('playing');
      audio.onended = () => {
        stop();
      };
      audio.onerror = () => {
        stop();
      };

      const reader = resp.body.getReader();
      let started = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        if (!value?.length) {
          continue;
        }

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
    [provider, stop, assertTtsResponseOk],
  );

  const speakFull = useCallback(
    async (cleaned: string, controller: AbortController) => {
      const resp = await fetch(getApiUrl('/tts/synthesize'), {
        method: 'POST',
        headers: getAuthHeaders(),
        body: buildRequestBody(cleaned, provider),
        signal: controller.signal,
      });

      await assertTtsResponseOk(resp);

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
    [provider, assertTtsResponseOk],
  );

  const speak = useCallback(
    async (text: string) => {
      stop();
      const cleaned = stripMarkdown(text);
      if (!cleaned) {
        return;
      }

      if (speakerStop && speakerStop !== stop) {
        speakerStop();
      }
      speakerStop = stop;

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
        if (err instanceof DOMException && err.name === 'AbortError') {
          return;
        }
        if (err instanceof TtsRequestError) {
          notifyTtsFailure(err.status);
        } else {
          notifyTtsFailure(0);
        }
        setState('idle');
      }
    },
    [stop, speakStream, speakFull, notifyTtsFailure],
  );

  const pause = useCallback(() => {
    if (state !== 'playing' || !audioRef.current) {
      return;
    }
    audioRef.current.pause();
    setState('paused');
  }, [state]);

  const resume = useCallback(() => {
    if (state !== 'paused' || !audioRef.current) {
      return;
    }
    audioRef.current.play();
    setState('playing');
  }, [state]);

  return { state, speak, pause, resume, stop, supported: true };
}
