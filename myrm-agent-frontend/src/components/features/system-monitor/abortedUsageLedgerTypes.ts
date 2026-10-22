/**
 * [INPUT]: Canonical usage ledger records, aborted auxiliary statuses, and availability metadata.
 * [OUTPUT]: Strong TypeScript definitions for AbortedAuxiliaryUsageHUD component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/abortedUsageLedgerTypes.ts
 */

export type UsageAvailabilityKindType = 'exact' | 'usage-unknown' | 'estimated';
export type LedgerCallStatusType = 'completed' | 'aborted' | 'failed' | 'cancelled';
export type AuxiliaryCallKindType =
  | 'primary'
  | 'auxiliary_summary'
  | 'auxiliary_audit'
  | 'auxiliary_router'
  | 'auxiliary_compaction'
  | 'auxiliary_other';

export interface CanonicalUsageLedgerRowItem {
  call_id: string;
  session_id: string;
  task_id: string;
  call_kind: AuxiliaryCallKindType;
  call_status: LedgerCallStatusType;
  usage_availability: UsageAvailabilityKindType;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
  provider_raw_status: string;
  timestamp_ms: number;
}

export interface AbortedUsageUnknownStatsItem {
  total_calls: number;
  known_usage_calls: number;
  unknown_usage_calls: number;
  aborted_calls_count: number;
  total_known_prompt_tokens: number;
  total_known_completion_tokens: number;
  total_known_tokens: number;
  total_known_cost_usd: number;
  unknown_risk_flag: boolean;
  timestamp_ms: number;
}

export interface AbortedAuxiliaryUsageHUDProps {
  stats: AbortedUsageUnknownStatsItem;
  records: CanonicalUsageLedgerRowItem[];
  onRefresh?: () => void;
  onReset?: () => void;
  className?: string;
}
