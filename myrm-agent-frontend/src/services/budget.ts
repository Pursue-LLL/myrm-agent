/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: HTTP client wrapper)
 *
 * [OUTPUT]
 * Budget policy CRUD and status APIs.
 *
 * [POS]
 * Frontend budget service. Bridges budget API endpoints with multi-dimensional support.
 */

import { apiRequest } from '@/lib/api';

export interface BudgetPolicy {
  enabled: boolean;
  daily_limit_usd: number | null;
  session_limit_usd: number | null;
  per_call_limit_usd: number | null;
  warning_threshold: number;
  finalization_reserve_pct: number;
  action_on_exceeded: 'warn' | 'block' | 'finalize';
}

export interface BudgetStatus {
  enabled: boolean;
  daily_limit_usd: number;
  session_limit_usd: number;
  today_cost_usd: number;
  session_cost_usd: number;
  remaining_usd: number;
  usage_pct: number;
  status: 'ok' | 'warning' | 'finalization' | 'exceeded' | 'disabled';
}

export async function getBudgetPolicy(): Promise<BudgetPolicy> {
  return apiRequest<BudgetPolicy>('/budget/policy', { silent: true });
}

export async function updateBudgetPolicy(policy: BudgetPolicy): Promise<BudgetPolicy> {
  return apiRequest<BudgetPolicy>('/budget/policy', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  });
}

export async function getBudgetStatus(): Promise<BudgetStatus> {
  return apiRequest<BudgetStatus>('/budget/status', { silent: true });
}
