import { describe, expect, it } from 'vitest';

import {
  QUEUE_POLL_INTERVAL_MS,
  SILENT_FAIL_STALE_THRESHOLD,
  computeShouldPollQueue,
  queueStatsDiverge,
  shouldShowStaleRefreshBanner,
} from '../wikiQueuePoll';
import type { QueueStatus } from '@/services/wikiService';

const baseStats = {
  pending: 0,
  processing: 0,
  completed: 0,
  failed: 0,
};

describe('wikiQueuePoll', () => {
  it('exports poll tuning constants', () => {
    expect(QUEUE_POLL_INTERVAL_MS).toBe(10_000);
    expect(SILENT_FAIL_STALE_THRESHOLD).toBe(2);
  });

  it('does not poll when queue data is missing', () => {
    expect(computeShouldPollQueue(null)).toBe(false);
    expect(computeShouldPollQueue(undefined)).toBe(false);
  });

  it('polls when compile circuit is paused', () => {
    const queue: QueueStatus = {
      stats: baseStats,
      pending_items: [],
      failed_items: [],
      compile_run: { state: 'paused', pause_reason: 'auth failure', primary_error_kind: 'auth' },
    };
    expect(computeShouldPollQueue(queue)).toBe(true);
  });

  it('polls when pending or processing items exist', () => {
    expect(
      computeShouldPollQueue({
        stats: { ...baseStats, pending: 3 },
        pending_items: [],
        failed_items: [],
      }),
    ).toBe(true);
    expect(
      computeShouldPollQueue({
        stats: { ...baseStats, processing: 1 },
        pending_items: [],
        failed_items: [],
      }),
    ).toBe(true);
  });

  it('does not poll when queue is idle', () => {
    expect(
      computeShouldPollQueue({
        stats: { ...baseStats, failed: 2 },
        pending_items: [],
        failed_items: [],
        compile_run: { state: 'running', pause_reason: '', primary_error_kind: '' },
      }),
    ).toBe(false);
  });

  it('shows stale banner after consecutive silent failures', () => {
    expect(shouldShowStaleRefreshBanner(0)).toBe(false);
    expect(shouldShowStaleRefreshBanner(1)).toBe(false);
    expect(shouldShowStaleRefreshBanner(2)).toBe(true);
  });

  it('detects queue stats divergence for SSE refresh', () => {
    const base = { pending: 0, processing: 0, completed: 0, failed: 0 };
    expect(queueStatsDiverge({ ...base, failed: 2 }, base)).toBe(true);
    expect(queueStatsDiverge(base, base)).toBe(false);
    expect(queueStatsDiverge(base, null)).toBe(true);
  });
});
