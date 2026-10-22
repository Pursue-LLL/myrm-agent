/**
 * [INPUT]
 * React hooks (useState, useEffect, useCallback)
 *
 * [OUTPUT]
 * useQueueDockCollapsePersistence: Hook managing per-chat queue dock collapse state with localStorage persistence.
 *
 * [POS]
 * UI persistence layer for Composer Queue Dock. Aligns with Traycer PR #2441 / Hermes Composer Queue UI.
 */

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY_PREFIX = 'myrm:queue-dock-collapsed:';

export function getQueueDockStorageKey(chatId: string | null | undefined): string | null {
  if (!chatId || !chatId.trim()) {
    return null;
  }
  return `${STORAGE_KEY_PREFIX}${chatId.trim()}`;
}

export function readQueueDockCollapsed(chatId: string | null | undefined, defaultValue = false): boolean {
  if (typeof window === 'undefined') {
    return defaultValue;
  }
  const key = getQueueDockStorageKey(chatId);
  if (!key) {
    return defaultValue;
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) {
      return defaultValue;
    }
    return raw === 'true';
  } catch {
    return defaultValue;
  }
}

export function writeQueueDockCollapsed(chatId: string | null | undefined, collapsed: boolean): void {
  if (typeof window === 'undefined') {
    return;
  }
  const key = getQueueDockStorageKey(chatId);
  if (!key) {
    return;
  }

  try {
    window.localStorage.setItem(key, collapsed ? 'true' : 'false');
  } catch {
    // Graceful fallback when localStorage is restricted or full
  }
}

export function useQueueDockCollapsePersistence(chatId: string | null | undefined, initialDefault = false) {
  const [isCollapsed, setIsCollapsedState] = useState<boolean>(() =>
    readQueueDockCollapsed(chatId, initialDefault),
  );

  useEffect(() => {
    setIsCollapsedState(readQueueDockCollapsed(chatId, initialDefault));
  }, [chatId, initialDefault]);

  const setCollapsed = useCallback(
    (collapsed: boolean) => {
      setIsCollapsedState(collapsed);
      writeQueueDockCollapsed(chatId, collapsed);
    },
    [chatId],
  );

  const toggleCollapsed = useCallback(() => {
    setIsCollapsedState((prev) => {
      const next = !prev;
      writeQueueDockCollapsed(chatId, next);
      return next;
    });
  }, [chatId]);

  return {
    isCollapsed,
    setCollapsed,
    toggleCollapsed,
  };
}
