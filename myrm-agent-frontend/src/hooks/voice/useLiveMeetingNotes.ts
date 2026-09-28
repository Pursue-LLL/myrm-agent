/**
 * [INPUT]
 * - @/services/liveMeeting::ingestLiveTranscript,finalizeLiveMeeting (POS: live meeting API client)
 *
 * [OUTPUT]
 * - useLiveMeetingNotes: live meeting session orchestration hook
 *
 * [POS]
 * Live meeting notes hook. Owns the live session id, drains finalized transcript lines
 * to the server (single-flight queue), and exposes the rolling structured-notes snapshot
 * for the in-meeting Live board. Best-effort: a dropped line never breaks the voice session.
 */

'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import {
  finalizeLiveMeeting,
  ingestLiveTranscript,
  type LiveMeetingSnapshot,
} from '@/services/liveMeeting';

export interface UseLiveMeetingNotesReturn {
  sessionId: string;
  snapshot: LiveMeetingSnapshot | null;
  ingest: (text: string) => void;
  finalize: () => Promise<LiveMeetingSnapshot | null>;
  reset: () => void;
}

function newSessionId(): string {
  const rand = Math.random().toString(16).slice(2, 10);
  return `live-${Date.now().toString(36)}-${rand}`;
}

export function useLiveMeetingNotes(): UseLiveMeetingNotesReturn {
  const [sessionId, setSessionId] = useState(newSessionId);
  const [snapshot, setSnapshot] = useState<LiveMeetingSnapshot | null>(null);
  const inFlightRef = useRef(false);
  const queueRef = useRef<string[]>([]);

  const flush = useCallback(async () => {
    if (inFlightRef.current) {
      return;
    }
    const next = queueRef.current.shift();
    if (next === undefined) {
      return;
    }
    inFlightRef.current = true;
    try {
      const result = await ingestLiveTranscript(sessionId, next);
      setSnapshot(result);
    } catch {
      // Best-effort: dropped transcript lines must not break the voice session.
    } finally {
      inFlightRef.current = false;
      if (queueRef.current.length > 0) {
        void flush();
      }
    }
  }, [sessionId]);

  const ingest = useCallback(
    (text: string) => {
      const cleaned = text.trim();
      if (!cleaned) {
        return;
      }
      queueRef.current.push(cleaned);
      void flush();
    },
    [flush],
  );

  const finalize = useCallback(async () => {
    try {
      const result = await finalizeLiveMeeting(sessionId);
      setSnapshot(result);
      return result;
    } catch {
      return null;
    }
  }, [sessionId]);

  const reset = useCallback(() => {
    queueRef.current = [];
    inFlightRef.current = false;
    setSnapshot(null);
    setSessionId(newSessionId());
  }, []);

  return useMemo(
    () => ({ sessionId, snapshot, ingest, finalize, reset }),
    [sessionId, snapshot, ingest, finalize, reset],
  );
}
