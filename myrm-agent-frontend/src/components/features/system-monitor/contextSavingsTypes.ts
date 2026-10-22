/**
 * [INPUT]: Tool savings records, session audits, retry metrics, and role perspective selectors.
 * [OUTPUT]: Strong TypeScript definitions for context optimization savings and engineering insight diagnostics.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/contextSavingsTypes.ts
 */

export type EngineeringSignalPattern =
  | 'HIGH_RETRY_CHURN'
  | 'TOOL_OUTPUT_BLOAT'
  | 'LONG_BLOCKING_IO'
  | 'CACHE_STARVATION'
  | 'SUBAGENT_DEADLOCK'
  | 'FLAKY_ENVIRONMENT'
  | 'COST_ANOMALY';

export type RoleInsightView = 'CTO' | 'EM' | 'FINOPS' | 'DEVOPS';

export interface ToolSavingsRecord {
  session_id: string;
  tool_name: string;
  original_tokens: number;
  optimized_tokens: number;
  saved_tokens: number;
  savings_rate_pct: number;
  cost_saved_usd: number;
  cost_saved_cny: number;
  cache_hit: boolean;
  recorded_at: string;
}

export interface ToolSavingsSummary {
  tool_name: string;
  total_calls: number;
  total_original_tokens: number;
  total_optimized_tokens: number;
  total_saved_tokens: number;
  average_savings_rate_pct: number;
  total_cost_saved_usd: number;
  total_cost_saved_cny: number;
  cache_hit_rate_pct: number;
}

export interface SessionSavingsAudit {
  session_id: string;
  total_tool_calls: number;
  total_original_tokens: number;
  total_optimized_tokens: number;
  total_saved_tokens: number;
  overall_savings_rate_pct: number;
  total_cost_saved_usd: number;
  total_cost_saved_cny: number;
  tool_breakdown: ToolSavingsSummary[];
  summary_headline: string;
}

export interface EngineeringSignalItem {
  signal_pattern: EngineeringSignalPattern;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  target_entity: string;
  detected_metric_value: number;
  metric_threshold: number;
  root_cause_explanation: string;
  actionable_remediation: string;
}

export interface RoleEngineeringInsightReport {
  role: RoleInsightView;
  evaluated_sessions_count: number;
  total_saved_tokens_aggregate: number;
  total_cost_saved_usd_aggregate: number;
  top_efficiency_tools: string[];
  identified_engineering_signals: EngineeringSignalItem[];
  primary_bottleneck_summary: string;
}
