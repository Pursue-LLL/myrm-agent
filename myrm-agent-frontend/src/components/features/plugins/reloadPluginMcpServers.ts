/**
 * [INPUT]
 * @/services/config (POS: config sync layer; `reloadKeys` swaps in what the backend holds)
 *
 * [OUTPUT]
 * reloadPluginMcpServers: refreshes the cached `mcpServers` row after a plugin import or uninstall changed it.
 *
 * [POS]
 * Plugin import and uninstall write the MCP server list straight into the database. The MCP settings page and the
 * integrations catalog read the cached copy, so without this refresh they keep listing the old servers and the next
 * save collides with the backend's version, which for a list can only be settled by dropping one side. Callers: the
 * import flow and the plugin manager.
 */
import { getConfigSyncManager } from '@/services/config';

/** Runs after the import or uninstall has succeeded, so a failed refresh only leaves the pages stale until a reload. */
export async function reloadPluginMcpServers(): Promise<void> {
  try {
    await getConfigSyncManager().reloadKeys(['mcpServers']);
  } catch (error) {
    console.warn('[Plugins] Reloading the MCP servers failed:', error);
  }
}
