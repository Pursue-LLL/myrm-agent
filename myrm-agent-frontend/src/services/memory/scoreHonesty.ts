/**
 * Retrieval score honesty and raw vs ranking API client.
 * Connects frontend inspection cards to dual-threshold gates and score breakdowns.
 */

import { apiClient } from '@/services/api';

export interface CandidateEvaluationItemDTO {
  id: string;
  content: string;
  raw_similarity: number;
  recency_factor?: number;
  importance_boost?: number;
  mmr_penalty?: number;
  rrf_score?: number;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface DualThresholdConfigDTO {
  raw_similarity_threshold: number;
  ranking_score_threshold: number;
  strict_mode: boolean;
}

export interface ScoreBreakdownDTO {
  raw_similarity: number;
  recency_factor: number;
  importance_boost: number;
  mmr_penalty: number;
  rrf_score: number;
  final_ranking_score: number;
  explanation: string;
}

export interface ThresholdEvaluationVerdictDTO {
  passed_raw: boolean;
  passed_ranking: boolean;
  admitted: boolean;
  rejection_stage: string;
  rejection_reason?: string | null;
}

export interface HonestCandidateResponseDTO {
  id: string;
  content: string;
  raw_similarity: number;
  ranking_score: number;
  breakdown: ScoreBreakdownDTO;
  metadata: Record<string, string | number | boolean | null>;
  verdict?: ThresholdEvaluationVerdictDTO | null;
}

export interface ScoreHonestyStatsDTO {
  total_candidates: number;
  admitted_count: number;
  rejected_count: number;
  raw_admitted_count: number;
  ranking_admitted_count: number;
  both_passed_count: number;
  divergence_count: number;
  divergence_rate: number;
  mean_raw_similarity: number;
  mean_ranking_score: number;
}

export interface EvaluateCandidatesRequest {
  candidates: CandidateEvaluationItemDTO[];
  config?: DualThresholdConfigDTO;
}

export interface EvaluateCandidatesResponse {
  evaluated: HonestCandidateResponseDTO[];
  stats: ScoreHonestyStatsDTO;
}

export interface FilterCandidatesResponse {
  admitted: HonestCandidateResponseDTO[];
  total_admitted: number;
}

export const scoreHonestyService = {
  /**
   * Run dual threshold evaluation on candidate memories and produce full attribution.
   */
  async evaluateCandidates(
    request: EvaluateCandidatesRequest
  ): Promise<EvaluateCandidatesResponse> {
    return apiClient.post<EvaluateCandidatesResponse>(
      '/api/memory/score-honesty/evaluate',
      request
    );
  },

  /**
   * Filter candidates and return only admitted items.
   */
  async filterCandidates(
    request: EvaluateCandidatesRequest
  ): Promise<FilterCandidatesResponse> {
    return apiClient.post<FilterCandidatesResponse>(
      '/api/memory/score-honesty/filter',
      request
    );
  },

  /**
   * Fetch aggregate diagnostics and divergence statistics.
   */
  async getStats(): Promise<ScoreHonestyStatsDTO> {
    return apiClient.get<ScoreHonestyStatsDTO>('/api/memory/score-honesty/stats');
  },

  /**
   * Liveness health check.
   */
  async checkHealth(): Promise<{ status: string; service: string }> {
    return apiClient.get<{ status: string; service: string }>(
      '/api/memory/score-honesty/health'
    );
  },
};
