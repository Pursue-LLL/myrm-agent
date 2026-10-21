/**
 * Model Overrides & BYOK Pricing Types.
 *
 * Strict zero-any TypeScript interfaces.
 */

export type CurrencyType = 'USD' | 'CNY';

export interface ModelOverrideItem {
  model_id: string;
  custom_context_window: number | null;
  custom_max_output_tokens: number | null;
  input_cost_per_mtoken: number | null;
  output_cost_per_mtoken: number | null;
  currency: CurrencyType;
  enabled: boolean;
  remarks: string | null;
}

export interface ModelOverrideUpsertPayload {
  custom_context_window?: number | null;
  custom_max_output_tokens?: number | null;
  input_cost_per_mtoken?: number | null;
  output_cost_per_mtoken?: number | null;
  currency?: CurrencyType;
  enabled?: boolean;
  remarks?: string | null;
}

export interface PreloadedModelSku {
  model_id: string;
  display_name: string;
  provider: string;
  default_context_window: number;
  default_max_output_tokens: number;
  suggested_input_cost_per_mtoken: number;
  suggested_output_cost_per_mtoken: number;
  currency: CurrencyType;
  recommended_use_case: string;
}

export interface CostEstimationRequest {
  model_id: string;
  input_tokens: number;
  output_tokens: number;
}

export interface CostEstimationResponse {
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  input_cost: number;
  output_cost: number;
  total_cost: number;
  currency: CurrencyType;
  is_overridden: boolean;
}
