/**
 * [INPUT]
 * - 纯 TypeScript 类型定义，用于 AI Agent 流量精准解构、跳出归因与 AEO 诊断
 *
 * [OUTPUT]
 * - AgenticTrafficSummaryData, AgentVisitRecordItem, AeoPageDiagnosticData
 *
 * [POS]
 * src/components/features/system-monitor/agenticTrafficTypes.ts — AI Agent 流量与静默审判契约
 */

export type FunnelStageType =
  | 'DISCOVERED'
  | 'CONTEXT_ABSORBED'
  | 'SANDBOX_PROBED'
  | 'ADOPTED';

export type AbandonmentReasonType =
  | 'TOKEN_OVERFLOW_20K'
  | 'LLMS_TXT_MISSING'
  | 'FIRST_500_TOKENS_VAGUE'
  | 'SPA_CLIENT_BLANK'
  | 'API_SPEC_UNRESOLVABLE'
  | 'NONE';

export interface AgentVisitRecordItem {
  visit_id: string;
  agent_type: string;
  user_agent: string;
  target_path: string;
  duration_ms: number;
  status_code: number;
  is_agent: boolean;
  confidence_score: number;
  funnel_stage: FunnelStageType | string;
  abandonment_reasons: string[];
  timestamp: string;
}

export interface AgentTrafficSummaryData {
  total_visits: number;
  agent_visits_count: number;
  human_visits_count: number;
  agent_traffic_ratio_pct: number;
  top_agents: Record<string, number>;
  funnel_conversion: Record<string, number>;
  abandonment_distribution: Record<string, number>;
  recent_visits: AgentVisitRecordItem[];
  generated_at: string;
}

export interface AeoPageDiagnosticData {
  path: string;
  estimated_tokens: number;
  has_llms_txt_declared: boolean;
  has_code_in_first_500_tokens: boolean;
  is_spa_client_blank: boolean;
  suggested_actions: string[];
  abandonment_reasons: string[];
  aeo_score: number;
}
