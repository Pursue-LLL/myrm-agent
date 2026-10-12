/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Ebbinghaus Temporal Decay and Tiered Storage Archival DTOs and API clients:
 * - registerMemoryDecay
 * - evaluateMemoryLifecycle
 * - rerankCandidatesWithDecay
 * - reviveColdMemory
 * - exportColdArchive
 *
 * [POS]
 * Frontend API client for Ebbinghaus decay curve lifecycle governance and tiered hot/warm/cold storage.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type StorageTierKind = 'HOT' | 'WARM' | 'COLD' | string;

export interface RegisterMemoryDecayRequest {
  memory_id: string;
  content: string;
  importance?: number;
  pinned?: boolean;
  created_at?: number;
}

export interface RegisterMemoryDecayResponse {
  memory_id: string;
  initial_score: number;
  initial_tier: StorageTierKind;
  pinned: boolean;
}

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

export interface CandidateItemInput {
  memory_id: string;
  content: string;
  base_similarity: number;
}

export interface RerankCandidatesRequest {
  candidates: CandidateItemInput[];
  decay_weight?: number;
  exclude_cold?: boolean;
  current_time?: number;
}

export interface ScoredRerankItemSchema {
  memory_id: string;
  content: string;
  base_similarity: number;
  decay_score: number;
  final_score: number;
  tier: StorageTierKind;
}

export interface RerankCandidatesResponse {
  total_returned: number;
  items: ScoredRerankItemSchema[];
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

export const registerMemoryDecay = async (
  request: RegisterMemoryDecayRequest,
): Promise<RegisterMemoryDecayResponse> => {
  return apiRequest<RegisterMemoryDecayResponse>('/memory/lifecycle/register', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: { 'Content-Type': 'application/json' },
  });
};

export const evaluateMemoryLifecycle = async (
  request?: EvaluateLifecycleRequest,
): Promise<EvaluateLifecycleResponse> => {
  return apiRequest<EvaluateLifecycleResponse>('/memory/lifecycle/evaluate', {
    method: 'POST',
    body: JSON.stringify(request || {}),
    headers: { 'Content-Type': 'application/json' },
  });
};

export const rerankCandidatesWithDecay = async (
  request: RerankCandidatesRequest,
): Promise<RerankCandidatesResponse> => {
  return apiRequest<RerankCandidatesResponse>('/memory/lifecycle/rerank', {
    method: 'POST',
    body: JSON.stringify(request),
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
