/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Vector Index Dimension Guard & Rebuild DTOs and API clients:
 * - inspectCollectionDim: Inspect dimensionality alignment and rebuild necessity
 * - startVectorRebuild: Start orchestrated non-destructive rebuild with task lock
 * - getRebuildTaskStatus: Retrieve real-time rebuild progress and failed items checklist
 * - getActiveRebuildTask: Check whether another rebuild task holds the concurrency lock
 *
 * [POS]
 * Frontend API service for Item 151 VectorDimGuardAndRebuildTaskSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface DimGuardInspectRequestDTO {
  collection: string;
  expected_dim: number;
}

export interface DimGuardInspectResponseDTO {
  collection: string;
  exists: boolean;
  current_dim: number | null;
  expected_dim: number;
  dim_match: boolean;
  needs_rebuild: boolean;
  data_intact: boolean;
  message: string;
}

export interface StartRebuildRequestDTO {
  collection: string;
  expected_dim: number;
  items?: Array<Record<string, string | number[]>>;
  fail_item_ids?: string[];
}

export interface FailedItemDTO {
  item_id: string;
  reason: string;
  phase: string;
  timestamp_ms: number;
}

export interface RebuildTaskStatusResponseDTO {
  task_id: string;
  collection: string;
  phase: string;
  progress_pct: number;
  processed_count: number;
  total_count: number;
  failed_items: FailedItemDTO[];
  started_at_ms: number;
  finished_at_ms: number | null;
  error: string | null;
}

/**
 * Inspect dimensionality alignment and rebuild necessity for a vector collection.
 */
export async function inspectCollectionDim(
  request: DimGuardInspectRequestDTO
): Promise<DimGuardInspectResponseDTO> {
  return apiRequest<DimGuardInspectResponseDTO>('/memory/vector-dim-guard/inspect', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

/**
 * Start an orchestrated non-destructive vector index rebuild task.
 */
export async function startVectorRebuild(
  request: StartRebuildRequestDTO
): Promise<RebuildTaskStatusResponseDTO> {
  return apiRequest<RebuildTaskStatusResponseDTO>('/memory/vector-dim-guard/rebuild/start', {
    method: 'POST',
    body: JSON.stringify(request),
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

/**
 * Retrieve progress snapshot and failed items checklist for a rebuild task.
 */
export async function getRebuildTaskStatus(
  taskId: string
): Promise<RebuildTaskStatusResponseDTO> {
  return apiRequest<RebuildTaskStatusResponseDTO>(
    `/memory/vector-dim-guard/rebuild/${encodeURIComponent(taskId)}/status`,
    {
      method: 'GET',
    }
  );
}

/**
 * Query active rebuild task ID holding the execution lock.
 */
export async function getActiveRebuildTask(): Promise<{ active_task_id: string | null }> {
  return apiRequest<{ active_task_id: string | null }>(
    '/memory/vector-dim-guard/rebuild/active',
    {
      method: 'GET',
    }
  );
}
