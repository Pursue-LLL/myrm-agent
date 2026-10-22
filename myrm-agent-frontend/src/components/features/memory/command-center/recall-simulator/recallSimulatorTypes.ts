/**
 * Type contracts for Interactive Memory Recall Simulator & Secondary Governance.
 * Adheres strictly to zero-emoji and explicit type constraints (no `any`).
 */

export type RecallType = 'bm25' | 'vector' | 'causal_gene';

export type MemoryLifecycleStatus = 'active' | 'disabled' | 'locked';

export interface RecallCandidateScore {
  rrf_score: number;
  bm25_score: number;
  vector_similarity: number;
  causal_relevance: number;
}

export interface RecallCandidate {
  memory_id: string;
  content: string;
  summary: string;
  recall_type: RecallType | string;
  scores: RecallCandidateScore;
  confidence: number;
  is_negative_trap: boolean;
  status: MemoryLifecycleStatus;
  hit_reason: string;
  tags: string[];
}

export interface RecallSimulateRequest {
  query: string;
  top_k?: number;
  domain_filter?: string | null;
  recall_types?: RecallType[];
}

export interface RecallSimulateResponse {
  query: string;
  total_matched: number;
  candidates: RecallCandidate[];
  execution_latency_ms: number;
}

export interface MemoryGovernanceUpdateRequest {
  memory_id: string;
  confidence?: number;
  is_negative_trap?: boolean;
  status?: MemoryLifecycleStatus;
  merged_into_id?: string;
}

export interface MemoryGovernanceUpdateResponse {
  success: boolean;
  memory_id: string;
  message: string;
  updated_record: RecallCandidate;
}
