import { describe, it, expect } from 'vitest';
import {
  buildSettingsSubTabQuery,
  defaultSubTabResolver,
  shouldSyncSettingsSubTabUrl,
} from '@/hooks/useSettingsSubTabUrl';

describe('useSettingsSubTabUrl helpers', () => {
  it('guards pathname before syncing sub tab URL', () => {
    expect(shouldSyncSettingsSubTabUrl('/settings/wiki', 'memory')).toBe(false);
    expect(shouldSyncSettingsSubTabUrl('/settings/memory', 'memory')).toBe(true);
  });

  it('builds sub query for non-default tabs', () => {
    const resolver = defaultSubTabResolver('explorer');
    expect(buildSettingsSubTabQuery('', 'archival', resolver)).toBe('sub=archival');
    expect(buildSettingsSubTabQuery('sub=archival', 'explorer', resolver)).toBe('');
  });
});
