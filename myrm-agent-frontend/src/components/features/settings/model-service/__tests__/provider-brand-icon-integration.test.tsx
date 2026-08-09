import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, beforeEach } from 'vitest';
import ProviderIcon from '../ProviderIcon';
import {
  BUILT_IN_PROVIDER_ICON_LOADERS,
  loadProviderBrandIconUrl,
  resetProviderBrandIconCacheForTests,
} from '../provider-brand-icon-loaders';

describe('provider brand icon integration', () => {
  beforeEach(() => {
    resetProviderBrandIconCacheForTests();
  });

  it('dynamic-imports real svg modules for representative providers', async () => {
    const sampleIds = ['openai', 'deepseek', 'siliconflow', 'dashscope', 'lm_studio'] as const;

    for (const providerId of sampleIds) {
      const mod = await BUILT_IN_PROVIDER_ICON_LOADERS[providerId]();
      expect(typeof mod.default).toBe('string');
      expect(mod.default.length).toBeGreaterThan(0);
    }
  });

  it('loadProviderBrandIconUrl resolves cacheable urls', async () => {
    const url = await loadProviderBrandIconUrl('anthropic');
    expect(url).toBeTruthy();
    expect(typeof url).toBe('string');

    const cached = await loadProviderBrandIconUrl('anthropic');
    expect(cached).toBe(url);
  });

  it('ProviderIcon renders img after real lazy load', async () => {
    render(<ProviderIcon providerId="openai" providerName="OpenAI" size={18} />);

    await waitFor(
      () => {
        const img = document.querySelector('img');
        expect(img).not.toBeNull();
        expect(img?.getAttribute('src')).toBeTruthy();
      },
      { timeout: 5000 },
    );
  });
});
