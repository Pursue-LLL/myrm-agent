'use client';

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { API_BASE_URL } from '@/lib/api';
import useApprovalStore, { normalizeApprovalPayload, type ApprovalPayload } from '@/store/useApprovalStore';

const STARTUP_DELAY_MS = 200;
const DEBOUNCE_WINDOW_MS = 2_000;
const FETCH_LIMIT = 100;

const recoveryState = {
  lastFetchAt: 0,
  inflight: null as Promise<number> | null,
};

interface ApprovalListResponse {
  approvals?: Record<string, unknown>[];
}

async function fetchPendingApprovals(): Promise<ApprovalPayload[]> {
  const url = `${API_BASE_URL}/approvals?limit=${FETCH_LIMIT}&offset=0`;
  const response = await fetch(url, { method: 'GET', credentials: 'include' });

  if (!response.ok) {
    throw new Error(`Failed to fetch pending approvals: ${response.status}`);
  }

  const json = (await response.json()) as ApprovalListResponse;
  const records = Array.isArray(json.approvals) ? json.approvals : [];

  return records.map((record) => normalizeApprovalPayload(record));
}

/**
 * Recover pending approvals from the server and enqueue them into the global
 * approval store. The server excludes background growth drafts (see
 * ApprovalRegistry.list_pending); this hook only receives inline HITL items.
 * Deduplicates against in-memory queue (handled by openApproval) and debounces
 * repeated calls within DEBOUNCE_WINDOW_MS to avoid request storms during SSE
 * exponential reconnect.
 *
 * Returns the number of recovered approvals (after dedup with current queue).
 */
export async function recoverPendingApprovals(): Promise<number> {
  const now = Date.now();
  if (now - recoveryState.lastFetchAt < DEBOUNCE_WINDOW_MS) {
    return 0;
  }

  if (recoveryState.inflight) {
    return recoveryState.inflight;
  }

  recoveryState.lastFetchAt = now;

  const task = (async () => {
    try {
      const approvals = await fetchPendingApprovals();
      if (approvals.length === 0) {
        return 0;
      }

      const store = useApprovalStore.getState();
      const existingIds = new Set(store.queue.map((a) => a.approval_id));
      let added = 0;

      for (const approval of approvals) {
        if (!approval.approval_id || existingIds.has(approval.approval_id)) {
          continue;
        }
        store.openApproval(approval);
        existingIds.add(approval.approval_id);
        added += 1;
      }
      return added;
    } catch (error) {
      console.warn('[pending-approvals] recovery failed', error);
      return 0;
    } finally {
      recoveryState.inflight = null;
    }
  })();

  recoveryState.inflight = task;
  return task;
}

/**
 * Mount-time recovery + listener for SSE reconnect events.
 *
 * On startup, waits a short delay to let the app finish initialization before
 * fetching the pending queue, then registers a listener for `app_resync_required`
 * (emitted by useGlobalEvents when the SSE connection re-establishes) to keep
 * the queue fresh after network blips.
 */
export function usePendingApprovalsRecovery(): void {
  const t = useTranslations('notifications');

  useEffect(() => {
    let cancelled = false;

    const runRecovery = async (showToast: boolean) => {
      const added = await recoverPendingApprovals();
      if (cancelled || added <= 0 || !showToast) {
        return;
      }
      toast.info(t('approvalsRecovered', { count: added }), {
        duration: 5_000,
        dismissible: true,
      });
    };

    const startupTimer = setTimeout(() => {
      void runRecovery(true);
    }, STARTUP_DELAY_MS);

    const handleResync = () => {
      void runRecovery(false);
    };
    window.addEventListener('app_resync_required', handleResync);

    return () => {
      cancelled = true;
      clearTimeout(startupTimer);
      window.removeEventListener('app_resync_required', handleResync);
    };
  }, [t]);
}
