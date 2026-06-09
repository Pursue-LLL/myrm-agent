import { describe, expect, it } from 'vitest';

import legacyRemapJson from '@shared/config/provider_legacy_remap.json';

import { remapLegacyProviderId } from '../providerIdentityMigration';

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
