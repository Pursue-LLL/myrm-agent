/**
 * [INPUT]: Custom Agent telemetry snapshot (intent clusters, skill health funnel, HITL friction, token ROI).
 * [OUTPUT]: Strong TypeScript definitions for CustomAgentInsightsCockpit component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/customAgentInsightsTypes.ts
 */

export interface AgentIntentClusterItem {
  intent_category: string;
  sample_utterance: string;
  request_count: number;
  share_pct: number;
}

export interface AgentSkillHealthMetricItem {
  skill_name: string;
  total_calls: number;
  success_rate_pct: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  top_error_reasons: string[];
}

export interface AgentHitlBottleneckMetricData {
  total_tasks: number;
  hitl_intercepted_tasks: number;
  hitl_interception_rate_pct: number;
  avg_approval_wait_seconds: number;
  token_roi_ratio: number;
}

export interface CustomAgentInsightsData {
  agent_id: string;
  time_window_days: number;
  total_interactions: number;
  total_tokens_consumed: number;
  intent_clusters: AgentIntentClusterItem[];
  skill_funnel: AgentSkillHealthMetricItem[];
  hitl_metrics: AgentHitlBottleneckMetricData;
  generated_at_ms: number;
}

export interface CustomAgentInsightsCockpitProps {
  data: CustomAgentInsightsData;
  onRefresh?: () => void;
  onReset?: () => Promise<void> | void;
  onSelectAgent?: (agentId: string) => void;
  isRefreshing?: boolean;
}
