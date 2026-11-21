/**
 * [INPUT]
 * - `@/lib/auth-cp-token` parseCpAuthTokenUserId (POS: client-side parser for control-plane API tokens)
 * - `@/lib/guest` getAuthToken (POS: the session's API token, null when nobody is signed in)
 * - `./configFingerprint` valuesEqual (POS: deep equality for config values)
 * - `./offlinePersistableKeys` OFFLINE_PERSISTABLE_CONFIG_KEYS (POS: the only keys allowed to touch browser storage)
 * - `./types` ConfigChange (POS: one pending config write)
 *
 * [OUTPUT]
 * loadOfflineQueue / saveOfflineQueue / removeOfflineEntries: the `localStorage` queue of changes that have not been settled by the backend.
 * takeUnpersistableOfflineEntries: lifts entries for non-allowlisted keys out of browser storage.
 * discardUnattributedOfflineQueue: drops the backlog that belongs to no account once an account is signed in.
 * isRecoverableSyncError: tells a write that never reached a backend (retry later) from one the backend refused.
 *
 * [POS]
 * Persistence half of the config sync layer's offline support. Only allowlisted keys are ever written; every other
 * key is retried from memory by `ConfigSyncManager` and is gone after a reload, so no secret lands in clear text next to
 * the page's scripts. An entry leaves the store only when the backend settled that key (`removeOfflineEntries`); a
 * newer edit of the same key stays. Replay decisions live in `offlineReplay.ts`.
 *
 * Each account has its own queue: a browser profile shared by two accounts never replays one account's leftovers into
 * the other's configuration. A session whose token names no account (local mode) uses the bare key.
 */
import { parseCpAuthTokenUserId } from '@/lib/auth-cp-token';
import { getAuthToken } from '@/lib/guest';
import { valuesEqual } from './configFingerprint';
import { OFFLINE_PERSISTABLE_CONFIG_KEYS } from './offlinePersistableKeys';
import type { ConfigChange } from './types';

/** The key of a queue that belongs to no particular account; a signed-in account's queue lives under `<key>:<userId>`. */
const OFFLINE_QUEUE_KEY = 'config-offline-queue';

/** Read per call: the signed-in account can change while the page lives. */
function queueKey(): string {
  const token = getAuthToken();
  const userId = token ? parseCpAuthTokenUserId(token) : null;
  return userId ? `${OFFLINE_QUEUE_KEY}:${userId}` : OFFLINE_QUEUE_KEY;
}

function isPersistable(change: ConfigChange): boolean {
  return OFFLINE_PERSISTABLE_CONFIG_KEYS.has(change.key);
}

/**
 * Same key queued twice: keep the latest value but the EARLIEST base version (the server version the edit diverged from).
 * "Latest" is by edit time, not by arrival: a change retained after a failed send reaches the store after the newer
 * edits made while it was in flight, and must not overwrite them.
 */
function mergeOfflineChanges(changes: ConfigChange[]): ConfigChange[] {
  const byKey = new Map<ConfigChange['key'], ConfigChange>();
  for (const change of [...changes].sort((a, b) => a.timestamp - b.timestamp)) {
    const existing = byKey.get(change.key);
    byKey.set(
      change.key,
      existing ? { ...change, expectedVersion: existing.expectedVersion ?? change.expectedVersion } : change,
    );
  }
  return Array.from(byKey.values());
}

export function loadOfflineQueue(): ConfigChange[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const stored = localStorage.getItem(queueKey());
    return stored ? (JSON.parse(stored) as ConfigChange[]) : [];
  } catch {
    return [];
  }
}

/** Persists the allowlisted part of `changes`, merged into what is already queued; the rest stays in memory only. */
export function saveOfflineQueue(changes: ConfigChange[]): void {
  if (typeof window === 'undefined') {
    return;
  }
  const persistable = changes.filter(isPersistable);
  if (persistable.length === 0) {
    return;
  }
  try {
    const merged = mergeOfflineChanges([...loadOfflineQueue(), ...persistable]);
    localStorage.setItem(queueKey(), JSON.stringify(merged));
  } catch (error) {
    console.warn('[ConfigSync] Failed to save offline queue:', error);
  }
}

/** The stored copy of an edit `settled` covers: the same edit or an older one; the same millisecond counts only for the same value. */
function isSettledBy(entry: ConfigChange, settled: ConfigChange): boolean {
  return (
    entry.key === settled.key &&
    (entry.timestamp < settled.timestamp ||
      (entry.timestamp === settled.timestamp && valuesEqual(entry.value, settled.value)))
  );
}

/**
 * Drops from browser storage what the backend settled: per key, the stored copy of the settled edit and of every older
 * one. A newer edit of the same key, saved while the settled one was in flight, and every other key stay queued.
 */
export function removeOfflineEntries(settled: ConfigChange[]): void {
  if (typeof window === 'undefined' || settled.length === 0) {
    return;
  }
  const stored = loadOfflineQueue();
  const remaining = stored.filter((entry) => !settled.some((change) => isSettledBy(entry, change)));
  if (remaining.length === stored.length) {
    return;
  }
  writeStoredQueue(remaining, 'Failed to update offline queue:');
}

/** Stores `entries` as the account's queue, or removes the queue when nothing is left. */
function writeStoredQueue(entries: ConfigChange[], failureMessage: string): void {
  try {
    if (entries.length > 0) {
      localStorage.setItem(queueKey(), JSON.stringify(entries));
    } else {
      localStorage.removeItem(queueKey());
    }
  } catch (error) {
    console.warn(`[ConfigSync] ${failureMessage}`, error);
  }
}

/**
 * Removes entries for non-allowlisted keys from browser storage and returns them for in-memory replay.
 * Such entries must not wait in browser storage in clear text until the backend is reachable again.
 * Allowlisted entries are left in place.
 */
export function takeUnpersistableOfflineEntries(): ConfigChange[] {
  const stored = loadOfflineQueue();
  const unpersistable = stored.filter((change) => !isPersistable(change));
  if (unpersistable.length === 0) {
    return [];
  }
  writeStoredQueue(stored.filter(isPersistable), 'Failed to remove unpersistable offline entries:');
  return unpersistable;
}

/**
 * The bare key's backlog was written by a session that named no account: once an account is signed in nobody can tell
 * whose edits those are, so it is dropped rather than replayed into this account's configuration.
 */
export function discardUnattributedOfflineQueue(): void {
  if (typeof window === 'undefined' || queueKey() === OFFLINE_QUEUE_KEY) {
    return;
  }
  try {
    if (localStorage.getItem(OFFLINE_QUEUE_KEY) !== null) {
      localStorage.removeItem(OFFLINE_QUEUE_KEY);
      console.warn('[ConfigSync] Dropped an offline queue that belongs to no known account');
    }
  } catch (error) {
    console.warn('[ConfigSync] Failed to drop the unattributed offline queue:', error);
  }
}

/** Whether `SyncResult.error` says the write never reached a backend (see `BACKEND_NOT_AVAILABLE_ERROR`). */
export function isRecoverableSyncError(error: string): boolean {
  const normalized = error.toLowerCase();
  return (
    normalized.includes('backend not available') || normalized.includes('network') || normalized.includes('offline')
  );
}
