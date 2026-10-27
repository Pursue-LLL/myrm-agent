/**
 * [INPUT]
 * - `window.__MYRM_E2E_BLOCK_SEARCH_SYNC__` (POS: flag the E2E chat bridge sets to freeze the search config locally)
 * - `./types` ConfigChange / ConfigKey (POS: queued write and key union)
 *
 * [OUTPUT]
 * isE2eBlockedKey: whether a config key is frozen locally for the current E2E run.
 * withoutBlockedSearchChanges: the change list with frozen search writes removed.
 *
 * [POS]
 * Test-harness switch consulted by `ConfigSyncManager` so an E2E run's search configuration never reaches the backend
 * or its subscribers. Inert unless the E2E bridge sets the flag.
 */
import type { ConfigChange, ConfigKey } from './types';

function isE2eSearchSyncBlocked(): boolean {
  return typeof window !== 'undefined' && Boolean(window.__MYRM_E2E_BLOCK_SEARCH_SYNC__);
}

export function isE2eBlockedKey(key: ConfigKey): boolean {
  return key === 'searchServices' && isE2eSearchSyncBlocked();
}

export function withoutBlockedSearchChanges(changes: ConfigChange[]): ConfigChange[] {
  return isE2eSearchSyncBlocked() ? changes.filter((change) => change.key !== 'searchServices') : changes;
}
