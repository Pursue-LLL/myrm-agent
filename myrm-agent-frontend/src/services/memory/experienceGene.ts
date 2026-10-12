/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Causal Experience Gene Synthesizer and Confidence Evolution Ledger DTOs and API clients:
 * - listExperienceGenes
 * - getExperienceGeneStats
 * - queryGeneMutationAdvice
 * - penalizeExperienceGene
 * - extractCausalGenes
 *
 * [POS]
 * Frontend API client for Causal Experience Genes, cross-task self-evolution, and Darwinian confidence ledger.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export type GenePolarityKind = 'positive' | 'negative' | string;

export interface ExecutionStepInput {
  step_index: number;
  tool_name: string;
  tool_input_summary: string;
  tool_output_snippet?: string;
  is_failure?: boolean;
  error_signature?: string;
}

export interface MultiTurnTraceInput {
  session_id: string;
  task_goal: string;
  steps: ExecutionStepInput[];
  success_verified?: boolean;
  final_solution_summary?: string;
  domain_tag?: string;
}

export interface ExperienceGeneResponse {
  gene_id: string;
  trigger_signals: string[];
  hypotheses_refuted: string[];
  proven_resolution: string;
  polarity: GenePolarityKind;
  confidence_score: number;
  proof_count: number;
  provenance_session_id: string;
  tags: string[];
  created_at: number;
  updated_at: number;
}

export interface ExtractGeneRequest {
  trace: MultiTurnTraceInput;
}

export interface ExtractGeneResponse {
  status: string;
  gene?: ExperienceGeneResponse | null;
  reinforced: boolean;
}

export interface GeneAdviceRequest {
  active_signals: string[];
  min_confidence?: number;
  limit?: number;
}

export interface GeneMutationAdviceResponse {
  gene_id: string;
  matched_signals: string[];
  refuted_paths: string[];
  recommended_resolution: string;
  confidence: number;
  polarity: GenePolarityKind;
}

export interface GeneAdviceListResponse {
  advices: GeneMutationAdviceResponse[];
  total_matched: number;
}

export interface GenePenalizeRequest {
  gene_id: string;
  penalty?: number;
}

export interface GeneLedgerStatsResponse {
  total_genes: number;
  avg_confidence: number;
  total_proof_count: number;
}

/**
 * List all persistent experience genes tracked in the evolution ledger.
 */
export async function listExperienceGenes(): Promise<ExperienceGeneResponse[]> {
  return apiRequest<ExperienceGeneResponse[]>('/memory/evolution/genes/list', {
    method: 'GET',
  });
}

/**
 * Get summary KPI metrics of the experience gene ledger.
 */
export async function getExperienceGeneStats(): Promise<GeneLedgerStatsResponse> {
  return apiRequest<GeneLedgerStatsResponse>('/memory/evolution/genes/stats', {
    method: 'GET',
  });
}

/**
 * Query actionable planning-stage mutation advice matching active symptoms and dead-ends.
 */
export async function queryGeneMutationAdvice(
  req: GeneAdviceRequest
): Promise<GeneAdviceListResponse> {
  return apiRequest<GeneAdviceListResponse>('/memory/evolution/genes/advice', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Apply confidence penalty when a recommended gene fails in production.
 */
export async function penalizeExperienceGene(
  req: GenePenalizeRequest
): Promise<ExperienceGeneResponse | null> {
  return apiRequest<ExperienceGeneResponse | null>('/memory/evolution/genes/penalize', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/**
 * Extract and reinforce causal experience genes from a multi-turn task trace.
 */
export async function extractCausalGenes(
  req: ExtractGeneRequest
): Promise<ExtractGeneResponse> {
  return apiRequest<ExtractGeneResponse>('/memory/evolution/genes/extract', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
