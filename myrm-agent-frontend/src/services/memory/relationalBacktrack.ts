/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 100:
 * TemporalRelationalAnchorAndCrossSessionEntityBacktrackingSuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints.
 * Strict typing applied: No `any` types allowed. Single file < 300 lines.
 */

import { apiClient } from '@/services/api';

export type EntityTypeKind = 'person' | 'client' | 'project' | 'organization' | 'location' | 'tool';

export interface TemporalRelationTripletDTO {
  triplet_id: string;
  subject: string;
  predicate_action: string;
  target_entity: string;
  target_entity_type: EntityTypeKind;
  temporal_anchor: string;
  session_id: string;
  message_id: string;
  verbatim_quote: string;
  action_synonyms: string[];
  confidence: number;
  created_at?: string | null;
}

export interface RecordTripletRequestDTO {
  subject?: string;
  predicate_action: string;
  target_entity: string;
  target_entity_type?: EntityTypeKind;
  temporal_anchor: string;
  session_id: string;
  message_id: string;
  verbatim_quote: string;
  action_synonyms?: string[];
  confidence?: number;
}

export interface RecordTripletResponseDTO {
  is_success: boolean;
  triplet: TemporalRelationTripletDTO;
}

export interface RelationalBacktrackQueryRequestDTO {
  action_cue: string;
  target_entity_type?: EntityTypeKind;
  session_id_scope?: string;
  min_confidence?: number;
}

export interface RelationalBacktrackHitDTO {
  triplet: TemporalRelationTripletDTO;
  matched_cue: string;
  match_score: number;
}

export interface RelationalBacktrackResponseDTO {
  hits: RelationalBacktrackHitDTO[];
  total_found: number;
  inferred_answer?: string | null;
}

export async function recordTemporalTriplet(
  request: RecordTripletRequestDTO
): Promise<RecordTripletResponseDTO> {
  const payload = {
    subject: request.subject ?? 'user',
    predicate_action: request.predicate_action,
    target_entity: request.target_entity,
    target_entity_type: request.target_entity_type ?? 'client',
    temporal_anchor: request.temporal_anchor,
    session_id: request.session_id,
    message_id: request.message_id,
    verbatim_quote: request.verbatim_quote,
    action_synonyms: request.action_synonyms ?? [],
    confidence: request.confidence ?? 1.0,
  };
  return apiClient.post<RecordTripletResponseDTO>('/memory/backtrack/record', payload);
}

export async function queryRelationalBacktrack(
  request: RelationalBacktrackQueryRequestDTO
): Promise<RelationalBacktrackResponseDTO> {
  const payload = {
    action_cue: request.action_cue,
    target_entity_type: request.target_entity_type,
    session_id_scope: request.session_id_scope,
    min_confidence: request.min_confidence ?? 0.5,
  };
  return apiClient.post<RelationalBacktrackResponseDTO>('/memory/backtrack/query', payload);
}

export async function listAllTemporalTriplets(): Promise<TemporalRelationTripletDTO[]> {
  return apiClient.get<TemporalRelationTripletDTO[]>('/memory/backtrack/list');
}
