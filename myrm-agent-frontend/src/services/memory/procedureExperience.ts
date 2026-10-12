/**
 * [INPUT]
 * @/services/api::apiClient (POS: standard client facade)
 *
 * [OUTPUT]
 * Types and client functions for Item 104:
 * ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite.
 *
 * [POS]
 * Client layer connecting frontend command-center UI to FastAPI backend endpoints.
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import { apiClient } from '@/services/api';

export type RetrievalNodeKind = 'first_user' | 'pre_write';

export interface ProcedureMemoryEntryDTO {
  entry_id: string;
  name: string;
  retrieval_anchor: string;
  operation_intent: string;
  preconditions: string[];
  immutable_boundary: string[];
  procedure_steps: string[];
  write_field_provenance: Record<string, string>;
  anti_patterns: string[];
  applicability: string[];
  negative_applicability: string[];
  confidence: number;
  source_session_id?: string | null;
  created_at?: string | null;
}

export interface RegisterProcedureMemoryRequest {
  entry_id?: string;
  name: string;
  operation_intent: string;
  preconditions: string[];
  immutable_boundary: string[];
  procedure_steps: string[];
  write_field_provenance: Record<string, string>;
  anti_patterns: string[];
  applicability: string[];
  negative_applicability: string[];
  retrieval_anchor?: string;
  confidence?: number;
  source_session_id?: string | null;
}

export interface DualNodeRetrievalRequest {
  query_text: string;
  node_kind?: RetrievalNodeKind;
  top_n?: number;
  scope_filter?: string;
}

export interface DualNodeRetrievalResponseDTO {
  node_kind: string;
  top_n_requested: number;
  total_matched: number;
  matched_entries: ProcedureMemoryEntryDTO[];
}

export interface ProtocolValidationResponseDTO {
  is_valid: boolean;
  violations: string[];
}

export interface MultiIntentSplitRequest {
  raw_text: string;
}

export interface MultiIntentSplitResponseDTO {
  fragment_count: number;
  fragments: Array<{ intent: string; body: string }>;
}

export async function listProcedures(): Promise<ProcedureMemoryEntryDTO[]> {
  return apiClient.get<ProcedureMemoryEntryDTO[]>('/memory/procedure/list');
}

export async function registerProcedure(
  request: RegisterProcedureMemoryRequest
): Promise<ProcedureMemoryEntryDTO> {
  return apiClient.post<ProcedureMemoryEntryDTO>('/memory/procedure/register', request);
}

export async function retrieveDualNode(
  request: DualNodeRetrievalRequest
): Promise<DualNodeRetrievalResponseDTO> {
  const payload = {
    query_text: request.query_text,
    node_kind: request.node_kind ?? 'first_user',
    top_n: request.top_n ?? 2,
    scope_filter: request.scope_filter,
  };
  return apiClient.post<DualNodeRetrievalResponseDTO>('/memory/procedure/retrieve', payload);
}

export async function validateProcedureProtocol(
  request: RegisterProcedureMemoryRequest
): Promise<ProtocolValidationResponseDTO> {
  return apiClient.post<ProtocolValidationResponseDTO>('/memory/procedure/validate', request);
}

export async function splitIntents(rawText: string): Promise<MultiIntentSplitResponseDTO> {
  return apiClient.post<MultiIntentSplitResponseDTO>('/memory/procedure/split-intents', {
    raw_text: rawText,
  });
}

export async function getProcedure(entryId: string): Promise<ProcedureMemoryEntryDTO> {
  return apiClient.get<ProcedureMemoryEntryDTO>(`/memory/procedure/${encodeURIComponent(entryId)}`);
}
