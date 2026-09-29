'use client';

/**
 * [INPUT]
 * - chatId: string (POS: Session identifier for scoped history isolation)
 *
 * [OUTPUT]
 * - useMobilePromptHistory: Hook for navigable prompt history on mobile devices.
 * - recordPromptHistory, getPromptHistory, clearPromptHistory: Pure helpers for external access.
 *
 * [POS]
 * Mobile prompt history state machine. Keeps a bounded (max 20) session-isolated
 * history stack and a single backward-walk cursor, mirroring terminal up-arrow recall
 * for touch screens. The user draft is owned by the consumer, not by this hook.
 */

import { useCallback, useState } from 'react';

const MAX_HISTORY_ITEMS = 20;

// Module-level registry scoped by chatId
const promptHistoryRegistry = new Map<string, string[]>();

export function getPromptHistory(chatId: string): string[] {
  return promptHistoryRegistry.get(chatId) ?? [];
}

export function recordPromptHistory(chatId: string, prompt: string): void {
  const trimmed = prompt.trim();
  if (!trimmed || !chatId) {
    return;
  }
  const current = promptHistoryRegistry.get(chatId) ?? [];
  // Deduplicate consecutive identical prompts
  if (current.length > 0 && current[current.length - 1] === trimmed) {
    return;
  }
  const next = [...current, trimmed];
  if (next.length > MAX_HISTORY_ITEMS) {
    next.shift();
  }
  promptHistoryRegistry.set(chatId, next);
}

export function clearPromptHistory(chatId: string): void {
  promptHistoryRegistry.delete(chatId);
}

export interface UseMobilePromptHistoryReturn {
  historyCount: number;
  currentIndex: number;
  pushHistory: (prompt: string) => void;
  /** 向更早的一条回溯；已在最旧一条时返回 null，由调用方回到自己的草稿。 */
  navigatePrevious: () => string | null;
  resetNavigation: () => void;
}

export function useMobilePromptHistory(chatId: string): UseMobilePromptHistoryReturn {
  // -1 indicates user is not browsing history (active draft mode)
  const [currentIndex, setCurrentIndex] = useState<number>(-1);
  const [historyCount, setHistoryCount] = useState<number>(() => getPromptHistory(chatId).length);

  const pushHistory = useCallback(
    (prompt: string) => {
      recordPromptHistory(chatId, prompt);
      setHistoryCount(getPromptHistory(chatId).length);
      setCurrentIndex(-1);
    },
    [chatId],
  );

  const resetNavigation = useCallback(() => {
    setCurrentIndex(-1);
  }, []);

  const navigatePrevious = useCallback((): string | null => {
    const history = getPromptHistory(chatId);
    if (history.length === 0) {
      return null;
    }

    const targetIndex = currentIndex === -1 ? history.length - 1 : Math.max(currentIndex - 1, 0);
    setCurrentIndex(targetIndex);
    return history[targetIndex] ?? null;
  }, [chatId, currentIndex]);

  const history = getPromptHistory(chatId);

  return {
    historyCount: history.length,
    currentIndex,
    pushHistory,
    navigatePrevious,
    resetNavigation,
  };
}
