/**
 * [INPUT]: Runtime code freshness evaluation models, process metadata, and module drift entries.
 * [OUTPUT]: Strong TypeScript definitions for RuntimeCodeFreshnessHUD component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/codeFreshnessTypes.ts
 */

export type FreshnessStateType = 'fresh' | 'stale' | 'indeterminate';

export type IndeterminateReasonType =
  | 'none'
  | 'file_not_found'
  | 'permission_denied'
  | 'virtual_or_bundled_executable'
  | 'clock_drift_anomaly'
  | 'dynamic_eval_or_in_memory_only';

export interface ModuleFreshnessEntryItem {
  module_name: string;
  file_path: string;
  process_start_time_ms: number;
  disk_mtime_ms?: number | null;
  time_drift_seconds?: number | null;
  state: FreshnessStateType;
  reason: IndeterminateReasonType;
  remediation_hint: string;
}

export interface RuntimeFreshnessReportItem {
  pid: number;
  overall_state: FreshnessStateType;
  total_inspected_modules: number;
  stale_modules_count: number;
  fresh_modules_count: number;
  indeterminate_count: number;
  inspected_at_ms: number;
  details: ModuleFreshnessEntryItem[];
}

export interface RuntimeCodeFreshnessHUDProps {
  report: RuntimeFreshnessReportItem;
  onRecheck?: () => Promise<void> | void;
  onInspectModule?: (moduleName: string, filePath: string) => Promise<void> | void;
  isChecking?: boolean;
}
