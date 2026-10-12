/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 107:
 * BusinessScenarioExperienceTemplatesAndEscalationChecklistSuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints.
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import { apiClient } from '@/services/api';

export interface ChecklistStepDTO {
  step_index: number;
  name: string;
  description: string;
  mandatory: boolean;
  validation_rule: string;
}

export interface BusinessExperienceTemplateDTO {
  template_id: string;
  name: string;
  category: string;
  summary: string;
  checklist_steps: ChecklistStepDTO[];
  boundary_conditions: string[];
  sample_trajectory_ref: string;
  version: string;
  tags: string[];
  metadata: Record<string, string>;
  validated_count: number;
  rejected_count: number;
  last_validated_at: string | null;
}

export interface ListTemplatesResponseDTO {
  status: string;
  total_count: number;
  templates: BusinessExperienceTemplateDTO[];
}

export interface EscalationEvaluationRequest {
  order_id?: string | null;
  user_id?: string | null;
  intent?: string;
  shipment_status?: string;
  warranty_valid?: boolean;
  inventory_available?: boolean;
  user_dispute_count?: number;
  is_custom_order?: boolean;
  policy_clear?: boolean;
  user_confirmed?: boolean;
}

export interface EscalationEvaluationResponseDTO {
  action: string;
  reason: string;
  message: string;
  required_context: Record<string, string>;
  suggested_skill_or_tool: string;
}

export interface RecordValidationRequest {
  template_id: string;
  is_validated: boolean;
  note?: string;
}

export interface RecordValidationResponseDTO {
  status: string;
  record_id: string;
  template_id: string;
  is_validated: boolean;
  validated_count: number;
  rejected_count: number;
  timestamp: string;
}

export async function fetchBusinessTemplates(
  category?: string,
  query?: string,
): Promise<ListTemplatesResponseDTO> {
  const params = new URLSearchParams();
  if (category) params.set('category', category);
  if (query) params.set('query', query);
  const qStr = params.toString() ? `?${params.toString()}` : '';
  return apiClient.get<ListTemplatesResponseDTO>(`/memory/business-templates/list${qStr}`);
}

export async function fetchBusinessTemplateById(
  templateId: string,
): Promise<BusinessExperienceTemplateDTO> {
  return apiClient.get<BusinessExperienceTemplateDTO>(
    `/memory/business-templates/${encodeURIComponent(templateId)}`,
  );
}

export async function evaluateEscalationGate(
  payload: EscalationEvaluationRequest,
): Promise<EscalationEvaluationResponseDTO> {
  return apiClient.post<EscalationEvaluationResponseDTO>(
    '/memory/business-templates/evaluate-escalation',
    payload,
  );
}

export async function recordTemplateValidation(
  payload: RecordValidationRequest,
): Promise<RecordValidationResponseDTO> {
  return apiClient.post<RecordValidationResponseDTO>(
    '/memory/business-templates/validate',
    payload,
  );
}
