'use client';

/**
 * [INPUT]
 * - react::useCallback, useMemo, useRef, useState (POS: React core hooks)
 * - @/services/budget (POS: Channel budget API service)
 * - ./useChannelBudgets::LoadStatus (POS: Where a load from the server stands)
 *
 * [OUTPUT]
 * - AUDIT_DAYS: the budget days an unfolded channel looks back over, which the toggle label names
 * - ChannelAuditView: what an unfolded channel shows: the status, each sender's spend, and the window's total
 * - useChannelAudit: unfolds and folds channels one at a time (`toggle`) and gives the view of a channel (`viewOf`),
 *   `null` while that channel is folded
 *
 * [POS]
 * Audit state of the channel budget panel. Unfolding another channel, or folding the open one, retires the request in
 * flight, so an answer for a channel that is no longer open never lands on the one that is. A failed load is shown as
 * such, and unfolding the channel again asks again.
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import { getChannelAudit, type ChannelAuditEntry } from '@/services/budget';
import type { LoadStatus } from './useChannelBudgets';

/** Budget days the audit looks back over; the toggle label shows this number. */
export const AUDIT_DAYS = 7;

export interface ChannelAuditView {
  status: LoadStatus;
  entries: ChannelAuditEntry[];
  /** What the whole window cost, which a sender's bar is a share of. */
  totalUsd: number;
}

export function useChannelAudit() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [entries, setEntries] = useState<ChannelAuditEntry[]>([]);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const latest = useRef(0);
  // The audit spans several days, so a sender's bar is its share of what the window cost, not of today's spend.
  const totalUsd = useMemo(() => entries.reduce((sum, entry) => sum + entry.total_cost_usd, 0), [entries]);

  const toggle = useCallback(
    async (channelKey: string) => {
      const request = ++latest.current;
      if (expanded === channelKey) {
        setExpanded(null);
        return;
      }
      setExpanded(channelKey);
      setStatus('loading');
      try {
        const data = await getChannelAudit(channelKey, AUDIT_DAYS);
        if (request === latest.current) {
          setEntries(data.entries);
          setStatus('ready');
        }
      } catch {
        // The request is silent: the unfolded channel says that its data could not be loaded.
        if (request === latest.current) {
          setEntries([]);
          setStatus('failed');
        }
      }
    },
    [expanded],
  );

  const viewOf = (channelKey: string): ChannelAuditView | null =>
    expanded === channelKey ? { status, entries, totalUsd } : null;

  return { toggle, viewOf };
}
