/**
 * [INPUT]
 * - `./types` ConfigAdapter / ConfigRecord / CORE_CONFIG_KEYS / ALL_CONFIG_KEYS (POS: backend access and the key sets)
 *
 * [OUTPUT]
 * loadInitialConfigs: first fetch of the user's configuration, with retry; optionally core-first.
 * landLateRecords: writes records that arrive after the first screen into the gaps of the caches and tells subscribers.
 *
 * [POS]
 * Loading half of `ConfigSyncManager.initialize()`. Sandbox mode returns only the core keys so the first screen is not
 * held back and hands over a thunk for the rest; local mode returns everything at once (the backend is on the same
 * machine). The manager owns what to do with the result; the records that come back later (background preload,
 * on-demand read of one key) land through one function.
 */
import { cloneDeep } from 'lodash-es';
import type { ConfigAdapter, ConfigKey, ConfigRecord } from './types';
import { ALL_CONFIG_KEYS, CORE_CONFIG_KEYS } from './types';

const INIT_FETCH_MAX_ATTEMPTS = 3;
const INIT_FETCH_RETRY_DELAY_MS = 500;

export interface InitialConfigLoad {
  configs: Map<ConfigKey, ConfigRecord>;
  /** Core-first loading only: starts fetching the keys that were not part of `configs`. */
  loadRemaining: (() => Promise<Map<ConfigKey, ConfigRecord>>) | null;
}

async function fetchAllWithRetry(
  fetchFn: () => Promise<Map<ConfigKey, ConfigRecord>>,
): Promise<Map<ConfigKey, ConfigRecord>> {
  let lastError: unknown;

  for (let attempt = 0; attempt < INIT_FETCH_MAX_ATTEMPTS; attempt += 1) {
    try {
      return await fetchFn();
    } catch (error) {
      lastError = error;
      if (attempt < INIT_FETCH_MAX_ATTEMPTS - 1) {
        await new Promise((resolve) => setTimeout(resolve, INIT_FETCH_RETRY_DELAY_MS));
      }
    }
  }

  throw lastError;
}

/**
 * A late answer can be older than the cache by the time it arrives: the user saved the key meanwhile, or an answer for
 * the same key came back first. A key the cache already holds therefore keeps its value; only the gaps are filled.
 * These writes do not go through `ConfigSyncManager.set()`, so subscribers are told here; without it, logic that waits
 * for a configuration to become ready (such as the securityConfig and YOLO mutual-exclusion replay) is never triggered.
 */
export function landLateRecords(
  records: Iterable<[ConfigKey, ConfigRecord]>,
  cache: Map<ConfigKey, ConfigRecord>,
  baseCache: Map<ConfigKey, ConfigRecord>,
  notify: (key: ConfigKey, record: ConfigRecord) => void,
): void {
  for (const [key, record] of records) {
    if (cache.has(key)) {
      continue;
    }
    cache.set(key, record);
    baseCache.set(key, cloneDeep(record));
    notify(key, record);
  }
}

export async function loadInitialConfigs(adapter: ConfigAdapter, coreFirst: boolean): Promise<InitialConfigLoad> {
  if (!coreFirst) {
    return { configs: await fetchAllWithRetry(() => adapter.getAll()), loadRemaining: null };
  }

  const configs = await fetchAllWithRetry(() => adapter.getAll(CORE_CONFIG_KEYS));
  const remainingKeys = ALL_CONFIG_KEYS.filter((key) => !CORE_CONFIG_KEYS.includes(key));
  return {
    configs,
    loadRemaining: remainingKeys.length > 0 ? () => fetchAllWithRetry(() => adapter.getAll(remainingKeys)) : null,
  };
}
