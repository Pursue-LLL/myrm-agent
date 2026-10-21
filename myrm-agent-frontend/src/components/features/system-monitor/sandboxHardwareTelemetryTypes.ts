/**
 * [INPUT]: Sandbox hardware metrics, three-tier circuit breaker status, and incident history.
 * [OUTPUT]: Strong TypeScript definitions for SandboxHardwareTelemetryDashboard component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/sandboxHardwareTelemetryTypes.ts
 */

export type CircuitBreakerLevelType = 'normal' | 'warning' | 'suspended' | 'tripped';

export interface HardwareMetricSampleItem {
  cpu_percent: number;
  memory_used_bytes: number;
  memory_total_bytes: number;
  memory_percent: number;
  disk_used_bytes: number;
  disk_total_bytes: number;
  disk_percent: number;
  network_bytes_sent: number;
  network_bytes_recv: number;
  timestamp_ms: number;
}

export interface CircuitBreakerConfigItem {
  warning_cpu_threshold: number;
  suspend_cpu_threshold: number;
  trip_cpu_threshold: number;
  warning_mem_threshold: number;
  suspend_mem_threshold: number;
  trip_mem_threshold: number;
  max_consecutive_violations: number;
  max_task_duration_seconds: number;
}

export interface CircuitBreakerEvaluationItem {
  level: CircuitBreakerLevelType;
  triggered_metric: string;
  current_value: number;
  threshold_value: number;
  action_description: string;
  sample: HardwareMetricSampleItem;
  evaluated_at_ms: number;
}

export interface HardwareTelemetrySnapshotData {
  latest_sample: HardwareMetricSampleItem | null;
  current_level: CircuitBreakerLevelType;
  config: CircuitBreakerConfigItem;
  consecutive_violations: number;
  incident_history: CircuitBreakerEvaluationItem[];
  generated_at_ms: number;
}

export interface SandboxHardwareTelemetryDashboardProps {
  snapshot: HardwareTelemetrySnapshotData;
  onRefresh?: () => void;
  onResetBreaker?: () => Promise<void> | void;
  onUpdateThresholds?: (thresholds: Partial<CircuitBreakerConfigItem>) => Promise<void> | void;
  isRefreshing?: boolean;
}
