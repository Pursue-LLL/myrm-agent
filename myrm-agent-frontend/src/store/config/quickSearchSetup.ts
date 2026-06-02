import type { SearchServiceConfigItem, SearchServiceType } from './types';
import { generateSearchServiceConfigId } from './searchService';
import { probeLocalCapabilities } from '@/services/localCapabilitiesProbe';
import { SEARXNG_REGION_PRESETS, type SearxngRegionPreset } from '@/lib/search/searxngPresets';

function defaultSearxngPreset(): SearxngRegionPreset {
  if (typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('zh')) {
    return 'china';
  }
  return 'global';
}

export function buildQuickSearchConfig(
  service: SearchServiceType,
  apiBase?: string | null,
  preset: SearxngRegionPreset = defaultSearxngPreset(),
): SearchServiceConfigItem {
  const extra = service === 'searxng' ? ({ ...SEARXNG_REGION_PRESETS[preset] } as Record<string, unknown>) : null;

  return {
    id: generateSearchServiceConfigId(),
    name: service === 'searxng' ? 'SearXNG Local' : service,
    enabled: true,
    role: 'primary',
    search_service: service,
    api_key: null,
    api_base: apiBase ?? null,
    extra_params: extra,
    latency: null,
    createdAt: Date.now(),
  };
}

export async function probeAndBuildQuickSearchConfig(): Promise<SearchServiceConfigItem | null> {
  const probe = await probeLocalCapabilities(true);
  const searxng = probe.search?.find((s) => s.provider === 'searxng' && s.available);
  if (searxng) {
    return buildQuickSearchConfig(
      'searxng',
      searxng.base_url || probe.recommended_searxng_url || 'http://127.0.0.1:8081',
    );
  }
  return null;
}
