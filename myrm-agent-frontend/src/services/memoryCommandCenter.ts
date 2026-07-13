/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 * ./memory::MemoryType (POS: Frontend memory API client)
 *
 * [OUTPUT]
 * getMemoryCommandCenter, runMemoryCommandAction, runMemoryDiagnosticAction: Personal Brain Command Center API client with migration diagnostics and cleanup DTOs.
 *
 * [POS]
 * Frontend Personal Brain Command Center client. Owns command-center DTOs, GUI governance actions, executable diagnostics, migration integrity state, and import cleanup metrics.
 */

import { apiRequest } from '@/lib/api';
import type { MemoryType } from './memory';

export interface MemoryCommandOverview {
  total_memories: number;
  by_type: Record<MemoryType, number>;
  pending_memories: number;
  pending_shared_proposals: number;
  active_shared_contexts: number;
  health_score?: number | null;
  health_status: 'healthy' | 'degraded' | 'critical' | 'unknown';
  deploy_mode: string;
}

export interface MemoryCommandSpace {
  namespace: string;
  kind: string;
  label: string;
  target_id?: string | null;
  context_id?: string | null;
  active: boolean;
  binding_count: number;
}

export interface MemoryCommandGovernanceItem {
  id: string;
  kind: string;
  target_kind: 'pending_memory' | 'shared_context_proposal' | 'memory';
  title: string;
  description: string;
  severity: 'info' | 'warning' | 'critical';
  status: string;
  created_at: string;
  available_actions: string[];
}

export interface MemoryCommandHealth {
  status: 'healthy' | 'degraded' | 'critical' | 'unknown';
  total?: number | null;
  dimensions: Record<string, number>;
  suggestions: string[];
  has_graph: boolean;
  sample_size: number;
  guardian_running: boolean;
  seconds_until_next?: number | null;
  checked_at?: string | null;
  cache_status: 'fresh' | 'refreshed' | 'unavailable';
}

export interface MemoryCommandTimelineEvent {
  id: string;
  kind: string;
  status: string;
  occurred_at: string;
  title: string;
  description: string;
  source: string;
  memory_type?: MemoryType | string | null;
  namespace?: string | null;
  target_kind?: string | null;
  target_id?: string | null;
  influence_count: number;
  metadata: Record<string, string | number | boolean | null>;
}

export interface MemoryCommandInfluenceRef {
  memory_id: string;
  memory_type: string;
  score?: number | null;
  content_preview: string;
  primary_namespace?: string | null;
  source_chat_id?: string | null;
  source_message_id?: string | null;
  reason?: string | null;
}

export interface MemoryCommandInfluenceItem {
  id: string;
  chat_id?: string | null;
  message_id?: string | null;
  occurred_at: string;
  answer_preview: string;
  influence_refs: MemoryCommandInfluenceRef[];
  prompt_tokens: number;
  cached_tokens: number;
}

export interface MemoryCommandCostProfile {
  prompt_tokens: number;
  cached_tokens: number;
  completion_tokens: number;
  cited_memory_refs: number;
  estimated_memory_tokens: number;
  cache_friendly: boolean;
}

export interface MemoryCommandConflictItem {
  id: string;
  kind: 'claim' | 'correction' | 'supersession';
  status: 'active' | 'needs_review' | 'resolved';
  memory_id?: string | null;
  related_memory_id?: string | null;
  title: string;
  description: string;
  created_at?: string | null;
}

export interface MemoryCommandReplayOverlay {
  chat_id: string;
  message_id?: string | null;
  event_count: number;
  influence_count: number;
  last_event_at: string;
  last_summary: string;
}

export interface MemoryCommandReplayEvent {
  id: string;
  phase: 'observe' | 'govern' | 'write' | 'index' | 'recall' | 'inject' | 'verify';
  status: string;
  occurred_at: string;
  title: string;
  summary: string;
  target_kind?: string | null;
  target_id?: string | null;
  correlation_id?: string | null;
  influence_count: number;
}

