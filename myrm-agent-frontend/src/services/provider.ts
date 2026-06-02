import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';

export interface AgentSummary {
  id: string;
  name: string;
  model: string | null;
}

export interface ProviderUsageResponse {
  has_usage: boolean;
  count: number;
  agents: AgentSummary[];
}

export interface BatchMigrateRequest {
  from_provider_id: string;
  to_provider_id: string;
  to_model: string;
  preview?: boolean;
}

export interface BatchMigratePreviewResponse {
  affected_count: number;
  affected_agents: Array<{
    id: string;
    name: string;
    current_model: string;
    new_model: string;
  }>;
}

export interface BatchMigrateResponse {
  updated_count: number;
}

export async function getProviderUsage(providerId: string): Promise<ProviderUsageResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/providers/${providerId}/usage`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to get provider usage: ${response.statusText}`);
  }

  return response.json();
}

export async function clearProviderUsage(providerId: string): Promise<void> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/providers/${providerId}/clear-usage`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to clear provider usage: ${response.statusText}`);
  }
}

export async function batchMigrateProvider(data: BatchMigrateRequest): Promise<BatchMigrateResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/providers/batch-migrate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`Failed to batch migrate provider: ${response.statusText}`);
  }

  return response.json();
}

export async function previewBatchMigrateProvider(
  data: Omit<BatchMigrateRequest, 'preview'>,
): Promise<BatchMigratePreviewResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/providers/batch-migrate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ ...data, preview: true }),
  });

  if (!response.ok) {
    throw new Error(`Failed to preview batch migrate: ${response.statusText}`);
  }

  return response.json();
}
