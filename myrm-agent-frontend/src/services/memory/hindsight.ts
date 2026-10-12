/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Hindsight Experience Replay and Retrospective Reflection Buffer DTOs and API clients:
 * - reflectTaskFailure
 * - queryPreExecutionWarnings
 * - listHindsightRules
 * - getHindsightBufferStats
 *
 * [POS]
 * Frontend API client for hindsight reflection buffer, counterfactual failure rule extraction, and proactive pre-execution warnings.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface FailureTurnInput {
  turn_index: number;
  tool_name: string;
  tool_input?: Record<string, string | number | boolean>;
  tool_output?: string;
  error_message?: string;
  timestamp?: number | null;
}

export interface FailureTrajectoryInput {
  task_id: string;
  task_goal: string;
  turns?: FailureTurnInput[];
  terminal_error?: string;
}

export interface HindsightRuleResponse {
  rule_id: string;
  task_pattern: string;
  mistake_signature: string;
  correction_advice: string;
  tags: string[];
  confidence: number;
  hit_count: number;
  created_at: number;
}

export interface ReflectTaskFailureRequest {
  trajectory: FailureTrajectoryInput;
  max_turns?: number;
}

export interface ReflectTaskFailureResponse {
  rule: HindsightRuleResponse;
  status: string;
  message: string;
}

export interface PreExecutionWarningQuery {
  task_goal: string;
  intended_tools?: string[] | null;
  top_k?: number;
}

export interface PreExecutionWarningResponse {
  rule_id: string;
  task_pattern: string;
  warning_text: string;
  recommended_action: string;
  confidence: number;
}

export interface PreExecutionWarningsListResponse {
  warnings: PreExecutionWarningResponse[];
  total_warnings: number;
  task_goal: string;
}

export interface ReflectionBufferStatsResponse {
  total_rules: number;
  avg_confidence: number;
  total_hits: number;
}

export const reflectTaskFailure = async (
  request: ReflectTaskFailureRequest,
): Promise<ReflectTaskFailureResponse> => {
  return apiRequest<ReflectTaskFailureResponse>('/memory/hindsight/reflect', {
    method: 'POST',
    body: JSON.stringify(request),
  });
};

export const queryPreExecutionWarnings = async (
  query: PreExecutionWarningQuery,
): Promise<PreExecutionWarningsListResponse> => {
  return apiRequest<PreExecutionWarningsListResponse>('/memory/hindsight/warnings', {
    method: 'POST',
    body: JSON.stringify(query),
  });
};

export const listHindsightRules = async (): Promise<HindsightRuleResponse[]> => {
  return apiRequest<HindsightRuleResponse[]>('/memory/hindsight/rules', {
    method: 'GET',
  });
};

export const getHindsightBufferStats = async (): Promise<ReflectionBufferStatsResponse> => {
  return apiRequest<ReflectionBufferStatsResponse>('/memory/hindsight/stats', {
    method: 'GET',
  });
};
