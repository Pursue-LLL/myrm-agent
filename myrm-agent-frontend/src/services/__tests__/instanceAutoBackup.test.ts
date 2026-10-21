import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ apiRequest: vi.fn() }));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: api.apiRequest,
}));

import { instanceAutoBackupService, type AutoBackup } from '../instanceAutoBackup';

const snapshot: AutoBackup = {
  supported: true,
  enabled: true,
  frequency: 'daily',
  keep: 3,
  directory: '/Users/me/backups',
  default_directory: false,
  folder_available: true,
  running: false,
  overdue: false,
  last_success_at: null,
  last_success_size: null,
  consecutive_failures: 0,
  last_error_code: null,
  backups: [],
};

describe('instanceAutoBackupService', () => {
  beforeEach(() => {
    api.apiRequest.mockReset();
    api.apiRequest.mockResolvedValue(snapshot);
  });

  it('reads the schedule silently so failures surface as localized copy', async () => {
    await expect(instanceAutoBackupService.get()).resolves.toBe(snapshot);

    expect(api.apiRequest).toHaveBeenCalledWith('/instance-archive/auto-backup', { method: 'GET', silent: true });
  });

  it('saves the whole schedule in one request', async () => {
    const settings = { enabled: true, frequency: 'weekly', keep: 5, directory: null } as const;

    await instanceAutoBackupService.update(settings);

    expect(api.apiRequest).toHaveBeenCalledWith('/instance-archive/auto-backup', {
      method: 'PUT',
      body: JSON.stringify(settings),
      silent: true,
    });
  });

  it('starts a backup without a request body', async () => {
    await instanceAutoBackupService.runNow();

    expect(api.apiRequest).toHaveBeenCalledWith('/instance-archive/auto-backup/run', { method: 'POST', silent: true });
  });
});
