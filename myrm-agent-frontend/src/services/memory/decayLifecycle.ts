/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Ebbinghaus Temporal Decay and Tiered Storage Archival DTOs and API clients:
 * - evaluateMemoryLifecycle
 * - reviveColdMemory
 * - exportColdArchive
 *
 * [POS]
 * Frontend API client for Ebbinghaus decay curve lifecycle governance and tiered hot/warm/cold storage.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type StorageTierKind = 'HOT' | 'WARM' | 'COLD' | string;

export interface EvaluateLifecycleRequest {
  current_time?: number;
}

export interface EvaluateLifecycleResponse {
  total_evaluated: number;
  hot_count: number;
  warm_count: number;
  cold_count: number;
  migrated_count: number;
  migrated_memory_ids: string[];
}

export interface ReviveMemoryRequest {
  memory_id: string;
  boost_importance?: number;
}

export interface ReviveMemoryResponse {
  memory_id: string;
  new_score: number;
  new_tier: StorageTierKind;
  access_count: number;
}

export interface ColdArchiveItemSchema {
  memory_id: string;
  content: string;
  importance: number;
  created_at: number;
  last_accessed_at: number;
  access_count: number;
  pinned: boolean;
  score: number;
  tier: StorageTierKind;
}

export interface ExportColdArchiveResponse {
  total_archived: number;
  records: ColdArchiveItemSchema[];
}

export const evaluateMemoryLifecycle = async (
  request?: EvaluateLifecycleRequest,
): Promise<EvaluateLifecycleResponse> => {
  return apiRequest<EvaluateLifecycleResponse>('/memory/lifecycle/evaluate', {
    method: 'POST',
    body: JSON.stringify(request || {}),
    headers: { 'Content-Type': 'application/json' },
  });
};

export const reviveColdMemory = async (
  request: ReviveMemoryRequest,
): Promise<ReviveMemoryResponse> => {
  return apiRequest<ReviveMemoryResponse>('/memory/lifecycle/revive', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: { 'Content-Type': 'application/json' },
  });
};

export const exportColdArchive = async (): Promise<ExportColdArchiveResponse> => {
  return apiRequest<ExportColdArchiveResponse>('/memory/lifecycle/cold-archive');
};
