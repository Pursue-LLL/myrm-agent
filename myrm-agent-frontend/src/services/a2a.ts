/**
 * A2A Agent integration API service.
 *
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * A2A Agent API DTOs and request helpers for managing third-party A2A agent connections.
 *
 * [POS]
 * Frontend A2A Agent API client. Typed HTTP contracts for adding, listing,
 * removing, and refreshing third-party A2A agent connections.
 */

import { apiRequest } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface A2AAgentListItem {
  id: string;
  base_url: string;
  name: string;
  description: string;
  version: string;
  skills_count: number;
  healthy: boolean;
  added_at: string;
}

export interface AddA2AAgentResponse {
  id: string;
  name: string;
  description: string;
  version: string;
  skills_count: number;
  base_url: string;
}

export interface RefreshA2AAgentResponse {
  id: string;
  name: string;
  description: string;
  version: string;
  skills_count: number;
  updated: boolean;
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

export async function listA2AAgents(): Promise<A2AAgentListItem[]> {
  return apiRequest<A2AAgentListItem[]>('/integrations/a2a/list');
}

export async function addA2AAgent(baseUrl: string): Promise<AddA2AAgentResponse> {
  return apiRequest<AddA2AAgentResponse>('/integrations/a2a/add', {
    method: 'POST',
    body: JSON.stringify({ base_url: baseUrl }),
  });
}

export async function removeA2AAgent(agentId: string): Promise<{ removed: boolean }> {
  return apiRequest<{ removed: boolean }>(`/integrations/a2a/${agentId}`, {
    method: 'DELETE',
  });
}

export async function refreshA2AAgent(agentId: string): Promise<RefreshA2AAgentResponse> {
  return apiRequest<RefreshA2AAgentResponse>(`/integrations/a2a/${agentId}/refresh`, {
    method: 'POST',
  });
}
