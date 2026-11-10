import { apiRequest } from '@/lib/api';

export type ReadinessLevel = 'ready' | 'warning' | 'blocked';

export interface AgentReadinessItem {
  dimension: string;
  level: ReadinessLevel;
  /** Stable finding identifier; the interface localizes it. `reason` and `next_action` are English diagnostics. */
  code: string;
  reason: string;
  next_action: string;
  settings_path: string;
  /** Connector names or secret keys the finding refers to. */
  names: string[];
  /** How many things are affected (skills are counted, not named). */
  count: number;
}

export interface AgentReadinessReport {
  overall_level: ReadinessLevel;
  items: AgentReadinessItem[];
  agent_id: string;
  checked_at: number;
}

export async function getAgentReadiness(agentId: string): Promise<AgentReadinessReport> {
  return apiRequest<AgentReadinessReport>(`/user-agents/${agentId}/readiness`, {
    method: 'GET',
    silent: true,
  });
}

/** SWR cache key for per-agent readiness — shared by the poller and secret-save invalidation. */
export const READINESS_SWR_KEY_PREFIX = 'agent-readiness:';

export async function invalidateAgentReadiness(agentId: string): Promise<void> {
  await apiRequest(`/user-agents/${agentId}/readiness/invalidate`, {
    method: 'POST',
    silent: true,
  });
}
