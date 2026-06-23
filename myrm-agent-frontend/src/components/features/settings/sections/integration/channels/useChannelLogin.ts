'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { LoginEvent } from '@/types/channels';
import { LoginStatus } from '@/types/channels';
import { startLogin, subscribeLoginStream, cancelLogin } from '@/services/channels';

export type ChannelLoginPhase =
  | 'idle'
  | 'starting'
  | 'waiting_qr'
  | 'scanned'
  | 'success'
  | 'failed'
  | 'cancelled';

export interface UseChannelLoginReturn {
  phase: ChannelLoginPhase;
  qrCodeBase64: string | null;
  errorMessage: string | null;
  progressPercent: number | null;
  start: () => Promise<void>;
  cancel: () => void;
  reset: () => void;
}

/**
 * Encapsulates the full QR code login lifecycle via SSE.
 *
 * Handles: session creation → SSE subscription → state machine →
 * EventSource cleanup on unmount/cancel/completion.
 */
export function useChannelLogin(
  channelId: string,
  loginMethod: string,
  onSuccess?: () => void,
): UseChannelLoginReturn {
  const [phase, setPhase] = useState<ChannelLoginPhase>('idle');
  const [qrCodeBase64, setQrCodeBase64] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [progressPercent, setProgressPercent] = useState<number | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const mountedRef = useRef(true);

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cleanup();
    };
  }, [cleanup]);

  const handleLoginEvent = useCallback(
    (event: LoginEvent) => {
      if (!mountedRef.current) return;

      const { status, qr_code_base64, error_message, progress_percent } = event.state;

      if (progress_percent != null) setProgressPercent(progress_percent);

      switch (status) {
        case LoginStatus.GENERATING:
          setPhase('starting');
          break;

        case LoginStatus.WAITING_USER_ACTION:
          if (qr_code_base64) setQrCodeBase64(qr_code_base64);
          setPhase('waiting_qr');
          break;

        case LoginStatus.VALIDATING:
          setPhase('scanned');
          break;

        case LoginStatus.SUCCESS:
          setPhase('success');
          cleanup();
          onSuccess?.();
          break;

        case LoginStatus.FAILED:
        case LoginStatus.TIMEOUT:
          setPhase('failed');
          setErrorMessage(error_message ?? 'Login failed');
          cleanup();
          break;

        case LoginStatus.CANCELLED:
          setPhase('cancelled');
          cleanup();
          break;
      }
    },
    [cleanup, onSuccess],
  );

  const phaseRef = useRef<ChannelLoginPhase>('idle');
  phaseRef.current = phase;

  const start = useCallback(async () => {
    cleanup();
    setPhase('starting');
    setQrCodeBase64(null);
    setErrorMessage(null);
    setProgressPercent(null);

    try {
      const resp = await startLogin(channelId, loginMethod);
      if (!mountedRef.current) return;

      sessionIdRef.current = resp.session_id;

      const es = subscribeLoginStream(resp.session_id, handleLoginEvent, () => {
        if (!mountedRef.current) return;
        if (phaseRef.current !== 'success' && phaseRef.current !== 'cancelled') {
          setPhase('failed');
          setErrorMessage('Connection lost');
        }
      });
      eventSourceRef.current = es;
    } catch (err) {
      if (!mountedRef.current) return;
      setPhase('failed');
      setErrorMessage(err instanceof Error ? err.message : 'Failed to start login');
    }
  }, [channelId, loginMethod, cleanup, handleLoginEvent]);

  const cancel = useCallback(() => {
    setPhase('cancelled');
    cleanup();
    if (sessionIdRef.current) {
      cancelLogin(sessionIdRef.current).catch(() => {});
      sessionIdRef.current = null;
    }
  }, [cleanup]);

  const reset = useCallback(() => {
    cleanup();
    setPhase('idle');
    setQrCodeBase64(null);
    setErrorMessage(null);
    setProgressPercent(null);
    sessionIdRef.current = null;
  }, [cleanup]);

  return { phase, qrCodeBase64, errorMessage, progressPercent, start, cancel, reset };
}
