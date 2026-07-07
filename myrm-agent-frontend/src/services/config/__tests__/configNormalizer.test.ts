import { describe, expect, it } from 'vitest';
import { normalizePersonalSettings, normalizeProviders } from '@/services/config/configNormalizer';
import { DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';
import { getInitialDefaultModelConfig } from '@/store/config/providerTypes';

describe('configNormalizer', () => {
  it('fills personal settings defaults without dropping server values', () => {
    const normalized = normalizePersonalSettings({ enableMemory: false });
    expect(normalized.enableMemory).toBe(false);
    expect(normalized.timezone).toBe(DEFAULT_PERSONAL_SETTINGS.timezone);
  });

  it('merges built-in providers on normalize', () => {
    const normalized = normalizeProviders({
      providers: [],
      defaultModelConfig: getInitialDefaultModelConfig(),
      customModelInfo: {},
    });
    expect(normalized.providers.length).toBeGreaterThan(0);
  });
});
