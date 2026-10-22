/**
 * [INPUT]: Durable spend ledger summaries, session actual-billed statements, and category breakdowns.
 * [OUTPUT]: Strong TypeScript definitions for DurableBudgetLedgerHUD component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/durableBudgetLedgerTypes.ts
 */

export type SpendCategoryType = 'chat' | 'auxiliary' | 'cache_warm' | 'subagent' | 'system';

export interface DurableSpendLedgerRecordItem {
  record_id: string;
  session_id: string | null;
  task_id: string | null;
  cost_usd: number;
  category: SpendCategoryType;
  date_utc: string;
  message_id: string | null;
  is_active_branch: boolean;
  timestamp_ms: number;
}

export interface DurableBudgetRecoverySummaryItem {
  date_utc: string;
  total_durable_cost_usd: number;
  total_surviving_message_cost_usd: number;
  discarded_branch_cost_usd: number;
  records_count: number;
  category_breakdown: Record<string, number>;
  budget_underestimation_gap_usd: number;
}

export interface SessionActualBilledStatementItem {
  session_id: string;
  visible_branch_cost_usd: number;
  actual_billed_cost_usd: number;
  discarded_diff_cost_usd: number;
  records: DurableSpendLedgerRecordItem[];
}

export interface DurableBudgetLedgerHUDProps {
  summary: DurableBudgetRecoverySummaryItem;
  statement?: SessionActualBilledStatementItem;
  onRefresh?: () => void;
  onReset?: () => void;
  className?: string;
}
