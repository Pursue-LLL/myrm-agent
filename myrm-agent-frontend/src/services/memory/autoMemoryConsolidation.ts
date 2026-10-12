/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: AutoMemoryGatingConfigDTO, TurnGatingDecisionDTO, BudgetGatingDecisionDTO,
 *        IdleDetectionStateDTO, OverallGatingReportDTO, SixDimensionalMemoryArtifactDTO,
 *        EvaluateGatingRequest, EvaluateGatingResponse, ConsolidateSessionRequest,
 *        ConsolidateSessionResponse, UpdateGatingConfigRequest
 * Functions: getAutoConsolidationConfig, updateAutoConsolidationConfig,
 *            evaluateAutoConsolidationGating, consolidateSessionAutoMemory
 *
 * [POS]
 * Client service for Idle & Budget Gated Auto-Memory Consolidation Suite (Item 123 P1).
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export interface AutoMemoryGatingConfigDTO {
  enabled: boolean;
  idle_timeout_seconds: number;
  min_turn_count: number;
  min_info_density: number;
  min_remaining_budget_tokens: number;
  max_consolidation_cost_ratio: number;
}

export interface TurnGatingDecisionDTO {
  passed: boolean;
  turn_count: number;
  info_density: number;
  reason: string;
}

export interface BudgetGatingDecisionDTO {
  passed: boolean;
  remaining_tokens: number;
  estimated_cost_tokens: number;
  cost_ratio: number;
  reason: string;
}

export interface IdleDetectionStateDTO {
  session_id: string;
  idle_seconds: number;
  idle_threshold_seconds: number;
  is_idle_triggered: boolean;
  reason: string;
}

export interface OverallGatingReportDTO {
  session_id: string;
  should_consolidate: boolean;
  turn_decision: TurnGatingDecisionDTO;
  budget_decision: BudgetGatingDecisionDTO;
  idle_state: IdleDetectionStateDTO;
  final_rationale: string;
}

export interface SixDimensionalMemoryArtifactDTO {
  artifact_id: string;
  session_id: string;
  created_at_iso: string;
  working_directory: string;
  key_topics: string[];
  user_preferences: string[];
  reusable_domain_knowledge: string[];
  failure_lessons: string[];
  tool_calling_patterns: string[];
  token_cost: number;
  summary_digest: string;
}

export interface EvaluateGatingRequest {
  session_id: string;
  messages: Array<{ role: string; content: string }>;
  remaining_tokens?: number;
  last_active_timestamp?: number;
  current_timestamp?: number | null;
  require_idle?: boolean;
}

export interface EvaluateGatingResponse {
  report: OverallGatingReportDTO;
}

export interface ConsolidateSessionRequest {
  session_id: string;
  messages: Array<{ role: string; content: string }>;
  remaining_tokens?: number;
  working_directory?: string;
  tool_call_records?: string[];
  last_active_timestamp?: number;
  current_timestamp?: number | null;
  force_bypass_gating?: boolean;
  require_idle?: boolean;
}

export interface ConsolidateSessionResponse {
  report: OverallGatingReportDTO;
  artifact?: SixDimensionalMemoryArtifactDTO | null;
  persisted: boolean;
}

export interface UpdateGatingConfigRequest {
  config: AutoMemoryGatingConfigDTO;
}

export async function getAutoConsolidationConfig(): Promise<AutoMemoryGatingConfigDTO> {
  return apiRequest<AutoMemoryGatingConfigDTO>('/memory/auto-consolidation/config', { method: 'GET' });
}

export async function updateAutoConsolidationConfig(
  config: AutoMemoryGatingConfigDTO,
): Promise<AutoMemoryGatingConfigDTO> {
  return apiRequest<AutoMemoryGatingConfigDTO>('/memory/auto-consolidation/config', {
    method: 'PUT',
    body: JSON.stringify({ config }),
  });
}

export async function evaluateAutoConsolidationGating(req: EvaluateGatingRequest): Promise<EvaluateGatingResponse> {
  return apiRequest<EvaluateGatingResponse>('/memory/auto-consolidation/evaluate-gate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function consolidateSessionAutoMemory(
  req: ConsolidateSessionRequest,
): Promise<ConsolidateSessionResponse> {
  return apiRequest<ConsolidateSessionResponse>('/memory/auto-consolidation/consolidate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
