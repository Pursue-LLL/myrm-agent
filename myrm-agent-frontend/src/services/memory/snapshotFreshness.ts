/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Snapshot Freshness DTOs and API clients:
 * - initSessionSnapshot: Seal snapshot generation digest for an active session
 * - recordSessionWrite: Record memory write event to disk and mark snapshot dirty
 * - getSnapshotFreshnessState: Fetch current staleness and delta state
 * - getDiskReadHint: Fetch direct-disk verification contract hint
 * - getDeltaPatch: Render intra-session append-only delta patch markdown block
 * - resetSessionFreshness: Reset freshness state upon session close
 *
 * [POS]
 * Frontend API service for Item 157 SnapshotLagAwareMemoryFreshnessAndDiskVerificationContractSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export type WriteAction = 'create' | 'update' | 'delete';

export interface MemorySnapshotDigestDTO {
  digest: string;
  session_id: string;
  created_at: string;
  initial_items_count: number;
}

export interface InitSnapshotRequest {
  session_id: string;
  initial_content?: string;
  items_count?: number;
}

export interface SessionWriteDeltaDTO {
  key: string;
  content: string;
  turn_index: number;
  written_at: string;
  action: WriteAction;
}

export interface RecordWriteRequest {
  session_id: string;
  key: string;
  content: string;
  turn_index?: number;
  action?: WriteAction;
}

export interface SnapshotFreshnessStateDTO {
  session_id: string;
  snapshot_digest: string;
  is_dirty: boolean;
  deltas: SessionWriteDeltaDTO[];
  latest_disk_version: number;
}

export interface DirectDiskReadHintDTO {
  session_id: string;
  hint_message: string;
  affected_keys: string[];
  is_dirty: boolean;
}

export interface DeltaPatchBlockDTO {
  header: string;
  patches: string[];
  formatted_block: string;
}

export interface ResetSessionResponse {
  status: string;
  session_id: string;
}

export async function initSessionSnapshot(
  req: InitSnapshotRequest
): Promise<MemorySnapshotDigestDTO> {
  return apiRequest<MemorySnapshotDigestDTO>('/api/memory/snapshot-freshness/init', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function recordSessionWrite(
  req: RecordWriteRequest
): Promise<SnapshotFreshnessStateDTO> {
  return apiRequest<SnapshotFreshnessStateDTO>('/api/memory/snapshot-freshness/record-write', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getSnapshotFreshnessState(
  sessionId: string
): Promise<SnapshotFreshnessStateDTO> {
  return apiRequest<SnapshotFreshnessStateDTO>(
    `/api/memory/snapshot-freshness/status/${encodeURIComponent(sessionId)}`,
    { method: 'GET' }
  );
}

export async function getDiskReadHint(
  sessionId: string
): Promise<DirectDiskReadHintDTO> {
  return apiRequest<DirectDiskReadHintDTO>(
    `/api/memory/snapshot-freshness/hint/${encodeURIComponent(sessionId)}`,
    { method: 'GET' }
  );
}

export async function getDeltaPatch(
  sessionId: string
): Promise<DeltaPatchBlockDTO> {
  return apiRequest<DeltaPatchBlockDTO>(
    `/api/memory/snapshot-freshness/delta-patch/${encodeURIComponent(sessionId)}`,
    { method: 'GET' }
  );
}

export async function resetSessionFreshness(
  sessionId: string
): Promise<ResetSessionResponse> {
  return apiRequest<ResetSessionResponse>(
    `/api/memory/snapshot-freshness/reset/${encodeURIComponent(sessionId)}`,
    { method: 'POST' }
  );
}
