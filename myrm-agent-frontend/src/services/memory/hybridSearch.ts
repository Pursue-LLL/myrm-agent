/**
 * Dual-engine hybrid search and graceful fallback service client.
 * Provides adaptive multi-factor RRF reranking and embedding circuit breaker telemetry.
 */

import { apiClient } from '@/services/api';

export interface CircuitBreakerStatsDTO {
  state: 'closed' | 'open' | 'half_open';
  failure_count: number;
  consecutive_successes: number;
  last_failure_time: number;
  tripped_count: number;
}

export interface AdaptiveRrfConfigDTO {
  rrf_k: number;
  fts_weight: number;
  vector_weight: number;
  importance_weight: number;
  half_life_seconds: number;
  apply_recency_decay: boolean;
}

export interface HybridMemoryItemDTO {
  item_id: string;
  content: string;
  title?: string;
  tags?: string[];
  metadata?: Record<string, string | number | boolean>;
  created_at?: string;
  importance?: number;
  timestamp?: number;
}

export interface HybridSearchResultDTO {
  item_id: string;
  title: string;
  content: string;
  score: number;
  source_channel: string;
  rank: number;
  matched_terms: string[];
  importance: number;
  recency_factor: number;
  is_degraded: boolean;
  degradation_reason: string;
}

export interface HybridSearchRequestDTO {
  query: string;
  limit?: number;
  enable_vector?: boolean;
  adaptive_rrf?: AdaptiveRrfConfigDTO;
}

export interface HybridSearchResponseDTO {
  query: string;
  mode: 'fts_only' | 'dense_only' | 'hybrid_rrf' | 'degraded_fallback';
  total_hits: number;
  results: HybridSearchResultDTO[];
}

export interface HybridEngineStatsDTO {
  total_items: number;
  synonym_terms_count: number;
  dense_vector_available: boolean;
  active_mode: string;
  db_path: string;
  circuit_breaker: CircuitBreakerStatsDTO;
  last_updated: string;
}

export interface TripCircuitBreakerResponseDTO {
  is_success: boolean;
  state: string;
  tripped_count: number;
}

export interface ResetCircuitBreakerResponseDTO {
  is_success: boolean;
  state: string;
}

export const hybridSearchService = {
  /**
   * Search memory using dual-drive FTS5 and vector with adaptive RRF and graceful fallback.
   */
  async search(request: HybridSearchRequestDTO): Promise<HybridSearchResponseDTO> {
    return apiClient.post<HybridSearchResponseDTO>('/memory/hybrid/items/search', request);
  },

  /**
   * Fetch current hybrid engine and circuit breaker telemetry snapshot.
   */
  async getStats(): Promise<HybridEngineStatsDTO> {
    return apiClient.get<HybridEngineStatsDTO>('/memory/hybrid/stats');
  },

  /**
   * Manually trip embedding circuit breaker for disaster recovery testing.
   */
  async tripCircuitBreaker(reason = 'manual_simulation'): Promise<TripCircuitBreakerResponseDTO> {
    return apiClient.post<TripCircuitBreakerResponseDTO>('/memory/hybrid/circuit-breaker/trip', { reason });
  },

  /**
   * Manually reset embedding circuit breaker to closed state.
   */
  async resetCircuitBreaker(): Promise<ResetCircuitBreakerResponseDTO> {
    return apiClient.post<ResetCircuitBreakerResponseDTO>('/memory/hybrid/circuit-breaker/reset');
  },

  /**
   * Insert or update a memory item in the local SQLite FTS5 engine.
   */
  async insertItem(item: HybridMemoryItemDTO): Promise<{ item_id: string; is_success: boolean }> {
    return apiClient.post<{ item_id: string; is_success: boolean }>('/memory/hybrid/items', { item });
  },
};
