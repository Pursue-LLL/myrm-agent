import { describe, expect, it } from 'vitest';
import { BUILT_IN_PROVIDERS } from '@/store/config/providerTypes';
import { LLM_PROVIDER_BRAND_ICONS } from '../llm-provider-icons';

describe('LLM_PROVIDER_BRAND_ICONS', () => {
  it('covers every built-in provider id', () => {
    for (const providerId of BUILT_IN_PROVIDERS) {
      expect(LLM_PROVIDER_BRAND_ICONS[providerId]).toBeDefined();
    }
    expect(Object.keys(LLM_PROVIDER_BRAND_ICONS)).toHaveLength(BUILT_IN_PROVIDERS.length);
  });
});
