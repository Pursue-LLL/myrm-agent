/**
 * Experience Compounding and Knowledge Condensation API client service.
 * Enables frequency-driven weight reinforcement, semantic Golden Rule synthesis,
 * rollback decondensation, and obsolete context annealing telemetry.
 */

import { apiClient } from '@/services/api';

export interface AddExperienceItemRequest {
  content: string;
  topic: string;
  base_weight?: number;
  is_temporary?: boolean;
  is_pinned?: boolean;
  tags?: string[];
  item_id?: string;
}

export interface ReinforceExperienceRequest {
  item_id: string;
  adopted?: boolean;
}

export interface PenalizeExperienceItemRequest {
  item_id: string;
  severity?: number;
}

export interface PenalizeExperienceItemResponse {
  item_id: string;
  new_weight: number;
  half_life_days: number;
  status: string;
}

export interface DecondenseRuleRequest {
  rule_id: string;
}

export interface CompoundedExperienceItemDTO {
  item_id: string;
  content: string;
  topic: string;
  base_weight: number;
  compounded_weight: number;
  peak_weight?: number;
  hit_count: number;
  adoption_count: number;
  state: 'active' | 'condensed_archived' | 'cold_tiered' | 'deprecated' | string;
  half_life_days: number;
  is_pinned: boolean;
  is_temporary: boolean;
  tags: string[];
}

export interface GoldenRuleDTO {
  rule_id: string;
  topic: string;
  rule_statement: string;
  rationale: string;
  confidence_score: number;
  source_fragment_ids: string[];
}

export interface CondensationResponseDTO {
  report_id: string;
  rules_generated: GoldenRuleDTO[];
  clusters_found: number;
  fragments_archived: number;
  compression_ratio: number;
  details: string[];
}

export interface AnnealingResponseDTO {
  report_id: string;
  inspected_count: number;
  active_lease_exempt_count: number;
  cold_tiered_count: number;
  decayed_items: string[];
}

export interface ExperienceCompoundingStatsResponse {
  total_items: number;
  active_items: number;
  condensed_items: number;
  cold_tiered_items: number;
  golden_rules_count: number;
  average_compounded_weight: number;
}

export const experienceCompoundingService = {
  /**
   * Register a new experience observation or habit fragment.
   */
  async addItem(request: AddExperienceItemRequest): Promise<CompoundedExperienceItemDTO> {
    return apiClient.post<CompoundedExperienceItemDTO>(
      '/api/memory/compounding/item',
      request
    );
  },

  /**
   * Record positive verification and apply bounded logarithmic compounding weight growth.
   */
  async reinforce(
    request: ReinforceExperienceRequest
  ): Promise<{ status: string; item_id: string; new_weight: number }> {
    return apiClient.post<{ status: string; item_id: string; new_weight: number }>(
      '/api/memory/compounding/reinforce',
      request
    );
  },

  /**
   * Record user contradiction or rejection to penalize weight and prevent upward blindness.
   */
  async penalize(
    request: PenalizeExperienceItemRequest
  ): Promise<PenalizeExperienceItemResponse> {
    return apiClient.post<PenalizeExperienceItemResponse>(
      '/api/memory/compounding/penalize',
      request
    );
  },

  /**
   * Cluster overlapping fragments and synthesize higher-order Golden Rules.
   */
  async condense(): Promise<CondensationResponseDTO> {
    return apiClient.post<CondensationResponseDTO>(
      '/api/memory/compounding/condense'
    );
  },

  /**
   * Roll back a synthesized Golden Rule and reactivate its archived fragments.
   */
  async decondense(request: DecondenseRuleRequest): Promise<CompoundedExperienceItemDTO[]> {
    return apiClient.post<CompoundedExperienceItemDTO[]>(
      '/api/memory/compounding/decondense',
      request
    );
  },

  /**
   * Run obsolete context annealing decay and cold tiering.
   */
  async anneal(): Promise<AnnealingResponseDTO> {
    return apiClient.post<AnnealingResponseDTO>(
      '/api/memory/compounding/anneal'
    );
  },

  /**
   * List all synthesized Golden Rules.
   */
  async listRules(): Promise<GoldenRuleDTO[]> {
    return apiClient.get<GoldenRuleDTO[]>(
      '/api/memory/compounding/rules'
    );
  },

  /**
   * List active un-condensed experience fragments.
   */
  async listActive(): Promise<CompoundedExperienceItemDTO[]> {
    return apiClient.get<CompoundedExperienceItemDTO[]>(
      '/api/memory/compounding/active'
    );
  },

  /**
   * Retrieve operational metrics across compounding, condensation, and cold storage.
   */
  async getStats(): Promise<ExperienceCompoundingStatsResponse> {
    return apiClient.get<ExperienceCompoundingStatsResponse>(
      '/api/memory/compounding/stats'
    );
  },
};
