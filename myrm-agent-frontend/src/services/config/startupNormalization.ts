/**
 * [INPUT]
 * - `./configInitLock` withConfigInitLock (POS: single-tab write lock for startup migrations)
 * - `./configNormalizer` normalizeConfigValue / isNormalizedDirty / STARTUP_NORMALIZE_KEYS (POS: the migration pipeline)
 *
 * [OUTPUT]
 * runStartupNormalization: re-saves the startup-normalized keys whose cached value differs from the normalized one.
 *
 * [POS]
 * Startup migration pass over the caches of `ConfigSyncManager`. Writes go through the manager's `commitIfDirty`, so a
 * row the server holds sealed but unreadable is never overwritten by a normalized default.
 */
import { withConfigInitLock } from './configInitLock';
import { isNormalizedDirty, normalizeConfigValue, STARTUP_NORMALIZE_KEYS } from './configNormalizer';
import type { ConfigKey, ConfigRecord, ConfigValueMap } from './types';

export async function runStartupNormalization(
  cache: ReadonlyMap<ConfigKey, ConfigRecord>,
  baseCache: ReadonlyMap<ConfigKey, ConfigRecord>,
  commitIfDirty: <K extends ConfigKey>(key: K, value: ConfigValueMap[K]) => boolean,
): Promise<void> {
  await withConfigInitLock(async () => {
    for (const key of STARTUP_NORMALIZE_KEYS) {
      const record = cache.get(key);
      if (!record) {
        continue;
      }

      const normalized = normalizeConfigValue(key, record.value as ConfigValueMap[typeof key]);
      if (normalized === null) {
        continue;
      }

      const base = baseCache.get(key);
      if (
        !isNormalizedDirty(key, base?.value as ConfigValueMap[typeof key], record.value as ConfigValueMap[typeof key])
      ) {
        continue;
      }

      commitIfDirty(key, normalized);
    }
  });
}
