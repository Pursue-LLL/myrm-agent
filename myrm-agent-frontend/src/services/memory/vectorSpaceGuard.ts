/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: SpaceFingerprintDTO, SpaceValidateRequest, SpaceValidateResponse,
 *        SpaceBindRequest, SpaceBindResponse, SpaceStatusResponse,
 *        SpaceReindexRequest, SpaceReindexResponse
 * Functions: validateVectorSpace, bindVectorSpace, fetchVectorSpaceStatus, reindexVectorSpace
 *
 * [POS]
 * Client service for Item 131 EmbeddingModelDimensionAndVectorSpaceGuardSuite.
 * Guards embedding model dimensions and vector space integrity across vector stores.
 * Strictly typed with zero `any` usage. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export type VectorMetricType = 'cosine' | 'dot' | 'euclidean';

export interface SpaceFingerprintDTO {
  provider_id: string;
  model_name: string;
  vector_dimension: number;
  metric_type: VectorMetricType;
  config_hash?: string;
}

export interface SpaceValidateRequest {
  collection: string;
  fingerprint: SpaceFingerprintDTO;
  auto_bind_if_empty?: boolean;
}

export interface SpaceValidateResponse {
  is_valid: boolean;
  status:
    | 'consistent'
    | 'dimension_mismatch'
    | 'model_base_mismatch'
    | 'uninitialized'
    | 'metadata_missing'
    | string;
  message: string;
  recommended_action:
    | 'proceed'
    | 'reindex_required'
    | 'initialize_space'
    | 'fallback_fts'
    | string;
  expected_fingerprint: SpaceFingerprintDTO | null;
  current_fingerprint: SpaceFingerprintDTO | null;
}

export interface SpaceBindRequest {
  collection: string;
  fingerprint: SpaceFingerprintDTO;
  total_vectors_indexed?: number;
}

export interface SpaceBindResponse {
  collection: string;
  fingerprint: SpaceFingerprintDTO;
  status: string;
}

export interface SpaceStatusResponse {
  collection: string;
  has_registered_space: boolean;
  fingerprint: SpaceFingerprintDTO | null;
  total_vectors_indexed: number;
  last_validated_at: string | null;
}

export interface SpaceReindexRequest {
  collection: string;
  target_fingerprint: SpaceFingerprintDTO;
  sample_items?: string[];
}

export interface SpaceReindexResponse {
  collection: string;
  status: 'completed' | 'failed' | 'in_progress' | string;
  reindexed_count: number;
  error_message: string | null;
}

export async function validateVectorSpace(
  req: SpaceValidateRequest
): Promise<SpaceValidateResponse> {
  return apiRequest<SpaceValidateResponse>('/memory/space-guard/validate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function bindVectorSpace(
  req: SpaceBindRequest
): Promise<SpaceBindResponse> {
  return apiRequest<SpaceBindResponse>('/memory/space-guard/bind', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function fetchVectorSpaceStatus(
  collection: string
): Promise<SpaceStatusResponse> {
  return apiRequest<SpaceStatusResponse>(
    `/memory/space-guard/status/${encodeURIComponent(collection)}`,
    {
      method: 'GET',
    }
  );
}

export async function reindexVectorSpace(
  req: SpaceReindexRequest
): Promise<SpaceReindexResponse> {
  return apiRequest<SpaceReindexResponse>('/memory/space-guard/reindex', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
