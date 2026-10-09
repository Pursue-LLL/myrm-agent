/**
 * CJK Ideographic Iteration Mark ('々') Disambiguation and Recall API Client.
 * Connects frontend inspection cards to the antecedent resolver,
 * 3D token matrix generator, and bidirectional recall matcher.
 */

import { apiClient } from '@/services/api';

export interface DisambiguatedCjkTokensDTO {
  raw_tokens: string[];
  normalized_tokens: string[];
  anchor_tokens: string[];
  all_tokens: string[];
}

export interface IterationMarkRunDTO {
  raw_run: string;
  expanded_run: string;
  expanded_indices: number[];
  raw_bigrams: string[];
  normalized_bigrams: string[];
  anchor_bigrams: string[];
}

export interface DisambiguateCjkRequest {
  text: string;
}

export interface DisambiguateCjkResponse {
  original_text: string;
  normalized_text: string;
  has_iteration_mark: boolean;
  marks_expanded_count: number;
  runs: IterationMarkRunDTO[];
  tokens: DisambiguatedCjkTokensDTO;
}

export interface MatchCjkRecallRequest {
  query: string;
  target_text: string;
  threshold?: number;
}

export interface MatchCjkRecallResponse {
  query: string;
  target: string;
  is_matched: boolean;
  raw_overlap_count: number;
  normalized_overlap_count: number;
  anchor_overlap_count: number;
  composite_score: number;
  matched_tokens: string[];
}

export interface CjkIterationHealthResponse {
  status: string;
  module: string;
  version: string;
}

export const cjkIterationApi = {
  /** Disambiguate CJK iteration marks into normalized text and 3D token matrix */
  async disambiguate(request: DisambiguateCjkRequest): Promise<DisambiguateCjkResponse> {
    const res = await apiClient.post<DisambiguateCjkResponse>(
      '/api/memory/cjk-iteration/disambiguate',
      request
    );
    return res.data;
  },

  /** Calculate bidirectional recall match score between query and target memory */
  async match(request: MatchCjkRecallRequest): Promise<MatchCjkRecallResponse> {
    const res = await apiClient.post<MatchCjkRecallResponse>(
      '/api/memory/cjk-iteration/match',
      request
    );
    return res.data;
  },

  /** Retrieve health status of CJK iteration mark subsystem */
  async getHealth(): Promise<CjkIterationHealthResponse> {
    const res = await apiClient.get<CjkIterationHealthResponse>(
      '/api/memory/cjk-iteration/health'
    );
    return res.data;
  },
};
