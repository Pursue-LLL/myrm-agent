/**
 * Artifact Provenance and Cross-Session Asset Hub service
 */

import { getApiUrl } from '@/lib/api';

export type ArtifactCategory = 'all' | 'document' | 'code' | 'data' | 'media' | 'link' | 'other';

export interface ArtifactProvenanceItem {
  id: string;
  name: string;
  description: string | null;
  category: ArtifactCategory;
  created_at: string;
  updated_at: string;
  chat_id: string | null;
  chat_title: string | null;
  agent_id: string | null;
  latest_version_id: string | null;
  vault_uri: string | null;
  sha256_hash: string | null;
  commit_message: string | null;
  size_bytes: number | null;
  extension: string;
}

export interface ArtifactCategoryStats {
  all: number;
  document: number;
  code: number;
  data: number;
  media: number;
  link: number;
  other: number;
}

export interface ArtifactProvenanceListResponse {
  items: ArtifactProvenanceItem[];
  total: number;
  stats: ArtifactCategoryStats;
}

export interface ArtifactVersionTimelineEntry {
  version_id: string;
  vault_uri: string;
  sha256_hash: string;
  creator_id: string | null;
  commit_message: string | null;
  created_at: string;
  size_bytes: number | null;
}

export interface ArtifactProvenanceDetailResponse {
  artifact: ArtifactProvenanceItem;
  versions: ArtifactVersionTimelineEntry[];
  audit_logs_count: number;
}

export interface ArtifactProvenanceQueryFilter {
  category?: ArtifactCategory;
  query?: string;
  chat_id?: string;
  agent_id?: string;
  limit?: number;
  offset?: number;
}

export async function fetchArtifactProvenance(
  filter: ArtifactProvenanceQueryFilter = {},
): Promise<ArtifactProvenanceListResponse> {
  const params = new URLSearchParams();
  if (filter.category && filter.category !== 'all') {
    params.set('category', filter.category);
  }
  if (filter.query) {
    params.set('query', filter.query);
  }
  if (filter.chat_id) {
    params.set('chat_id', filter.chat_id);
  }
  if (filter.agent_id) {
    params.set('agent_id', filter.agent_id);
  }
  if (filter.limit !== undefined) {
    params.set('limit', String(filter.limit));
  }
  if (filter.offset !== undefined) {
    params.set('offset', String(filter.offset));
  }

  const queryStr = params.toString() ? `?${params.toString()}` : '';
  const response = await fetch(getApiUrl(`/files/artifacts/provenance${queryStr}`));
  if (!response.ok) {
    throw new Error(`Failed to fetch artifact provenance: ${response.statusText}`);
  }
  return response.json() as Promise<ArtifactProvenanceListResponse>;
}

export async function fetchArtifactProvenanceDetail(
  artifactId: string,
): Promise<ArtifactProvenanceDetailResponse> {
  const response = await fetch(getApiUrl(`/files/artifacts/provenance/${artifactId}`));
  if (!response.ok) {
    throw new Error(`Failed to fetch artifact provenance detail: ${response.statusText}`);
  }
  return response.json() as Promise<ArtifactProvenanceDetailResponse>;
}
