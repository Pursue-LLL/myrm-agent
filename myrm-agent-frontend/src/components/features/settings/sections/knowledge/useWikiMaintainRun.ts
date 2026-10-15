'use client';

/**
 * [INPUT]
 * @/services/wikiService::startWikiMaintain,getWikiMaintainStatus (POS: start and status endpoints of the background maintenance run)
 * @/lib/api::ApiError (POS: HTTP status of a rejected start)
 *
 * [OUTPUT]
 * useWikiMaintainRun: start a maintenance run, follow it to the end, and pick a run in flight back up on mount
 * WikiMaintainOutcome: how a followed run ended
 * MAINTAIN_POLL_INTERVAL_MS / MAINTAIN_POLL_MAX_CONSECUTIVE_ERRORS: polling cadence and tolerance
 *
 * [POS]
 * Settings Wiki maintenance. A full run takes minutes and outlives any single request, so the page starts it
 * and polls its status until it ends; the outcome is reported once per run to whoever is watching.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '@/lib/api';
import {
  getWikiMaintainStatus,
  startWikiMaintain,
  type WikiMaintainMode,
  type WikiMaintainProgress,
  type WikiMaintainResponse,
  type WikiMaintainStatus,
} from '@/services/wikiService';
import type { MaintainFailureReason } from './wiki/wikiSectionUtils';

export const MAINTAIN_POLL_INTERVAL_MS = 2000;
export const MAINTAIN_POLL_MAX_CONSECUTIVE_ERRORS = 5;

export type WikiMaintainOutcome =
  | { kind: 'success'; mode: WikiMaintainMode; result: WikiMaintainResponse }
  | { kind: 'failure'; reason: MaintainFailureReason };

interface UseWikiMaintainRunOptions {
  agentScopeId?: string | null;
  onFinished: (outcome: WikiMaintainOutcome) => void;
}

interface TrackedStatus {
  agentScopeId: string | null | undefined;
  status: WikiMaintainStatus;
}

function outcomeOf(status: WikiMaintainStatus): WikiMaintainOutcome {
  if (status.state === 'succeeded' && status.result) {
    return { kind: 'success', mode: status.mode ?? 'structural', result: status.result };
  }
  // 'idle' after a run was followed means the server forgot it (restarted): nothing finished.
  return { kind: 'failure', reason: status.error_code === 'compile_in_progress' ? 'compile_busy' : 'failed' };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export function useWikiMaintainRun({ agentScopeId, onFinished }: UseWikiMaintainRunOptions) {
  const [isStarting, setIsStarting] = useState(false);
  const [tracked, setTracked] = useState<TrackedStatus | null>(null);
  const onFinishedRef = useRef(onFinished);
  // Bumped whenever the followed run changes or the hook goes away: a loop whose token is stale stops silently.
  const watchTokenRef = useRef(0);

  useEffect(() => {
    onFinishedRef.current = onFinished;
  });

  const watch = useCallback(
    async (first: WikiMaintainStatus): Promise<void> => {
      watchTokenRef.current += 1;
      const token = watchTokenRef.current;
      const isCurrent = () => watchTokenRef.current === token;
      let status = first;
      let failedPolls = 0;

      while (status.state === 'running') {
        setTracked({ agentScopeId, status });
        await sleep(MAINTAIN_POLL_INTERVAL_MS);
        if (!isCurrent()) {
          return;
        }
        try {
          status = await getWikiMaintainStatus(agentScopeId);
          failedPolls = 0;
        } catch (error) {
          failedPolls += 1;
          console.warn('Failed to read wiki maintenance status:', error);
          if (failedPolls >= MAINTAIN_POLL_MAX_CONSECUTIVE_ERRORS) {
            if (isCurrent()) {
              setTracked(null);
              onFinishedRef.current({ kind: 'failure', reason: 'failed' });
            }
            return;
          }
        }
        if (!isCurrent()) {
          return;
        }
      }

      setTracked(null);
      onFinishedRef.current(outcomeOf(status));
    },
    [agentScopeId],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const status = await getWikiMaintainStatus(agentScopeId);
        if (!cancelled && status.state === 'running') {
          void watch(status);
        }
      } catch (error) {
        console.warn('Failed to resume wiki maintenance status:', error);
      }
    })();
    return () => {
      cancelled = true;
      watchTokenRef.current += 1;
    };
  }, [agentScopeId, watch]);

  const start = useCallback(
    async (mode: WikiMaintainMode): Promise<void> => {
      const tokenBeforeStart = watchTokenRef.current;
      setIsStarting(true);
      try {
        const status = await startWikiMaintain(mode, agentScopeId);
        // A changed token means the page left this scope, or another loop already follows the run.
        if (watchTokenRef.current === tokenBeforeStart) {
          void watch(status);
        }
      } catch (error) {
        console.error('Failed to start wiki maintenance:', error);
        onFinishedRef.current({
          kind: 'failure',
          reason: error instanceof ApiError && error.code === 409 ? 'compile_busy' : 'failed',
        });
      } finally {
        setIsStarting(false);
      }
    },
    [agentScopeId, watch],
  );

  const status = tracked && tracked.agentScopeId === agentScopeId ? tracked.status : null;
  const progress: WikiMaintainProgress | null =
    status?.phase != null ? { phase: status.phase, done: status.done, total: status.total } : null;

  return { isRunning: isStarting || status !== null, progress, start };
}
