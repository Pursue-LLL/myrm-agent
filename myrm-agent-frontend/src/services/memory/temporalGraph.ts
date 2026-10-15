/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: Frontend API client transport)
 *
 * [OUTPUT]
 * Temporal Knowledge Graph, Half-Life Decay & Fact Conflict Reconciliation DTOs and API clients:
 * - saveEntityNode, listEntityNodes, deleteEntityNode
 * - saveFactEdge (Atomically inserts fact edge and reconciles mutual exclusion conflicts)
 * - listFactEdges, getEdgeLineage (Evolutionary history lineage traversal)
 * - queryTemporalFacts (Ranked by dynamic exponential half-life decay score)
 * - getTemporalGraphStats (Graph health and recency summary metrics)
 *
 * [POS]
 * Frontend API service for Topic 01 Item 93 (Temporal Knowledge Graph Decay
 * and Entity Fact Conflict Resolution Suite).
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface TemporalEntityNodeDTO {
  node_id: string;
  name: string;
  entity_type: string;
  attributes: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface SaveEntityNodeRequestDTO {
  name: string;
  entity_type?: string;
  attributes?: Record<string, string>;
  node_id?: string;
}

export interface TemporalFactEdgeDTO {
  edge_id: string;
  source_id: string;
  target_id: string;
  predicate: string;
  valid_from: string;
  valid_until: string | null;
  is_superseded: boolean;
  superseded_by: string | null;
  confidence_score: number;
  access_count: number;
  last_accessed_at: string | null;
  created_at: string;
}

export interface SaveFactEdgeRequestDTO {
  source_id: string;
  target_id: string;
  predicate: string;
  confidence_score?: number;
  edge_id?: string;
}

export interface FactConflictResolutionResultDTO {
  new_edge: TemporalFactEdgeDTO;
  superseded_edges: TemporalFactEdgeDTO[];
  is_conflict_detected: boolean;
  conflict_reason: string;
}

export interface TemporalFactHitDTO {
  edge: TemporalFactEdgeDTO;
  source_node: TemporalEntityNodeDTO;
  target_node: TemporalEntityNodeDTO;
  decayed_score: number;
  effective_status: string;
}

export interface TemporalGraphStatsDTO {
  total_nodes_count: number;
  active_edges_count: number;
  superseded_edges_count: number;
  average_decayed_score: number;
}

/**
 * Saves or updates an entity node in the temporal knowledge graph.
 */
export async function saveEntityNode(
  request: SaveEntityNodeRequestDTO
): Promise<TemporalEntityNodeDTO> {
  return apiRequest<TemporalEntityNodeDTO>('/memory/temporal-graph/nodes', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Lists stored entity nodes optionally filtered by classification type.
 */
export async function listEntityNodes(
  entityType?: string,
  limit = 100
): Promise<TemporalEntityNodeDTO[]> {
  const params = new URLSearchParams();
  if (entityType) {
    params.set('entity_type', entityType);
  }
  params.set('limit', String(limit));
  return apiRequest<TemporalEntityNodeDTO[]>(
    `/memory/temporal-graph/nodes?${params.toString()}`
  );
}

/**
 * Deletes an entity node and cascades removal of associated edges.
 */
export async function deleteEntityNode(
  nodeId: string
): Promise<{ deleted: boolean; node_id: string }> {
  return apiRequest<{ deleted: boolean; node_id: string }>(
    `/memory/temporal-graph/nodes/${encodeURIComponent(nodeId)}`,
    {
      method: 'DELETE',
    }
  );
}

/**
 * Inserts a relationship fact edge, automatically reconciling mutual exclusion conflicts.
 */
export async function saveFactEdge(
  request: SaveFactEdgeRequestDTO
): Promise<FactConflictResolutionResultDTO> {
  return apiRequest<FactConflictResolutionResultDTO>('/memory/temporal-graph/edges', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Lists relationship fact edges with optional filtering.
 */
export async function listFactEdges(
  predicate?: string,
  activeOnly = true,
  limit = 100
): Promise<TemporalFactEdgeDTO[]> {
  const params = new URLSearchParams();
  if (predicate) {
    params.set('predicate', predicate);
  }
  params.set('active_only', String(activeOnly));
  params.set('limit', String(limit));
  return apiRequest<TemporalFactEdgeDTO[]>(
    `/memory/temporal-graph/edges?${params.toString()}`
  );
}

/**
 * Traces the backward evolutionary lineage chain of superseded historical edges.
 */
export async function getEdgeLineage(
  edgeId: string
): Promise<TemporalFactEdgeDTO[]> {
  return apiRequest<TemporalFactEdgeDTO[]>(
    `/memory/temporal-graph/edges/${encodeURIComponent(edgeId)}/lineage`
  );
}

/**
 * Queries temporal fact edges ranked by dynamic half-life decay score.
 */
export async function queryTemporalFacts(
  sourceId?: string,
  predicate?: string,
  activeOnly = true,
  limit = 50
): Promise<TemporalFactHitDTO[]> {
  const params = new URLSearchParams();
  if (sourceId) {
    params.set('source_id', sourceId);
  }
  if (predicate) {
    params.set('predicate', predicate);
  }
  params.set('active_only', String(activeOnly));
  params.set('limit', String(limit));
  return apiRequest<TemporalFactHitDTO[]>(
    `/memory/temporal-graph/query?${params.toString()}`
  );
}

/**
 * Fetches summary metrics and average recency decay score for the graph.
 */
export async function getTemporalGraphStats(): Promise<TemporalGraphStatsDTO> {
  return apiRequest<TemporalGraphStatsDTO>('/memory/temporal-graph/stats');
}
