'use client';

/**
 * [INPUT]
 * chatId: string (current active session id)
 *
 * [OUTPUT]
 * ContinualOverlayWatcher: Polling & state synchronization wrapper mounting ContinualOverlayBadge
 *
 * [POS]
 * Bridges server session overlays query/rollback API with the ContinualOverlayBadge view.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { ContinualOverlayBadge, type ActiveOverlayItem } from './ContinualOverlayBadge';
import { getSessionOverlays, rollbackSessionOverlay } from '@/services/chat';

interface ContinualOverlayWatcherProps {
  chatId: string;
}

export const ContinualOverlayWatcher = memo<ContinualOverlayWatcherProps>(({ chatId }) => {
  const [overlays, setOverlays] = useState<ActiveOverlayItem[]>([]);

  const fetchOverlays = useCallback(async () => {
    if (!chatId) return;
    try {
      const items = await getSessionOverlays(chatId);
      if (Array.isArray(items)) {
        setOverlays(
          items.map((it) => ({
            overlayId: it.overlayId,
            shellType: it.shellType,
            triggerReason: it.triggerReason,
            remainingTurns: it.remainingTurns,
            advisoryText: it.advisoryText,
          })),
        );
      }
    } catch {
      // Non-blocking: background polling shouldn't throw to UI
    }
  }, [chatId]);

  useEffect(() => {
    fetchOverlays();
    const interval = setInterval(fetchOverlays, 8000);
    return () => clearInterval(interval);
  }, [fetchOverlays]);

  const handleRollback = useCallback(
    async (overlayId: string) => {
      try {
        await rollbackSessionOverlay(chatId, overlayId);
        await fetchOverlays();
      } catch {
        // Handled silently or by caller
      }
    },
    [chatId, fetchOverlays],
  );

  if (overlays.length === 0) {
    return null;
  }

  return (
    <div className="fixed top-14 left-1/2 -translate-x-1/2 z-30 w-full max-w-xl px-4 pointer-events-auto">
      <ContinualOverlayBadge overlays={overlays} onRollback={handleRollback} />
    </div>
  );
});

ContinualOverlayWatcher.displayName = 'ContinualOverlayWatcher';
