import { beforeEach, describe, expect, it, vi } from 'vitest';

import { reloadPluginMcpServers } from '../reloadPluginMcpServers';

const { reloadKeys } = vi.hoisted(() => ({ reloadKeys: vi.fn() }));
vi.mock('@/services/config', () => ({ getConfigSyncManager: () => ({ reloadKeys }) }));

describe('reloadPluginMcpServers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    reloadKeys.mockResolvedValue(undefined);
  });

  it('reloads only the mcpServers row that plugin import and uninstall write on the server', async () => {
    await reloadPluginMcpServers();

    expect(reloadKeys).toHaveBeenCalledExactlyOnceWith(['mcpServers']);
  });

  it('logs and carries on when the reload fails, because the import or uninstall itself already succeeded', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    reloadKeys.mockRejectedValue(new Error('backend unreachable'));

    await expect(reloadPluginMcpServers()).resolves.toBeUndefined();

    expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
  });
});
