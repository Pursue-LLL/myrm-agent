/**
 * Hook for session-scoped recurring loop status, countdown, and controls.
 *
 * [INPUT]
 * @/services/sessionLoop::{SessionLoopStatus, getSessionLoopStatus, stopSessionLoop}
 *
 * [OUTPUT]
 * useLoopStatus -> { status, countdown, isLoading, isStopping, error, stopLoop, refetch }
 *
 * [POS]
 * Client-side reactive polling and lifecycle hook for /loop scheduler.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { getSessionLoopStatus, stopSessionLoop, type SessionLoopStatus } from '@/services/sessionLoop';

export interface UseLoopStatusResult {
  status: SessionLoopStatus | null;
  countdown: number;
  isLoading: boolean;
  isStopping: boolean;
  error: Error | null;
  stopLoop: (reason?: string) => Promise<void>;
  refetch: () => Promise<void>;
}

export function useLoopStatus(chatId: string | undefined): UseLoopStatusResult {
  const [status, setStatus] = useState<SessionLoopStatus | null>(null);
  const [countdown, setCountdown] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isStopping, setIsStopping] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);

  const mountedRef = useRef<boolean>(true);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async (): Promise<void> => {
    if (!chatId) {
      if (mountedRef.current) {
        setStatus(null);
        setCountdown(0);
      }
      return;
    }

    try {
      const data = await getSessionLoopStatus(chatId);
      if (!mountedRef.current) {
        return;
      }

      setStatus(data);
      setError(null);

      if (data.is_active && data.next_due_in_seconds > 0) {
        setCountdown(Math.max(0, Math.round(data.next_due_in_seconds)));
      } else {
        setCountdown(0);
      }
    } catch (err: unknown) {
      if (!mountedRef.current) {
        return;
      }
      // Network error or 404 should not blow up the UI
      setError(err instanceof Error ? err : new Error(String(err)));
    }
  }, [chatId]);

  const statusRef = useRef<SessionLoopStatus | null>(status);
  statusRef.current = status;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      if (countdownTimerRef.current) {
        clearInterval(countdownTimerRef.current);
        countdownTimerRef.current = null;
      }
    };
  }, []);

  // Main polling lifecycle
  useEffect(() => {
    let isActive = true;

    const poll = async () => {
      if (!isActive || !chatId) {
        return;
      }
      await fetchStatus();

      if (!isActive) {
        return;
      }
      // Active loops poll every 2.5s; inactive loops poll every 10s to conserve resources
      const nextDelay = statusRef.current?.is_active ? 2500 : 10000;
      pollTimerRef.current = setTimeout(poll, nextDelay);
    };

    setIsLoading(true);
    void fetchStatus().finally(() => {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    });

    pollTimerRef.current = setTimeout(poll, 3000);

    return () => {
      isActive = false;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [chatId, fetchStatus]);

  // Countdown timer: 1-second cadence ticker
  useEffect(() => {
    if (!status?.is_active || countdown <= 0) {
      if (countdownTimerRef.current) {
        clearInterval(countdownTimerRef.current);
        countdownTimerRef.current = null;
      }
      return;
    }

    countdownTimerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          // When timer hits 0, trigger a refresh to get the latest status
          void fetchStatus();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (countdownTimerRef.current) {
        clearInterval(countdownTimerRef.current);
        countdownTimerRef.current = null;
      }
    };
  }, [status?.is_active, countdown, fetchStatus]);

  // Instant event synchronization: listen for session-loop-changed events
  useEffect(() => {
    if (typeof window === 'undefined' || !chatId) {
      return;
    }

    const handleLoopChanged = (e: Event) => {
      const detail = (e as CustomEvent<{ chatId?: string }>).detail;
      if (!detail?.chatId || detail.chatId === chatId) {
        void fetchStatus();
      }
    };

    window.addEventListener('session-loop-changed', handleLoopChanged);
    return () => {
      window.removeEventListener('session-loop-changed', handleLoopChanged);
    };
  }, [chatId, fetchStatus]);

  const handleStopLoop = useCallback(
    async (reason: string = 'user_stopped'): Promise<void> => {
      if (!chatId || isStopping) {
        return;
      }
      setIsStopping(true);
      try {
        const updated = await stopSessionLoop(chatId, reason);
        if (mountedRef.current) {
          setStatus(updated);
          setCountdown(0);
        }
      } catch (err: unknown) {
        if (mountedRef.current) {
          setError(err instanceof Error ? err : new Error(String(err)));
        }
      } finally {
        if (mountedRef.current) {
          setIsStopping(false);
        }
      }
    },
    [chatId, isStopping],
  );

  return {
    status,
    countdown,
    isLoading,
    isStopping,
    error,
    stopLoop: handleStopLoop,
    refetch: fetchStatus,
  };
}
