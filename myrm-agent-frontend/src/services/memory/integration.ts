/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Integration Memory API DTOs and request helpers for sync, browse, status operations.
 *
 * [POS]
 * Frontend Integration Memory API client. Typed HTTP contracts for integration memory sync, status, and tree browsing.
 */

import { apiRequest } from '@/lib/api';

// ==================== Types ====================

export interface IntegrationSyncRequest {
  provider_id?: string;
  account_key?: string;
  max_items?: number;
}

export interface IntegrationSyncResult {
  provider: string;
  account_key: string;
  created: number;
  updated: number;
  skipped: number;
  failed: number;
  elapsed_seconds: number;
  errors: string[];
}

export interface IntegrationTreeSummary {
  tree_id: string;
  provider: string;
  account_key: string;
  leaf_count: number;
  root_summary: string;
}

export interface IntegrationStatus {
  providers: string[];
  provider_count: number;
  tree_count: number;
  total_indexed_items: number;
  trees: IntegrationTreeSummary[];
}

export interface IntegrationTreeNode {
  id: string;
  labels: string[];
  properties: Record<string, string | number | boolean>;
}

// ==================== API Functions ====================

export async function syncIntegration(req: IntegrationSyncRequest = {}): Promise<IntegrationSyncResult[]> {
  return apiRequest<IntegrationSyncResult[]>('/integrations/memory/sync', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getIntegrationStatus(): Promise<IntegrationStatus> {
  return apiRequest<IntegrationStatus>('/integrations/memory/status');
}

export async function listIntegrationTrees(provider?: string): Promise<IntegrationTreeSummary[]> {
  const params = provider ? `?provider=${encodeURIComponent(provider)}` : '';
  return apiRequest<IntegrationTreeSummary[]>(`/integrations/memory/trees${params}`);
}

export async function getIntegrationTreeStructure(treeId: string): Promise<IntegrationTreeNode[]> {
  return apiRequest<IntegrationTreeNode[]>(`/integrations/memory/trees/${encodeURIComponent(treeId)}`);
}

export async function removeIntegrationTree(treeId: string): Promise<{ tree_id: string; deleted_elements: number }> {
  return apiRequest<{ tree_id: string; deleted_elements: number }>(
    `/integrations/memory/trees/${encodeURIComponent(treeId)}`,
    {
      method: 'DELETE',
    },
  );
}

export async function listIntegrationProviders(): Promise<{ providers: string[] }> {
  return apiRequest<{ providers: string[] }>('/integrations/memory/providers');
}

export async function countProviderTrees(providerId: string): Promise<number> {
  const trees = await listIntegrationTrees(providerId);
  return trees.length;
}
