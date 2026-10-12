/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Token-Budget-Aware Codebase Semantic Memory Compaction DTOs and API clients:
 * - compactCodeMemory
 * - extractCodeSkeleton
 *
 * [POS]
 * Frontend API client for code memory AST skeletonization and token budget dynamic compaction.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type AbstractionLevelTier = 'L1_SIGNATURES' | 'L2_CONTROL_FLOW' | 'L3_FULL_SOURCE' | string;

export interface CodeBlockInput {
  file_path: string;
  source_code: string;
  relevance_score?: number;
  language?: string;
}

export interface CompactedBlockOutput {
  file_path: string;
  abstraction_level: AbstractionLevelTier;
  content: string;
  original_token_count: number;
  compacted_token_count: number;
}

export interface CodeCompactionRequest {
  items: CodeBlockInput[];
  token_budget?: number;
  min_level?: string;
  strip_private_symbols?: boolean;
  tokens_per_char_ratio?: number;
}

export interface CodeCompactionResponse {
  compacted_blocks: CompactedBlockOutput[];
  total_original_tokens: number;
  total_compacted_tokens: number;
  budget_limit: number;
  compression_ratio: number;
}

export interface SingleSkeletonRequest {
  source_code: string;
  level?: string;
  strip_private_symbols?: boolean;
  language?: string;
}

export interface SingleSkeletonResponse {
  abstraction_level: AbstractionLevelTier;
  content: string;
  original_token_count: number;
  compacted_token_count: number;
}

/**
 * Compact multiple codebase memory files/symbols dynamically under a target token budget.
 */
export async function compactCodeMemory(
  req: CodeCompactionRequest
): Promise<CodeCompactionResponse> {
  return apiRequest<CodeCompactionResponse>('/memory/compaction/code/compact', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Extract AST structural skeleton or control-flow skeleton for a single code snippet.
 */
export async function extractCodeSkeleton(
  req: SingleSkeletonRequest
): Promise<SingleSkeletonResponse> {
  return apiRequest<SingleSkeletonResponse>('/memory/compaction/code/skeleton', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
