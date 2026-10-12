/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: RetrievalChannelKindEnum, ReasonerDecisionKindEnum, ParsedTaskGoalDTO,
 *        RerankedMemoryHitDTO, QuadrupleSearchRequest, QuadrupleSearchResponse,
 *        ParseGoalRequest, ParseGoalResponse, QuadrupleRetrievalStatsDTO
 * Functions: fetchQuadrupleRetrievalStats, executeQuadrupleSearch, parseRetrievalGoal
 *
 * [POS]
 * Client service for Item 127 Goal-Driven Quadruple Retrieval & Reasoner Suite.
 * Aligns strictly with server /memory/retrieval/quadruple/* endpoints.
 * Strict typing applied: Zero `any` types allowed. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export type RetrievalChannelKindEnum = 'graph' | 'vector' | 'lexical' | 'metadata';

export type ReasonerDecisionKindEnum = 'keep' | 'suppress' | 'boost' | 'penalize_stale';

export interface ParsedTaskGoalDTO {
  goal_id: string;
  original_query: string;
  explicit_intent: string;
  target_entities: string[];
  extracted_keywords: string[];
  metadata_filters: Record<string, string>;
  temporal_constraints?: string | null;
  confidence: number;
}

export interface RerankedMemoryHitDTO {
  memory_id: string;
  content: string;
  final_rank: number;
  final_score: number;
  channels_hit: RetrievalChannelKindEnum[];
  reasoner_decision: ReasonerDecisionKindEnum;
  rationale: string;
  metadata: Record<string, string>;
}

export interface QuadrupleSearchRequest {
  query: string;
  top_k?: number;
}

export interface QuadrupleSearchResponse {
  query: string;
  parsed_goal: ParsedTaskGoalDTO;
  channel_hits_count: Record<string, number>;
  fused_candidates_count: number;
  final_hits: RerankedMemoryHitDTO[];
  latency_ms: number;
  created_at: string;
}

export interface ParseGoalRequest {
  query: string;
}

export interface ParseGoalResponse {
  parsed_goal: ParsedTaskGoalDTO;
}

export interface QuadrupleRetrievalStatsDTO {
  total_indexed_memories: number;
  active_channels_count: number;
  average_latency_ms: number;
  channel_weights: Record<string, number>;
}

/**
 * Fetch health stats and channel weights for the quadruple parallel retrieval engine.
 */
export async function fetchQuadrupleRetrievalStats(): Promise<QuadrupleRetrievalStatsDTO> {
  return apiRequest<QuadrupleRetrievalStatsDTO>('/memory/retrieval/quadruple/stats', {
    method: 'GET',
  });
}

/**
 * Execute end-to-end quadruple parallel search with goal parsing and reasoner reranking.
 */
export async function executeQuadrupleSearch(
  payload: QuadrupleSearchRequest
): Promise<QuadrupleSearchResponse> {
  return apiRequest<QuadrupleSearchResponse>('/memory/retrieval/quadruple/search', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Execute isolated pre-retrieval goal parsing to preview deconstructed constraints.
 */
export async function parseRetrievalGoal(
  payload: ParseGoalRequest
): Promise<ParseGoalResponse> {
  const parsedGoal = await apiRequest<ParsedTaskGoalDTO>(
    `/memory/retrieval/quadruple/parse-goal?query=${encodeURIComponent(payload.query)}`,
    { method: 'POST' }
  );
  return { parsed_goal: parsedGoal };
}
