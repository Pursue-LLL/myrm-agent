'use client';

/**
 * [INPUT]
 * @/services/wiki/ima::* (POS: ima REST client)
 * ./imaCopy::imaErrorKey, shouldPollIma (POS: server error code → locale key; whether anything can still change)
 *
 * [OUTPUT]
 * useImaSync: ima status for one agent vault, kept fresh while a sync runs, plus every user action as a typed result
 * ImaAction / ImaResult: which action is in flight and how an action ended
 * IMA_POLL_INTERVAL_MS / IMA_WATCH_AFTER_SYNC_NOW_MS: polling cadence, and how long polling continues after "sync now"
 *
 * [POS]
 * State holder of the ima card. The first import takes minutes and outlives any request, so the page reads status on
 * an interval while a sync is active and the tab is visible, and stops as soon as the job is idle or paused. Actions
 * never throw: they resolve to `{ok: false, errorKey}` so the card can show plain-language copy, never server text.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  compileImaImports,
  deleteImaCredentials,
  getImaStatus,
  pauseImaSync,
  resumeImaSync,
  retryFailedImaItems,
  saveImaCredentials,
  saveImaSelection,
  startImaSync,
  type ImaCredentialsInput,
  type ImaSelectionInput,
  type ImaStatus,
} from '@/services/wiki/ima';
import { imaErrorKey, shouldPollIma } from './imaCopy';

export const IMA_POLL_INTERVAL_MS = 4000;
/** An idle, up-to-date sync never polls on its own; after "sync now" it does for this long so the outcome shows up. */
export const IMA_WATCH_AFTER_SYNC_NOW_MS = 60_000;

export type ImaAction = 'connect' | 'disconnect' | 'start' | 'syncNow' | 'pause' | 'resume' | 'retry' | 'compile';

export type ImaResult<T = void> = { ok: true; value: T } | { ok: false; errorKey: string };

interface TrackedStatus {
  agentId: string | null;
  status: ImaStatus;
}

export function useImaSync(agentId: string | null) {
  const [tracked, setTracked] = useState<TrackedStatus | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState<ImaAction | null>(null);
  // Bumped by every "sync now" so each click restarts the observation window; 0 means not watching.
  const [watchRun, setWatchRun] = useState(0);
  const pollInFlightRef = useRef(false);

  // A status read for another agent vault is never shown: switching scope reads as "not loaded yet".
  const status = tracked && tracked.agentId === agentId ? tracked.status : null;

  const adopt = useCallback((next: ImaStatus) => setTracked({ agentId, status: next }), [agentId]);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      adopt(await getImaStatus(agentId));
      setLoadFailed(false);
    } catch {
      setLoadFailed(true);
    }
  }, [adopt, agentId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (watchRun === 0) {
      return;
    }
    const timer = window.setTimeout(() => setWatchRun(0), IMA_WATCH_AFTER_SYNC_NOW_MS);
    return () => window.clearTimeout(timer);
  }, [watchRun]);

  const polling =
    shouldPollIma(status) || (watchRun > 0 && status?.connected === true && status.job.state === 'active');
  useEffect(() => {
    if (!polling) {
      return;
    }
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible' || pollInFlightRef.current) {
        return;
      }
      pollInFlightRef.current = true;
      void refresh().finally(() => {
        pollInFlightRef.current = false;
      });
    }, IMA_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [polling, refresh]);

  const run = useCallback(async <T>(action: ImaAction, call: () => Promise<T>): Promise<ImaResult<T>> => {
    setBusy(action);
    try {
      return { ok: true, value: await call() };
    } catch (error) {
      return { ok: false, errorKey: imaErrorKey(error) };
    } finally {
      setBusy(null);
    }
  }, []);

  const runStatus = useCallback(
    async (action: ImaAction, call: () => Promise<ImaStatus>): Promise<ImaResult> => {
      const result = await run(action, call);
      if (!result.ok) {
        return result;
      }
      adopt(result.value);
      return { ok: true, value: undefined };
    },
    [adopt, run],
  );

  const connect = useCallback(
    (input: ImaCredentialsInput) => runStatus('connect', () => saveImaCredentials(input, agentId)),
    [agentId, runStatus],
  );

  const disconnect = useCallback(
    () => runStatus('disconnect', () => deleteImaCredentials(agentId)),
    [agentId, runStatus],
  );

  /** Saves the chosen libraries and starts (or re-runs) the import; the server restarts its inventory if the choice changed. */
  const startSync = useCallback(
    (selection: ImaSelectionInput, locale: string) =>
      runStatus('start', async () => {
        await saveImaSelection(selection, agentId);
        return startImaSync(locale, agentId);
      }),
    [agentId, runStatus],
  );

  /** Runs the scheduled check right away; the server only wakes the existing job, it never re-saves the selection. */
  const syncNow = useCallback(
    async (locale: string): Promise<ImaResult> => {
      const result = await runStatus('syncNow', () => startImaSync(locale, agentId));
      if (result.ok) {
        setWatchRun((run) => run + 1);
      }
      return result;
    },
    [agentId, runStatus],
  );

  const pause = useCallback(() => runStatus('pause', () => pauseImaSync(agentId)), [agentId, runStatus]);

  const resume = useCallback(() => runStatus('resume', () => resumeImaSync(agentId)), [agentId, runStatus]);

  const retryFailed = useCallback(async (): Promise<ImaResult<number>> => {
    const result = await run('retry', () => retryFailedImaItems(agentId));
    if (result.ok) {
      await refresh();
    }
    return result;
  }, [agentId, refresh, run]);

  const compile = useCallback(() => run('compile', () => compileImaImports(agentId)), [agentId, run]);

  return {
    status,
    loadFailed,
    busy,
    refresh,
    connect,
    disconnect,
    startSync,
    syncNow,
    pause,
    resume,
    retryFailed,
    compile,
  };
}
