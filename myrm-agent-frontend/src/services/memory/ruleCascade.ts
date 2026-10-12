/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 99:
 * FiveDimPreFilteredEvidenceMemoryAndDeterministicRuleCascadeSuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints.
 * Strict typing applied: No `any` types allowed. Single file < 300 lines.
 */

import { apiClient } from '@/services/api';

export type EvidenceScopeKind = 'global' | 'organization' | 'workspace' | 'directory' | 'file';
export type EvidenceSourceKind = 'user_explicit' | 'tool_verified' | 'agent_inferred';
export type EvidencePermissionLevel = 'public' | 'workspace_internal' | 'confidential_admin';

export interface FiveDimEvidenceMetadataDTO {
  scope: EvidenceScopeKind;
  scope_path: string;
  source: EvidenceSourceKind;
  source_authority: number;
  created_at?: string | null;
  half_life_days: number;
  confidence: number;
  permission: EvidencePermissionLevel;
}

export interface DeterministicRuleEntryDTO {
  rule_id: string;
  title: string;
  rule_content: string;
  metadata: FiveDimEvidenceMetadataDTO;
  is_enforced: boolean;
}

export interface RegisterRuleRequestDTO {
  rule_id: string;
  title: string;
  rule_content: string;
  metadata: FiveDimEvidenceMetadataDTO;
  is_enforced?: boolean;
}

export interface RegisterRuleResponseDTO {
  is_success: boolean;
  rule_id: string;
  registered_rule: DeterministicRuleEntryDTO;
}

export interface QueryCascadedRulesRequestDTO {
  target_path: string;
}

export interface CascadedRuleSetDTO {
  target_path: string;
  inherited_rules: DeterministicRuleEntryDTO[];
  effective_rules_count: number;
  sources_breakdown: Record<string, number>;
}

export interface PreFilterEvidenceRequestDTO {
  candidates: DeterministicRuleEntryDTO[];
  allowed_scopes?: EvidenceScopeKind[];
  scope_path_prefix?: string;
  min_authority?: number;
  min_confidence?: number;
  required_permission?: EvidencePermissionLevel;
  max_decay_age_days?: number;
}

export interface PreFilteredEvidenceResponseDTO {
  passed_items: DeterministicRuleEntryDTO[];
  total_evaluated: number;
  passed_count: number;
  rejection_reasons: Record<string, number>;
}

export async function registerDeterministicRule(
  request: RegisterRuleRequestDTO
): Promise<RegisterRuleResponseDTO> {
  const payload = {
    rule_id: request.rule_id,
    title: request.title,
    rule_content: request.rule_content,
    metadata: request.metadata,
    is_enforced: request.is_enforced ?? true,
  };
  return apiClient.post<RegisterRuleResponseDTO>('/memory/rules/register', payload);
}

export async function queryCascadedRules(
  targetPath: string
): Promise<CascadedRuleSetDTO> {
  return apiClient.post<CascadedRuleSetDTO>('/memory/rules/cascade', {
    target_path: targetPath,
  });
}

export async function listAllDeterministicRules(): Promise<DeterministicRuleEntryDTO[]> {
  return apiClient.get<DeterministicRuleEntryDTO[]>('/memory/rules/list');
}

export async function preFilterEvidence(
  request: PreFilterEvidenceRequestDTO
): Promise<PreFilteredEvidenceResponseDTO> {
  const payload = {
    candidates: request.candidates,
    allowed_scopes: request.allowed_scopes,
    scope_path_prefix: request.scope_path_prefix,
    min_authority: request.min_authority ?? 0.0,
    min_confidence: request.min_confidence ?? 0.0,
    required_permission: request.required_permission,
    max_decay_age_days: request.max_decay_age_days,
  };
  return apiClient.post<PreFilteredEvidenceResponseDTO>('/memory/rules/pre-filter', payload);
}
