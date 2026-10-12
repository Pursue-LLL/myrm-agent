/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Types: LineageRelationTypeEnum, MemoryNodeStatusEnum, MemoryGraphNodeDTO,
 *        MemoryGraphEdgeDTO, LineageStepDTO, MemoryLineageTrailDTO,
 *        ReorganizationBatchRequest, ReorganizationBatchResponse,
 *        LineageRevertRequest, LineageRevertResponse, MemoryTopologyGraphDTO, LineageStatsDTO
 * Functions: triggerReorganizationPass, traceNodeLineage, revertMemoryVersion,
 *            getGraphTopology, getLineageStats
 *
 * [POS]
 * Client service for Item 126 Graph Memory Reorganization & Lineage Traceability Suite.
 * Aligns strictly with server /memory/lineage/* endpoints.
 * Strict typing applied: Zero `any` types allowed. Single file < 200 lines.
 */

import { apiRequest } from '@/lib/api';

export type LineageRelationTypeEnum =
  'subsumption' | 'temporal_sequence' | 'deduction' | 'supersedes' | 'derived_from' | 'contradiction' | 'merged_into';

export type MemoryNodeStatusEnum = 'active' | 'superseded' | 'archived' | 'reverted';

export interface MemoryGraphNodeDTO {
  node_id: string;
  lineage_root_id: string;
  version: number;
  subject: string;
  predicate: string;
  object_value: string;
  content: string;
  confidence: number;
  status: MemoryNodeStatusEnum;
  created_at: string;
  updated_at: string;
  source_session_id?: string | null;
  evidence_quote?: string | null;
  metadata?: Record<string, string>;
}

export interface MemoryGraphEdgeDTO {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relation_type: LineageRelationTypeEnum;
  weight: number;
  rationale: string;
  created_at: string;
}

export interface LineageStepDTO {
  step_index: number;
  node: MemoryGraphNodeDTO;
  relation_to_target?: LineageRelationTypeEnum | null;
  rationale: string;
  timestamp: string;
}

export interface MemoryLineageTrailDTO {
  target_node: MemoryGraphNodeDTO;
  lineage_root_id: string;
  ancestor_nodes: MemoryGraphNodeDTO[];
  descendant_nodes: MemoryGraphNodeDTO[];
  steps: LineageStepDTO[];
  relation_edges: MemoryGraphEdgeDTO[];
  depth: number;
  is_latest: boolean;
}

export interface ReorganizationBatchRequest {
  min_confidence?: number;
}

export interface ReorganizationBatchResponse {
  batch_id: string;
  analyzed_nodes_count: number;
  created_edges_count: number;
  superseded_nodes_count: number;
  deductions_count: number;
  edges: MemoryGraphEdgeDTO[];
  created_at: string;
}

export interface LineageRevertRequest {
  historical_node_id: string;
  rationale?: string;
}

export interface LineageRevertResponse {
  reverted_node: MemoryGraphNodeDTO;
  restored_active_node: MemoryGraphNodeDTO;
}

export interface MemoryTopologyGraphDTO {
  nodes: MemoryGraphNodeDTO[];
  edges: MemoryGraphEdgeDTO[];
}

export interface LineageStatsDTO {
  total_nodes: number;
  active_nodes: number;
  superseded_nodes: number;
  reverted_nodes: number;
  total_edges: number;
  max_depth: number;
}

export async function triggerReorganizationPass(
  req: ReorganizationBatchRequest = {},
): Promise<ReorganizationBatchResponse> {
  return apiRequest<ReorganizationBatchResponse>('/memory/lineage/reorganize', {
    method: 'POST',
    body: JSON.stringify({ min_confidence: req.min_confidence ?? 0.8 }),
  });
}

export async function traceNodeLineage(nodeId: string): Promise<MemoryLineageTrailDTO> {
  return apiRequest<MemoryLineageTrailDTO>(`/memory/lineage/trace/${encodeURIComponent(nodeId)}`, {
    method: 'GET',
  });
}

export async function revertMemoryVersion(req: LineageRevertRequest): Promise<LineageRevertResponse> {
  return apiRequest<LineageRevertResponse>('/memory/lineage/revert', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getGraphTopology(): Promise<MemoryTopologyGraphDTO> {
  return apiRequest<MemoryTopologyGraphDTO>('/memory/lineage/topology', { method: 'GET' });
}

export async function getLineageStats(): Promise<LineageStatsDTO> {
  return apiRequest<LineageStatsDTO>('/memory/lineage/stats', { method: 'GET' });
}
