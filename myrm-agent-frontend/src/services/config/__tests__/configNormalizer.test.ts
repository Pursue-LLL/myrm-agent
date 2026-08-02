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

  it('strips studio preview profile from personal settings on startup normalize', () => {
    const normalized = normalizePersonalSettings({
      activeThemeProfileId: 'studio/__preview__',
      themeProfiles: [
        {
          id: 'studio/__preview__',
          name: 'Preview',
          layoutId: 'full-bleed',
          fontId: 'inter',
          builtin: false,
          palette: {
            primaryLight: '#112233',
            primaryDark: '#223344',
            primaryHoverLight: '#334455',
            primaryHoverDark: '#445566',
            primaryDarkLight: '#556677',
            primaryDarkDark: '#667788',
            dualAccent: false,
          },
          art: {
            focusX: 0.5,
            focusY: 0.5,
            wash: 0.5,
            mediaKind: 'none',
            assetRef: null,
            posterAssetRef: null,
          },
        },
      ],
    });
    expect(normalized.activeThemeProfileId).toBe('official-default');
    expect(normalized.themeProfiles).toEqual([]);
  });
});