export interface MemoryCommandWaterfallStep {
  phase: 'observe' | 'scan' | 'propose' | 'approve' | 'write' | 'index' | 'recall' | 'inject' | 'cite' | 'verify';
  status: 'ready' | 'active' | 'warning' | 'missing';
  event_count: number;
  evidence_count: number;
  latest_at?: string | null;
  description: string;
}

export interface MemoryCommandTraceStep {
  id: string;
  phase: string;
  status: 'success' | 'warning' | 'error' | 'skipped';
  title: string;
  description: string;
  occurred_at: string;
  duration_ms?: number | null;
  output_count: number;
  result_count: number;
  step_index: number;
}

export interface MemoryCommandTraceRun {
  id: string;
  trace_id: string;
  message_id?: string | null;
  chat_id?: string | null;
  query_preview: string;
  status: 'success' | 'warning' | 'error' | 'skipped';
  occurred_at: string;
  duration_ms?: number | null;
  result_count: number;
  steps: MemoryCommandTraceStep[];
}

export interface MemoryCommandEvalMetric {
  id: string;
  label: string;
  status: 'ready' | 'partial' | 'missing';
  score: number;
  evidence: string;
}

export interface MemoryCommandConnectorStatus {
  id: string;
  label: string;
  status: 'ready' | 'manual_config_required' | 'missing';
  supported_actions: string[];
  notes: string;
}

export interface MemoryCommandPrivacySignal {
  id: string;
  label: string;
  status: 'ready' | 'warning' | 'missing';
  evidence: string;
  event_count: number;
}

export interface MemoryCommandDoctorCheck {
  id: string;
  category: 'storage' | 'index' | 'embedding' | 'ledger' | 'deployment' | 'quality' | 'migration';
  label: string;
  status: 'ready' | 'warning' | 'critical' | 'missing';
  evidence: string;
  impact: string;
  next_action: string;
  can_auto_fix: boolean;
  safe_to_retry: boolean;
  docs_ref?: string | null;
  repair_actions: string[];
  repair_plans: MemoryCommandRepairPlan[];
}

export interface MemoryCommandRepairPlan {
  id: string;
  label: string;
  risk_level: 'safe' | 'confirmation_required' | 'manual';
  dry_run_result: string;
  expected_effect: string;
  requires_confirmation: boolean;
  executable: boolean;
}

export interface MemoryCommandBenchmarkSummary {
  case_count: number;
  passed_count: number;
  recall_at_k: number;
  ndcg_at_k: number;
  mrr_score: number;
  precision_at_k: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  top_k: number;
  categories: Record<string, string>;
}

export interface MemoryCommandDiagnosticProbeResult {
  id: string;
  category: 'storage' | 'index' | 'embedding' | 'ledger' | 'deployment' | 'quality' | 'migration';
  label: string;
  status: 'ready' | 'warning' | 'critical' | 'missing';
  evidence: string;
  impact: string;
  next_action: string;
  can_auto_fix: boolean;
  safe_to_retry: boolean;
  docs_ref?: string | null;
  duration_ms?: number | null;
  benchmark_summary?: MemoryCommandBenchmarkSummary | null;
  repair_actions: string[];
  repair_plans: MemoryCommandRepairPlan[];
}

export interface MemoryCommandDiagnosticSlo {
  window_runs: number;
  pass_rate: number;
  failed_runs: number;
  average_duration_ms: number;
  status: 'ready' | 'warning' | 'critical' | 'missing';
}

export interface MemoryCommandDiagnosticRun {
  id: string;
  status: 'ready' | 'warning' | 'critical' | 'missing';
  summary: string;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  probe_count: number;
  failed_count: number;
  audit_recorded: boolean;
  audit_error?: string | null;
  slo?: MemoryCommandDiagnosticSlo | null;
  probes: MemoryCommandDiagnosticProbeResult[];
}

