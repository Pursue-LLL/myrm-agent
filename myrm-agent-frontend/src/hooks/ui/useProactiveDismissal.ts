'use client';

/**
 * [INPUT]
 * - (localStorage, StorageEvent)
 *
 * [OUTPUT]
 * - dismissProactive: remember that a card was closed, for good or for a number of days.
 * - isProactiveDismissed: read that memory.
 * - useProactiveDismissed: the same memory as a hydration-safe, reactive hook.
 *
 * [POS]
 * Per-device memory for proactive cards (suggestion strips, discovery and update banners). A card the viewer
 * closed must stay closed on the next new chat, not only until the tab reloads. Storage can be unavailable
 * (private mode, quota), so the memory also lives in this module: closing then lasts for the page's lifetime
 * instead of silently doing nothing. A missing or corrupt value means "not dismissed".
 */

import { useSyncExternalStore } from 'react';

const KEY_PREFIX = 'myrm.proactive.dismissed.';
const FOREVER = 'forever';
const DAY_MS = 24 * 60 * 60 * 1000;

const memory = new Map<string, string>();
const listeners = new Set<() => void>();

function readStored(storageKey: string): string | null {
  try {
    const stored = localStorage.getItem(storageKey);
    if (stored !== null) {
      return stored;
    }
  } catch {
    // Storage is unavailable: fall back to what this page remembered.
  }
  return memory.get(storageKey) ?? null;
}

/** Whether `key` is dismissed right now: closed for good, or snoozed and not yet expired. */
export function isProactiveDismissed(key: string, now: number = Date.now()): boolean {
  const value = readStored(KEY_PREFIX + key);
  if (value === null) {
    return false;
  }
  return value === FOREVER || Number(value) > now;
}

/** Remembers the close. Without `snoozeDays` it is permanent; with it, the card may return after that many days. */
export function dismissProactive(key: string, options?: { snoozeDays?: number }): void {
  const storageKey = KEY_PREFIX + key;
  const value = options?.snoozeDays === undefined ? FOREVER : String(Date.now() + options.snoozeDays * DAY_MS);
  try {
    localStorage.setItem(storageKey, value);
  } catch {
    // Private mode or quota: the in-memory copy still keeps the card closed for this page view.
    memory.set(storageKey, value);
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key.startsWith(KEY_PREFIX)) {
      listener();
    }
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', onStorage);
  };
}

/** Server and hydration render "not dismissed", then the client's real memory applies without a mismatch. */
export function useProactiveDismissed(key: string): boolean {
  return useSyncExternalStore(
    subscribe,
    () => isProactiveDismissed(key),
    () => false,
  );
}
