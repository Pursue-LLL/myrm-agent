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

// --- Per-channel budget ---

export interface ChannelBudgetPolicy {
  channel_key: string;
  daily_limit_usd: number;
  warning_threshold: number;
  enabled: boolean;
  label: string;
}

export interface ChannelBudgetStatus {
  channel_key: string;
  label: string;
  enabled: boolean;
  daily_limit_usd: number;
  today_cost_usd: number;
  remaining_usd: number;
  usage_pct: number;
  status: 'ok' | 'warning' | 'exceeded' | 'disabled';
}

export interface ChannelBudgetsResponse {
  policies: ChannelBudgetPolicy[];
  statuses: ChannelBudgetStatus[];
}

export interface ChannelAuditEntry {
  sender_id: string;
  message_count: number;
  total_cost_usd: number;
}

export interface ChannelAuditResponse {
  channel_key: string;
  period_days: number;
  entries: ChannelAuditEntry[];
  total_cost_usd: number;
}

export async function getChannelBudgets(): Promise<ChannelBudgetsResponse> {
  return apiRequest<ChannelBudgetsResponse>('/budget/channels', { silent: true });
}

export async function updateChannelBudget(
  channelKey: string,
  policy: Omit<ChannelBudgetPolicy, 'channel_key'>,
): Promise<ChannelBudgetPolicy> {
  return apiRequest<ChannelBudgetPolicy>(`/budget/channels/${encodeURIComponent(channelKey)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(policy),
  });
}

export async function deleteChannelBudget(channelKey: string): Promise<void> {
  await apiRequest(`/budget/channels/${encodeURIComponent(channelKey)}`, {
    method: 'DELETE',
  });
}

export async function getChannelAudit(channelKey: string, days = 7): Promise<ChannelAuditResponse> {
  return apiRequest<ChannelAuditResponse>(
    `/budget/channels/${encodeURIComponent(channelKey)}/audit?days=${days}`,
    { silent: true },
  );
}
