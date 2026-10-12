/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Hybrid Vector and Knowledge Graph Reciprocal Rank Fusion (RRF) DTOs and API clients:
 * - createEntityNode
 * - getEntityNode
 * - createRelationEdge
 * - associateMemoryEntity
 * - traverseKnowledgeGraph
 * - searchDualChannelRRF
 *
 * [POS]
 * Frontend API client for hybrid knowledge graph and semantic vector RRF memory retrieval.
 * Strict typing applied: No `any` types allowed.
 */

import { apiRequest } from '@/lib/api';

export interface EntityNodeCreateRequest {
  id: string;
  name: string;
  entity_type: string;
  properties?: Record<string, string>;
}

export interface EntityNodeResponse {
  id: string;
  name: string;
  entity_type: string;
  properties: Record<string, string>;
  created_at: number;
}

export interface RelationEdgeCreateRequest {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  weight?: number;
  properties?: Record<string, string>;
}

export interface RelationEdgeResponse {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  weight: number;
  properties: Record<string, string>;
  created_at: number;
}

export interface MemoryAssociationRequest {
  memory_id: string;
  entity_id: string;
  content?: string;
}

export interface GraphTraversalPath {
  source_id: string;
  target_id: string;
  relation_type: string;
  depth: number;
}

export interface GraphTraverseRequest {
  seed_entity_ids: string[];
  max_hops?: number;
  allowed_relations?: string[] | null;
}

export interface GraphTraverseResponse {
  nodes: EntityNodeResponse[];
  edges: RelationEdgeResponse[];
  paths: GraphTraversalPath[];
  associated_memory_ids: string[];
}

export interface VectorHitInput {
  memory_id: string;
  content?: string;
  score?: number;
  rank: number;
}

export interface DualChannelSearchRequest {
  query: string;
  seed_entity_names?: string[] | null;
  seed_entity_ids?: string[] | null;
  vector_candidates?: VectorHitInput[] | null;
  top_k?: number;
  k?: number;
  vector_weight?: number;
  graph_weight?: number;
  max_graph_hops?: number;
}

export interface FusedMemoryHitResponse {
  memory_id: string;
  content: string;
  fused_score: number;
  vector_rank: number | null;
  graph_rank: number | null;
  hit_sources: string[];
  explanation: Record<string, string | number | string[]>;
}

export interface DualChannelSearchResponse {
  results: FusedMemoryHitResponse[];
  total_hits: number;
  query: string;
}

export const createEntityNode = async (
  request: EntityNodeCreateRequest,
): Promise<EntityNodeResponse> => {
  return apiRequest<EntityNodeResponse>('/memory/graph-rrf/nodes', {
    method: 'POST',
    body: JSON.stringify(request),
  });
};

export const getEntityNode = async (
  nodeId: string,
): Promise<EntityNodeResponse> => {
  return apiRequest<EntityNodeResponse>(`/memory/graph-rrf/nodes/${encodeURIComponent(nodeId)}`, {
    method: 'GET',
  });
};

export const createRelationEdge = async (
  request: RelationEdgeCreateRequest,
): Promise<RelationEdgeResponse> => {
  return apiRequest<RelationEdgeResponse>('/memory/graph-rrf/edges', {
    method: 'POST',
    body: JSON.stringify(request),
  });
};

export const associateMemoryEntity = async (
  request: MemoryAssociationRequest,
): Promise<{ status: string; memory_id: string; entity_id: string }> => {
  return apiRequest<{ status: string; memory_id: string; entity_id: string }>('/memory/graph-rrf/associate', {
    method: 'POST',
    body: JSON.stringify(request),
  });
};

export const traverseKnowledgeGraph = async (
  request: GraphTraverseRequest,
): Promise<GraphTraverseResponse> => {
  return apiRequest<GraphTraverseResponse>('/memory/graph-rrf/traverse', {
    method: 'POST',
    body: JSON.stringify(request),
  });
};

export const searchDualChannelRRF = async (
  request: DualChannelSearchRequest,
): Promise<DualChannelSearchResponse> => {
  return apiRequest<DualChannelSearchResponse>('/memory/graph-rrf/search', {
    method: 'POST',
    body: JSON.stringify(request),
  });
};
