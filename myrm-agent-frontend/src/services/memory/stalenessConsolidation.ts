/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Staleness Consolidation DTOs and API clients:
 * - registerMemory: Register memory item for staleness & fact validity tracking
 * - listMemories: Fetch tracked memory items, optionally filtered by status
 * - getMemory: Retrieve single memory record profile
 * - touchMemoryRecall: Record recall event to reset half-life decay and increment count
 * - runMemoryAudit: Conduct comprehensive memory health audit
 * - applyConsolidation: Approve and execute a rule consolidation proposal
 * - archiveMemories: Safely move stale or invalidated memories to archive
 *
 * [POS]
 * Frontend API service for Item 158 AutoMemoryStalenessDecayAndConsolidationAuditSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { apiRequest } from '@/lib/api';

export type MemoryStatus =
  | 'active'
  | 'stale'
  | 'invalidated'
  | 'consolidated'
  | 'archived';

export interface MemoryItemProfileDTO {
  memory_id: string;
  content: string;
  category: string;
  created_at: string;
  last_recalled_at: string;
  recalled_count: number;
  staleness_score: number;
  status: MemoryStatus;
  referenced_paths: string[];
  referenced_assertions: string[];
  invalidation_reason: string | null;
  subsumed_by_id: string | null;
}

export interface RegisterMemoryRequest {
  memory_id: string;
  content: string;
  category?: string;
  created_at?: string;
  referenced_paths?: string[];
  referenced_assertions?: string[];
}

export interface TouchRecallRequest {
  memory_id: string;
  now_iso?: string;
}

export interface RepoAssertionCheckResultDTO {
  memory_id: string;
  is_valid: boolean;
  missing_paths: string[];
  failed_assertions: string[];
  diagnostic: string;
}

export interface ConsolidationProposalDTO {
  proposal_id: string;
  source_memory_ids: string[];
  category: string;
  proposed_content: string;
  rationale: string;
}

export interface MemoryAuditReportDTO {
  total_items: number;
  active_items: number;
  stale_items: number;
  invalidated_items: number;
  consolidated_items: number;
  archived_items: number;
  average_staleness: number;
  invalidated_results: RepoAssertionCheckResultDTO[];
  consolidation_proposals: ConsolidationProposalDTO[];
  generated_at: string;
}

export interface RunAuditRequest {
  workspace_dir?: string;
  now_iso?: string;
}

export interface ApplyConsolidationRequest {
  proposal_id: string;
  now_iso?: string;
}

export interface ArchiveMemoriesRequest {
  memory_ids: string[];
}

export async function registerMemory(
  req: RegisterMemoryRequest
): Promise<MemoryItemProfileDTO> {
  return apiRequest<MemoryItemProfileDTO>('/memory/staleness-consolidation/memories', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function listMemories(
  status?: MemoryStatus
): Promise<MemoryItemProfileDTO[]> {
  const url = status
    ? `/memory/staleness-consolidation/memories?status=${encodeURIComponent(status)}`
    : '/memory/staleness-consolidation/memories';
  return apiRequest<MemoryItemProfileDTO[]>(url, { method: 'GET' });
}

export async function getMemory(
  memoryId: string
): Promise<MemoryItemProfileDTO> {
  return apiRequest<MemoryItemProfileDTO>(
    `/memory/staleness-consolidation/memories/${encodeURIComponent(memoryId)}`,
    { method: 'GET' }
  );
}

export async function touchMemoryRecall(
  req: TouchRecallRequest
): Promise<MemoryItemProfileDTO> {
  return apiRequest<MemoryItemProfileDTO>('/memory/staleness-consolidation/touch-recall', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function runMemoryAudit(
  req: RunAuditRequest
): Promise<MemoryAuditReportDTO> {
  return apiRequest<MemoryAuditReportDTO>('/memory/staleness-consolidation/audit', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function applyConsolidation(
  req: ApplyConsolidationRequest
): Promise<MemoryItemProfileDTO> {
  return apiRequest<MemoryItemProfileDTO>('/memory/staleness-consolidation/consolidate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function archiveMemories(
  req: ArchiveMemoriesRequest
): Promise<string[]> {
  return apiRequest<string[]>('/memory/staleness-consolidation/archive', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
