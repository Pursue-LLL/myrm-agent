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
  return apiRequest<ChannelAuditResponse>(`/budget/channels/${encodeURIComponent(channelKey)}/audit?days=${days}`, {
    silent: true,
  });
}

// --- Four-Tier Progressive Spend Control ---

export type SpendInterventionTier =
  'tier_1_visibility' | 'tier_2_soft_gate' | 'tier_3_auto_downgrade' | 'tier_4_critical_pause';

export type InterventionAction =
  'allow' | 'recommend_downgrade' | 'require_confirmation' | 'switch_model' | 'pause_for_approval';

export interface SpendInterventionDecision {
  tier: SpendInterventionTier;
  action: InterventionAction;
  currentSpendUsd: number;
  quotaLimitUsd: number;
  spendRatio: number;
  message: string;
  downgradeModelId?: string | null;
  bypassToken?: string | null;
  approvalToken?: string | null;
  isBlocked: boolean;
  decisionId: string;
  createdAt: string;
}

export interface FleetQuotaItem {
  dimension: string;
  identifier: string;
  spendUsd: number;
  allocatedQuotaUsd: number;
  utilizationPct: number;
  tier: SpendInterventionTier;
  activeSessions: number;
  updatedAt: string;
}

export interface FleetQuotaDeckResponse {
  items: FleetQuotaItem[];
}

export async function getSpendInterventionDecision(params: {
  currentSpendUsd: number;
  quotaLimitUsd: number;
  sessionId?: string;
}): Promise<SpendInterventionDecision> {
  const q = new URLSearchParams({
    current_spend_usd: params.currentSpendUsd.toString(),
    quota_limit_usd: params.quotaLimitUsd.toString(),
  });
  if (params.sessionId) {
    q.set('session_id', params.sessionId);
  }
  return apiRequest<SpendInterventionDecision>(`/budget/spend-control/decision?${q.toString()}`, { silent: true });
}

export async function confirmSoftSpendGate(params: {
  sessionId: string;
  bypassToken: string;
}): Promise<{ confirmed: boolean; sessionId: string }> {
  return apiRequest<{ confirmed: boolean; sessionId: string }>('/budget/spend-control/confirm-soft-gate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: params.sessionId, bypass_token: params.bypassToken }),
  });
}

export async function approveTier4SpendPause(params: {
  sessionId: string;
  approvalToken: string;
}): Promise<{ approved: boolean; sessionId: string }> {
  return apiRequest<{ approved: boolean; sessionId: string }>('/budget/spend-control/approve-pause', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: params.sessionId, approval_token: params.approvalToken }),
  });
}

export async function getFleetQuotaDeck(dimension?: string): Promise<FleetQuotaDeckResponse> {
  const q = dimension ? `?dimension=${encodeURIComponent(dimension)}` : '';
  return apiRequest<FleetQuotaDeckResponse>(`/budget/spend-control/fleet-deck${q}`, { silent: true });
}
