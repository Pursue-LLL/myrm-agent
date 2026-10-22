/**
 * [INPUT]
 * - 纯 TypeScript 类型契约
 *
 * [OUTPUT]
 * - PortProcessInfo, ProcessLineageNode, PortInspectResponse, ProcessKillResponse
 * - TraceSpanNode, CausalTraceData: 因果 Trace 树数据契约
 * - TierLevel, HealthStatus, ProbeResultItem, MultiTierHealthReportData: 分层健康数据契约
 * - CronDoctor: 定时任务舰队巡检与快速修复
 * - CumulativeDeliveryBudget: 整轮交付累计预算与未知用量审计契约
 * - AgenticTraffic: AI Agent 流量识别、AEO 诊断与静默审判漏斗
 *
 * [POS]
 * src/components/features/system-monitor/types.ts — 系统监控、端口冲突、因果链路、分层健康、交付累计预算与 Agent 流量类型。
 */

export * from './cronDoctorTypes';
export * from './deliveryBudgetTypes';
export * from './agenticTrafficTypes';


export interface PortProcessInfo {
  pid: number;
  name: string;
  cmdline: string[];
  cpu_percent: number;
  memory_mb: number;
  status: string;
  username: string;
  cwd?: string | null;
  create_time: number;
  is_protected: boolean;
}

export interface ProcessLineageNode {
  pid: number;
  ppid: number;
  name: string;
  cmdline: string[];
  cwd?: string | null;
  username: string;
  is_high_resource: boolean;
}

export interface PortInspectResponse {
  port: number;
  is_in_use: boolean;
  process?: PortProcessInfo | null;
  lineage: ProcessLineageNode[];
}

export interface ProcessKillRequest {
  force?: boolean;
  reason?: string;
}

export interface ProcessKillResponse {
  success: boolean;
  pid: number;
  signal_sent: string;
  message: string;
}

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

export type PruningReason =
  | 'none'
  | 'score_below_threshold'
  | 'topk_overflow'
  | 'semantic_dedup'
  | 'policy_blocked'
  | 'unknown';

export interface RetrievalTreeNode {
  node_id: string;
  name: string;
  path: string;
  depth: number;
  similarity_score: number;
  pruning_threshold: number;
  is_pruned: boolean;
  pruning_reason: PruningReason;
  reason_detail: string;
  is_hit: boolean;
  metadata: Record<string, string>;
  children: RetrievalTreeNode[];
}

export interface VisitedPathTrace {
  trace_id: string;
  query: string;
  root_nodes: RetrievalTreeNode[];
  total_nodes_visited: number;
  pruned_nodes_count: number;
  hits_count: number;
  duration_ms: number;
  created_at: number;
}

export interface RetrievalSimulateRequest {
  query: string;
  pruning_threshold?: number;
  top_k?: number;
}

export interface HardwareUsage {
  execution_seconds: number;
  cpu_cores: number;
  memory_gb: number;
  volume_read_mb: number;
  volume_write_mb: number;
  hardware_credits: number;
}

export interface CognitiveUsage {
  model_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  cached_prompt_tokens: number;
  cognitive_credits: number;
}

export interface HybridLedgerReport {
  task_id: string;
  hardware: HardwareUsage;
  cognitive: CognitiveUsage;
  total_credits: number;
  estimated_cost_usd: number;
  is_budget_exceeded: boolean;
  budget_exceeded_reason: string;
  created_at: number;
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

export interface LaborAccelerationSummary {
  task_id: string;
  task_elapsed_seconds: number;
  total_hours_saved: number;
  acceleration_factor: number;
  hourly_rate_usd: number;
  estimated_saved_value_usd: number;
  compute_cost_usd: number;
  roi_ratio: number;
  breakdown: LaborEquivalencyItem[];
  created_at: number;
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

export type BudgetLadderTier =
  | 'NORMAL'
  | 'TIER1_NOTICE'
  | 'TIER2_DEGRADED'
  | 'TIER3_SUSPENDED';

export interface BudgetLadderVerdict {
  workflow_id: string;
  tier: BudgetLadderTier;
  used_pct: number;
  is_throttled: boolean;
  is_suspended: boolean;
  throttle_factor: number;
  action_message: string;
  recommended_model_tier: 'primary' | 'economy' | 'halted' | string;
}

export interface WorkflowBurnStatus {
  workflow_id: string;
  tokens_per_sec: number;
  cost_per_hour_usd: number;
  cumulative_prompt_tokens: number;
  cumulative_completion_tokens: number;
  total_cumulative_tokens: number;
  cumulative_cost_usd: number;
  budget_tokens?: number | null;
  budget_cost_usd?: number | null;
  active_agent_count: number;
  agent_burn_distribution: Record<string, number>;
  verdict: BudgetLadderVerdict;
  updated_at: string;
}

export interface AdjustBudgetPayload {
  added_tokens?: number;
  added_cost_usd?: number;
  force_resume?: boolean;
}

export type InterventionType =
  | 'APPROVAL_GATE'
  | 'STEER_CORRECTION'
  | 'REJECT_REWORK'
  | 'PARAMETER_OVERRIDE';

export interface SupervisionDecayPoint {
  sequence_number: number;
  intervention_rate_pct: number;
  average_attention_minutes: number;
  sample_count: number;
}

export interface CoordinationScoreboardSummary {
  template_type: string;
  total_runs: number;
  average_friction_rate: number;
  rework_rate_pct: number;
  total_coordination_hours_saved: number;
  friction_decay_pct: number;
  decay_curve: SupervisionDecayPoint[];
  active_templates?: string[];
  updated_at?: string;
}

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

export * from './sanitizedDebugTypes';
export * from './tokenEconomicsTypes';
export * from './deliveryDossierTypes';
