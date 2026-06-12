'use client';

/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: HTTP client wrapper)
 *
 * [OUTPUT]
 * useNavBadges: NavBar badge counts with SSE-driven refresh.
 *
 * [POS]
 * NavBar badge data hook. Fetches aggregated badge counts and refreshes
 * when relevant SSE custom events fire (cron failures, approvals, notifications).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiRequest } from '@/lib/api';

interface NavBadges {
  cronFailures: number;
  pendingApprovals: number;
  unreadNotifications: number;
  total: number;
  extensionConnected: boolean;
}

const EMPTY_BADGES: NavBadges = {
  cronFailures: 0,
  pendingApprovals: 0,
  unreadNotifications: 0,
  total: 0,
  extensionConnected: false,
};

export function useNavBadges(): NavBadges {
  const [badges, setBadges] = useState<NavBadges>(EMPTY_BADGES);
  const fetchingRef = useRef(false);

  const fetchBadges = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const res = await apiRequest<{ data: NavBadges }>('/statistics/badges', { silent: true });
      if (res?.data) {
        setBadges(res.data);
      }
    } catch {
      // Silent — badge fetch failure should not disrupt UX
    } finally {
      fetchingRef.current = false;
    }
  }, []);

  useEffect(() => {
    fetchBadges();
  }, [fetchBadges]);

  // Refresh on SSE events that affect badge counts
  useEffect(() => {
    const refresh = () => fetchBadges();
    const events = [
      'approval-required',
      'message_dead_lettered',
      'idle-status',
      'skill-draft-created',
      'skill-growth-updated',
      'cron_updated',
      'extension-status-changed',
    ];
    for (const evt of events) {
      window.addEventListener(evt, refresh);
    }
    return () => {
      for (const evt of events) {
        window.removeEventListener(evt, refresh);
      }
    };
  }, [fetchBadges]);

  return badges;
}
