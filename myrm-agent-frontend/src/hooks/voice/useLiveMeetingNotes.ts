/**
 * [INPUT]
 * - @/services/liveMeeting::ingestLiveTranscript,finalizeLiveMeeting (POS: live meeting API client)
 *
 * [OUTPUT]
 * - useLiveMeetingNotes: live meeting session orchestration hook
 *
 * [POS]
 * Live meeting notes hook. Owns the live session id (resumed across reloads via
 * sessionStorage when a stable key is given), drains finalized transcript lines to the
 * server (single-flight queue), and exposes the rolling structured-notes snapshot for the
 * in-meeting Live board. Best-effort: a dropped line never breaks the voice session.
 */

'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import {
  finalizeLiveMeeting,
  ingestLiveTranscript,
  type LiveMeetingSnapshot,
  type LiveTranscriptLine,
} from '@/services/liveMeeting';

export interface UseLiveMeetingNotesReturn {
  sessionId: string;
  snapshot: LiveMeetingSnapshot | null;
  ingest: (text: string, timestamp?: number) => void;
  finalize: () => Promise<LiveMeetingSnapshot | null>;
}

const STORAGE_PREFIX = 'myrm-live-notes:';

function newSessionId(): string {
  const rand = Math.random().toString(16).slice(2, 10);
  return `live-${Date.now().toString(36)}-${rand}`;
}

/** Stable per-utterance id so a replayed ingest cannot duplicate the line. */
function newLineId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `line-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 10)}`;
}

function storageKey(sessionKey: string): string {
  return `${STORAGE_PREFIX}${sessionKey}`;
}

/** Resume the live session id for a stable key (e.g. chatId) across page reloads. */
function resolveInitialSessionId(sessionKey: string | undefined): string {
  if (!sessionKey || typeof window === 'undefined') {
    return newSessionId();
  }
  try {
    const existing = window.sessionStorage.getItem(storageKey(sessionKey));
    if (existing) {
      return existing;
    }
    const fresh = newSessionId();
    window.sessionStorage.setItem(storageKey(sessionKey), fresh);
    return fresh;
  } catch {
    return newSessionId();
  }
}

export function useLiveMeetingNotes(sessionKey?: string): UseLiveMeetingNotesReturn {
  const [sessionId] = useState(() => resolveInitialSessionId(sessionKey));
  const [snapshot, setSnapshot] = useState<LiveMeetingSnapshot | null>(null);
  const inFlightRef = useRef(false);
  const queueRef = useRef<LiveTranscriptLine[]>([]);

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
    (text: string, timestamp?: number) => {
      const cleaned = text.trim();
      if (!cleaned) {
        return;
      }
      queueRef.current.push({ id: newLineId(), text: cleaned, ...(timestamp !== undefined ? { timestamp } : {}) });
      void flush();
    },
    [flush],
  );

  const finalize = useCallback(async () => {
    try {
      const result = await finalizeLiveMeeting(sessionId);
      setSnapshot(result);
      if (sessionKey && typeof window !== 'undefined') {
        window.sessionStorage.removeItem(storageKey(sessionKey));
      }
      return result;
    } catch {
      return null;
    }
  }, [sessionId, sessionKey]);

  return useMemo(
    () => ({ sessionId, snapshot, ingest, finalize }),
    [sessionId, snapshot, ingest, finalize],
  );
}
