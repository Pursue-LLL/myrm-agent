import { beforeEach, describe, expect, it, vi } from 'vitest';

import { reloadMigratedConfigs } from '../memory/migratedConfigReload';

const { reloadKeys } = vi.hoisted(() => ({ reloadKeys: vi.fn() }));
vi.mock('@/services/config', () => ({ getConfigSyncManager: () => ({ reloadKeys }) }));

describe('reloadMigratedConfigs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    reloadKeys.mockResolvedValue(undefined);
  });

  it('reloads the three rows the import lanes and the rollback write on the server', async () => {
    await reloadMigratedConfigs();

    expect(reloadKeys).toHaveBeenCalledExactlyOnceWith(['providers', 'mcpServers', 'personalSettings']);
  });

  it('logs and carries on when the reload fails, because the import itself already succeeded', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    reloadKeys.mockRejectedValue(new Error('backend unreachable'));

    await expect(reloadMigratedConfigs()).resolves.toBeUndefined();

    expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
  });
});
