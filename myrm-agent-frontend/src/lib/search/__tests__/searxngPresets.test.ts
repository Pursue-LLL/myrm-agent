import { describe, expect, it } from 'vitest';

import { buildSearxngExtraParams, detectSearxngPreset, SEARXNG_REGION_PRESETS } from '@/lib/search/searxngPresets';

describe('searxngPresets', () => {
  it('buildSearxngExtraParams returns china preset fields', () => {
    const extra = buildSearxngExtraParams('china');
    expect(extra).toEqual(SEARXNG_REGION_PRESETS.china);
    expect(extra.language).toBe('zh-CN');
  });

  it('detectSearxngPreset recognizes stored extra_params', () => {
    expect(detectSearxngPreset(SEARXNG_REGION_PRESETS.academic)).toBe('academic');
    expect(detectSearxngPreset({ language: 'en', categories: 'it' })).toBe('global');
  });
});
