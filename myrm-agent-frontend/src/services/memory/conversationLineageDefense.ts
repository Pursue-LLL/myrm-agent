/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 97:
 * LineageDedupRecallBlindnessDefenseAndAutomationDemotionSuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints.
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import { apiClient } from '@/services/api';

export type ConversationSourceKind = 'interactive' | 'cron' | 'internal_worker';
export type HydrationDetailLevel = 'expanded_window' | 'compact_card';

export interface CandidateSessionDTO {
  session_id: string;
  lineage_root_id: string;
  parent_id?: string | null;
  generation: number;
  source_kind: ConversationSourceKind;
  title: string;
  raw_score: number;
  messages_context: string[];
  updated_at?: string | null;
}

export interface HydratedHitDTO {
  session_id: string;
  lineage_root_id: string;
  title: string;
  source_kind: ConversationSourceKind;
  detail_level: HydrationDetailLevel;
  content_snippet: string;
  window_messages: string[];
  token_estimate: number;
  is_demoted: boolean;
  is_lineage_primary: boolean;
  collapsed_generations_count: number;
  collapsed_session_ids: string[];
}

export interface LineageDedupAuditReportDTO {
  total_candidates: number;
  retained_hits_count: number;
  hidden_internal_count: number;
  demoted_cron_count: number;
  collapsed_lineage_count: number;
  interactive_top1_ratio: number;
  estimated_tokens_saved: number;
  token_saving_percent: number;
}

export interface LineageDefenseSearchRequestDTO {
  query?: string;
  limit?: number;
  include_internal?: boolean;
  window_size?: number;
  cron_weight_multiplier?: number;
  candidates?: CandidateSessionDTO[];
}

export interface LineageDefenseSearchResponseDTO {
  query: string;
  hits: HydratedHitDTO[];
  audit_report: LineageDedupAuditReportDTO;
}

export interface LineageDefenseAuditRequestDTO {
  candidates: CandidateSessionDTO[];
  include_internal?: boolean;
  window_size?: number;
  cron_weight_multiplier?: number;
}

export interface LineageDefenseStatsDTO {
  total_inspected_sessions: number;
  interactive_sessions_count: number;
  cron_sessions_count: number;
  internal_workers_count: number;
  average_token_savings_percent: number;
  recall_blindness_defense_active: boolean;
}

export async function searchWithLineageDefense(
  request: LineageDefenseSearchRequestDTO = {}
): Promise<LineageDefenseSearchResponseDTO> {
  const payload: LineageDefenseSearchRequestDTO = {
    query: request.query ?? '',
    limit: request.limit ?? 5,
    include_internal: request.include_internal ?? false,
    window_size: request.window_size ?? 5,
    cron_weight_multiplier: request.cron_weight_multiplier ?? 0.45,
    candidates: request.candidates ?? [],
  };
  return apiClient.post<LineageDefenseSearchResponseDTO>(
    '/memory/lineage-defense/search',
    payload
  );
}

export async function auditLineageDefense(
  request: LineageDefenseAuditRequestDTO
): Promise<LineageDefenseSearchResponseDTO> {
  return apiClient.post<LineageDefenseSearchResponseDTO>(
    '/memory/lineage-defense/audit',
    request
  );
}

export async function getLineageDefenseStats(): Promise<LineageDefenseStatsDTO> {
  return apiClient.get<LineageDefenseStatsDTO>('/memory/lineage-defense/stats');
}
