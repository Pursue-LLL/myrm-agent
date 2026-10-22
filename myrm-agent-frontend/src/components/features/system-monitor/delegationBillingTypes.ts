/**
 * [INPUT]: Token usage data, delegation source backend, and subscription/api_key auth mode.
 * [OUTPUT]: Strong TypeScript definitions for DelegationBillingTransparencyBadge and audit views.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/delegationBillingTypes.ts
 */

export type DelegationAuthModeType = 'subscription' | 'api_key';

export interface DelegationUsageBadgeData {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  auth_mode?: string;
  billable?: boolean;
  source?: string;
  cost_usd?: number;
  estimated_savings_usd?: number;
}

export interface DelegationBillingTransparencyBadgeProps {
  usage: DelegationUsageBadgeData;
  compact?: boolean;
  onOpenDetails?: () => void;
  className?: string;
}

export interface DelegationSourceMetricItem {
  source: string;
  calls_count: number;
  subscription_tokens: number;
  api_key_tokens: number;
  savings_usd: number;
  cost_usd: number;
}

export interface DelegationBillingSummaryItem {
  total_delegations: number;
  subscription_calls_count: number;
  api_key_calls_count: number;
  total_subscription_tokens: number;
  total_api_key_tokens: number;
  total_estimated_savings_usd: number;
  total_billed_cost_usd: number;
  sources: DelegationSourceMetricItem[];
  timestamp_ms: number;
}
