'use client';

/**
 * [INPUT]
 * - ./persistedStringStore::createPersistedStringStore (POS: per-device key → string memory with change notifications)
 *
 * [OUTPUT]
 * - dismissProactive: remember that a card was closed, for good or for a number of days.
 * - OFFER_SNOOZE_DAYS: how long a closed one-off offer (import, install) stays quiet.
 * - isProactiveDismissed: read that memory.
 * - useProactiveDismissed: the same memory as a hydration-safe, reactive hook.
 *
 * [POS]
 * Per-device memory for proactive cards (suggestion strips, discovery and update banners). A card the viewer
 * closed must stay closed on the next new chat, not only until the tab reloads. A missing or corrupt value
 * means "not dismissed".
 */

import { useSyncExternalStore } from 'react';

import { createPersistedStringStore } from './persistedStringStore';

const FOREVER = 'forever';
const DAY_MS = 24 * 60 * 60 * 1000;

/** A one-off offer is a single decision, so a closed one stays quiet this long instead of returning with every new chat. */
export const OFFER_SNOOZE_DAYS = 7;

const store = createPersistedStringStore('myrm.proactive.dismissed.');

/** Whether `key` is dismissed right now: closed for good, or snoozed and not yet expired. */
export function isProactiveDismissed(key: string, now: number = Date.now()): boolean {
  const value = store.read(key);
  if (value === null) {
    return false;
  }
  return value === FOREVER || Number(value) > now;
}

/** Remembers the close. Without `snoozeDays` it is permanent; with it, the card may return after that many days. */
export function dismissProactive(key: string, options?: { snoozeDays?: number }): void {
  store.write(key, options?.snoozeDays === undefined ? FOREVER : String(Date.now() + options.snoozeDays * DAY_MS));
}

/** Server and hydration render "not dismissed", then the client's real memory applies without a mismatch. */
export function useProactiveDismissed(key: string): boolean {
  return useSyncExternalStore(
    store.subscribe,
    () => isProactiveDismissed(key),
    () => false,
  );
}
