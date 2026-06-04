/**
 * [INPUT]
 * @/store/config/providerTypes::SingleModelSelection (POS: Provider/model selection type contract)
 *
 * [OUTPUT]
 * Chat message, stream event, artifact, memory citation and store state TypeScript contracts.
 *
 * [POS]
 * Chat state and SSE event type definitions. Split from monolithic types.ts for maintainability.
 */

export interface ArchiveRestoreAction {
  type: 'archive_restore';
  restoreArg: string;
}

export interface ArchiveRestoreRangeHint {
  range_arg: string;
  reason?: string;
  start_line?: number;
  end_line?: number;
  label?: string;
}

export interface ArchiveRestoreContentFeature {
  feature_type: string;
  count: number;
  values: string[];
}

export interface ArchiveRestoreBlockPayload {
  type?: 'archive_restore_blocked';
  reason?: string;
  message?: string;
  suggested_action?: string;
  archive_path?: string;
  estimated_tokens?: number;
  reason_label_key?: string;
  severity?: 'info' | 'warning' | 'critical';
  primary_restore_arg?: string;
  recommended_ranges?: string[];
  restore_range_hints?: ArchiveRestoreRangeHint[];
  content_features?: ArchiveRestoreContentFeature[];
  guidance_source?: string;
  fallback_reason?: string;
}

export interface ArchiveRestoreResultPayload {
  type?: 'archive_restore_result';
  outcome?: 'restored';
  archive_path: string;
  restore_arg: string;
  start_line: number;
  end_line: number;
  restored_line_count: number;
  estimated_tokens: number;
  restored_bytes: number;
}
