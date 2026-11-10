import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { throwUserAgentFetchError } from './agentFetchError';

export interface AgentProfileSnapshotItem {
  id: string;
  agent_id: string;
  reason: string | null;
  snapshot_data: Record<string, unknown>;
  created_at: string;
}

/**
 * 回滚智能体配置到最近一次快照
 */
export async function rollbackAgentProfile(agentId: string): Promise<void> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/rollback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'rollback agent profile');
  }
}

/**
 * 回滚智能体配置到指定快照
 */
export async function rollbackAgentProfileToSnapshot(agentId: string, snapshotId: string): Promise<void> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/rollback/${snapshotId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'rollback agent profile to snapshot');
  }
}

/**
 * 获取智能体配置快照列表
 */
export async function listAgentSnapshots(agentId: string): Promise<AgentProfileSnapshotItem[]> {
  const response = await fetch(`${getBackendUrl()}/api/v1/user-agents/${agentId}/snapshots`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'list agent snapshots');
  }

  const result = await response.json();
  return result.data as AgentProfileSnapshotItem[];
}
