/**
 * [INPUT]: Active skill span telemetry records, latency percentiles, and ContextVar attributes.
 * [OUTPUT]: Strong TypeScript definitions for ActiveSkillSpanTelemetryCockpit component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/activeSkillTelemetryTypes.ts
 */

export interface SkillSpanRecordItem {
  span_id: string;
  trace_id: string;
  name: string;
  active_skill: string | null;
  duration_ms: number;
  status: string;
  attributes: Record<string, string>;
  timestamp_ms: number;
}

export interface SkillTelemetryAggregationItem {
  skill_name: string;
  total_spans: number;
  error_spans: number;
  error_rate: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
}

export interface ActiveSkillTelemetryReportItem {
  total_spans_recorded: number;
  skills_count: number;
  skill_aggregations: SkillTelemetryAggregationItem[];
  unattributed_spans_count: number;
  timestamp_ms: number;
}

export interface ActiveSkillSpanTelemetryCockpitProps {
  report: ActiveSkillTelemetryReportItem;
  spans?: SkillSpanRecordItem[];
  onRefresh?: () => void;
  onReset?: () => void;
  className?: string;
}
