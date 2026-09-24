/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: HTTP client wrapper)
 *
 * [OUTPUT]
 * Autonomous Agentic Commerce Budget and Spending Ledger APIs.
 *
 * [POS]
 * Frontend commerce budget client service. Interacts with /api/v1/commerce/spending.
 */

import { apiRequest } from '@/lib/api';

export interface CommerceBudgetConfig {
  daily_cap_cents: number;
  per_action_cap_cents: number;
  allowed_merchants: string[];
  currency?: string;
  is_frozen?: boolean;
  lease_ttl_seconds?: number;
}

export interface CommerceBudgetStatus {
  daily_cap_cents: number;
  per_action_cap_cents: number;
  daily_spent_cents: number;
  active_reserved_cents: number;
  remaining_cents: number;
  currency: string;
  is_frozen: boolean;
  allowed_merchants: string[];
  total_leases_tracked: number;
}

export interface SpendingLedgerEntry {
  entry_id: string;
  lease_id: string;
  session_id: string;
  task_id?: string | null;
  merchant_domain: string;
  amount_cents: number;
  currency: string;
  status: 'reserved' | 'committed' | 'refunded' | 'rejected';
  action_digest?: string | null;
  entry_hash?: string | null;
  idempotency_key?: string;
  created_at: string;
  updated_at: string;
}

export async function getCommerceBudgetStatus(): Promise<CommerceBudgetStatus> {
  return apiRequest<CommerceBudgetStatus>('/commerce/spending/budget', { silent: true });
}

export async function updateCommerceBudgetConfig(
  config: CommerceBudgetConfig
): Promise<CommerceBudgetStatus> {
  return apiRequest<CommerceBudgetStatus>('/commerce/spending/budget', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

export async function setEmergencySpendingFreeze(
  freeze: boolean
): Promise<CommerceBudgetStatus> {
  return apiRequest<CommerceBudgetStatus>('/commerce/spending/freeze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ freeze }),
  });
}

export async function getSpendingLedger(params?: {
  session_id?: string;
  limit?: number;
}): Promise<SpendingLedgerEntry[]> {
  const query = new URLSearchParams();
  if (params?.session_id) {
    query.set('session_id', params.session_id);
  }
  if (params?.limit) {
    query.set('limit', String(params.limit));
  }
  const qs = query.toString();
  const endpoint = qs ? `/commerce/spending/ledger?${qs}` : '/commerce/spending/ledger';
  return apiRequest<SpendingLedgerEntry[]>(endpoint, { silent: true });
}
