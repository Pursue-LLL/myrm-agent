/**
 * [INPUT]: Enterprise credit allocation data, risk severities, and unified audit trail items.
 * [OUTPUT]: Strong TypeScript definitions for EnterpriseCreditAndRiskOpsCockpit component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/enterpriseCreditCockpitTypes.ts
 */

export type RiskLevelType = 'NONE' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type RiskBehaviorType =
  | 'NONE'
  | 'PII_LEAK_PREVENTED'
  | 'SENSITIVE_DATA_EXPORT'
  | 'PROMPT_INJECTION_ATTEMPT'
  | 'RATE_SPIKE'
  | 'UNAUTHORIZED_DATA_ACCESS';

export type PolicyVerdictType = 'ALLOW' | 'AUDIT' | 'BLOCKED';

export interface CreditRiskAuditRecordItem {
  record_id: string;
  actor_id: string;
  product_surface: string;
  interaction_summary: string;
  data_object_scope: string;
  credit_consumed: number;
  risk_level: RiskLevelType;
  risk_behavior: RiskBehaviorType;
  policy_verdict: PolicyVerdictType;
  timestamp_ms: number;
}

export interface CreditPoolAllocationItem {
  surface_name: string;
  credit_spent: number;
  request_count: number;
}

export interface EnterpriseCockpitData {
  total_credit_quota: number;
  total_credit_spent: number;
  available_credit: number;
  utilization_pct: number;
  is_quota_breached: boolean;
  warning_threshold_pct: number;
  total_audit_records: number;
  risk_event_count: number;
  blocked_count: number;
  allocations_by_surface: CreditPoolAllocationItem[];
  recent_audit_records: CreditRiskAuditRecordItem[];
}

export interface EnterpriseCreditAndRiskOpsCockpitProps {
  cockpitData: EnterpriseCockpitData;
  onRefresh?: () => void;
  onConfigureQuota?: (newQuota: number, thresholdPct: number) => Promise<void> | void;
  onReset?: () => Promise<void> | void;
  isRefreshing?: boolean;
}
