/**
 * Enterprise Admin API Service — Audit & Usage.
 *
 * Calls Control Plane security, usage, and agent-audit endpoints directly
 * (not via the sandbox proxy — these routes live on the Control Plane itself).
 * Requires the Control Plane JWT that the sandbox proxy already validated.
 * Only available in cloud-hosted enterprise edition.
 */

import { resolveCpBaseUrl } from '@/lib/cp-base-url';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

// ── Types ───────────────────────────────────────────────────────────────

export interface AuditEvent {
  event_type: string;
  timestamp: string;
  severity: string;
  user_id: string | null;
  sandbox_id: string | null;
  resource: string | null;
  action: string;
  result: string;
  metadata: Record<string, unknown> | null;
  ip_address: string | null;
  trace_id: string | null;
  request_id: string | null;
  traffic_class: string | null;
}

export interface AuditLogsResponse {
  events: AuditEvent[];
  total: number;
  filters: Record<string, string | number | null>;
}

export interface AuditTimeSeriesBucket {
  timestamp: string;
  total: number;
  success: number;
  failed: number;
}

export interface AuditStatsResponse {
  time_series: AuditTimeSeriesBucket[];
  top_ips: { ip_address: string; request_count: number }[];
  event_distribution: { event_type: string; count: number }[];
  success_vs_failed: { success: number; failed: number };
  total_events: number;
  time_range_hours: number;
}

export interface MemberUsage {
  user_id: string;
  display_name: string;
  wu_used: number;
}

export interface CategoryUsage {
  category: string;
  wu_used: number;
}

export interface OrgUsageSummary {
  org_id: string;
  org_name: string;
  month: string;
  total_wu: number;
  budget_wu_monthly: number | null;
  usage_ratio: number | null;
  members: MemberUsage[];
  by_category: CategoryUsage[];
}

export interface BudgetSettings {
  org_id: string;
  budget_wu_monthly: number | null;
  alert_threshold: number;
}

// ── Audit API ───────────────────────────────────────────────────────────

const SECURITY_BASE = '/api/security';

function securityUrl(path: string): string {
  return `${resolveCpBaseUrl()}${SECURITY_BASE}${path}`;
}

function jsonHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json', ...getAuthHeaders() };
}

export interface AuditLogFilters {
  user_id?: string;
  sandbox_id?: string;
  event_type?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
}

export async function queryAuditLogs(filters: AuditLogFilters = {}): Promise<AuditLogsResponse> {
  const params = new URLSearchParams();
  if (filters.user_id) {
    params.set('user_id', filters.user_id);
  }
  if (filters.sandbox_id) {
    params.set('sandbox_id', filters.sandbox_id);
  }
  if (filters.event_type) {
    params.set('event_type', filters.event_type);
  }
  if (filters.start_time) {
    params.set('start_time', filters.start_time);
  }
  if (filters.end_time) {
    params.set('end_time', filters.end_time);
  }
  if (filters.limit) {
    params.set('limit', String(filters.limit));
  }

  const qs = params.toString();
  const url = securityUrl(`/audit-logs${qs ? `?${qs}` : ''}`);
  const res = await fetch(url, { headers: getAuthHeaders() });
  if (!res.ok) {
    throw new Error(`Query audit logs failed: ${res.status}`);
  }
  return res.json();
}

export async function getAuditStats(hours: number = 24): Promise<AuditStatsResponse> {
  const res = await fetch(securityUrl(`/audit-logs/stats?hours=${hours}`), {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Get audit stats failed: ${res.status}`);
  }
  return res.json();
}

export async function exportAuditLogs(format: 'csv' | 'json' = 'csv', filters: AuditLogFilters = {}): Promise<Blob> {
  const params = new URLSearchParams({ format });
  if (filters.user_id) {
    params.set('user_id', filters.user_id);
  }
  if (filters.sandbox_id) {
    params.set('sandbox_id', filters.sandbox_id);
  }
  if (filters.event_type) {
    params.set('event_type', filters.event_type);
  }
  if (filters.start_time) {
    params.set('start_time', filters.start_time);
  }
  if (filters.end_time) {
    params.set('end_time', filters.end_time);
  }
  if (filters.limit) {
    params.set('limit', String(filters.limit));
  }

  const res = await fetch(securityUrl(`/audit-logs/export?${params.toString()}`), {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Export audit logs failed: ${res.status}`);
  }
  return res.blob();
}

// ── Usage API ───────────────────────────────────────────────────────────

const ORG_BASE = '/api/enterprise/org';

function orgUrl(orgId: string, path: string): string {
  return `${resolveCpBaseUrl()}${ORG_BASE}/${orgId}${path}`;
}

export async function getOrgUsageSummary(orgId: string, month?: string): Promise<OrgUsageSummary> {
  const params = month ? `?month=${month}` : '';
  const res = await fetch(orgUrl(orgId, `/usage-summary${params}`), { headers: getAuthHeaders() });
  if (!res.ok) {
    throw new Error(`Get usage summary failed: ${res.status}`);
  }
  return res.json();
}

export async function getOrgBudget(orgId: string): Promise<BudgetSettings> {
  const res = await fetch(orgUrl(orgId, '/budget'), { headers: getAuthHeaders() });
  if (!res.ok) {
    throw new Error(`Get budget failed: ${res.status}`);
  }
  return res.json();
}

export async function setOrgBudget(
  orgId: string,
  budgetWuMonthly: number | null,
  alertThreshold: number = 0.8,
): Promise<BudgetSettings> {
  const res = await fetch(orgUrl(orgId, '/budget'), {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify({ budget_wu_monthly: budgetWuMonthly, alert_threshold: alertThreshold }),
  });
  if (!res.ok) {
    throw new Error(`Set budget failed: ${res.status}`);
  }
  return res.json();
}

// ── Agent Audit API (org-level, from CP fan-out) ────────────────────────

export interface AgentAuditEvent {
  seq: number;
  ts: number;
  type: string;
  sid: string;
  data: Record<string, unknown>;
  /** Sandbox the event originated from — injected by the Control Plane during fan-out aggregation. */
  sandbox_id?: string;
  /** Org member owning the sandbox — injected by the Control Plane during fan-out aggregation. */
  user_id?: string;
  /** Human-readable identity (email/display_name) of the owning member — injected by the Control Plane. */
  user_display?: string;
}

export interface OrgAgentAuditResponse {
  events: AgentAuditEvent[];
  total: number;
  /** Full-window tool-call event count across all sandboxes, computed before truncation. */
  tool_call_total: number;
  /** Full-window security-audit event count across all sandboxes, computed before truncation. */
  security_event_total: number;
  /** Full-window policy-denial decision count (BLOCK/DENY/REDACT/LEAK) across all sandboxes. */
  security_deny_total: number;
  scanned_sandboxes: number;
  failed_sandboxes: string[];
}

export async function queryOrgAgentAudit(
  orgId: string,
  options: { hours?: number; limit?: number } = {},
): Promise<OrgAgentAuditResponse> {
  const params = new URLSearchParams({
    hours: String(options.hours ?? 24),
    limit: String(options.limit ?? 200),
  });
  const res = await fetch(`${resolveCpBaseUrl()}${ORG_BASE}/${orgId}/agent-audit/events?${params.toString()}`, {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Query org agent audit failed: ${res.status}`);
  }
  return res.json();
}
