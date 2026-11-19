/**
 * [INPUT]
 * @/services/config (POS: config sync layer; `reloadKeys` swaps in what the backend holds)
 *
 * [OUTPUT]
 * reloadMigratedConfigs: refreshes the cached settings rows that a migration import and its rollback write.
 *
 * [POS]
 * The import lanes write settings straight into the database: model slots and imported keys (providers), MCP servers,
 * and the global instructions (personal settings); the rollback restores the instructions. The settings pages read the
 * cached copy, so without this refresh they keep showing the old values and the next save collides with the backend's
 * version. Callers: the migration wizard and the Memory Command Center rollback.
 */
import { getConfigSyncManager, type ConfigKey } from '@/services/config';

const MIGRATION_WRITTEN_KEYS: readonly ConfigKey[] = ['providers', 'mcpServers', 'personalSettings'];

/** Runs after the import or rollback has succeeded, so a failed refresh only leaves the pages stale until a reload. */
export async function reloadMigratedConfigs(): Promise<void> {
  try {
    await getConfigSyncManager().reloadKeys(MIGRATION_WRITTEN_KEYS);
  } catch (error) {
    console.warn('[Migration] Reloading the migrated settings failed:', error);
  }
}
