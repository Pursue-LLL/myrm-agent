/**
 * A plugin import writes its MCP servers straight into the backend's mcpServers row. With the real config manager and
 * the real config store, the refresh that follows the import must put the imported server on the settings page, and the
 * user's next edit must go out on the backend's version with that server still in the saved list, instead of a stale
 * list that would drop it.
 */

import { describe, expect, it, vi } from 'vitest';

import { reloadPluginMcpServers } from '@/components/features/plugins/reloadPluginMcpServers';
import { getConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ConfigChange, ConfigRecord, MCPServersConfigValue, SyncResult } from '@/services/config/types';
import type { MCPServiceConfig } from '../config/types';
import useConfigStore from '../useConfigStore';

const BROWSER = 'dev-local';
const PLUGIN_IMPORT = 'plugin-import';

const server = (name: string): MCPServiceConfig => ({
  name,
  type: 'stdio',
  command: `./${name}`,
  args: [],
  description: '',
  enabled: false,
});

const mcpServersRecord = (names: string[], version: string, deviceId: string): ConfigRecord => ({
  key: 'mcpServers',
  value: { mcpConfigs: names.map(server) } satisfies MCPServersConfigValue,
  meta: { version, updatedAt: '2026-01-01T00:00:00.000Z', deviceId },
});

const namesOf = (value: MCPServersConfigValue | MCPServiceConfig[]): string[] =>
  (Array.isArray(value) ? value : value.mcpConfigs).map((config) => config.name);

const accepted: SyncResult = { success: true, conflicts: [], newVersions: new Map([['mcpServers', '1000_9']]) };

describe('MCP settings after a plugin import wrote servers on the backend', () => {
  it('lists the imported server, and the next save keeps it and goes out on the backend version', async () => {
    const sync = vi.fn().mockResolvedValue(accepted);
    const getAll = vi
      .fn()
      .mockResolvedValue(new Map([['mcpServers', mcpServersRecord(['docs', 'pdf-server'], '1000_8', PLUGIN_IMPORT)]]));
    const manager = getConfigSyncManager();
    Object.assign(manager, {
      adapter: { getDeviceId: () => BROWSER, sync, getAll },
      cache: new Map([['mcpServers', mcpServersRecord(['docs'], '1000_7', BROWSER)]]),
      baseCache: new Map([['mcpServers', mcpServersRecord(['docs'], '1000_7', BROWSER)]]),
      _isInitialized: true,
    });
    await useConfigStore.getState().initConfig();
    expect(namesOf(useConfigStore.getState().mcpConfigs)).toEqual(['docs']);

    await reloadPluginMcpServers();

    expect(namesOf(useConfigStore.getState().mcpConfigs)).toEqual(['docs', 'pdf-server']);

    useConfigStore.getState().addMCPConfig(server('search'));
    await manager.forceSync();

    expect(sync).toHaveBeenCalledOnce();
    const [sent] = sync.mock.calls[0] as [ConfigChange[]];
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ key: 'mcpServers', expectedVersion: '1000_8' });
    expect(namesOf(sent[0].value as MCPServersConfigValue)).toEqual(['docs', 'pdf-server', 'search']);
  });
});
