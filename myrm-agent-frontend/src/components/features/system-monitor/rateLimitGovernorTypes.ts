/**
 * [INPUT]: Provider HTTP rate limit headers, model configurations, and subagent concurrency tasks.
 * [OUTPUT]: Strong type definitions for rate limit pacing, quota snapshots, and subagent slicing.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/rateLimitGovernorTypes.ts
 */

export type PacingAction =
  | 'IMMEDIATE_PASS'
  | 'MICRO_SLEEP_PACED'
  | 'QUEUE_WAIT'
  | 'FALLBACK_DOWNGRADE';

export interface GovernorLiveStatus {
  model_name: string;
  tpm_watermark_pct: number;
  rpm_watermark_pct: number;
  smoothed_request_count: number;
  prevented_429_count: number;
  active_subagent_slices_count: number;
  status_label: string;
}

export interface QuotaPacingDecision {
  action: PacingAction;
  delay_ms: number;
  current_tpm_usage: number;
  max_tpm_limit: number;
  tpm_watermark_pct: number;
  current_rpm_usage: number;
  max_rpm_limit: number;
  reason: string;
  target_model_or_fallback: string;
}

export interface ProviderQuotaHeaderSnapshot {
  model_name: string;
  remaining_tokens?: number;
  reset_tokens_seconds?: number;
  remaining_requests?: number;
  reset_requests_seconds?: number;
  retry_after_seconds?: number;
  extracted_at: string;
}

export interface SubagentQuotaSlice {
  workspace_id: string;
  subagent_id: string;
  allocated_tpm_share: number;
  consumed_tokens_in_window: number;
  remaining_tokens_in_window: number;
  is_throttled: boolean;
}
