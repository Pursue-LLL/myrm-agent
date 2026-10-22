/**
 * [INPUT]: Metric cardinality telemetry, cap limit configurations, and overflow stats.
 * [OUTPUT]: Strong TypeScript definitions for MetricCardinalityCapHUD component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/metricCardinalityTypes.ts
 */

export type CardinalityStatusType = 'healthy' | 'approaching_cap' | 'overflowing';

export interface MetricCardinalityStatItem {
  metric_name: string;
  cap_limit: number;
  tracked_cardinality: number;
  overflow_count: number;
  total_samples: number;
  utilization_pct: number;
  status: CardinalityStatusType;
  top_tracked_labels: string[];
  label_hits: Record<string, number>;
}

export interface MetricCardinalityCapHUDProps {
  stats: MetricCardinalityStatItem[];
  onConfigureCap?: (metricName: string, newCap: number) => Promise<void> | void;
  onRefresh?: () => void;
  onReset?: () => Promise<void> | void;
  isRefreshing?: boolean;
}
