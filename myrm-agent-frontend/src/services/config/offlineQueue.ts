/**
 * [INPUT]
 * - `./offlinePersistableKeys` OFFLINE_PERSISTABLE_CONFIG_KEYS (POS: the only keys allowed to touch browser storage)
 * - `./types` ConfigChange (POS: one pending config write)
 *
 * [OUTPUT]
 * loadOfflineQueue / saveOfflineQueue / clearOfflineQueue: the `localStorage` queue of changes that could not reach the backend.
 * takeUnpersistableOfflineEntries: lifts entries for non-allowlisted keys out of browser storage.
 * isNetworkError / isRecoverableSyncError: tell a transient failure (retry later) from a real one.
 *
 * [POS]
 * Persistence half of the config sync layer's offline support. Only allowlisted keys are ever written; every other
 * key is retried from memory by `ConfigSyncManager` and is gone after a reload, so no secret lands in clear text next to
 * the page's scripts. Replay decisions live in `offlineReplay.ts`.
 */
import { OFFLINE_PERSISTABLE_CONFIG_KEYS } from './offlinePersistableKeys';
import type { ConfigChange } from './types';

const OFFLINE_QUEUE_KEY = 'config-offline-queue';

function isPersistable(change: ConfigChange): boolean {
  return OFFLINE_PERSISTABLE_CONFIG_KEYS.has(change.key);
}

/** Same key queued twice: keep the latest value but the EARLIEST base version (the server version the edit diverged from). */
function mergeOfflineChanges(changes: ConfigChange[]): ConfigChange[] {
  const byKey = new Map<ConfigChange['key'], ConfigChange>();
  for (const change of changes) {
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
    const stored = localStorage.getItem(OFFLINE_QUEUE_KEY);
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
    localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(merged));
  } catch (error) {
    console.warn('[ConfigSync] Failed to save offline queue:', error);
  }
}

export function clearOfflineQueue(): void {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.removeItem(OFFLINE_QUEUE_KEY);
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
  try {
    const kept = stored.filter(isPersistable);
    if (kept.length > 0) {
      localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(kept));
    } else {
      localStorage.removeItem(OFFLINE_QUEUE_KEY);
    }
  } catch (error) {
    console.warn('[ConfigSync] Failed to remove unpersistable offline entries:', error);
  }
  return unpersistable;
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError && (error.message.includes('fetch') || error.message.includes('network'));
}

export function isRecoverableSyncError(error: string): boolean {
  const normalized = error.toLowerCase();
  return (
    normalized.includes('backend not available') || normalized.includes('network') || normalized.includes('offline')
  );
}
