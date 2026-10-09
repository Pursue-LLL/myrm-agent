/**
 * Conclusion Attribution and Verifiable Chat Evidence API service.
 * Connects frontend views to backend bidirectional causality tree traversals,
 * ripple impact assessment, and on-demand grounding evidence packages.
 */

import { apiClient } from '@/services/api';

export type AttributionLevel = 'explicit' | 'deductive' | 'inductive' | 'contradiction';

export interface AttributedConclusionDTO {
  id: string;
  peer_id: string;
  content: string;
  level: AttributionLevel | string;
  source_ids: string[];
  times_derived: number;
  session_id?: string | null;
  confidence: number;
  created_at: string;
  updated_at?: string | null;
  metadata?: Record<string, string>;
}

export interface MessageReferenceDTO {
  message_id: string;
  session_id: string;
  role: string;
  snippet: string;
  timestamp?: string | null;
}

export interface ToolCallRecordDTO {
  tool_name: string;
  tool_input: Record<string, string>;
  tool_output_snippet: string;
}

export interface ChatEvidenceDTO {
  conclusions: AttributedConclusionDTO[];
  messages: MessageReferenceDTO[];
  tool_calls: ToolCallRecordDTO[];
  reasoning_trace_id?: string | null;
}

export interface GraphTraversalNodeDTO {
  conclusion: AttributedConclusionDTO;
  depth: number;
  direct_parent_ids: string[];
  direct_child_ids: string[];
}

export interface CreateConclusionRequest {
  peer_id: string;
  content: string;
  level?: AttributionLevel | string;
  source_ids?: string[];
  session_id?: string | null;
  confidence?: number;
  metadata?: Record<string, string>;
}

export interface CreateConclusionResponse {
  conclusion: AttributedConclusionDTO;
  status: string;
}

export interface ListConclusionsResponse {
  items: AttributedConclusionDTO[];
  total: number;
  page: number;
  size: number;
}

export interface TraverseTreeResponse {
  root_id: string;
  direction: 'downward' | 'upward';
  nodes: GraphTraversalNodeDTO[];
  total_nodes: number;
}

export interface RippleImpactResponse {
  target_conclusion_id: string;
  impacted_conclusion_ids: string[];
  depth_reached: number;
  severity: 'low' | 'medium' | 'high' | 'critical';
  explanation: string;
}

export interface ChatWithEvidenceRequest {
  query: string;
  peer_id: string;
  session_id?: string | null;
  include_evidence?: boolean;
}

export interface ChatWithEvidenceResponse {
  reply: string;
  evidence?: ChatEvidenceDTO | null;
}

export interface AttributionMetricsResponse {
  total_conclusions: number;
  explicit_count: number;
  deductive_count: number;
  inductive_count: number;
  contradiction_count: number;
  max_derivation_depth: number;
  average_times_derived: number;
}

export const conclusionAttributionApi = {
  /** Create an attributed conclusion */
  createConclusion: async (payload: CreateConclusionRequest): Promise<CreateConclusionResponse> => {
    return apiClient.post('/api/memory/attribution/conclusions', payload);
  },

  /** List conclusions with pagination and filters */
  listConclusions: async (params?: {
    peer_id?: string;
    session_id?: string;
    level?: string;
    reverse?: boolean;
    page?: number;
    size?: number;
  }): Promise<ListConclusionsResponse> => {
    return apiClient.get('/api/memory/attribution/conclusions', { params });
  },

  /** Query conclusions via keyword/semantic match */
  queryConclusions: async (payload: {
    query: string;
    peer_id?: string;
    level?: string;
    top_k?: number;
  }): Promise<{ items: AttributedConclusionDTO[]; total: number }> => {
    return apiClient.post('/api/memory/attribution/query', payload);
  },

  /** Walk downwards from conclusion to explicit premises */
  walkDownwardTree: async (conclusionId: string, maxDepth = 15): Promise<TraverseTreeResponse> => {
    return apiClient.get(`/api/memory/attribution/tree/downward/${conclusionId}`, {
      params: { max_depth: maxDepth },
    });
  },

  /** Walk upwards from premise to derived conclusions */
  walkUpwardTree: async (premiseId: string, maxDepth = 15): Promise<TraverseTreeResponse> => {
    return apiClient.get(`/api/memory/attribution/tree/upward/${premiseId}`, {
      params: { max_depth: maxDepth },
    });
  },

  /** Evaluate ripple effects of modifying or deleting a premise */
  getRippleImpact: async (conclusionId: string): Promise<RippleImpactResponse> => {
    return apiClient.get(`/api/memory/attribution/impact/${conclusionId}`);
  },

  /** Delete a conclusion */
  deleteConclusion: async (
    conclusionId: string,
    cascade = false,
  ): Promise<{ deleted_ids: string[]; cascade: boolean; status: string }> => {
    return apiClient.delete(`/api/memory/attribution/conclusions/${conclusionId}`, {
      params: { cascade },
    });
  },

  /** Ask a question and obtain transparent ChatEvidence */
  chatWithEvidence: async (payload: ChatWithEvidenceRequest): Promise<ChatWithEvidenceResponse> => {
    return apiClient.post('/api/memory/attribution/chat', payload);
  },

  /** Get telemetry metrics */
  getStats: async (peerId?: string): Promise<AttributionMetricsResponse> => {
    return apiClient.get('/api/memory/attribution/stats', {
      params: peerId ? { peer_id: peerId } : undefined,
    });
  },
};
