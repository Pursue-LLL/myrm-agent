/**
 * [INPUT]
 * - Initial pinned IDs or session identifier
 *
 * [OUTPUT]
 * - useContextPinning Hook: { pinnedIds, togglePin, isPinned, pinItem, unpinItem }
 *
 * [POS]
 * Client-side context pinning state management hook (Item 146).
 * Manages zero-pruning context pin IDs for chat messages, files, and architectural decisions.
 */

import { useCallback, useState } from 'react';

export interface PinnedItemSummary {
  readonly id: string;
  readonly type: 'message' | 'fact' | 'file_path' | 'decision';
  readonly content: string;
  readonly title?: string;
  readonly pinnedAt: number;
}

export function useContextPinning(initialPinnedIds: ReadonlyArray<string> = []) {
  const [pinnedIds, setPinnedIds] = useState<ReadonlySet<string>>(
    () => new Set(initialPinnedIds),
  );

  const isPinned = useCallback(
    (id: string): boolean => {
      return pinnedIds.has(id);
    },
    [pinnedIds],
  );

  const pinItem = useCallback((id: string) => {
    setPinnedIds((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);

  const unpinItem = useCallback((id: string) => {
    setPinnedIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const togglePin = useCallback((id: string) => {
    setPinnedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  return {
    pinnedIds: Array.from(pinnedIds),
    isPinned,
    pinItem,
    unpinItem,
    togglePin,
  };
}
