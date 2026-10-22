/**
 * [INPUT]
 * - sessionId: Target active chat session ID
 * - options: { enabled?: boolean; onDelta?: (delta: LiveDeltaEvent) => void }
 * - useZeroReplayReconnectStore: Zustand store
 *
 * [OUTPUT]
 * - useZeroReplayStream: Core hook managing atomic snapshot fetch and zero-replay live SSE stream
 *
 * [POS]
 * Client-side streaming hook for Item 36 P0. Strictly under 220 lines. Zero `any`.
 */

import { useEffect, useRef } from 'react';
import type { LiveDeltaEvent } from './reconnectProtocolTypes';
import { useZeroReplayReconnectStore } from './useZeroReplayReconnectStore';

export interface UseZeroReplayStreamOptions {
  enabled?: boolean;
  onDelta?: (delta: LiveDeltaEvent) => void;
}

export function useZeroReplayStream(
  sessionId: string | null,
  options: UseZeroReplayStreamOptions = {},
) {
  const { enabled = true, onDelta } = options;

  const status = useZeroReplayReconnectStore((s) => s.status);
  const snapshot = useZeroReplayReconnectStore((s) => s.snapshot);
  const currentVersion = useZeroReplayReconnectStore((s) => s.currentVersion);
  const currentEpoch = useZeroReplayReconnectStore((s) => s.currentEpoch);
  const reconnectCount = useZeroReplayReconnectStore((s) => s.reconnectCount);
  const error = useZeroReplayReconnectStore((s) => s.error);

  const setActiveSession = useZeroReplayReconnectStore((s) => s.setActiveSession);
  const fetchSnapshot = useZeroReplayReconnectStore((s) => s.fetchSnapshot);
  const setSubscribingLive = useZeroReplayReconnectStore((s) => s.setSubscribingLive);
  const setConnected = useZeroReplayReconnectStore((s) => s.setConnected);
  const handleLiveDelta = useZeroReplayReconnectStore((s) => s.handleLiveDelta);
  const setReconnecting = useZeroReplayReconnectStore((s) => s.setReconnecting);
  const setDisconnected = useZeroReplayReconnectStore((s) => s.setDisconnected);
  const forceResync = useZeroReplayReconnectStore((s) => s.forceResync);

  const eventSourceRef = useRef<EventSource | null>(null);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onDeltaRef = useRef(onDelta);
  onDeltaRef.current = onDelta;

  useEffect(() => {
    setActiveSession(sessionId);
  }, [sessionId, setActiveSession]);

  useEffect(() => {
    if (!enabled || !sessionId) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
      return;
    }

    let isCancelled = false;

    const cleanupCurrentSource = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };

    const startStreamingFlow = async () => {
      cleanupCurrentSource();
      if (isCancelled) {
        return;
      }

      // Stage 1: Atomic Snapshot Baseline Fetch
      const snap = await fetchSnapshot(sessionId);
      if (isCancelled || !snap) {
        return;
      }

      setSubscribingLive();

      // Stage 2: Zero-Replay Live SSE Subscription
      const queryParams = new URLSearchParams({
        client_epoch: snap.epoch_id,
        client_version: String(snap.state_version),
        client_timestamp_ms: String(snap.snapshot_timestamp_ms),
      });

      const sseUrl = `/api/v1/chats/${encodeURIComponent(sessionId)}/live-stream?${queryParams.toString()}`;
      const es = new EventSource(sseUrl);
      eventSourceRef.current = es;

      es.addEventListener('live_ready', (e: MessageEvent) => {
        if (isCancelled) {
          return;
        }
        try {
          const parsed = JSON.parse(e.data) as { epoch_id: string; current_version: number };
          setConnected(parsed.epoch_id, parsed.current_version);
        } catch {
          setConnected(snap.epoch_id, snap.state_version);
        }
      });

      es.addEventListener('live_delta', (e: MessageEvent) => {
        if (isCancelled) {
          return;
        }
        try {
          const delta = JSON.parse(e.data) as LiveDeltaEvent;
          handleLiveDelta(delta);
          if (onDeltaRef.current) {
            onDeltaRef.current(delta);
          }
        } catch {
          // Ignore malformed delta
        }
      });

      es.addEventListener('handshake_failed', () => {
        if (isCancelled) {
          return;
        }
        cleanupCurrentSource();
        setReconnecting();
        // Fallback: Immediate snapshot reload
        retryTimeoutRef.current = setTimeout(() => {
          if (!isCancelled) {
            void startStreamingFlow();
          }
        }, 1000);
      });

      es.onerror = () => {
        if (isCancelled) {
          return;
        }
        cleanupCurrentSource();
        setReconnecting();
        // Exponential/bounded retry
        retryTimeoutRef.current = setTimeout(() => {
          if (!isCancelled) {
            void startStreamingFlow();
          }
        }, 3000);
      };
    };

    void startStreamingFlow();

    return () => {
      isCancelled = true;
      cleanupCurrentSource();
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
    };
  }, [
    enabled,
    sessionId,
    fetchSnapshot,
    setSubscribingLive,
    setConnected,
    handleLiveDelta,
    setReconnecting,
    setDisconnected,
  ]);

  return {
    status,
    snapshot,
    currentVersion,
    currentEpoch,
    reconnectCount,
    error,
    forceResync: () => {
      if (sessionId) {
        void forceResync(sessionId);
      }
    },
  };
}
