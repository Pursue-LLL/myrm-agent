/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Ground Truth Priority & Code Drift Stale Memory Defense DTOs and API clients:
 * - checkMemoryDrift
 * - checkBatchMemoryDrift
 *
 * [POS]
 * Frontend API client for evaluating candidate memories against physical workspace files and symbols.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type DriftTypeKind =
  | 'file_not_found'
  | 'file_content_drift'
  | 'symbol_not_found'
  | 'config_changed'
  | string;

export interface MemoryDriftFindingDTO {
  drift_type: DriftTypeKind;
  reference_target: string;
  detail: string;
  is_stale: boolean;
}

export interface DriftCheckRequestDTO {
  memory_id: string;
  content: string;
  workspace_root?: string | null;
  recorded_path?: string | null;
  recorded_symbol?: string | null;
}

export interface DriftCheckResponseDTO {
  memory_id: string;
  is_drifted: boolean;
  confidence_penalty: number;
  findings: MemoryDriftFindingDTO[];
  decorated_content: string;
}

export interface BatchDriftCheckRequestDTO {
  items: DriftCheckRequestDTO[];
  workspace_root?: string | null;
}

export interface BatchDriftCheckResponseDTO {
  results: DriftCheckResponseDTO[];
  total_checked: number;
  drifted_count: number;
}

/**
 * Evaluate an individual memory for file presence and code symbol drift.
 */
export async function checkMemoryDrift(
  req: DriftCheckRequestDTO
): Promise<DriftCheckResponseDTO> {
  return apiRequest<DriftCheckResponseDTO>('/memory/drift/check', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Batch evaluate candidate memories before prompt injection.
 */
export async function checkBatchMemoryDrift(
  req: BatchDriftCheckRequestDTO
): Promise<BatchDriftCheckResponseDTO> {
  return apiRequest<BatchDriftCheckResponseDTO>('/memory/drift/check-batch', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
