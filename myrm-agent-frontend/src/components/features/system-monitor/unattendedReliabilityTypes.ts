/**
 * [INPUT]: Unattended reliability triad metrics, run veracity states, and benchmark records.
 * [OUTPUT]: Strong TypeScript definitions for UnattendedReliabilityTriadHUD component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/unattendedReliabilityTypes.ts
 */

export type ResumeStatusType = 'RESUMED_SUCCESS' | 'RESUMED_FAILED' | 'NOT_APPLICABLE';

export type SideEffectStatusType = 'ZERO_DUPLICATE' | 'DUPLICATE_DETECTED' | 'NO_SIDE_EFFECTS';

export type FinalReportingStatusType = 'GENUINE_SUCCESS' | 'HONEST_BLOCKER' | 'HALLUCINATED_SUCCESS';

export interface RunReliabilityRecordItem {
  run_id: string;
  task_name: string;
  resume_status: ResumeStatusType;
  side_effect_status: SideEffectStatusType;
  reporting_status: FinalReportingStatusType;
  detail: string;
  timestamp_ms: number;
}

export interface ReliabilityTriadScoreData {
  total_evaluated_runs: number;
  resume_rate_pct: number;
  zero_duplicate_side_effect_rate_pct: number;
  honest_blocker_rate_pct: number;
  composite_triad_score: number;
  hallucinated_success_count: number;
  duplicate_side_effect_count: number;
  failed_resume_count: number;
  recent_records: RunReliabilityRecordItem[];
}

export interface UnattendedReliabilityTriadHUDProps {
  scoreData: ReliabilityTriadScoreData;
  onRefresh?: () => void;
  onRunBenchmark?: () => Promise<void> | void;
  onReset?: () => Promise<void> | void;
  isRefreshing?: boolean;
  isRunningBenchmark?: boolean;
}
