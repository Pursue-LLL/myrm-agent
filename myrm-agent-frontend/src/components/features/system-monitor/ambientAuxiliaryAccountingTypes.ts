/**
 * [INPUT]: Telemetry from ambient auxiliary task contexts and breakdown reports.
 * [OUTPUT]: Strong TypeScript definitions for AmbientAuxiliaryAccountingHUD component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/ambientAuxiliaryAccountingTypes.ts
 */

export type AuxiliaryTaskTypeValue =
  | 'main_dialogue'
  | 'vision_prep'
  | 'context_compression'
  | 'title_generation'
  | 'shadow_eval'
  | 'background_reflection'
  | 'custom';

export interface AuxiliaryUsageSnapshotItem {
  session_id: string;
  task_type: AuxiliaryTaskTypeValue | string;
  custom_task_name: string;
  effective_task_name: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  duration_ms: number;
  cost_usd: number;
  timestamp_ms: number;
}

export interface TaskCostSummaryItem {
  task_name: string;
  call_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_duration_ms: number;
  share_pct: number;
}

export interface AmbientAccountingReportData {
  total_invocations: number;
  total_cost_usd: number;
  core_dialogue_cost_usd: number;
  auxiliary_cost_usd: number;
  auxiliary_cost_share_pct: number;
  task_summaries: TaskCostSummaryItem[];
  prompt_cache_purity_preserved: boolean;
  generated_at_ms: number;
}

export interface AmbientAuxiliaryAccountingHUDProps {
  report: AmbientAccountingReportData;
  snapshots?: AuxiliaryUsageSnapshotItem[];
  onRefresh?: () => void;
  onReset?: () => Promise<void> | void;
  isRefreshing?: boolean;
}
