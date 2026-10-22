/**
 * [INPUT]: Dual-domain metering records, 3D cost breakdowns, and reconciliation statements.
 * [OUTPUT]: Strong TypeScript definitions for DualDomainMeteringCockpit component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/dualDomainMeteringTypes.ts
 */

export type MeteringDomainType = 'gateway_domain' | 'sandbox_domain';

export interface ThreeDimensionalCostItem {
  model_token_cost_usd: number;
  sandbox_compute_cost_usd: number;
  thirdparty_tool_cost_usd: number;
  total_cost_usd: number;
}

export interface DomainMeteringRecordItem {
  record_id: string;
  session_id: string;
  domain: MeteringDomainType;
  operation_name: string;
  resource_units: number;
  cost_breakdown: ThreeDimensionalCostItem;
  billable: boolean;
  policy_note: string;
  timestamp_ms: number;
}

export interface SessionDualDomainSummaryItem {
  session_id: string;
  gateway_token_cost_usd: number;
  sandbox_compute_cost_usd: number;
  thirdparty_tool_cost_usd: number;
  total_cost_usd: number;
  total_operations: number;
  gateway_ops_count: number;
  sandbox_ops_count: number;
  gateway_cost_ratio: number;
  sandbox_cost_ratio: number;
  generated_at_ms: number;
}

export interface ReconciliationStatementItem {
  statement_id: string;
  session_id: string;
  summary: SessionDualDomainSummaryItem;
  records: DomainMeteringRecordItem[];
  integrity_sha256: string;
  generated_at_ms: number;
}

export interface DualDomainMeteringCockpitProps {
  summary: SessionDualDomainSummaryItem;
  records: DomainMeteringRecordItem[];
  statement?: ReconciliationStatementItem | null;
  onGenerateStatement?: (sessionId: string) => Promise<void> | void;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}
