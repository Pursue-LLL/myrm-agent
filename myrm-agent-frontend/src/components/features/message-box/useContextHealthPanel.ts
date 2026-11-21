/**
 * [INPUT]
 * - services/statistics::getSessionAnalytics (POS: Statistics API client DTO layer.)
 * - services/contextHealth::ContextHealth (POS: Statistics context-health DTO layer.)
 *
 * [OUTPUT]
 * - useContextHealthPanel: open state of the strategy panel plus the strategy health of the chat it shows.
 *
 * [POS]
 * Data source of the context usage ring and its strategy panel. The health is read whenever the panel opens and
 * whenever the chat records a compaction. `health` and `loading` are derived from the chat in view, so an answer that
 * belongs to another chat, or to a read the panel closed on, is never shown.
 */

import { useCallback, useEffect, useState } from 'react';
import type { ContextHealth } from '@/services/contextHealth';
import { getSessionAnalytics } from '@/services/statistics';

interface SettledRead {
  key: string;
  chatId: string;
  health: ContextHealth | null;
}

export function useContextHealthPanel(chatId: string | null, compactionRefreshNonce: number) {
  const [panelOpen, setPanelOpenState] = useState(false);
  const [openCount, setOpenCount] = useState(0);
  const [settled, setSettled] = useState<SettledRead | null>(null);

  // Each opening reads again; counting it in the event that opens the panel keeps the read a function of state.
  const setPanelOpen = useCallback((open: boolean) => {
    setPanelOpenState(open);
    if (open) {
      setOpenCount((count) => count + 1);
    }
  }, []);

  // A chat that recorded a compaction keeps reading while the panel is closed, so the ring dot follows its health.
  const wanted = chatId !== null && (panelOpen || compactionRefreshNonce > 0);
  const key = `${chatId}|${openCount}|${compactionRefreshNonce}`;
  // The analytics service holds a chat's answer for 30 s, and after a compaction that answer predates it.
  const afterCompaction = compactionRefreshNonce > 0;

  useEffect(() => {
    if (!wanted || chatId === null) {
      return;
    }
    const controller = new AbortController();
    getSessionAnalytics(chatId, afterCompaction)
      .then(
        (analytics) => analytics.context_health ?? null,
        () => null,
      )
      .then((health) => {
        if (!controller.signal.aborted) {
          setSettled({ key, chatId, health });
        }
      });
    return () => controller.abort();
  }, [wanted, chatId, key, afterCompaction]);

  return {
    panelOpen,
    setPanelOpen,
    health: settled !== null && settled.chatId === chatId ? settled.health : null,
    loading: wanted && settled?.key !== key,
  };
}
