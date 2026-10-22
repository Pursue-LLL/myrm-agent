/**
 * [INPUT]
 * - 纯 TypeScript 类型定义，用于多智能体整轮交付全生命周期成本核算、未知用量审计与硬预算熔断
 *
 * [OUTPUT]
 * - TrialRecordItem, CumulativeDeliveryLedgerData, AdjustDeliveryBudgetPayload
 *
 * [POS]
 * src/components/features/system-monitor/deliveryBudgetTypes.ts — 整轮交付累计预算与未知用量审计契约
 */

export type DeliveryBudgetGateStatus =
  | 'NORMAL'
  | 'WARNING_70'
  | 'EXCEEDED_PAUSED_100';

export type UnknownUsageReason =
  | 'METERED'
  | 'UNMETERED_TIMEOUT'
  | 'UNMETERED_PROVIDER_EMPTY'
  | 'UNMETERED_CONNECTION_RESET';

export interface TrialRecordItem {
  trial_id: string;
  agent_id: string;
  agent_role: string;
  attempt_index: number;
  step_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  is_unmetered: boolean;
  unmetered_status: UnknownUsageReason | string;
  imputed_prompt_tokens: number;
  imputed_completion_tokens: number;
  imputed_cost_usd: number;
  effective_tokens: number;
  effective_cost_usd: number;
  status: string;
  created_at: string;
}

export interface CumulativeDeliveryLedgerData {
  delivery_id: string;
  title: string;
  budget_tokens_limit?: number | null;
  budget_cost_limit_usd?: number | null;
  total_metered_tokens: number;
  total_imputed_tokens: number;
  total_effective_tokens: number;
  total_metered_cost_usd: number;
  total_imputed_cost_usd: number;
  total_effective_cost_usd: number;
  unmetered_trials_count: number;
  total_trials_count: number;
  gate_verdict: DeliveryBudgetGateStatus | string;
  is_paused: boolean;
  pause_reason?: string | null;
  trials: TrialRecordItem[];
  created_at: string;
  updated_at: string;
}

export interface AdjustDeliveryBudgetPayload {
  additional_tokens?: number;
  additional_cost_usd?: number;
  set_budget_tokens_limit?: number;
  set_budget_cost_limit_usd?: number;
  force_unpause?: boolean;
}
