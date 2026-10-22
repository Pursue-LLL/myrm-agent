/**
 * [INPUT]: Memory backend labels, recall phase telemetry, P50/P95 latencies, and opt-in settings.
 * [OUTPUT]: Strong TypeScript definitions for MemoryBackendMetricsDashboard component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/memoryBackendMetricsTypes.ts
 */

export type MemoryBackendKindType = 'sqlite_fts5' | 'qdrant' | 'in_memory' | 'external';
export type MemoryOperationType = 'retain' | 'recall' | 'consolidate';
export type RecallPhaseType = 'collect' | 'fuse' | 'rerank' | 'none';

export interface MemoryBackendPerformanceStatsItem {
  backend: MemoryBackendKindType;
  operation: MemoryOperationType;
  phase: RecallPhaseType;
  total_operations: number;
  success_count: number;
  success_rate: number;
  degraded_count: number;
  avg_duration_ms: number;
  p50_duration_ms: number;
  p95_duration_ms: number;
}

export interface MemoryBackendMetricsReportItem {
  opt_in_enabled: boolean;
  total_samples: number;
  backend_stats: MemoryBackendPerformanceStatsItem[];
  timestamp_ms: number;
}

export interface MemoryBackendMetricsDashboardProps {
  report: MemoryBackendMetricsReportItem;
  onToggleOptIn?: (enabled: boolean) => void;
  onReset?: () => void;
  className?: string;
}
