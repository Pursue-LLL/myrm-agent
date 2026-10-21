/**
 * Local capabilities probe client.
 *
 * [INPUT] lib/api::apiRequest (POS: authenticated HTTP client)
 * [OUTPUT] probeLocalCapabilities, invalidateLocalCapabilitiesProbeCache, PROBE_CACHE_TTL_MS
 * [POS] Frontend probe cache for onboarding (Ollama/LM Studio + SearXNG).
 */

import { apiRequest } from '@/lib/api';

interface DetectedModel {
  name: string;
  size_bytes: number | null;
  modified_at: string | null;
}

interface LocalProbeResult {
  provider: string;
  base_url: string;
  available: boolean;
  models: DetectedModel[];
  error: string | null;
  latency_ms: number;
}

export interface SearchProbeResult {
  provider: 'searxng';
  base_url: string;
  available: boolean;
  latency_ms: number;
  error?: string | null;
}

export interface ProbeLocalResponse {
  results: LocalProbeResult[];
  has_available: boolean;
  recommended_model: string | null;
  search?: SearchProbeResult[];
  search_has_available?: boolean;
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
    return {
      results: [],
      has_available: false,
      recommended_model: null,
      search: [],
      search_has_available: false,
    };
  }
}

export function invalidateLocalCapabilitiesProbeCache(): void {
  probeCache = null;
  probeCachedAt = 0;
}
