/**
 * [INPUT]
 * - 纯 TypeScript 类型契约
 *
 * [OUTPUT]
 * - TraceSpanNode, CausalTraceData: 因果 Trace 树数据契约
 * - TierLevel, HealthStatus, ProbeResultItem, MultiTierHealthReportData: 分层健康数据契约
 * - CronDoctor: 定时任务舰队巡检与快速修复
 *
 * [POS]
 * src/components/features/system-monitor/types.ts — 系统监控、因果链路与分层健康类型。
 */

export * from './cronDoctorTypes';

export type SpanKind =
  | 'input'
  | 'context_stage'
  | 'llm_call'
  | 'approval_gate'
  | 'tool_call'
  | 'output_delivery'
  | 'internal';

export type SpanStatus = 'unset' | 'ok' | 'error' | 'denied' | 'timeout';

export interface TraceSpanNode {
  name: string;
  kind: SpanKind;
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  start_time: number;
  end_time?: number | null;
  duration_ms: number;
  status: SpanStatus;
  status_message?: string;
  attributes: Record<string, string | number | boolean>;
  events: Array<{ name: string; timestamp: number }>;
  children: TraceSpanNode[];
}

export interface CausalTraceData {
  trace_id: string;
  created_at: number;
  root: TraceSpanNode;
}

export type TierLevel = 'component' | 'ingress';
export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy';

export interface ProbeResultItem {
  name: string;
  tier: TierLevel;
  status: HealthStatus;
  latency_ms: number;
  message: string;
  is_core: boolean;
  last_checked_at: number;
}

export interface MultiTierHealthReportData {
  overall_status: HealthStatus;
  probes: ProbeResultItem[];
  summary: string;
  checked_at: number;
}

export type FailureSymptom =
  | 'looping'
  | 'context_exhaustion'
  | 'tool_execution_failed'
  | 'human_rejection'
  | 'unknown';

export type BreakpointStage =
  | 'input_intake'
  | 'context_retrieval'
  | 'llm_reasoning'
  | 'approval_gate'
  | 'tool_execution'
  | 'output_delivery';

export type NegativeOutcome =
  | 'none'
  | 'denied'
  | 'parameter_mismatch'
  | 'zero_retrieval'
  | 'budget_exhaustion';

export interface TriageReport {
  triage_id: string;
  trace_id: string;
  symptom: FailureSymptom;
  root_stage: BreakpointStage;
  negative_outcome: NegativeOutcome;
  is_system_failure: boolean;
  summary: string;
  detailed_reasons: string[];
  remediation_action: string;
  can_redispatch: boolean;
  created_at: number;
}

export interface RedispatchRequest {
  triage_id: string;
  trace_id: string;
  resume_stage?: BreakpointStage | null;
  overrides?: Record<string, string | number | boolean>;
}

export interface RedispatchResponse {
  success: boolean;
  new_trace_id: string;
  resumed_stage: BreakpointStage;
  message: string;
}

export interface ResourceEstimateRequest {
  task_id: string;
  execution_seconds?: number;
  cpu_cores?: number;
  memory_gb?: number;
  volume_read_mb?: number;
  volume_write_mb?: number;
  model_name?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  cached_prompt_tokens?: number;
  max_execution_seconds?: number | null;
  max_total_tokens?: number | null;
  max_total_credits?: number | null;
}

export type TaskActionType =
  | 'web_research'
  | 'doc_extraction'
  | 'code_execution'
  | 'email_drafting'
  | 'general_cognition';

export interface LaborEquivalencyItem {
  action_type: TaskActionType;
  label: string;
  count: number;
  hours_per_unit: number;
  total_hours_saved: number;
}

export interface MonthlyProductivitySummary {
  month: string;
  total_tasks_automated: number;
  total_hours_saved: number;
  total_saved_value_usd: number;
  total_compute_cost_usd: number;
  overall_roi_ratio: number;
  top_saving_categories: LaborEquivalencyItem[];
}

export interface DiagnosticLogEvent {
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL';
  subsystem: string;
  message: string;
  metadata?: Record<string, string>;
}

export interface SandboxVitals {
  cpu_pct: number;
  mem_pct: number;
  disk_free_bytes: number;
  network_state: 'healthy' | 'degraded' | 'disconnected';
  uptime_secs: number;
  is_volume_healthy?: boolean;
}

export interface ClientContext {
  client_version: string;
  platform: string;
  browser_or_os: string;
  active_route: string;
  session_id: string;
}

export interface DiagnosticBundle {
  bundle_id: string;
  session_id: string;
  sandbox_id: string;
  vitals: SandboxVitals;
  logs: DiagnosticLogEvent[];
  client_context: ClientContext;
  scrubbed_pii_count: number;
  checksum: string;
  created_at: string;
  user_description?: string;
}

export interface TicketSubmitResponse {
  ticket_id: string;
  bundle_id: string;
  status: 'DISPATCHED' | 'INVESTIGATING' | 'RESOLVED' | 'CLOSED';
  sla_target_minutes: number;
  assigned_tier: string;
  auto_diagnosis: string;
  suggested_actions: string[];
  created_at: string;
}

export interface TicketDetail extends TicketSubmitResponse {
  session_id: string;
  sandbox_id: string;
  status_history: string[];
  updated_at: string;
}

export interface SelfHealRebootResult {
  sandbox_id: string;
  status: 'REBOOT_SUCCESS' | 'REBOOT_FAILED';
  recovered_in_seconds: number;
  volume_intact: boolean;
  message: string;
  rebooted_at: string;
}

export type InterventionType =
  | 'APPROVAL_GATE'
  | 'STEER_CORRECTION'
  | 'REJECT_REWORK'
  | 'PARAMETER_OVERRIDE';

export interface TaskFrictionRecord {
  task_id: string;
  template_type: string;
  execution_sequence: number;
  total_substeps: number;
  intervention_count: number;
  rework_count: number;
  human_attention_minutes: number;
  friction_rate: number;
  timestamp: number;
}
