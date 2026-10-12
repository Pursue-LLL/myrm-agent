/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Four-Tier Persistent Memory & SQLite FTS5 Compaction DTOs and API clients:
 * - saveFourTierMemory, getFourTierMemory, deleteFourTierMemory, listFourTierMemories
 * - searchFourTierFts (Millisecond BM25 full-text recall via SQLite FTS5)
 * - runFourTierDreamCompaction (Background /dream maintenance merging and pruning)
 *
 * [POS]
 * Frontend API service for Topic 01 Item 92 (Xiaomi MiMo Code/Desktop-inspired
 * Four-Tier Persistent Memory and FTS5 Self-Maintenance Compaction Suite).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type FourTierMemoryScope = 'project' | 'session' | 'progress' | 'global';

export interface FourTierMemoryItemDTO {
  item_id: string;
  scope: FourTierMemoryScope | string;
  title: string;
  content: string;
  project_hash: string;
  session_id: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface SaveFourTierMemoryRequestDTO {
  scope: FourTierMemoryScope | string;
  title: string;
  content: string;
  project_hash?: string;
  session_id?: string;
  tags?: string[];
  item_id?: string;
}

export interface FtsSearchResultDTO {
  item_id: string;
  scope: FourTierMemoryScope | string;
  project_hash: string;
  title: string;
  content: string;
  snippet: string;
  bm25_rank: number;
  updated_at: string;
}

export interface DreamCompactionReportDTO {
  dream_id: string;
  scanned_items_count: number;
  merged_items_count: number;
  pruned_items_count: number;
  retained_items_count: number;
  duration_ms: number;
  created_at: string;
}

export interface RunDreamCompactionRequestDTO {
  project_hash?: string;
  purge_progress_days?: number;
}

/**
 * Saves or updates a four-tier persistent memory item.
 */
export async function saveFourTierMemory(
  request: SaveFourTierMemoryRequestDTO
): Promise<FourTierMemoryItemDTO> {
  return apiRequest<FourTierMemoryItemDTO>('/memory/four-tier/items', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Retrieves a single four-tier memory item by ID.
 */
export async function getFourTierMemory(
  itemId: string,
  projectHash = 'default'
): Promise<FourTierMemoryItemDTO> {
  return apiRequest<FourTierMemoryItemDTO>(
    `/memory/four-tier/items/${encodeURIComponent(itemId)}?project_hash=${encodeURIComponent(projectHash)}`
  );
}

/**
 * Deletes a four-tier memory item by ID.
 */
export async function deleteFourTierMemory(
  itemId: string,
  projectHash = 'default'
): Promise<{ deleted: boolean; item_id: string }> {
  return apiRequest<{ deleted: boolean; item_id: string }>(
    `/memory/four-tier/items/${encodeURIComponent(itemId)}?project_hash=${encodeURIComponent(projectHash)}`,
    {
      method: 'DELETE',
    }
  );
}

/**
 * Lists stored memory items filtered optionally by scope, project_hash, and session_id.
 */
export async function listFourTierMemories(
  scope?: string,
  projectHash = 'default',
  sessionId?: string
): Promise<FourTierMemoryItemDTO[]> {
  const params = new URLSearchParams();
  if (projectHash) {
    params.set('project_hash', projectHash);
  }
  if (scope) {
    params.set('scope', scope);
  }
  if (sessionId) {
    params.set('session_id', sessionId);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiRequest<FourTierMemoryItemDTO[]>(
    `/memory/four-tier/items${query}`
  );
}

/**
 * Executes high-performance SQLite FTS5 BM25 search across memories.
 */
export async function searchFourTierFts(
  query: string,
  scope?: string,
  projectHash = 'default',
  limit = 10
): Promise<FtsSearchResultDTO[]> {
  const params = new URLSearchParams();
  params.set('query', query);
  if (projectHash) {
    params.set('project_hash', projectHash);
  }
  if (scope) {
    params.set('scope', scope);
  }
  if (limit) {
    params.set('limit', String(limit));
  }
  return apiRequest<FtsSearchResultDTO[]>(
    `/memory/four-tier/search?${params.toString()}`
  );
}

/**
 * Triggers background /dream compaction merging fragments and purging stale progress items.
 */
export async function runFourTierDreamCompaction(
  request: RunDreamCompactionRequestDTO = {}
): Promise<DreamCompactionReportDTO> {
  return apiRequest<DreamCompactionReportDTO>('/memory/four-tier/dream', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}
