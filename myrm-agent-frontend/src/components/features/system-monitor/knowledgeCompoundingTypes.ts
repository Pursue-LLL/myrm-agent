/**
 * [INPUT]: Raw metric signals from memory, loop guard, friction ledger, and eval protocols.
 * [OUTPUT]: Strong TypeScript definitions for 5-metric closure, compounding health snapshot, and scoreboard.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/knowledgeCompoundingTypes.ts
 */

export type CompoundingMetricName =
  | 'repeated_error_rate'
  | 'knowledge_hit_rate'
  | 'human_corrections_count'
  | 'first_pass_success_rate'
  | 'stale_knowledge_ratio';

export type MetricHealthStatus = 'HEALTHY' | 'WARNING' | 'CRITICAL';

export type CompoundingTier =
  | 'HIGHLY_COMPOUNDING'
  | 'STEADY_GROWTH'
  | 'EARLY_PHASE'
  | 'REGRESSING';

export interface CompoundingMetricPoint {
  name: string;
  value: number;
  unit: string;
  status: MetricHealthStatus;
  benchmark_threshold: number;
  description: string;
  data_source_origin: string;
}

export interface KnowledgeCompoundingHealthSnapshot {
  overall_score: number;
  compounding_tier: CompoundingTier;
  metrics: Record<string, CompoundingMetricPoint>;
  regression_alerts: string[];
  evaluated_at: string;
  window_days: number;
}

export interface EvaluateCompoundingPayload {
  repeated_error_rate_pct: number;
  knowledge_hit_rate_pct: number;
  human_corrections_count: number;
  first_pass_success_rate_pct: number;
  stale_knowledge_ratio_pct: number;
  window_days: number;
}
