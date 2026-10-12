/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Disk Memory FTS Reconciliation Loop & Explicit Write Gate DTOs and API clients:
 * - triggerReconciliation (Executes bi-directional reconciliation pass over disk directories)
 * - checkWriteGate (Evaluates whether persistent memory writes are authorized under active gate policy)
 * - setWriteGatePolicy (Updates write gate policy globally or for a specific session)
 * - searchReconciledFts (Full-text ranked query across reconciled memory notes via SQLite FTS5)
 * - getReconciliationStats (Summary metrics on indexed disk memory notes and active write gate policy)
 *
 * [POS]
 * Frontend API service for Topic 01 Item 94 (Disk Memory FTS Reconciliation Loop
 * and Explicit Write Gate Suite).
 * Strict typing applied: No `any` types allowed. Single file < 250 lines.
 */

import { apiRequest } from '@/lib/api';

export type WriteGatePolicy =
  | 'enabled'
  | 'read_only_session'
  | 'disabled_temporary'
  | 'disabled_config_fault';

export interface WriteGateCheckResultDTO {
  is_allowed: boolean;
  policy: WriteGatePolicy | string;
  reason: string;
}

export interface SetWriteGatePolicyRequestDTO {
  policy: WriteGatePolicy | string;
  session_id?: string;
}

export interface ReconciliationReportDTO {
  reconcile_id: string;
  scanned_disk_files_count: number;
  indexed_or_updated_count: number;
  pruned_dead_rows_count: number;
  duration_ms: number;
  status: string;
  created_at: string;
}

export interface TriggerReconciliationRequestDTO {
  roots?: string[];
  session_id?: string;
}

export interface FtsReconciledHitDTO {
  file_path: string;
  title: string;
  snippet: string;
  rank_score: number;
}

export interface ReconciliationStatsDTO {
  total_indexed_files: number;
  global_write_policy: string;
}

/**
 * Triggers a bi-directional reconciliation pass over specified disk directories.
 * Direction A: index newly discovered / modified markdown files into SQLite FTS5.
 * Direction B: prune dead FTS rows where physical files have been deleted on disk.
 */
export async function triggerReconciliation(
  request: TriggerReconciliationRequestDTO = {}
): Promise<ReconciliationReportDTO> {
  return apiRequest<ReconciliationReportDTO>('/memory/reconciliation/sync', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Checks whether persistent memory writes are authorized under the active gate policy.
 * Reads are always open and never blocked by this gate.
 */
export async function checkWriteGate(
  sessionId?: string
): Promise<WriteGateCheckResultDTO> {
  const params = new URLSearchParams();
  if (sessionId) {
    params.set('session_id', sessionId);
  }
  const queryStr = params.toString();
  return apiRequest<WriteGateCheckResultDTO>(
    `/memory/reconciliation/write-gate${queryStr ? `?${queryStr}` : ''}`
  );
}

/**
 * Updates the write gate policy globally or for a specific session override.
 */
export async function setWriteGatePolicy(
  request: SetWriteGatePolicyRequestDTO
): Promise<WriteGateCheckResultDTO> {
  return apiRequest<WriteGateCheckResultDTO>('/memory/reconciliation/write-gate', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Executes a full-text ranked query across reconciled markdown memory notes.
 */
export async function searchReconciledFts(
  query: string,
  limit = 20
): Promise<FtsReconciledHitDTO[]> {
  const params = new URLSearchParams({
    query,
    limit: String(limit),
  });
  return apiRequest<FtsReconciledHitDTO[]>(
    `/memory/reconciliation/search?${params.toString()}`
  );
}

/**
 * Retrieves summary metrics on indexed disk memory notes and active write gate policy.
 */
export async function getReconciliationStats(): Promise<ReconciliationStatsDTO> {
  return apiRequest<ReconciliationStatsDTO>('/memory/reconciliation/stats');
}
