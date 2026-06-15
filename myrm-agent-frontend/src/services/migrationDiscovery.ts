/**
 * Migration assistant discovery client.
 *
 * [INPUT] lib/api::apiRequest (POS: authenticated HTTP client)
 * [OUTPUT] discoverMigrationSources, DiscoveryResponse
 * [POS] Frontend service for local/Tauri assistant data auto-discovery.
 */

import { apiRequest } from '@/lib/api';

export interface DiscoveredFile {
  path: string;
  kind: string;
  size_bytes: number;
}

export interface ExternalSource {
  competitor: string;
  root: string;
  confidence: 'low' | 'medium' | 'high';
  files: DiscoveredFile[];
  memory_count_estimate: number;
  skill_count: number;
  has_api_keys: boolean;
}

export interface DiscoveryResponse {
  sources: ExternalSource[];
  scan_path: string;
  available: boolean;
}

const DISCOVERY_CACHE_TTL_MS = 60_000;

let discoveryCache: DiscoveryResponse | null = null;
let discoveryCachedAt = 0;

export async function discoverMigrationSources(force = false): Promise<DiscoveryResponse> {
  const now = Date.now();
  if (!force && discoveryCache && now - discoveryCachedAt < DISCOVERY_CACHE_TTL_MS) {
    return discoveryCache;
  }

  const response = await apiRequest<DiscoveryResponse>('/migration/discover');
  discoveryCache = response;
  discoveryCachedAt = Date.now();
  return response;
}

export function invalidateDiscoveryCache(): void {
  discoveryCache = null;
  discoveryCachedAt = 0;
}

export interface SecretsImportResponse {
  imported_keys: string[];
  skipped_keys: string[];
  message: string;
}

export async function importMigrationSecrets(competitor: string, root: string): Promise<SecretsImportResponse> {
  return apiRequest<SecretsImportResponse>('/migration/secrets/import', {
    method: 'POST',
    body: JSON.stringify({ competitor, root }),
  });
}

export function getMigrationSourceDisplayName(competitor: string): string {
  const names: Record<string, string> = {
    hermes: 'Hermes',
    claude: 'Claude Code',
    openclaw: 'OpenClaw',
    codex: 'Codex',
  };
  return names[competitor] ?? competitor;
}
