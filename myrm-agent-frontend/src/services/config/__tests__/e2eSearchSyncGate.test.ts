import { afterEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_PERSONAL_SETTINGS, DEFAULT_SEARCH_SERVICES, type ConfigChange } from '@/services/config/types';
import { isE2eBlockedKey, withoutBlockedSearchChanges } from '@/services/config/e2eSearchSyncGate';

const searchChange: ConfigChange<'searchServices'> = {
  key: 'searchServices',
  value: DEFAULT_SEARCH_SERVICES,
  expectedVersion: 'v1',
  timestamp: 1,
};
const settingsChange: ConfigChange<'personalSettings'> = {
  key: 'personalSettings',
  value: DEFAULT_PERSONAL_SETTINGS,
  expectedVersion: 'v1',
  timestamp: 2,
};

afterEach(() => {
  vi.unstubAllEnvs();
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
});

describe('e2eSearchSyncGate', () => {
  it('lets every key sync while the E2E flag is unset', () => {
    expect(isE2eBlockedKey('searchServices')).toBe(false);
    expect(withoutBlockedSearchChanges([searchChange, settingsChange])).toEqual([searchChange, settingsChange]);
  });

  it('freezes only the search services key while the E2E flag is set', () => {
    window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
    expect(isE2eBlockedKey('searchServices')).toBe(true);
    expect(isE2eBlockedKey('personalSettings')).toBe(false);
    expect(withoutBlockedSearchChanges([searchChange, settingsChange])).toEqual([settingsChange]);
  });

  it('never reads the E2E flag in a production build', () => {
    window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
    vi.stubEnv('NODE_ENV', 'production');
    expect(isE2eBlockedKey('searchServices')).toBe(false);
    expect(withoutBlockedSearchChanges([searchChange, settingsChange])).toEqual([searchChange, settingsChange]);
  });
});
