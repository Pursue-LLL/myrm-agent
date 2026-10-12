/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: PackingCandidateDTO, BilledTokenBudgetDTO, MarginalValueMetricsDTO,
 *        PackedCandidateItemDTO, DroppedCandidateItemDTO, TokenAccountingReportDTO,
 *        PackedRecallResultDTO, PackRecallRequest, InspectMarginalRequest, InspectMarginalResponseItem
 * Functions: packRecallCandidates, inspectMarginalValues, getDefaultBudget
 *
 * [POS]
 * Client service for Budget Greedy Marginal Value Recall Packing Suite (Item 122 P2).
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export interface PackingCandidateDTO {
  id: string;
  content: string;
  relevance_score: number;
  confidence_score?: number;
  billed_tokens?: number;
  storage_tokens?: number;
  domain_tags?: string[];
  source_session_id?: string | null;
}

export interface BilledTokenBudgetDTO {
  max_billed_tokens: number;
  diversity_penalty_lambda: number;
  min_marginal_value_threshold: number;
  max_redundancy_threshold: number;
  max_items_limit: number;
  allow_greedy_backfill: boolean;
}

export interface MarginalValueMetricsDTO {
  base_utility: number;
  redundancy_score: number;
  marginal_info_gain: number;
  marginal_value: number;
  marginal_value_density: number;
}

export interface PackedCandidateItemDTO {
  candidate: PackingCandidateDTO;
  metrics: MarginalValueMetricsDTO;
  order_index: number;
  cumulative_billed_tokens: number;
}

export interface DroppedCandidateItemDTO {
  candidate: PackingCandidateDTO;
  metrics: MarginalValueMetricsDTO;
  reason: string;
}

export interface TokenAccountingReportDTO {
  total_candidates_examined: number;
  items_packed_count: number;
  items_dropped_count: number;
  billed_tokens_spent: number;
  billed_tokens_budget: number;
  billed_tokens_remaining: number;
  storage_tokens_total: number;
  storage_tokens_saved: number;
  budget_utilization_pct: number;
  redundant_tokens_filtered: number;
  average_marginal_density: number;
}

export interface PackedRecallResultDTO {
  packed_items: PackedCandidateItemDTO[];
  dropped_candidates: DroppedCandidateItemDTO[];
  accounting: TokenAccountingReportDTO;
  composed_prompt_block: string;
  active_mode: string;
}

export interface PackRecallRequest {
  candidates: PackingCandidateDTO[];
  budget?: BilledTokenBudgetDTO;
  enable_knapsack?: boolean;
}

export interface InspectMarginalRequest {
  candidates: PackingCandidateDTO[];
  budget?: BilledTokenBudgetDTO;
}

export interface InspectMarginalResponseItem {
  candidate: PackingCandidateDTO;
  metrics: MarginalValueMetricsDTO;
}

const BASE_URL = '/memory/budget-packing';

export async function packRecallCandidates(payload: PackRecallRequest): Promise<PackedRecallResultDTO> {
  return apiRequest<PackedRecallResultDTO>(`${BASE_URL}/pack`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function inspectMarginalValues(payload: InspectMarginalRequest): Promise<InspectMarginalResponseItem[]> {
  return apiRequest<InspectMarginalResponseItem[]>(`${BASE_URL}/inspect-marginal`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getDefaultBudget(): Promise<BilledTokenBudgetDTO> {
  return apiRequest<BilledTokenBudgetDTO>(`${BASE_URL}/default-budget`, { method: 'GET' });
}
