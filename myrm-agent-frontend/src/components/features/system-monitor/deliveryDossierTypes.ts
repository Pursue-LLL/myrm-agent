/**
 * [INPUT]: None (Domain contracts for delivery evidence dossier and stratified asset friction).
 * [OUTPUT]: Strong TypeScript definitions for dossier verification receipts and friction metrics.
 * [POS]: myrm-agent-frontend/src/components/features/system-monitor/deliveryDossierTypes.ts
 */

export type UserAcceptanceStatus = 'ACCEPTED' | 'PARTIALLY_MODIFIED' | 'REJECTED_REWORK';

export type ExecutionMode = 'SINGLE_SHOT' | 'MULTI_TURN_AGENT';

export type AssetHealthTag = 'CORE_EFFICIENT' | 'NORMAL' | 'FRICTION_ASSASSIN' | 'SAMPLE_INSUFFICIENT';

export interface TaskSpecRecord {
  task_goal: string;
  acceptance_criteria: string[];
  non_goals: string[];
}

export interface AgentPersonaFingerprint {
  agent_id: string;
  model_name: string;
  prompt_hash: string;
  mounted_skills: string[];
}

export interface ToolExecutionTraceItem {
  tool_name: string;
  arguments_summary: string;
  duration_ms: number;
  exit_code: number;
  error_message?: string | null;
}

export interface PhysicalVerificationReceipt {
  test_suite_exit_code: number;
  passed_tests_count: number;
  failed_tests_count: number;
  artifact_path: string;
  artifact_sha256: string;
  verified_at: string;
}

export interface DeliveryEvidenceDossier {
  dossier_id: string;
  task_id: string;
  execution_mode: ExecutionMode;
  spec: TaskSpecRecord;
  persona: AgentPersonaFingerprint;
  tool_traces: ToolExecutionTraceItem[];
  verification: PhysicalVerificationReceipt;
  acceptance: UserAcceptanceStatus;
  total_tokens_consumed: number;
  wasted_friction_tokens: number;
  rework_count: number;
  dossier_checksum_sha256: string;
  created_at: string;
}

export interface AssetFrictionMetric {
  skill_id: string;
  model_name: string;
  execution_mode: ExecutionMode;
  sample_count: number;
  true_efficacy_rate_pct: number;
  friction_index: number;
  total_wasted_tokens: number;
  rework_count: number;
  retry_count: number;
  health_tag: AssetHealthTag;
  governance_advice: string;
}
