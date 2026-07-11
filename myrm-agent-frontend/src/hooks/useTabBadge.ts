/**
 * [INPUT]
 * @/hooks/useLivenessState::useLivenessState (POS: Global agent liveness SSOT)
 * @/lib/approval/approvalAlertService::isTitleFlashing (POS: Approval title flash guard)
 *
 * [OUTPUT]
 * useTabBadge: Prefixes document.title with a liveness state text badge.
 *
 * [POS]
 * Tab badge hook. Adds a visual prefix to the browser tab title reflecting
 * global agent liveness (busy/degraded). Yields to approval alert title
 * flashing when active. Works in all deployment modes (Web, Tauri, cloud).
 */
import { useEffect, useRef } from 'react';

import { isTitleFlashing } from '@/lib/approval/approvalAlertService';
import { useLivenessState } from '@/hooks/useLivenessState';

import type { LivenessState } from '@/hooks/useLivenessState';

const BADGE_PREFIX: Record<LivenessState, string> = {
  busy: '[*] ',
  degraded: '[!] ',
  idle: '',
};

export function useTabBadge(): void {
  const liveness = useLivenessState();
  const baseTitleRef = useRef<string | null>(null);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    if (baseTitleRef.current === null) {
      baseTitleRef.current = document.title.replace(/^\[[\*!]\]\s*/, '');
    }

    if (isTitleFlashing()) return;

    const prefix = BADGE_PREFIX[liveness.state];
    const base = baseTitleRef.current;
    document.title = prefix ? `${prefix}${base}` : base;

    return () => {
      if (baseTitleRef.current !== null && !isTitleFlashing()) {
        document.title = baseTitleRef.current;
      }
    };
  }, [liveness.state]);
}
