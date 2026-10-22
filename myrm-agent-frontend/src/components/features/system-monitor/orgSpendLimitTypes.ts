/**
 * [INPUT]: Organization budgets, query spend labels, governor decisions, and ident attribution stats.
 * [OUTPUT]: Strong TypeScript definitions for OrgSharedAgentSpendGovernor and attribution dashboard.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/orgSpendLimitTypes.ts
 */

export type SpendSurface = 'CHANNEL' | 'DIRECT_MESSAGE' | 'REST_API' | 'AUTOMATED_CI';
export type BillingScope = 'ORG_SHARED' | 'PERSONAL_DM';
export type GovernorAction = 'ALLOW' | 'WARN_APPROACHING' | 'CIRCUIT_BREAKER_BLOCKED';

export interface SpendGovernorDecision {
  action: GovernorAction;
  current_spend_usd: number;
  monthly_budget_usd: number;
  utilization_pct: number;
  reason: string;
  is_blocked: boolean;
}

export interface OrgSpendSummary {
  monthly_budget_usd: number;
  current_spend_usd: number;
  remaining_budget_usd: number;
  utilization_pct: number;
  total_records_count: number;
}

export interface IdentAttributionItem {
  requesting_user_id: string;
  total_calls_count: number;
  total_tokens: number;
  total_spend_usd: number;
  surfaces_breakdown: Record<string, number>;
  primary_surface: string;
}

export interface SpendLimitConfig {
  org_id: string;
  monthly_budget_usd: number;
  soft_warn_watermark_pct: number;
  hard_block_limit_usd: number;
  is_circuit_breaker_enabled: boolean;
}
