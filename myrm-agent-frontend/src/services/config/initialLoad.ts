/**
 * [INPUT]
 * - `./types` ConfigAdapter / ConfigRecord / CORE_CONFIG_KEYS / ALL_CONFIG_KEYS (POS: backend access and the key sets)
 *
 * [OUTPUT]
 * loadInitialConfigs: first fetch of the user's configuration, with retry; optionally core-first.
 *
 * [POS]
 * Loading half of `ConfigSyncManager.initialize()`. Sandbox mode returns only the core keys so the first screen is not
 * held back and hands over a thunk for the rest; local mode returns everything at once (the backend is on the same
 * machine). The manager owns what to do with the result.
 */
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

export async function loadInitialConfigs(adapter: ConfigAdapter, coreFirst: boolean): Promise<InitialConfigLoad> {
  if (!coreFirst) {
    return { configs: await fetchAllWithRetry(() => adapter.getAll()), loadRemaining: null };
  }

  const configs = await fetchAllWithRetry(() => adapter.getAll(CORE_CONFIG_KEYS));
  const remainingKeys = ALL_CONFIG_KEYS.filter((key) => !CORE_CONFIG_KEYS.includes(key));
  return {
    configs,
    loadRemaining: remainingKeys.length > 0 ? () => adapter.getAll(remainingKeys) : null,
  };
}
