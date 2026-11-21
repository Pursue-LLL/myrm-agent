/**
 * [INPUT]
 * - @/services/liveMeeting::ingestLiveTranscript,finalizeLiveMeeting,finalizeLiveMeetingOnPageExit (POS: live meeting API client)
 * - @/lib/api::ApiError (POS: typed API failure carrying the HTTP status)
 * - @/lib/utils/toast::toast (POS: unified toast wrapper)
 *
 * [OUTPUT]
 * - useLiveMeetingNotes: live meeting session orchestration hook
 *
 * [POS]
 * Live meeting notes hook. Owns the live session id (resumed across reloads via
 * sessionStorage when a stable key is given), drains finalized transcript lines to the
 * server (single-flight queue), and exposes the rolling structured-notes snapshot for the
 * in-meeting Live board. The minutes are published into the agent's vault when the voice
 * session stops being active (stop, transport drop, unmount) and the user is told how that
 * went; on page exit a keepalive request publishes what the server holds, unanswered. Line
 * upload is best-effort: a dropped line never breaks the voice session.
 */

'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ApiError } from '@/lib/api';
import { toast } from '@/lib/utils/toast';
import {
  finalizeLiveMeeting,
  finalizeLiveMeetingOnPageExit,
  ingestLiveTranscript,
  type LiveMeetingSnapshot,
  type LiveTranscriptLine,
} from '@/services/liveMeeting';

