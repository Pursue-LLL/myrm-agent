/** SearXNG region presets aligned with harness `SEARXNG_REGION_PRESETS`. */

export const SEARXNG_REGION_PRESETS = {
  global: { language: 'auto', categories: 'general' },
  china: { language: 'zh-CN', categories: 'general', engines: 'baidu,bing,google' },
  code: { language: 'en', categories: 'it', engines: 'github,stackoverflow,npm,pypi' },
  academic: { language: 'en', categories: 'science', engines: 'arxiv,google scholar,semantic scholar' },
} as const;

export type SearxngRegionPreset = keyof typeof SEARXNG_REGION_PRESETS;

export function detectSearxngPreset(extra: Record<string, unknown> | null | undefined): SearxngRegionPreset {
  if (!extra) return 'global';
  for (const key of Object.keys(SEARXNG_REGION_PRESETS) as SearxngRegionPreset[]) {
    const preset = SEARXNG_REGION_PRESETS[key];
    const matches = Object.entries(preset).every(([field, value]) => extra[field] === value);
    if (matches) return key;
  }
  return 'global';
}

export function buildSearxngExtraParams(preset: SearxngRegionPreset): Record<string, string> {
  return { ...SEARXNG_REGION_PRESETS[preset] };
}
