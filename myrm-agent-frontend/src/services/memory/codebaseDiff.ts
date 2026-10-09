/**
 * Codebase memory large diff fallback API client.
 * Connects frontend inspection cards to multi-tiered volume evaluation,
 * lockfile noise filtration, and fail-safe topology summarization.
 */

import { apiClient } from '@/services/api';

export interface DiffFileEntryDTO {
  path: string;
  additions: number;
  deletions: number;
  category: 'core_code' | 'lockfile' | 'generated' | 'documentation' | 'config_infra' | 'asset_binary' | string;
  is_generated?: boolean;
  is_renamed?: boolean;
  old_path?: string | null;
  patch_snippet?: string | null;
}

export interface DirectoryAggregateDTO {
  directory: string;
  file_count: number;
  total_additions: number;
  total_deletions: number;
  primary_category: string;
}

export interface LargeDiffFallbackConfigDTO {
  micro_max_files?: number;
  micro_max_lines?: number;
  moderate_max_files?: number;
  moderate_max_lines?: number;
  large_max_files?: number;
  large_max_lines?: number;
  hard_file_cap?: number;
  filter_lockfiles_in_moderate?: boolean;
  token_budget?: number;
}

export interface DiffFallbackVerdictDTO {
  tier: 'micro' | 'moderate' | 'large' | 'massive' | string;
  total_files: number;
  total_additions: number;
  total_deletions: number;
  is_truncated: boolean;
  truncation_reason?: string | null;
  active_files_count: number;
  filtered_noise_files_count: number;
  directory_aggregates: DirectoryAggregateDTO[];
  summary_text: string;
  applied_optimizations: string[];
}

export interface EvaluateDiffRequest {
  files: DiffFileEntryDTO[];
  declared_total_files?: number | null;
  is_api_truncated?: boolean;
  commit_message?: string | null;
  config?: LargeDiffFallbackConfigDTO | null;
}

export interface EvaluateDiffResponse {
  verdict: DiffFallbackVerdictDTO;
}

export interface ParseNumstatRequest {
  numstat_content: string;
}

export interface ParseNumstatResponse {
  entries: DiffFileEntryDTO[];
}

export const codebaseDiffService = {
  /**
   * Evaluates diff volume entries and returns complete fallback verdict.
   */
  async evaluateDiff(request: EvaluateDiffRequest): Promise<EvaluateDiffResponse> {
    return apiClient.post<EvaluateDiffResponse>(
      '/api/memory/codebase-diff/evaluate',
      request
    );
  },

  /**
   * Parses raw git diff --numstat output into structured file change entries.
   */
  async parseNumstat(request: ParseNumstatRequest): Promise<ParseNumstatResponse> {
    return apiClient.post<ParseNumstatResponse>(
      '/api/memory/codebase-diff/parse-numstat',
      request
    );
  },

  /**
   * Liveness health check.
   */
  async checkHealth(): Promise<{ status: string; service: string }> {
    return apiClient.get<{ status: string; service: string }>(
      '/api/memory/codebase-diff/health'
    );
  },
};
