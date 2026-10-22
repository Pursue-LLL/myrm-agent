/**
 * [INPUT]
 * ./workspaceCockpitTypes (POS: WorkspaceTaskItem, OfflineDigestSummary, OfflineDigestHighlight)
 *
 * [OUTPUT]
 * useWorkspaceOfflineDigest: Hook computing offline digest statistics and managing user activity timestamps.
 *
 * [POS]
 * Analytical engine for "While You Were Away" offline digest in personal workspace cockpit.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import type {
  OfflineDigestHighlight,
  OfflineDigestSummary,
  WorkspaceTaskItem,
} from './workspaceCockpitTypes';

const STORAGE_LAST_ACTIVE_KEY = 'myrm:workspace-last-active-at';
const DEFAULT_AWAY_THRESHOLD_MS = 60 * 1000; // 1 minute threshold to trigger digest

export function readLastActiveTimestamp(): number {
  if (typeof window === 'undefined') {
    return Date.now();
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_LAST_ACTIVE_KEY);
    if (!raw) {
      return Date.now();
    }
    const val = Number.parseInt(raw, 10);
    return Number.isNaN(val) ? Date.now() : val;
  } catch {
    return Date.now();
  }
}

export function writeLastActiveTimestamp(ts: number): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(STORAGE_LAST_ACTIVE_KEY, ts.toString());
  } catch {
    // Non-blocking fallback
  }
}

export function formatTimeDuration(durationMs: number): string {
  const seconds = Math.floor(durationMs / 1000);
  if (seconds < 60) {
    return `${Math.max(1, seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ${minutes % 60}m`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

export function useWorkspaceOfflineDigest(
  tasks: WorkspaceTaskItem[],
  customLastActiveTimestamp?: number,
) {
  const [lastActive, setLastActive] = useState<number>(() => {
    return customLastActiveTimestamp ?? readLastActiveTimestamp();
  });
  const [isDismissed, setIsDismissed] = useState(false);

  useEffect(() => {
    if (customLastActiveTimestamp !== undefined) {
      setLastActive(customLastActiveTimestamp);
    }
  }, [customLastActiveTimestamp]);

  const summary = useMemo<OfflineDigestSummary>(() => {
    const now = Date.now();
    const awayDurationMs = Math.max(0, now - lastActive);

    const completed = tasks.filter((t) => t.status === 'success' && t.updatedAt >= lastActive);
    const failed = tasks.filter((t) => t.status === 'failed' && t.updatedAt >= lastActive);
    const pendingDecisions = tasks.filter(
      (t) => t.swimlane === 'needs-you' || t.status === 'waiting_approval',
    );
    const inProgress = tasks.filter(
      (t) =>
        (t.swimlane === 'in-progress' || t.status === 'running') &&
        t.status !== 'success' &&
        t.status !== 'failed',
    );

    const highlights: OfflineDigestHighlight[] = [];

    for (const t of pendingDecisions.slice(0, 3)) {
      highlights.push({
        id: t.id,
        title: t.title,
        type: 'decision',
        timeAgo: formatTimeDuration(now - t.updatedAt),
        chatId: t.chatId,
      });
    }

    for (const t of failed.slice(0, 2)) {
      highlights.push({
        id: t.id,
        title: t.title,
        type: 'failure',
        timeAgo: formatTimeDuration(now - t.updatedAt),
        chatId: t.chatId,
      });
    }

    for (const t of completed.slice(0, 3)) {
      highlights.push({
        id: t.id,
        title: t.title,
        type: 'success',
        timeAgo: formatTimeDuration(now - t.updatedAt),
        chatId: t.chatId,
      });
    }

    return {
      awayDurationMs,
      completedGoalsCount: completed.length,
      failedTasksCount: failed.length,
      pendingDecisionsCount: pendingDecisions.length,
      inProgressCount: inProgress.length,
      highlights,
    };
  }, [tasks, lastActive]);

  const shouldShowDigest =
    !isDismissed && summary.awayDurationMs >= DEFAULT_AWAY_THRESHOLD_MS;

  const dismissDigest = useCallback(() => {
    const now = Date.now();
    setIsDismissed(true);
    setLastActive(now);
    writeLastActiveTimestamp(now);
  }, []);

  return {
    summary,
    shouldShowDigest,
    dismissDigest,
  };
}
