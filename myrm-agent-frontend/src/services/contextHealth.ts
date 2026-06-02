/**
 * [INPUT]
 * - Server statistics context_health payload.
 *
 * [OUTPUT]
 * - ContextHealth: session context-health response DTO.
 * - ArchiveRestoreBlockEvent: archive restore guidance event DTO.
 *
 * [POS]
 * Statistics context-health DTO layer. Defines compaction, pruning/archive restore, adaptive backoff,
 * and prompt-cache health contracts for Session Analytics UI.
 */

export type HealthStatus = 'inactive' | 'healthy' | 'warning' | 'critical';

export interface CompactionHealth {
  status: HealthStatus;
  active: boolean;
  count: number;
  tokens_saved: number;
  net_tokens_saved: number;
  efficiency: number;
  refetch_count: number;
  refetch_ratio: number;
  dedup_tokens_saved: number;
  integrity_skipped: number;
  summary_persisted: boolean;
  last_compacted_at: string | null;
}

export interface PruningHealth {
  status: HealthStatus;
  active: boolean;
  archived: number;
  soft_trimmed: number;
  offload_failed: number;
  archive_written_count: number;
  archive_reused_count: number;
  archive_bytes_written: number;
  archive_bytes_reused: number;
  deferred_count: number;
  deferred_reasons: Record<string, number>;
  archive_deferred_count: number;
  archive_deferred_reasons: Record<string, number>;
  archive_deferred_soft_trimmed_count: number;
  archive_deferred_soft_trimmed_reasons: Record<string, number>;
  archive_refetch_count: number;
  archive_refetch_tokens: number;
  archive_restore_requested_count: number;
  archive_restore_allowed_count: number;
  archive_restore_blocked_count: number;
  archive_restore_blocked_ratio: number;
  archive_restore_result_count: number;
  archive_restore_result_tokens: number;
  archive_restore_result_lines: number;
  archive_restore_result_bytes: number;
  pruning_restore_cost_ratio: number;
  pruning_restore_roi_ratio: number;
  archive_restore_block_events: ArchiveRestoreBlockEvent[];
  offload_failure_kinds: Record<string, number>;
  original_tokens: number;
  tokens_saved: number;
  net_tokens_saved: number;
  refetch_ratio: number;
  backoff_applied: boolean;
  backoff_reasons: Record<string, number>;
  effective_soft_trim_ratio: number;
  effective_hard_clear_ratio: number;
  effective_min_prunable_tokens: number;
  archive_summary_queued_count: number;
  archive_summary_succeeded_count: number;
  archive_summary_failed_count: number;
  archive_summary_skipped_count: number;
  archive_summary_skipped_reasons: Record<string, number>;
}

export interface ArchiveRestoreBlockEvent {
  reason: string;
  estimated_tokens: number;
  archive_path: string;
  message: string;
  suggested_action: string;
  reason_label_key: string;
  severity: 'info' | 'warning' | 'critical' | string;
  primary_restore_arg: string;
  recommended_ranges: string[];
  restore_range_hints: ArchiveRestoreRangeHint[];
  content_features: ArchiveRestoreContentFeature[];
  guidance_source: string;
  fallback_reason: string;
  timestamp: string;
}

export interface ArchiveRestoreRangeHint {
  range_arg: string;
  reason: string;
  start_line: number;
  end_line: number;
  line: number;
}

export interface ArchiveRestoreContentFeature {
  feature_type: string;
  count: number;
  values: string[];
}

export interface CacheHealth {
  status: HealthStatus;
  active: boolean;
  calls: number;
  input_tokens: number;
  cached_tokens: number;
  cache_hit_rate: number;
  model_family: string;
  retention_mode: string;
  ttl_seconds: number;
  policy_reason: string;
  policy_source_url: string;
  retention_observation_state: 'observed' | 'estimated' | 'insufficient_data';
  retention_observation_reason: string;
  observation_sample_source: 'dominant_model' | 'session_aggregate';
  observation_model_name: string;
  observed_calls: number;
  observed_input_tokens: number;
  observed_cached_tokens: number;
  observed_cache_hit_rate: number;
}

export interface ContextHealth {
  status: HealthStatus;
  compaction: CompactionHealth;
  pruning: PruningHealth;
  cache: CacheHealth;
}
