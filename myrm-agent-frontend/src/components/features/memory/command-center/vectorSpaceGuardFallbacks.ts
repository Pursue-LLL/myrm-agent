/**
 * [INPUT]
 * @/services/memory/vectorSpaceGuard::SpaceFingerprintDTO, SpaceStatusResponse, SpaceValidateResponse, SpaceReindexResponse
 *
 * [OUTPUT]
 * Constants: FALLBACK_SPACE_STATUS, FALLBACK_VALIDATE_RESPONSE, FALLBACK_REINDEX_RESPONSE, PRESET_MODEL_FINGERPRINTS
 *
 * [POS]
 * Fallback values and preset model fingerprints for Vector Space Guard UI components.
 * Zero `any` usage. Single file < 150 lines.
 */

import type {
  SpaceFingerprintDTO,
  SpaceReindexResponse,
  SpaceStatusResponse,
  SpaceValidateResponse,
} from '@/services/memory/vectorSpaceGuard';

export const PRESET_MODEL_FINGERPRINTS: Record<string, SpaceFingerprintDTO> = {
  'openai-small': {
    provider_id: 'openai',
    model_name: 'text-embedding-3-small',
    vector_dimension: 1536,
    metric_type: 'cosine',
    config_hash: '9a8b7c6d5e4f3a2b',
  },
  'openai-large': {
    provider_id: 'openai',
    model_name: 'text-embedding-3-large',
    vector_dimension: 3072,
    metric_type: 'cosine',
    config_hash: '1b2c3d4e5f6a7b8c',
  },
  'ollama-bge': {
    provider_id: 'ollama',
    model_name: 'bge-m3',
    vector_dimension: 1024,
    metric_type: 'cosine',
    config_hash: 'f0e1d2c3b4a59687',
  },
  'voyage-3': {
    provider_id: 'voyage',
    model_name: 'voyage-3',
    vector_dimension: 1024,
    metric_type: 'cosine',
    config_hash: '3c4d5e6f7a8b9c0d',
  },
};

export const FALLBACK_SPACE_STATUS: SpaceStatusResponse = {
  collection: 'working_memory',
  has_registered_space: true,
  fingerprint: {
    provider_id: 'openai',
    model_name: 'text-embedding-3-small',
    vector_dimension: 1536,
    metric_type: 'cosine',
    config_hash: '9a8b7c6d5e4f3a2b',
  },
  total_vectors_indexed: 128,
  last_validated_at: '2026-10-08T06:00:00Z',
};

export const FALLBACK_VALIDATE_RESPONSE: SpaceValidateResponse = {
  is_valid: true,
  status: 'consistent',
  message: '运行时模型与集合向量空间完全一致',
  recommended_action: 'proceed',
  expected_fingerprint: FALLBACK_SPACE_STATUS.fingerprint,
  current_fingerprint: FALLBACK_SPACE_STATUS.fingerprint,
};

export const FALLBACK_REINDEX_RESPONSE: SpaceReindexResponse = {
  collection: 'working_memory',
  status: 'completed',
  reindexed_count: 128,
  error_message: null,
};
