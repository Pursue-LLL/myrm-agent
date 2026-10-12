/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Targeted Experience Auto-Recall Trigger and Sliding Dedup DTOs and API clients:
 * - evaluateAutoRecall
 * - getSlidingWindowStats
 * - clearSessionAutoRecall
 *
 * [POS]
 * Frontend API client for 5-scenario trigger filtering, 5-turn sliding deduplication, and fail-open reranking.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type RecallTriggerKind =
  | 'task_start'
  | 'skill_load'
  | 'subagent_start'
  | 'write_preflight'
  | 'cron_start'
  | 'none'
  | string;

export type RerankerStatusKind =
  | 'applied'
  | 'reranker_skipped'
  | 'timed_out'
  | 'failed_open'
  | string;

export interface RecallCandidateDTO {
  memory_id: string;
  content: string;
  initial_score?: number;
  metadata?: Record<string, string | number | boolean>;
}

export interface AutoRecallEvaluateRequest {
  session_id: string;
  current_turn?: number;
  raw_candidates: RecallCandidateDTO[];
  event_name?: string | null;
  tool_name?: string | null;
  query_text?: string | null;
  force_recall?: boolean;
}

export interface AutoRecallDecisionResponse {
  triggered: boolean;
  trigger_type: RecallTriggerKind;
  candidates_pre_dedup: number;
  candidates_post_dedup: number;
  injected_candidates: RecallCandidateDTO[];
  reranker_status: RerankerStatusKind;
  audit_reason: string;
}

export interface SlidingWindowStatsResponse {
  session_id: string;
  active_window_turns: number;
  total_suppressed_id_count: number;
}

export interface SessionClearResponse {
  session_id: string;
  cleared: boolean;
}

/**
 * Evaluate sensitive lifecycle triggers, apply 5-turn sliding dedup, and fail-open rerank candidates.
 */
export async function evaluateAutoRecall(
  req: AutoRecallEvaluateRequest
): Promise<AutoRecallDecisionResponse> {
  return apiRequest<AutoRecallDecisionResponse>('/memory/auto-recall/evaluate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Get multi-turn sliding window suppression metrics for a session.
 */
export async function getSlidingWindowStats(
  sessionId: string
): Promise<SlidingWindowStatsResponse> {
  return apiRequest<SlidingWindowStatsResponse>(`/memory/auto-recall/stats/${sessionId}`, {
    method: 'GET',
  });
}

/**
 * Purge multi-turn deduplication history for a specific session.
 */
export async function clearSessionAutoRecall(
  sessionId: string
): Promise<SessionClearResponse> {
  return apiRequest<SessionClearResponse>(`/memory/auto-recall/sessions/${sessionId}`, {
    method: 'DELETE',
  });
}
