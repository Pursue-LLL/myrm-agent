/**
 * Local capabilities probe client.
 *
 * [INPUT] lib/api::apiRequest (POS: authenticated HTTP client)
 * [OUTPUT] probeLocalCapabilities, invalidateLocalCapabilitiesProbeCache, PROBE_CACHE_TTL_MS
 * [POS] Frontend probe cache for one-click search setup (local SearXNG).
 */

import { apiRequest } from '@/lib/api';

export interface SearchProbeResult {
  provider: 'searxng';
  base_url: string;
  available: boolean;
  latency_ms: number;
  error?: string | null;
}

export interface ProbeLocalResponse {
  search?: SearchProbeResult[];
  recommended_searxng_url?: string;
}

const PROBE_CACHE_TTL_MS = 30_000;

export { PROBE_CACHE_TTL_MS };

let probeCache: ProbeLocalResponse | null = null;
let probeCachedAt = 0;

export async function probeLocalCapabilities(force = false): Promise<ProbeLocalResponse> {
  const now = Date.now();
  if (probeCache && !force && now - probeCachedAt < PROBE_CACHE_TTL_MS) {
    return probeCache;
  }

  try {
    const data = await apiRequest<ProbeLocalResponse>('/config/onboarding/probe-local', { method: 'GET' });
    probeCache = data;
    probeCachedAt = now;
    return data;
  } catch {
    return { search: [] };
  }
}

export function invalidateLocalCapabilitiesProbeCache(): void {
  probeCache = null;
  probeCachedAt = 0;
}
