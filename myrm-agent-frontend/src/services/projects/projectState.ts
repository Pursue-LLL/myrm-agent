/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client)
 *
 * [OUTPUT]
 * Project State Living Fact Ledger and Four-Tier Context Projection DTOs & API clients:
 * - recordLivingFact
 * - listLivingFacts
 * - getLivingFact
 * - deleteLivingFact
 * - projectContext
 * - auditValidation
 *
 * [POS]
 * Frontend API service for long-term project living fact ledger and context projection pipeline (Topic 01 Item 63).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type ProjectFactType =
  | 'decision'
  | 'rejected_alternative'
  | 'constraint'
  | 'interface_contract'
  | 'validation_result'
  | string;

export type FactPromotionStage =
  | 'observation'
  | 'project_event'
  | 'confirmed_fact'
  | 'knowledge'
  | 'skill'
  | string;

export interface LivingFactDTO {
  fact_id: string;
  project_id: string;
  fact_type: ProjectFactType;
  title: string;
  content: string;
  target_components: string[];
  reason_or_constraint: string;
  validation_count: number;
  regression_count: number;
  promotion_stage: FactPromotionStage;
  created_at: string;
  updated_at: string;
  metadata: Record<string, string>;
}

export interface CreateLivingFactRequestDTO {
  fact_id: string;
  fact_type: ProjectFactType;
  title: string;
  content: string;
  target_components: string[];
  reason_or_constraint?: string;
  promotion_stage?: FactPromotionStage;
  metadata?: Record<string, string>;
}

export interface LivingFactListResponseDTO {
  project_id: string;
  total_count: number;
  facts: LivingFactDTO[];
}

export interface ContextProjectionRequestDTO {
  target_task: string;
  target_components: string[];
  token_budget?: number;
}

export interface ContextProjectionResponseDTO {
  project_id: string;
  rule_layer_facts: LivingFactDTO[];
  dependency_layer_facts: LivingFactDTO[];
  semantic_layer_facts: LivingFactDTO[];
  routed_facts: LivingFactDTO[];
  token_count_estimated: number;
  token_budget: number;
  projected_context_prompt: string;
}

export interface ValidationAuditRequestDTO {
  fact_id: string;
  passed: boolean;
  evidence_summary?: string;
}

export interface ValidationAuditResponseDTO {
  fact_id: string;
  project_id: string;
  passed: boolean;
  previous_stage: string;
  current_stage: string;
  promotion_occurred: boolean;
  regression_occurred: boolean;
  validation_count: number;
  regression_count: number;
  message: string;
}

/**
 * Record or update a living fact in the project state ledger.
 */
export async function recordLivingFact(
  projectId: string,
  payload: CreateLivingFactRequestDTO,
): Promise<LivingFactDTO> {
  return apiRequest<LivingFactDTO>(`/projects/${encodeURIComponent(projectId)}/state/facts`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * List living facts from the project state ledger with optional filters.
 */
export async function listLivingFacts(
  projectId: string,
  factType?: string,
  stage?: string,
): Promise<LivingFactListResponseDTO> {
  const query = new URLSearchParams();
  if (factType) query.set('fact_type', factType);
  if (stage) query.set('stage', stage);
  const qStr = query.toString();
  const url = `/projects/${encodeURIComponent(projectId)}/state/facts${qStr ? `?${qStr}` : ''}`;
  return apiRequest<LivingFactListResponseDTO>(url, {
    method: 'GET',
  });
}

/**
 * Retrieve a single living fact by ID.
 */
export async function getLivingFact(
  projectId: string,
  factId: string,
): Promise<LivingFactDTO> {
  return apiRequest<LivingFactDTO>(
    `/projects/${encodeURIComponent(projectId)}/state/facts/${encodeURIComponent(factId)}`,
    {
      method: 'GET',
    },
  );
}

/**
 * Delete a living fact from the project state ledger.
 */
export async function deleteLivingFact(
  projectId: string,
  factId: string,
): Promise<void> {
  await apiRequest<void>(
    `/projects/${encodeURIComponent(projectId)}/state/facts/${encodeURIComponent(factId)}`,
    {
      method: 'DELETE',
    },
  );
}

/**
 * Execute four-tier context projection pipeline for a specific task.
 */
export async function projectContext(
  projectId: string,
  payload: ContextProjectionRequestDTO,
): Promise<ContextProjectionResponseDTO> {
  return apiRequest<ContextProjectionResponseDTO>(
    `/projects/${encodeURIComponent(projectId)}/state/project-context`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

/**
 * Audit deterministic validation outcomes and promote/demote fact in promotion stages.
 */
export async function auditValidation(
  projectId: string,
  payload: ValidationAuditRequestDTO,
): Promise<ValidationAuditResponseDTO> {
  return apiRequest<ValidationAuditResponseDTO>(
    `/projects/${encodeURIComponent(projectId)}/state/audit-validation`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}
