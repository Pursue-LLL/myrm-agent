import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { throwUserAgentFetchError } from './agentFetchError';
import { normalizeAgentSecretKeyNames } from './agentFetchErrorCore';

export interface AgentSecretCreate {
  key_name: string;
  secret_value: string;
}

export interface AgentSecretResponse {
  agent_id: string;
  key_name: string;
  created_at: string;
  updated_at: string;
}

/**
 * 获取智能体密钥列表
 */
export async function listAgentSecrets(agentId: string): Promise<string[]> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/secrets`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'list agent secrets');
  }

  const result = await response.json();
  return normalizeAgentSecretKeyNames(result.data);
}

/**
 * 创建或更新智能体密钥
 */
export async function createOrUpdateAgentSecret(
  agentId: string,
  data: AgentSecretCreate,
): Promise<AgentSecretResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/secrets`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'save agent secret');
  }

  const result = await response.json();
  return result.data;
}

/**
 * 删除智能体密钥
 */
export async function deleteAgentSecret(agentId: string, keyName: string): Promise<void> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/secrets/${keyName}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (response.status === 404) {
    return;
  }
  if (!response.ok) {
    await throwUserAgentFetchError(response, 'delete agent secret');
  }
}
