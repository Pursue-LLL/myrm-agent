/**
 * [INPUT]: Six-dimensional usage ledger telemetry, dual-track reconciliation states, and task attributions.
 * [OUTPUT]: Strong TypeScript definitions for CompositeUsageLedgerHUD component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/compositeUsageLedgerTypes.ts
 */

export type CostReconciliationStatusType =
  | 'ESTIMATED_ONLY'
  | 'RECONCILED'
  | 'DISCREPANCY_ALERT';

export interface CompositeUsageRecordItem {
  session_id: string;
  model: string;
  billing_provider: string;
  billing_base_url: string;
  billing_mode: string;
  task: string;
  api_call_count: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  reasoning_tokens: number;
  estimated_cost_usd: number;
  actual_cost_usd: number;
  cost_status: CostReconciliationStatusType;
  discrepancy_pct: number;
  first_seen_ms: number;
  last_seen_ms: number;
}

export interface LedgerSummaryData {
  total_records: number;
  total_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_tokens: number;
  total_estimated_usd: number;
  total_actual_usd: number;
  reconciled_records_count: number;
  discrepancy_records_count: number;
  task_spend_distribution: Record<string, number>;
  model_spend_distribution: Record<string, number>;
}

export interface CompositeUsageLedgerHUDProps {
  summary: LedgerSummaryData;
  records?: CompositeUsageRecordItem[];
  onRefresh?: () => void;
  onReconcile?: (record: CompositeUsageRecordItem, actualCost: number) => Promise<void> | void;
  onReset?: () => Promise<void> | void;
  isRefreshing?: boolean;
}
