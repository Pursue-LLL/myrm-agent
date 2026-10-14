/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 109:
 * FailureTriggeredHistoricalSessionRetrievalSuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints (/memory/failure-search).
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import { apiClient } from '@/services/api';

export type FailureOutcomeType = 'successful_resolution' | 'cautionary_failure';

export interface ErrorFingerprintDTO {
  error_type: string;
  tool_name: string;
  normalized_pattern: string;
  exit_code: number | null;
  context_tags: string[];
}

export interface HistoricalResolutionEntryDTO {
  entry_id: string;
  session_id: string;
  turn_index: number;
  error_signature: string;
  outcome_type: FailureOutcomeType;
  solution_snippet: string;
  explanation: string;
  confidence: number;
  created_at: string;
}

export interface FailureRetrievalResultDTO {
  query_fingerprint: ErrorFingerprintDTO;
  total_matched: number;
  successful_resolutions: HistoricalResolutionEntryDTO[];
  cautionary_failures: HistoricalResolutionEntryDTO[];
  suggested_action: string;
}

export interface SearchFailureRequest {
  error_message: string;
  tool_name?: string;
  exit_code?: number | null;
  top_n?: number;
  include_cautionary?: boolean;
}

export interface FailureTriggerConfigDTO {
  enabled: boolean;
  auto_trigger_on_error: boolean;
  max_matches: number;
  min_similarity_threshold: number;
  include_cautionary_failures: boolean;
}

export async function queryFailureResolutions(
  request: SearchFailureRequest,
): Promise<FailureRetrievalResultDTO> {
  return apiClient.post<FailureRetrievalResultDTO>(
    '/memory/failure-search/query',
    request,
  );
}

export async function fetchHistoricalResolutions(): Promise<HistoricalResolutionEntryDTO[]> {
  return apiClient.get<HistoricalResolutionEntryDTO[]>(
    '/memory/failure-search/resolutions',
  );
}

export async function fetchFailureTriggerConfig(): Promise<FailureTriggerConfigDTO> {
  return apiClient.get<FailureTriggerConfigDTO>(
    '/memory/failure-search/config',
  );
}

export async function updateFailureTriggerConfig(
  config: FailureTriggerConfigDTO,
): Promise<FailureTriggerConfigDTO> {
  return apiClient.put<FailureTriggerConfigDTO>(
    '/memory/failure-search/config',
    config,
  );
}