export interface MemoryCommandMigrationProvenance {
  supported_sources: string[];
  tracked_imports: number;
  unmapped_items: number;
  coverage_status: 'not_tracked' | 'partial' | 'complete';
  adapter_status: Record<string, 'ready' | 'planned' | 'missing'>;
  last_import_batch_id?: string | null;
  verification_recommended: boolean;
  last_import_diagnostic_status?: string | null;
  last_import_diagnostic_run_id?: string | null;
  cleanup_pending_sessions: number;
  cleanup_confirmed_sessions: number;
  cleanup_expired_sessions: number;
  cleanup_rolled_back_sessions: number;
  cleanup_retention_days: number;
}

export interface MemoryCommandPlaneSummary {
  enabled: boolean;
  content_visibility: 'not_shared';
  health_status: string;
  import_rollback_health_status: 'ready' | 'warning' | 'critical';
  archive_restore_health_status: 'ready' | 'warning' | 'critical';
  event_count: number;
  failed_event_count: number;
  queue_backlog: number;
  import_rollback_in_progress: number;
  import_rollback_failed: number;
  import_rollback_partial: number;
  import_rollback_missing_items: number;
  import_rollback_failed_items: number;
  archive_restore_in_progress: number;
  archive_restore_failed: number;
  archive_restore_partial: number;
  archive_restore_rollback_in_progress: number;
  archive_restore_rollback_failed: number;
  archive_restore_missing_items: number;
  archive_restore_failed_items: number;
  storage_mode: string;
  last_event_at?: string | null;
  redaction_scope: 'metadata_only';
  sandbox_isolation: 'local_or_per_user_sandbox';
}

export interface MemoryCommandRuntimeStatus {
  deploy_mode: string;
  storage_mode: string;
  memory_base_path: string;
  relational_status: 'available' | 'unavailable';
  vector_status: 'available' | 'unavailable';
  graph_status: 'available' | 'unavailable';
  embedding_status: 'custom' | 'unavailable';
  control_plane_status: 'not_used' | 'proxied_by_sandbox';
  event_ledger_status: 'available' | 'unavailable';
  health_snapshot_status: 'available' | 'unavailable';
  supported_clients: ('local_web' | 'tauri_desktop' | 'saas_sandbox')[];
}

export interface MemoryCommandCenterResponse {
  generated_at: string;
  overview: MemoryCommandOverview;
  spaces: MemoryCommandSpace[];
  governance: MemoryCommandGovernanceItem[];
  health: MemoryCommandHealth;
  timeline: MemoryCommandTimelineEvent[];
  live_stream: MemoryCommandTimelineEvent[];
  influence: MemoryCommandInfluenceItem[];
  cost: MemoryCommandCostProfile;
  conflicts: MemoryCommandConflictItem[];
  replay: MemoryCommandReplayOverlay[];
  replay_events: MemoryCommandReplayEvent[];
  waterfall: MemoryCommandWaterfallStep[];
  trace_runs: MemoryCommandTraceRun[];
  eval_metrics: MemoryCommandEvalMetric[];
  connectors: MemoryCommandConnectorStatus[];
  privacy: MemoryCommandPrivacySignal[];
  doctor_checks: MemoryCommandDoctorCheck[];
  migration: MemoryCommandMigrationProvenance;
  plane_summary: MemoryCommandPlaneSummary;
  runtime: MemoryCommandRuntimeStatus;
}

export interface MemoryCommandGraphNode {
  id: string;
  labels: string[];
  properties: Record<string, string | number | boolean>;
}

export interface MemoryCommandGraphEdge {
  id: string;
  source: string;
  target: string;
  rel_type: string;
  properties: Record<string, string | number>;
}

export interface MemoryCommandGraphStats {
  node_count: number;
  relationship_count: number;
  node_label_counts: Record<string, number>;
  relationship_type_counts: Record<string, number>;
}

