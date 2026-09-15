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
 * Mobile input enhancement layer. Provides bounded (max 20) session-isolated history
 * navigation mimicking terminal up/down arrow behavior for touch-screen mobile devices.
 */

import { useCallback, useRef, useState } from 'react';

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
  navigatePrevious: (currentInput: string) => string | null;
  navigateNext: () => string | null;
  resetNavigation: () => void;
}

export function useMobilePromptHistory(chatId: string): UseMobilePromptHistoryReturn {
  // -1 indicates user is not browsing history (active draft mode)
  const [currentIndex, setCurrentIndex] = useState<number>(-1);
  const draftBufferRef = useRef<string>('');

  const pushHistory = useCallback(
    (prompt: string) => {
      recordPromptHistory(chatId, prompt);
      setCurrentIndex(-1);
      draftBufferRef.current = '';
    },
    [chatId],
  );

  const resetNavigation = useCallback(() => {
    setCurrentIndex(-1);
    draftBufferRef.current = '';
  }, []);

  const navigatePrevious = useCallback(
    (currentInput: string): string | null => {
      const history = getPromptHistory(chatId);
      if (history.length === 0) {
        return null;
      }

      if (currentIndex === -1) {
        // Save current user draft before entering historical navigation
        draftBufferRef.current = currentInput;
        const targetIndex = history.length - 1;
        setCurrentIndex(targetIndex);
        return history[targetIndex] ?? null;
      }

      if (currentIndex > 0) {
        const targetIndex = currentIndex - 1;
        setCurrentIndex(targetIndex);
        return history[targetIndex] ?? null;
      }

      // Already at the oldest recorded item
      return history[0] ?? null;
    },
    [chatId, currentIndex],
  );

  const navigateNext = useCallback((): string | null => {
    const history = getPromptHistory(chatId);
    if (history.length === 0 || currentIndex === -1) {
      return null;
    }

    if (currentIndex < history.length - 1) {
      const targetIndex = currentIndex + 1;
      setCurrentIndex(targetIndex);
      return history[targetIndex] ?? null;
    }

    // Navigated past the newest record -> restore user draft
    setCurrentIndex(-1);
    return draftBufferRef.current;
  }, [chatId, currentIndex]);

  const history = getPromptHistory(chatId);

  return {
    historyCount: history.length,
    currentIndex,
    pushHistory,
    navigatePrevious,
    navigateNext,
    resetNavigation,
  };
}
