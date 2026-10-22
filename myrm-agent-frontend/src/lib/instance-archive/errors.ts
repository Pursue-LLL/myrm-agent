/**
 * [INPUT]
 * - Stable error codes returned by /instance-archive/*
 *
 * [OUTPUT]
 * - archiveErrorMessageKey: i18n key suffix for a failed call
 *
 * [POS]
 * Keeps the set of codes the UI has localized copy for in one place; anything else falls
 * back to the generic message so server wording is never shown.
 */

const KNOWN_CODES: ReadonlySet<string> = new Set([
  'backup_dir_inside_state',
  'backup_dir_invalid',
  'backup_dir_not_writable',
  'backup_incomplete',
  'backup_unreadable',
  'backup_write_failed',
  'restore_failed',
  'acknowledgement_required',
  'corrupt',
  'export_busy',
  'export_failed',
  'insufficient_space',
  'invalid_archive',
  'invalid_chunk',
  'invalid_geometry',
  'newer_schema',
  'no_main_db',
  'not_instance_db',
  'not_staged',
  'not_uploading',
  'nothing_to_undo',
  'operation_pending',
  'passphrase_required',
  'restore_point_corrupt',
  'restore_point_incomplete',
  'rollback_incomplete',
  'secrets_unavailable',
  'stage_failed',
  'unknown_export',
  'unknown_restore_point',
  'unknown_session',
  'unsupported_layout',
  'upload_incomplete',
  'wrong_passphrase',
]);

/** Failure codes a boot-time swap can record; they all read as "could not be applied". */
const SWAP_FAILURES: ReadonlySet<string> = new Set([
  'interrupted',
  'invalid_marker',
  'staging_missing',
  'promotion_failed',
]);

export function archiveErrorMessageKey(code: string | null | undefined): string {
  if (!code) {
    return 'generic';
  }
  if (SWAP_FAILURES.has(code)) {
    return 'restore_failed';
  }
  return KNOWN_CODES.has(code) ? code : 'generic';
}