export interface UseLiveMeetingNotesReturn {
  sessionId: string;
  snapshot: LiveMeetingSnapshot | null;
  ingest: (text: string, timestamp?: number) => void;
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

function forgetStoredSessionId(sessionKey: string | undefined): void {
  if (!sessionKey || typeof window === 'undefined') {
    return;
  }
  try {
    window.sessionStorage.removeItem(storageKey(sessionKey));
  } catch {
    // The stored id only serves resuming after a reload; publishing must not depend on it.
  }
}

/**
 * @param sessionKey Stable key (e.g. chatId) that resumes the live session across reloads.
 * @param agentId Agent whose vault the final minutes are published into.
 * @param active Whether the voice session is running; the minutes are published when it stops being.
 */
export function useLiveMeetingNotes(sessionKey?: string, agentId?: string, active = false): UseLiveMeetingNotesReturn {
  const t = useTranslations('voice.liveNotes');
  const [sessionId] = useState(() => resolveInitialSessionId(sessionKey));
  const [snapshot, setSnapshot] = useState<LiveMeetingSnapshot | null>(null);
  const queueRef = useRef<LiveTranscriptLine[]>([]);
  const inFlightRef = useRef(false);
  const drainRef = useRef<Promise<void>>(Promise.resolve());
  const activeRef = useRef(false);
  // The server holds lines that no published minutes cover yet. Only then is a stop worth a request.
  const unpublishedRef = useRef(false);
  // Set once the minutes of the meeting are on their way: lines after that point belong to no meeting.
  const closedRef = useRef(false);
  const publishingRef = useRef<Promise<void> | null>(null);
  const endRef = useRef<() => Promise<void>>(async () => undefined);

  // One drain loop at a time. Lines queued while a request is in flight are picked up by the
  // running loop, and the guard is released in the same tick the queue is found empty, so a
  // line can never be left waiting without a drainer. While the minutes of the previous meeting
  // are being published, lines of a newer meeting wait in the queue instead (see afterPublish).
  const flush = useCallback(() => {
    if (inFlightRef.current || closedRef.current) {
      return;
    }
    inFlightRef.current = true;
    drainRef.current = (async () => {
      try {
        for (let line = queueRef.current.shift(); line !== undefined; line = queueRef.current.shift()) {
          try {
            setSnapshot(await ingestLiveTranscript(sessionId, line, agentId));
          } catch {
            // Best-effort: dropped transcript lines must not break the voice session.
          }
        }
      } finally {
        inFlightRef.current = false;
      }
    })();
  }, [sessionId, agentId]);

  const ingest = useCallback(
    (text: string, timestamp?: number) => {
      const cleaned = text.trim();
      // A late line of a meeting that already ended belongs to no meeting: the server dropped its
      // session together with the minutes, so uploading it would open an orphan session whose
      // line resurfaces at the start of the next meeting's minutes.
      if (!cleaned || (closedRef.current && !activeRef.current)) {
        return;
      }
      unpublishedRef.current = true;
      queueRef.current.push({ id: newLineId(), text: cleaned, ...(timestamp !== undefined ? { timestamp } : {}) });
      flush();
    },
    [flush],
  );

  // The meeting is over on the server: clear the board so the next voice session starts empty
  // instead of showing this meeting's notes.
  const settleMeeting = useCallback(() => {
    // Lines held back for a newer meeting keep the flag raised: they open a fresh server session.
    unpublishedRef.current = queueRef.current.length > 0;
    setSnapshot(null);
    forgetStoredSessionId(sessionKey);
  }, [sessionKey]);

  const publish = useCallback(async () => {
    if (!unpublishedRef.current) {
      // Nothing to publish, yet the meeting is over all the same: a line still on its way must not open a session.
      closedRef.current = true;
      return;
    }
    // Lines already captured reach the server first, so the minutes cover the end of the meeting.
    while (inFlightRef.current) {
      await drainRef.current;
    }
    closedRef.current = true;
    try {
      const result = await finalizeLiveMeeting(sessionId, agentId);
      settleMeeting();
      if (result.published_wiki_paths.length > 0) {
        toast.success(t('saved'), { description: result.title || undefined });
      } else {
        toast.error(t('saveFailed'));
      }
    } catch (error) {
      // Nothing else on screen reports a failed save and the request can run for up to two minutes, so these two
      // notices outlive Sonner's 4 s default: long enough to read the 404 copy and to reach the retry action.
      if (error instanceof ApiError && error.code === 404) {
        // The server no longer holds this meeting: a retry cannot publish it, and whether it was saved is unknown.
        settleMeeting();
        toast.warning(t('sessionGone'), { duration: 8000 });
        return;
      }
      toast.error(t('saveFailed'), {
        duration: 15_000,
        action: { label: t('retry'), onClick: () => void endRef.current() },
      });
    }
  }, [sessionId, agentId, settleMeeting, t]);

  const afterPublish = useCallback(() => {
    publishingRef.current = null;
    const heldLines = queueRef.current.length > 0;
    if (activeRef.current || heldLines) {
      closedRef.current = false;
    }
    if (heldLines) {
      flush();
      if (!activeRef.current) {
        // The newer meeting ended while this one was publishing: it is waiting for its own minutes.
        void endRef.current();
      }
    }
  }, [flush]);

  // Single-flight: a second stop signal (button, transport drop, unmount) joins the publish in progress.
  const end = useCallback((): Promise<void> => {
    publishingRef.current ??= publish().finally(afterPublish);
    return publishingRef.current;
  }, [publish, afterPublish]);

  useEffect(() => {
    endRef.current = end;
  }, [end]);

  // The edges of `active` bound a meeting: a new voice session opens the gate, the end of one publishes it.
  useEffect(() => {
    if (active === activeRef.current) {
      return;
    }
    activeRef.current = active;
    if (!active) {
      void end();
    } else if (!publishingRef.current) {
      closedRef.current = false;
    }
  }, [active, end]);

  // Leaving the page (route change) while a meeting is still open must not strand its minutes.
  useEffect(
    () => () => {
      void endRef.current();
    },
    [],
  );

  // Closing or reloading the tab cannot wait for an answer; the request itself must leave in time.
  useEffect(() => {
    const publishOnPageExit = () => {
      if (!unpublishedRef.current || publishingRef.current) {
        return;
      }
      unpublishedRef.current = false;
      finalizeLiveMeetingOnPageExit(sessionId, agentId);
    };
    window.addEventListener('pagehide', publishOnPageExit);
    return () => window.removeEventListener('pagehide', publishOnPageExit);
  }, [sessionId, agentId]);

  return useMemo(() => ({ sessionId, snapshot, ingest }), [sessionId, snapshot, ingest]);
}
