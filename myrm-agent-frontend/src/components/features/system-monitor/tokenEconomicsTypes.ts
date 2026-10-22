/**
 * [INPUT]: None (Pure domain types for Token Economics, 99% Cache ROI, and Cost Drift).
 * [OUTPUT]: Strong TypeScript definitions for Cache savings, drift alerts, and budget guard evaluation.
 * [POS]: myrm-agent-frontend/src/components/features/system-monitor/tokenEconomicsTypes.ts
 */

export interface CacheSavingsMetrics {
  task_id: string;
  model_name: string;
  cache_hit_rate_pct: number;
  baseline_cost_rmb: number;
  actual_cost_rmb: number;
  saved_amount_rmb: number;
  saved_percentage: number;
  burn_rate_rmb_per_minute: number;
}

export type DriftReasonType =
  | 'NORMAL'
  | 'UPSTREAM_PRICE_INCREASE'
  | 'SUBSIDY_REVOKED'
  | 'CACHE_HIT_DEGRADED'
  | 'ROUTING_FALLBACK'
  | 'PROMPT_BLOAT';

export interface CostDriftAlert {
  task_category: string;
  model_name: string;
  current_unit_cost_per_k: number;
  baseline_unit_cost_per_k: number;
  drift_percentage: number;
  is_significant_drift: boolean;
  reason: DriftReasonType;
  explanation: string;
}

export type GuardStatus = 'OK' | 'SOFT_WARNING' | 'CIRCUIT_BREAKER_TRIPPED';

export interface BudgetGuardEvaluation {
  status: GuardStatus;
  current_cost_rmb: number;
  current_burn_rate_rmb_min: number;
  current_tokens: number;
  is_paused: boolean;
  reason: string;
  suggested_action: string;
}
