/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 98:
 * PromptCachePreservingEphemeralDeltaMemorySuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints.
 * Strict typing applied: No `any` types allowed. Single file < 300 lines.
 */

import { apiClient } from '@/services/api';

export type DeltaAction = 'override' | 'add_fact' | 'revoke';
export type DeltaSource = 'user_explicit' | 'agent_inferred';

export interface EphemeralDeltaItemDTO {
  delta_id: string;
  session_id: string;
  target_key: string;
  content: string;
  action: DeltaAction;
  turn_index: number;
  source: DeltaSource;
  confidence: number;
  created_at: string;
  is_reconciled: boolean;
}

export interface RecordDeltaRequestDTO {
  session_id: string;
  target_key: string;
  content: string;
  action?: DeltaAction;
  turn_index?: number;
  source?: DeltaSource;
  confidence?: number;
}

export interface SessionDeltaSnapshotDTO {
  session_id: string;
  active_deltas: EphemeralDeltaItemDTO[];
  is_reconciled: boolean;
  reconciled_at?: string | null;
}

export interface ReconcileSessionResponseDTO {
  session_id: string;
  active_delta_count: number;
  injection_still_active: boolean;
}

export interface PromptCacheMetricsDTO {
  system_prompt_frozen: boolean;
  system_prompt_byte_hash?: string | null;
  in_flight_deltas_count: number;
  recency_perception_delay_ms?: number | null;
  kv_cache_hit_ratio?: number | null;
  avoided_recomputation_tokens?: number | null;
}

export interface PreviewDeltaInjectionRequestDTO {
  session_id: string;
  raw_system_prompt?: string;
  human_messages?: string[];
}

export interface PreviewDeltaInjectionResponseDTO {
  session_id: string;
  frozen_system_prompt: string;
  augmented_final_human_message: string;
  tail_tag_snippet: string;
  active_deltas: EphemeralDeltaItemDTO[];
  metrics: PromptCacheMetricsDTO;
}

export async function recordEphemeralDelta(
  request: RecordDeltaRequestDTO
): Promise<EphemeralDeltaItemDTO> {
  const payload = {
    session_id: request.session_id,
    target_key: request.target_key,
    content: request.content,
    action: request.action ?? 'override',
    turn_index: request.turn_index ?? 1,
    source: request.source ?? 'user_explicit',
    confidence: request.confidence ?? 1.0,
  };
  return apiClient.post<EphemeralDeltaItemDTO>('/memory/ephemeral-delta/record', payload);
}

export async function getActiveEphemeralDeltas(
  sessionId: string
): Promise<EphemeralDeltaItemDTO[]> {
  return apiClient.get<EphemeralDeltaItemDTO[]>(
    `/memory/ephemeral-delta/active/${encodeURIComponent(sessionId)}`
  );
}

export async function getEphemeralDeltaSnapshot(
  sessionId: string
): Promise<SessionDeltaSnapshotDTO> {
  return apiClient.get<SessionDeltaSnapshotDTO>(
    `/memory/ephemeral-delta/snapshot/${encodeURIComponent(sessionId)}`
  );
}

export async function previewDeltaInjection(
  request: PreviewDeltaInjectionRequestDTO
): Promise<PreviewDeltaInjectionResponseDTO> {
  const payload = {
    session_id: request.session_id,
    raw_system_prompt:
      request.raw_system_prompt ?? 'You are Myrm Agent. System Profile: Senior Architect.',
    human_messages: request.human_messages ?? [
      'Hello, please inspect my repo.',
      'Please call me Old Zhang instead.',
    ],
  };
  return apiClient.post<PreviewDeltaInjectionResponseDTO>(
    '/memory/ephemeral-delta/preview',
    payload
  );
}

export async function getPromptCacheMetrics(
  sessionId: string
): Promise<PromptCacheMetricsDTO> {
  return apiClient.get<PromptCacheMetricsDTO>(
    `/memory/ephemeral-delta/metrics/${encodeURIComponent(sessionId)}`
  );
}
