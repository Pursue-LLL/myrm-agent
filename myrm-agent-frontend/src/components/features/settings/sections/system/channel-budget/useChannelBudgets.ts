'use client';

/**
 * [INPUT]
 * - react::useCallback, useEffect, useRef, useState (POS: React core hooks)
 * - @/services/budget (POS: Channel budget API service)
 *
 * [OUTPUT]
 * - LoadStatus: where the list stands: the first load (or a retry) is running, the list is loaded, or the last load failed
 * - useChannelBudgets: the stored policies and today's statuses of every channel, how the last load went, and the two
 *   ways to load again: `refresh` after a write, `retry` from the failure notice
 *
 * [POS]
 * Data source of the channel budget panel. Loads overlap, because every write reads the list back, so each load is
 * numbered and only an outcome that is not older than the one on screen may change the screen: a slow earlier answer
 * can neither bring back what a later one no longer lists nor hide the list a later one loaded. The list on screen
 * stays when a load fails.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getChannelBudgets, type ChannelBudgetPolicy, type ChannelBudgetStatus } from '@/services/budget';

export type LoadStatus = 'loading' | 'ready' | 'failed';

export function useChannelBudgets() {
  const [policies, setPolicies] = useState<ChannelBudgetPolicy[]>([]);
  const [statuses, setStatuses] = useState<ChannelBudgetStatus[]>([]);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>('loading');
  // The number of the latest load that started, and of the load whose outcome is on screen.
  const started = useRef(0);
  const applied = useRef(0);

  /** Reads the list again; never throws, and leaves the screen alone until the answer is in. */
  const refresh = useCallback(async () => {
    const load = ++started.current;
    // The request is silent: a failed load is reported by the failure notice, not by a toast.
    const answer = await getChannelBudgets().catch(() => null);
    if (load < applied.current) {
      return;
    }
    applied.current = load;
    if (answer) {
      setPolicies(answer.policies);
      setStatuses(answer.statuses);
      setLoadStatus('ready');
    } else {
      setLoadStatus('failed');
    }
  }, []);

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- the effect starts the first load; the list and its status only mirror that in-flight request
    void refresh();
  }, [refresh]);

  /** Loads again after a failure, showing that it is loading until the answer is in. */
  const retry = useCallback(() => {
    setLoadStatus('loading');
    return refresh();
  }, [refresh]);

  return { policies, statuses, loadStatus, refresh, retry };
}
