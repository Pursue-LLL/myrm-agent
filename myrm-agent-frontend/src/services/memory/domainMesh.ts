/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Domain Mesh DTOs and API clients for the three-domain progressive L0/L1/L2 memory view.
 *
 * [POS]
 * Frontend client for the progressive retrieval mesh.
 */

import { apiRequest } from '@/lib/api';

export interface ProgressiveHighlight {
  id: string;
  l0: string;
  l1: string;
  category: string;
  memory_type: string;
  updated_at: string;
}

export interface DomainBucketOverview {
  domain: 'user' | 'assistant' | 'task';
  total_count: number;
  category_counts: Record<string, number>;
  highlights: ProgressiveHighlight[];
}

export interface DomainMeshOverviewResponse {
  user: DomainBucketOverview;
  assistant: DomainBucketOverview;
  task: DomainBucketOverview;
  total_memories: number;
}

export interface DrillDownResponse {
  id: string;
  domain: string;
  category: string;
  memory_type: string;
  l0: string;
  l1: string;
  l2_content: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export const getDomainMeshOverview = async (): Promise<DomainMeshOverviewResponse> => {
  return apiRequest<DomainMeshOverviewResponse>('/memory/domain-mesh/overview');
};

export const getMemoryDrillDown = async (memoryId: string): Promise<DrillDownResponse> => {
  return apiRequest<DrillDownResponse>(`/memory/domain-mesh/drill-down/${encodeURIComponent(memoryId)}`);
};
