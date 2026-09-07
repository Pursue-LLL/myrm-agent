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

export type ProviderBalanceStatus = 'healthy' | 'warning' | 'critical' | 'unsupported';

export interface ProviderBalanceGauge {
  provider_id: string;
  balance: number | null;
  currency: string;
  status: ProviderBalanceStatus;
  is_estimated: boolean;
  details?: string | null;
  updated_at: string;
}

export async function fetchProviderBalanceGauges(forceRefresh = false): Promise<ProviderBalanceGauge[]> {
  const query = forceRefresh ? '?force_refresh=true' : '';
  const response = await fetch(`${getBackendUrl()}/api/v1/providers/balance-gauges${query}`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch provider balance gauges: ${response.statusText}`);
  }

  const resJson = await response.json();
  return (resJson.data || []) as ProviderBalanceGauge[];
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
