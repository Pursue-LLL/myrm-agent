/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API client transport)
 *
 * [OUTPUT]
 * Onboarding insight sampling, first-encounter reporting & batch memory ingestion DTOs & API clients:
 * - scanAgentSources
 * - generateFirstEncounterReport
 * - confirmInsightIngest
 *
 * [POS]
 * Frontend API service for historical session keyframe sampling and first encounter report (Topic 01 Item 67).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface ScanAgentSourcesRequestDTO {
  custom_search_paths?: string[];
}

export interface OnboardingAgentSourceInfoDTO {
  source_id: string;
  display_name: string;
  detected: boolean;
  recent_sessions_count: number;
}

export interface OnboardingScanSummaryResponseDTO {
  sources: OnboardingAgentSourceInfoDTO[];
  total_detected: number;
}

export interface GenerateFirstEncounterReportRequestDTO {
  target_sources?: string[];
  max_sessions_per_source?: number;
  enable_entropy_inspection?: boolean;
}

export interface ExtractedInsightFactDTO {
  fact_id: string;
  category: 'tech_stack_preference' | 'hard_learned_lesson' | 'active_project_goal';
  summary: string;
  source_agent: string;
  confidence: number;
  fingerprint: string;
  origin_conversation_id: string;
  raw_quote?: string;
}

export interface FirstEncounterReportResponseDTO {
  report_id: string;
  generated_at: string;
  total_sessions_scanned: number;
  total_facts_extracted: number;
  secrets_redacted_count: number;
  token_budget_saved_estimate: number;
  candidate_facts: ExtractedInsightFactDTO[];
  sources_sampled: string[];
}

export interface ConfirmInsightIngestRequestDTO {
  report_id: string;
  selected_fact_ids: string[];
  target_agent_id?: string;
}

export interface ConfirmInsightIngestResponseDTO {
  success: boolean;
  ingested_count: number;
  deduplicated_count: number;
  message: string;
  ingested_fact_ids: string[];
}

/**
 * Probe host machine for active external agent directories (Cursor, Claude Code, Codex, Hermes, OpenClaw).
 */
export async function scanAgentSources(
  payload: ScanAgentSourcesRequestDTO = {},
): Promise<OnboardingScanSummaryResponseDTO> {
  return apiRequest<OnboardingScanSummaryResponseDTO>('/memory/onboarding/scan-sources', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Sample historical keyframes and generate structured first-encounter report.
 */
export async function generateFirstEncounterReport(
  payload: GenerateFirstEncounterReportRequestDTO = {},
): Promise<FirstEncounterReportResponseDTO> {
  return apiRequest<FirstEncounterReportResponseDTO>('/memory/onboarding/generate-report', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Confirm user-selected insight facts and batch ingest into persistent memory.
 */
export async function confirmInsightIngest(
  payload: ConfirmInsightIngestRequestDTO,
): Promise<ConfirmInsightIngestResponseDTO> {
  return apiRequest<ConfirmInsightIngestResponseDTO>('/memory/onboarding/confirm-ingest', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
