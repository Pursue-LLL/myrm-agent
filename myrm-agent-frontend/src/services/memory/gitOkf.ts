/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Git-Native OKF v0.2 Knowledge Bundle & Memory Rot Prevention DTOs and API clients:
 * - loadOkfBundle (Loads and indexes OKF v0.2 bundle from filesystem directory)
 * - searchOkfConcepts (Executes sub-millisecond in-memory BM25 lexical search)
 * - validateOkfBundle (Audits bundle conformance, stale_after shelf life, and anti-tamper trust)
 * - getOkfDisclosureSummary (Phase 1 lightweight progressive disclosure card <300 tokens)
 * - getOkfConceptDetail (Phase 2 full concept markdown content and metadata inspection)
 *
 * [POS]
 * Frontend API service for Topic 01 Item 95 (Git-Native Project Knowledge Bundle
 * and Memory Rot Prevention Suite).
 * Strict typing applied: No `any` types allowed. Single file < 250 lines.
 */

import { apiRequest } from '@/lib/api';

export interface LoadBundleRequestDTO {
  bundle_path: string;
}

export interface LoadBundleResponseDTO {
  bundle_path: string;
  loaded_concepts_count: number;
  is_success: boolean;
}

export interface OKFSearchRequestDTO {
  query: string;
  limit?: number;
  filter_governance?: string;
  filter_status?: string;
}

export interface OKFSearchResultDTO {
  concept_id: string;
  title: string;
  type: string;
  description: string;
  governance: string;
  score: number;
  matched_fields: string[];
  tags: string[];
  code_refs: string[];
  is_stale: boolean;
}

export interface OKFConceptDetailDTO {
  id: string;
  path: string;
  type: string;
  title: string;
  description: string;
  governance: string;
  status: string;
  stale_after: string;
  code_refs: string[];
  tags: string[];
  body: string;
  is_stale: boolean;
}

export interface OKFValidationReportDTO {
  bundle_path: string;
  declared_version: string;
  concept_count: number;
  errors: string[];
  warnings: string[];
  gate_findings: string[];
  stale_count: number;
  superseded_trust_count: number;
  is_conformant: boolean;
  gate_passed: boolean;
}

export interface ConceptSummaryItemDTO {
  id: string;
  title: string;
  description: string;
  governance: string;
  status: string;
  is_stale: boolean;
  code_refs: string[];
}

export interface OKFDisclosureSummaryDTO {
  bundle_path: string;
  total_concepts: number;
  stale_count: number;
  concepts: ConceptSummaryItemDTO[];
}

/**
 * Loads and indexes an OKF v0.2 knowledge bundle from the filesystem.
 */
export async function loadOkfBundle(
  request: LoadBundleRequestDTO
): Promise<LoadBundleResponseDTO> {
  return apiRequest<LoadBundleResponseDTO>('/memory/git-okf/bundle/load', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Executes sub-millisecond in-memory BM25 lexical search over loaded concepts.
 */
export async function searchOkfConcepts(
  request: OKFSearchRequestDTO
): Promise<OKFSearchResultDTO[]> {
  return apiRequest<OKFSearchResultDTO[]>('/memory/git-okf/concepts/search', {
    method: 'POST',
    body: JSON.stringify({
      query: request.query,
      limit: request.limit ?? 10,
      filter_governance: request.filter_governance || undefined,
      filter_status: request.filter_status || undefined,
    }),
  });
}

/**
 * Runs full OKF v0.2 conformance, memory rot (stale_after), and anti-tamper trust audit.
 */
export async function validateOkfBundle(): Promise<OKFValidationReportDTO> {
  return apiRequest<OKFValidationReportDTO>('/memory/git-okf/validate', {
    method: 'POST',
  });
}

/**
 * Retrieves first-phase lightweight progressive disclosure summary (<300 tokens footprint).
 */
export async function getOkfDisclosureSummary(): Promise<OKFDisclosureSummaryDTO> {
  return apiRequest<OKFDisclosureSummaryDTO>('/memory/git-okf/disclosure/summary');
}

/**
 * Retrieves complete concept markdown content and metadata for phase-two deep inspection.
 */
export async function getOkfConceptDetail(
  conceptId: string
): Promise<OKFConceptDetailDTO> {
  return apiRequest<OKFConceptDetailDTO>(
    `/memory/git-okf/concepts/${encodeURIComponent(conceptId)}`
  );
}
