import { describe, expect, it } from 'vitest';

import legacyRemapJson from '@shared/config/provider_legacy_remap.json';

import { remapLegacyProviderId, deriveRoutingProfile, migrateDefaultModelConfig, migrateProvidersBundle } from '../providerIdentityMigration';

describe('providerIdentityMigration legacy remap', () => {
  it('matches shared/config/provider_legacy_remap.json for every entry', () => {
    const sharedRemap = legacyRemapJson as Record<string, string>;

    for (const [legacyId, canonicalId] of Object.entries(sharedRemap)) {
      expect(remapLegacyProviderId(legacyId)).toBe(canonicalId);
      expect(remapLegacyProviderId(legacyId.replace(/_/g, '-'))).toBe(canonicalId);
    }
  });

  it('leaves unknown provider ids unchanged', () => {
    expect(remapLegacyProviderId('openai')).toBe('openai');
    expect(remapLegacyProviderId('')).toBe('');
  });

  it('normalizes mixed case and hyphen variants like server normalize_storage_provider_id', () => {
    expect(remapLegacyProviderId('Google')).toBe('gemini');
    expect(remapLegacyProviderId('GOOGLE')).toBe('gemini');
    expect(remapLegacyProviderId('google-genai')).toBe('gemini');
    expect(remapLegacyProviderId('QWEN')).toBe('dashscope');
  });
});

describe('deriveRoutingProfile', () => {
  it('returns existing routingProfile when set', () => {
    expect(
      deriveRoutingProfile({
        id: 'custom',
        routingProfile: 'openrouter',
        name: 'Custom',
        isBuiltIn: false,
        isEnabled: true,
        apiKeys: [],
        apiUrl: '',
        enabledModels: [],
        availableModels: [],
        providerType: 'openai-like',
      }),
    ).toBe('openrouter');
  });

  it('derives from valid custom providerType', () => {
    expect(
      deriveRoutingProfile({
        id: 'my-gateway',
        routingProfile: '',
        name: 'Gateway',
        isBuiltIn: false,
        isEnabled: true,
        apiKeys: [],
        apiUrl: '',
        enabledModels: [],
        availableModels: [],
        providerType: 'anthropic-like',
      }),
    ).toBe('anthropic');
  });

  it('falls back to provider id when providerType is legacy/invalid', () => {
    expect(
      deriveRoutingProfile({
        id: 'openai',
        routingProfile: '',
        name: 'OpenAI',
        isBuiltIn: false,
        isEnabled: true,
        apiKeys: [],
        apiUrl: '',
        enabledModels: [],
        availableModels: [],
        providerType: 'openai' as never,
      }),
    ).toBe('openai');
  });
});

describe('migrateDefaultModelConfig visionFallbackModel slot', () => {
  it('wraps legacy SingleModelSelection into ModelSlot primary', () => {
    const migrated = migrateDefaultModelConfig({
      baseModel: { primary: null, fallback: null },
      liteModel: { primary: null, fallback: null },
      fastModeModel: null,
      routingConfig: null,
      visionFallbackModel: { providerId: 'openai', model: 'gpt-4o-mini' } as never,
    });

    expect(migrated.visionFallbackModel).toEqual({
      primary: { providerId: 'openai', model: 'gpt-4o-mini' },
      fallback: null,
    });
  });
});

describe('migrateProvidersBundle legacy providerType', () => {
  it('does not throw when persisted providers carry invalid providerType', () => {
    const migrated = migrateProvidersBundle({
      providers: [
        {
          id: 'openai',
          routingProfile: '',
          name: 'OpenAI',
          isBuiltIn: false,
          isEnabled: true,
          apiKeys: [],
          apiUrl: '',
          enabledModels: [],
          availableModels: [],
          providerType: 'openai' as never,
        },
      ],
    });

    expect(migrated.providers[0]?.routingProfile).toBe('openai');
  });
});

describe('migrateRouting partial/incomplete routingConfig', () => {
  it('does not throw when routingConfig lacks lightModel/reasoningModel slots', () => {
    const migrated = migrateDefaultModelConfig({
      baseModel: { primary: null, fallback: null },
      liteModel: { primary: null, fallback: null },
      fastModeModel: null,
      routingConfig: { enabled: true } as never,
    });

    expect(migrated.routingConfig?.enabled).toBe(true);
    expect(migrated.routingConfig?.lightModel).toBeUndefined();
  });

  it('does not throw when routingConfig slot is null', () => {
    const migrated = migrateDefaultModelConfig({
      baseModel: { primary: null, fallback: null },
      liteModel: { primary: null, fallback: null },
      fastModeModel: null,
      routingConfig: {
        enabled: true,
        lightModel: null,
        reasoningModel: null,
      } as never,
    });

    expect(migrated.routingConfig?.lightModel).toBeNull();
  });
});
