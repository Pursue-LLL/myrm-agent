/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Four-Layer Memory and Tri-Channel Promotion DTOs and API request functions:
 * - verifyRulesCompliance
 * - rollbackConsolidationBatch
 * - listActiveCapabilityMethods
 *
 * [POS]
 * Frontend API client for Four-Layer Memory Tri-Channel Promotion and Anti-Poisoning Audit.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type PromotionChannelType =
  | 'repeated_across_sessions'
  | 'tool_failure_evidence'
  | 'explicit_user_instruction';

export interface CapabilityMethodSchema {
  method_id: string;
  title: string;
  applies_when: string;
  method_steps: string[];
  validation_criteria: string;
  failure_signals: string[];
  supported_event_ids: string[];
  promotion_channel: PromotionChannelType | string;
}

export interface RulesComplianceRequest {
  response_text: string;
}

export interface RulesComplianceItemSchema {
  rule_id: string;
  statement: string;
  compliant: boolean;
  rationale: string;
}

export interface RulesComplianceResponse {
  items: RulesComplianceItemSchema[];
  all_compliant: boolean;
}

export interface BatchRollbackRequest {
  batch_id: string;
}

export interface BatchRollbackResponse {
  batch_id: string;
  success: boolean;
  reverted_method_ids: string[];
}

export const verifyRulesCompliance = async (
  request: RulesComplianceRequest,
): Promise<RulesComplianceResponse> => {
  return apiRequest<RulesComplianceResponse>('/memory/four-layer-promotion/verify-compliance', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: { 'Content-Type': 'application/json' },
  });
};

export const rollbackConsolidationBatch = async (
  request: BatchRollbackRequest,
): Promise<BatchRollbackResponse> => {
  return apiRequest<BatchRollbackResponse>('/memory/four-layer-promotion/rollback', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: { 'Content-Type': 'application/json' },
  });
};

export const listActiveCapabilityMethods = async (): Promise<CapabilityMethodSchema[]> => {
  return apiRequest<CapabilityMethodSchema[]>('/memory/four-layer-promotion/active-methods');
};
