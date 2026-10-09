/**
 * Memory Skill Triad and Physical Scope Isolation API Client.
 * Connects frontend inspection cards to deterministic scope physical partitioning,
 * visible provider degradation monitoring, machine CLI envelope formatting,
 * and 4-question pre-integration pipeline verification.
 */

import { apiClient } from '@/services/api';

export interface ScopeCoordinatesDTO {
  tenant_id: string;
  workspace_id: string;
  agent_id: string;
  session_id: string;
}

export interface ResolveScopeRequest {
  coordinates: ScopeCoordinatesDTO;
}

export interface ScopePartitionResponse {
  coordinates: ScopeCoordinatesDTO;
  namespace_hash: string;
  partition_dir: string;
  sqlite_path: string;
  is_isolated: boolean;
}

export interface DeleteScopeRequest {
  coordinates: ScopeCoordinatesDTO;
}

export interface DeleteScopeResponse {
  deleted: boolean;
  namespace_hash: string;
}

export interface ProviderAssessRequest {
  configured_providers: Record<string, string>;
  strict_mode?: boolean;
}

export interface ProviderDegradedInfoDTO {
  provider_type: string;
  configured_vendor: string;
  active_vendor: string;
  is_degraded: boolean;
  degradation_reason: string;
}

export interface DegradedReportResponse {
  overall_status: string;
  providers: ProviderDegradedInfoDTO[];
  strict_mode: boolean;
  summary: string;
}

export interface FormatCliEnvelopeRequest {
  command: string;
  scope: ScopeCoordinatesDTO;
  payload?: Record<string, string>;
  agent_mode?: boolean;
}

export interface CliEnvelopeResponse {
  status: string;
  command: string;
  duration_ms: number;
  scope: Record<string, string>;
  payload: Record<string, string>;
  error_code: string;
  error_message: string;
  exit_code: number;
  auto_confirmed: boolean;
}

export interface SurveyFindingDTO {
  message_assembly_site: string;
  identity_binding: string;
  installed_provider: string;
  write_hook_seam: string;
  is_ready_for_wiring: boolean;
}

export interface ValidateSurveyRequest {
  finding: SurveyFindingDTO;
}

export interface ValidateSurveyResponse {
  is_valid: boolean;
  issues: string[];
}

export interface VerifySeamsRequest {
  read_seam_configured: boolean;
  write_seam_configured: boolean;
  token_budget?: number;
  roundtrip_test_passed?: boolean;
}

export interface VerifySeamsResponse {
  is_verified: boolean;
  message: string;
}

export interface SkillTriadHealthResponse {
  status: string;
  module: string;
  version: string;
}

export const skillTriadApi = {
  /** Resolve physical partition layout and dedicated SQLite path for a scope */
  async resolveScope(request: ResolveScopeRequest): Promise<ScopePartitionResponse> {
    const res = await apiClient.post<ScopePartitionResponse>(
      '/api/memory/skill-triad/scope/resolve',
      request
    );
    return res.data;
  },

  /** Purge physical directory and SQLite database for a scope */
  async deleteScope(request: DeleteScopeRequest): Promise<DeleteScopeResponse> {
    const res = await apiClient.post<DeleteScopeResponse>(
      '/api/memory/skill-triad/scope/delete',
      request
    );
    return res.data;
  },

  /** Assess external provider availability and inspect visible degradation fallbacks */
  async assessProviders(request: ProviderAssessRequest): Promise<DegradedReportResponse> {
    const res = await apiClient.post<DegradedReportResponse>(
      '/api/memory/skill-triad/provider/assess',
      request
    );
    return res.data;
  },

  /** Format result into machine CLI JSON envelope with non-zero exit code on failure */
  async formatCliEnvelope(request: FormatCliEnvelopeRequest): Promise<CliEnvelopeResponse> {
    const res = await apiClient.post<CliEnvelopeResponse>(
      '/api/memory/skill-triad/cli/envelope',
      request
    );
    return res.data;
  },

  /** Validate repository pre-integration 4-question survey findings */
  async validateSurvey(request: ValidateSurveyRequest): Promise<ValidateSurveyResponse> {
    const res = await apiClient.post<ValidateSurveyResponse>(
      '/api/memory/skill-triad/pipeline/survey',
      request
    );
    return res.data;
  },

  /** Verify read/write integration seams and round-trip verification status */
  async verifySeams(request: VerifySeamsRequest): Promise<VerifySeamsResponse> {
    const res = await apiClient.post<VerifySeamsResponse>(
      '/api/memory/skill-triad/pipeline/verify',
      request
    );
    return res.data;
  },

  /** Retrieve health status of skill triad subsystem */
  async getHealth(): Promise<SkillTriadHealthResponse> {
    const res = await apiClient.get<SkillTriadHealthResponse>(
      '/api/memory/skill-triad/health'
    );
    return res.data;
  },
};
