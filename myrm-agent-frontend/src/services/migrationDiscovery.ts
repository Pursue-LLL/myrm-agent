/**
 * Migration assistant discovery client.
 *
 * [INPUT] lib/api::apiRequest (POS: authenticated HTTP client)
 * [OUTPUT] discoverMigrationSources, uploadMigrationZip, DiscoveryResponse
 * [POS] Frontend service for assistant data auto-discovery (local scan + cloud ZIP upload).
 */

import { apiRequest } from '@/lib/api';
import type { MemoryImportSource } from '@/services/memory/archive';

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

export interface MigrationSourceManifestItem {
  id: string;
  display_name: string;
  import_source: MemoryImportSource;
  discover_modes: ('local_scan' | 'zip_upload')[];
  deep_link_enabled: boolean;
}

export interface DiscoveryResponse {
  sources: ExternalSource[];
  scan_path: string;
  available: boolean;
  source_manifest?: MigrationSourceManifestItem[];
  source_manifest_authoritative?: boolean;
}

const DISCOVERY_CACHE_TTL_MS = 60_000;
const DEFAULT_MIGRATION_SOURCE_MANIFEST: readonly MigrationSourceManifestItem[] = [
  {
    id: 'hermes',
    display_name: 'Hermes',
    import_source: 'hermes',
    discover_modes: ['local_scan'],
    deep_link_enabled: true,
  },
  {
    id: 'openclaw',
    display_name: 'OpenClaw',
    import_source: 'openclaw',
    discover_modes: ['local_scan'],
    deep_link_enabled: true,
  },
  {
    id: 'claude',
    display_name: 'Claude Code',
    import_source: 'claude',
    discover_modes: ['local_scan'],
    deep_link_enabled: true,
  },
  {
    id: 'codex',
    display_name: 'Codex',
    import_source: 'codex',
    discover_modes: ['local_scan'],
    deep_link_enabled: true,
  },
  {
    id: 'pi',
    display_name: 'Pi Agent',
    import_source: 'pi',
    discover_modes: ['local_scan'],
    deep_link_enabled: true,
  },
  {
    id: 'chatgpt',
    display_name: 'ChatGPT',
    import_source: 'chatgpt',
    discover_modes: ['zip_upload'],
    deep_link_enabled: true,
  },
];
const DEFAULT_MIGRATION_SOURCE_MANIFEST_BY_ID = buildManifestById(DEFAULT_MIGRATION_SOURCE_MANIFEST);

let discoveryCache: DiscoveryResponse | null = null;
let discoveryCachedAt = 0;
let sourceManifestById: Record<string, MigrationSourceManifestItem> = {
  ...DEFAULT_MIGRATION_SOURCE_MANIFEST_BY_ID,
};

function normalizeSourceId(value: string): string {
  return value.trim().toLowerCase();
}

function buildManifestById(
  entries: readonly MigrationSourceManifestItem[],
): Record<string, MigrationSourceManifestItem> {
  const byId: Record<string, MigrationSourceManifestItem> = {};
  for (const entry of entries) {
    const id = normalizeSourceId(entry.id);
    if (!id) {
      continue;
    }
    byId[id] = {
      id,
      display_name: entry.display_name.trim() || entry.id,
      import_source: entry.import_source,
      discover_modes: [...entry.discover_modes],
      deep_link_enabled: entry.deep_link_enabled,
    };
  }
  return byId;
}

function resolveManifestEntry(sourceId: string): MigrationSourceManifestItem | null {
  const normalized = normalizeSourceId(sourceId);
  if (!normalized) {
    return null;
  }
  return sourceManifestById[normalized] ?? null;
}

export function registerMigrationSourceManifest(
  entries: readonly MigrationSourceManifestItem[] | null | undefined,
  options?: { authoritative?: boolean },
): void {
  const authoritative = options?.authoritative === true;
  if (!entries || entries.length === 0) {
    return;
  }
  const byId = buildManifestById(entries);
  if (Object.keys(byId).length === 0) {
    return;
  }
  sourceManifestById = authoritative
    ? byId
    : {
        ...DEFAULT_MIGRATION_SOURCE_MANIFEST_BY_ID,
        ...byId,
      };
}

export async function discoverMigrationSources(force = false): Promise<DiscoveryResponse> {
  const now = Date.now();
  if (!force && discoveryCache && now - discoveryCachedAt < DISCOVERY_CACHE_TTL_MS) {
    return discoveryCache;
  }

  const response = await apiRequest<DiscoveryResponse>('/migration/discover');
  registerMigrationSourceManifest(response.source_manifest, {
    authoritative: response.source_manifest_authoritative,
  });
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

export async function uploadMigrationZip(file: File): Promise<DiscoveryResponse> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiRequest<DiscoveryResponse>('/migration/upload', {
    method: 'POST',
    body: form,
  });
  registerMigrationSourceManifest(response.source_manifest, {
    authoritative: response.source_manifest_authoritative,
  });
  discoveryCache = response;
  discoveryCachedAt = Date.now();
  return response;
}

export function getMigrationSourceDisplayName(competitor: string): string {
  const entry = resolveManifestEntry(competitor);
  if (entry) {
    return entry.display_name;
  }
  const normalized = normalizeSourceId(competitor);
  return normalized || competitor;
}

export function resolveMigrationImportSource(competitor: string): MemoryImportSource {
  const entry = resolveManifestEntry(competitor);
  return entry?.import_source ?? 'auto';
}

export function canDeepLinkMigrationSource(sourceId: string): boolean {
  const entry = resolveManifestEntry(sourceId);
  return entry?.deep_link_enabled ?? false;
}