export interface MemoryCommandGraphResponse {
  nodes: MemoryCommandGraphNode[];
  edges: MemoryCommandGraphEdge[];
  stats: MemoryCommandGraphStats;
  has_graph: boolean;
}

export interface MemoryCommandActionRequest {
  target_kind: 'pending_memory' | 'shared_context_proposal' | 'memory';
  target_id: string;
  action: 'approve' | 'reject' | 'edit' | 'correct' | 'forget' | 'pin' | 'unpin';
  memory_type?: string;
  content?: string;
}

export interface MemoryCommandActionResponse {
  status: 'success';
  target_kind: string;
  target_id: string;
  action: string;
}

export interface MemoryCommandDiagnosticActionRequest {
  action: 'run_diagnostics' | 'run_health_refresh';
}

export interface MemoryCommandDiagnosticActionResponse {
  status: 'completed' | 'completed_with_findings' | 'failed';
  action: string;
  run: MemoryCommandDiagnosticRun;
}

export interface MemoryCommandRepairExecutionResult {
  plan_id: string;
  status: 'completed' | 'blocked' | 'failed' | 'dry_run';
  message: string;
  audit_event_id?: string | null;
  probe_run_id?: string | null;
  changed: boolean;
}

export interface MemoryCommandRepairActionRequest {
  plan_id:
    | 'run_diagnostics'
    | 'run_health_refresh'
    | 'review_storage_config'
    | 'enable_vector_store'
    | 'configure_embedding'
    | 'review_retrieval_trace';
  mode?: 'dry_run' | 'execute';
}

export interface MemoryCommandRepairActionResponse {
  result: MemoryCommandRepairExecutionResult;
  run?: MemoryCommandDiagnosticRun | null;
}

export const getMemoryCommandCenter = async (): Promise<MemoryCommandCenterResponse> => {
  return apiRequest<MemoryCommandCenterResponse>('/memory/command-center/');
};

export const runMemoryCommandAction = async (
  body: MemoryCommandActionRequest,
): Promise<MemoryCommandActionResponse> => {
  return apiRequest<MemoryCommandActionResponse>('/memory/command-center/actions', {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export const runMemoryDiagnosticAction = async (
  body: MemoryCommandDiagnosticActionRequest,
): Promise<MemoryCommandDiagnosticActionResponse> => {
  return apiRequest<MemoryCommandDiagnosticActionResponse>('/memory/command-center/diagnostics/actions', {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export const getMemoryGraph = async (
  limit = 50,
  offset = 0,
  namespace?: string,
): Promise<MemoryCommandGraphResponse> => {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (namespace) params.set('namespace', namespace);
  return apiRequest<MemoryCommandGraphResponse>(`/memory/command-center/graph?${params.toString()}`);
};

export const runMemoryDiagnosticRepair = async (
  body: MemoryCommandRepairActionRequest,
): Promise<MemoryCommandRepairActionResponse> => {
  return apiRequest<MemoryCommandRepairActionResponse>('/memory/command-center/diagnostics/repairs', {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

export interface ConsolidationLastSummary {
  available: boolean;
  event_id?: string;
  timestamp?: string;
  summary?: string;
  affected_ids?: string[];
  affected_count?: number;
  rollback_available?: boolean;
  conflict_ids?: string[];
}

export interface ConsolidationRollbackResult {
  rolled_back: number;
  skipped_conflict: number;
  errors: number;
  conflict_ids: string[];
}

export const getConsolidationLastSummary = async (): Promise<ConsolidationLastSummary> => {
  return apiRequest<ConsolidationLastSummary>('/memory/command-center/consolidation/last-summary');
};

export const rollbackConsolidation = async (): Promise<ConsolidationRollbackResult> => {
  return apiRequest<ConsolidationRollbackResult>('/memory/command-center/consolidation/rollback', {
    method: 'POST',
  });
};
