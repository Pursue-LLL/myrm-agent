/**
 * [INPUT]
 * @/services/wikiService::QueueStatus (POS: Wiki queue API DTO types)
 *
 * [OUTPUT]
 * computeShouldPollQueue: pure eligibility check for active queue polling
 * QUEUE_POLL_INTERVAL_MS, SILENT_FAIL_STALE_THRESHOLD: poll tuning constants
 *
 * [POS]
 * Pure helpers for Wiki Queue tab polling. Keeps poll conditions unit-testable without rendering.
 */

import type { QueueStatus } from '@/services/wikiService';

export const QUEUE_POLL_INTERVAL_MS = 10_000;
export const SILENT_FAIL_STALE_THRESHOLD = 2;

export function computeShouldPollQueue(queueData: QueueStatus | null | undefined): boolean {
  if (!queueData) {
    return false;
  }
  if (queueData.compile_run?.state === 'paused') {
    return true;
  }
  return queueData.stats.processing > 0 || queueData.stats.pending > 0;
}

export function shouldShowStaleRefreshBanner(consecutiveSilentFailures: number): boolean {
  return consecutiveSilentFailures >= SILENT_FAIL_STALE_THRESHOLD;
}

export interface QueueStatsSnapshot {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
}

export function queueStatsDiverge(
  liveStats: QueueStatsSnapshot,
  cachedStats: QueueStatsSnapshot | null | undefined,
): boolean {
  if (!cachedStats) {
    return true;
  }
  return (
    liveStats.pending !== cachedStats.pending ||
    liveStats.processing !== cachedStats.processing ||
    liveStats.completed !== cachedStats.completed ||
    liveStats.failed !== cachedStats.failed
  );
}
