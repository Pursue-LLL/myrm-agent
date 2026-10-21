/**
 * [INPUT]
 * API client endpoints: /memory/two-layer-dialectic/*
 *
 * [OUTPUT]
 * Types & client methods for Two-Layer Context Injection & Multi-Pass Dialectic Reconciliation Suite (Item 112).
 *
 * [POS]
 * Domain service client for Item 112.
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export interface DialecticConflictCandidateDTO {
  statement_a: string;
  statement_b: string;
  subject_domain: string;
  conflict_score: number;
}

export interface DialecticReconciliationResultDTO {
  passes_executed: string[];
  resolved_statement: string;
  superseded_statements: string[];
  confidence: number;
  rationale: string;
}

export interface BaseContextPayloadDTO {
  session_summary: string;
  standing_peer_cards: string[];
  cache_control_hash: string;
  refreshed_at_turn: number;
  created_at: string;
}

export interface TwoLayerContextInjectionResultDTO {
  layer1_base_context: string;
  layer2_dialectic_block: string;
  injected_position: string;
  is_cache_safe: boolean;
  token_overhead: number;
}

export interface DialecticInspectRequest {
  statements: string[];
  cutoff?: number;
}

export interface DialecticReconcileRequest {
  statements: string[];
  depth?: number;
}

export interface AssembleInjectionRequest {
  session_id: string;
  turn: number;
  session_summary: string;
  peer_cards?: string[];
  candidate_memories?: string[];
  context_cadence?: number;
  dialectic_cadence?: number;
  force_refresh_base?: boolean;
  force_dialectic?: boolean;
}

export interface DialecticCadenceConfigDTO {
  context_cadence: number;
  dialectic_cadence: number;
  dialectic_depth: number;
  dialectic_reasoning_level: 'fast' | 'standard' | 'deep';
}

export async function inspectDialecticConflicts(
  request: DialecticInspectRequest,
): Promise<DialecticConflictCandidateDTO[]> {
  const res = await apiRequest<DialecticConflictCandidateDTO[]>('/memory/two-layer-dialectic/inspect', {
    method: 'POST',
    body: JSON.stringify(request),
  });
  return res || [];
}

export async function reconcileDialecticConflicts(
  request: DialecticReconcileRequest,
): Promise<DialecticReconciliationResultDTO[]> {
  const res = await apiRequest<DialecticReconciliationResultDTO[]>('/memory/two-layer-dialectic/reconcile', {
    method: 'POST',
    body: JSON.stringify(request),
  });
  return res || [];
}

export async function assembleTwoLayerInjection(
  request: AssembleInjectionRequest,
): Promise<TwoLayerContextInjectionResultDTO> {
  return await apiRequest<TwoLayerContextInjectionResultDTO>('/memory/two-layer-dialectic/assemble', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function getBaseContextCache(sessionId: string): Promise<BaseContextPayloadDTO | null> {
  try {
    return await apiRequest<BaseContextPayloadDTO>(
      `/memory/two-layer-dialectic/cache/${encodeURIComponent(sessionId)}`,
      { method: 'GET' },
    );
  } catch {
    return null;
  }
}

export async function resetSessionCadence(sessionId: string): Promise<boolean> {
  try {
    const res = await apiRequest<{ ok: boolean }>(
      `/memory/two-layer-dialectic/reset/${encodeURIComponent(sessionId)}`,
      { method: 'POST' },
    );
    return res?.ok ?? false;
  } catch {
    return false;
  }
}
