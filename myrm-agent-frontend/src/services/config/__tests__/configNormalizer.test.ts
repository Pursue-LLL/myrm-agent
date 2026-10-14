import { describe, expect, it } from 'vitest';
import { isNormalizedDirty, normalizePersonalSettings, normalizeProviders } from '@/services/config/configNormalizer';
import { DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';
import type { ProviderConfig } from '@/store/config/providerTypes';
import { getInitialDefaultModelConfig, getInitialProviders } from '@/store/config/providerTypes';

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

describe('built-in provider merge on normalize', () => {
  const definition = (): ProviderConfig => {
    const found = getInitialProviders().find((p) => p.id === 'xai');
    if (!found) {
      throw new Error('xai built-in provider is missing');
    }
    return found;
  };

  const normalizeSavedXai = (saved: Partial<ProviderConfig>): ProviderConfig => {
    const normalized = normalizeProviders({
      providers: [{ ...definition(), ...saved }],
      defaultModelConfig: getInitialDefaultModelConfig(),
      customModelInfo: {},
    });
    const result = normalized.providers.find((p) => p.id === 'xai');
    if (!result) {
      throw new Error('xai provider was dropped');
    }
    return result;
  };

  it('keeps every user-owned setting of a built-in provider', () => {
    const saved = {
      isEnabled: true,
      apiKeys: [{ id: 'key-1', key: 'not-a-real-key', remark: 'work', isActive: true }],
      apiUrl: 'https://gateway.example.com/v1',
      enabledModels: ['grok-4'],
      availableModels: ['grok-4', 'grok-3'],
      credentialPoolStrategy: 'least_used',
      oauthConnected: true,
      egressProxy: 'http://127.0.0.1:7890',
    } satisfies Partial<ProviderConfig>;

    expect(normalizeSavedXai(saved)).toMatchObject(saved);
  });

  it('keeps a saved "not connected" flag instead of treating it as missing', () => {
    expect(normalizeSavedXai({ oauthConnected: false }).oauthConnected).toBe(false);
  });

  it('falls back to the shipped definition for fields the saved copy lacks', () => {
    const shipped = definition();
    const result = normalizeSavedXai({
      isEnabled: undefined,
      apiUrl: undefined,
      enabledModels: undefined,
      availableModels: undefined,
    });

    expect(result).toMatchObject({
      isEnabled: shipped.isEnabled,
      apiUrl: shipped.apiUrl,
      enabledModels: shipped.enabledModels,
      availableModels: shipped.availableModels,
    });
  });

  it('pins identity fields to the shipped definition', () => {
    const shipped = definition();
    const result = normalizeSavedXai({ name: 'Renamed', routingProfile: 'openai', providerType: 'openai-like' });

    expect(result.name).toBe(shipped.name);
    expect(result.routingProfile).toBe(shipped.routingProfile);
    expect(result.isBuiltIn).toBe(true);
    expect(result.providerType).toBeUndefined();
  });

  it('does not rewrite a saved provider whose settings startup normalization used to drop', () => {
    const normalized = normalizeProviders(null);
    const saved = {
      ...normalized,
      providers: normalized.providers.map((p) =>
        p.id === 'xai'
          ? {
              ...p,
              oauthConnected: true,
              egressProxy: 'http://127.0.0.1:7890',
              credentialPoolStrategy: 'random' as const,
            }
          : p,
      ),
    };

    expect(isNormalizedDirty('providers', saved, saved)).toBe(false);
  });
});
