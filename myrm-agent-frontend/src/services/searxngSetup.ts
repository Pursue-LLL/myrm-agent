/**
 * Local SearXNG Docker setup via backend (local deploy only).
 */

import { apiRequest } from '@/lib/api';
import { invalidateLocalCapabilitiesProbeCache, probeLocalCapabilities } from '@/services/localCapabilitiesProbe';

export interface StartSearxngResponse {
  docker_invoked: boolean;
  available: boolean;
  base_url: string;
  latency_ms?: number;
  error?: string | null;
}

export async function startLocalSearxng(): Promise<StartSearxngResponse> {
  return apiRequest<StartSearxngResponse>('/config/onboarding/searxng/start', {
    method: 'POST',
  });
}

/** Start Docker SearXNG, refresh probe cache, return latest probe payload. */
export async function startLocalSearxngAndRefreshProbe() {
  const startResult = await startLocalSearxng();
  invalidateLocalCapabilitiesProbeCache();
  const probe = await probeLocalCapabilities(true);
  return { startResult, probe };
}
