import { describe, expect, it, vi } from 'vitest';
import { resetConfigSyncManager, getConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { PersonalSettingsConfigValue } from '@/services/config/types';
import { DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';

describe('ConfigSyncManager.commitIfDirty', () => {
  it('skips write when value matches baseCache', () => {
    resetConfigSyncManager();
    const manager = getConfigSyncManager();
    const key = 'personalSettings' as const;
    const value: PersonalSettingsConfigValue = { ...DEFAULT_PERSONAL_SETTINGS };

    const cache = new Map([
      [
        key,
        {
          key,
          value,
          meta: { version: '1000_0', updatedAt: '2026-01-01T00:00:00.000Z', deviceId: 'dev' },
        },
      ],
    ]);

    Object.assign(manager, {
      cache,
      baseCache: new Map(cache),
      _isInitialized: true,
    });

    const setSpy = vi.spyOn(manager, 'set');
    const dirty = manager.commitIfDirty(key, value);
    expect(dirty).toBe(false);
    expect(setSpy).not.toHaveBeenCalled();
  });
});
