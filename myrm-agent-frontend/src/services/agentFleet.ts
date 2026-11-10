import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { throwUserAgentFetchError } from './agentFetchError';

export interface AgentFleetStats {
  sessionCount: number;
  monthTokens: number;
  monthCost: number;
  cronCount: number;
  pendingApprovals: number;
  status: 'busy' | 'idle';
}

export interface FleetKPI {
  onlineAgents: number;
  monthTokens: number;
  monthCost: number;
  pendingApprovals: number;
}

export interface FleetOverviewResponse {
  kpi: FleetKPI;
  agents: Record<string, AgentFleetStats>;
}

export interface ActiveSession {
  chatId: string;
  agentId: string | null;
  agentType: string;
  agentName: string | null;
  elapsedSeconds: number;
}

export interface RecentSession {
  chatId: string;
  title: string | null;
  agentId: string | null;
  agentName: string | null;
  updatedAt: string;
}

/** 工位帷幕状态（仅 Tauri 桌面端上报；非桌面端 available=false）。 */
export interface CurtainStatus {
  available: boolean;
  active: boolean;
}

export interface ActiveSessionsResponse {
  activeSessions: ActiveSession[];
  recentSessions: RecentSession[];
  maxConcurrent: number;
  availableSlots: number;
  /** 移动端 hub 附带：本机工位帷幕状态（无人值守时手机可见「屏幕已保护」）。 */
  curtain?: CurtainStatus;
}

export async function getFleetOverview(): Promise<FleetOverviewResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/fleet-overview`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'fetch fleet overview');
  }

  const json = await response.json();
  return json.data;
}

export interface GovernanceAgentRow {
  id: string;
  name: string;
  built_in: boolean;
  agent_type: string;
  skill_ids: string[];
  tools: string[];
  subagent_ids: string[];
  responsibility_scope: string | null;
  owner_label: string | null;
  acceptance_criteria: string[];
  sessions_90d: number;
  last_used: string | null;
  active_crons: number;
  channel_bound: boolean;
  team_member: boolean;
}

export interface GovernanceOverlap {
  agent_a: { id: string; name: string };
  agent_b: { id: string; name: string };
  shared_skills: string[];
  shared_tools: string[];
}

export interface GovernanceOverview {
  total: number;
  needs_attention: boolean;
  agents: GovernanceAgentRow[];
  orphans: { id: string; name: string; reason: string }[];
  overlaps: GovernanceOverlap[];
}

export async function getGovernanceOverview(): Promise<GovernanceOverview> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/governance/overview`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'fetch governance overview');
  }

  const json = await response.json();
  return json.data;
}

export interface MergeDryRun {
  ok: boolean;
  reason?: string;
  source?: { id: string; name: string };
  target?: { id: string; name: string };
  plan?: {
    move_skills: string[];
    move_subagents: string[];
    keep_tools_note: string;
    conflicts: string[];
  };
  affected?: {
    cron_jobs: number;
    cron_names?: string[];
    cron_truncated?: boolean;
    channel_bound: boolean;
    channel_topics?: string[];
    channel_truncated?: boolean;
    kanban_note: string;
  };
}

export interface MergeExecuteResult {
  ok: boolean;
  reason?: string;
  steps?: { step: string; ok: boolean; count?: number; snapshot_id?: string | null; reason?: string }[];
  undo?: { rollback: string };
}

export async function mergeDryRun(sourceId: string, targetId: string): Promise<MergeDryRun> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/governance/merge/dry-run`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ source_id: sourceId, target_id: targetId }),
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'preview agent merge');
  }

  const json = await response.json();
  return json.data;
}

export async function mergeExecute(
  sourceId: string,
  targetId: string,
  confirmName: string,
  options?: { move_skills?: boolean; move_subagents?: boolean; move_bindings?: boolean },
): Promise<MergeExecuteResult> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/governance/merge/execute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      source_id: sourceId,
      target_id: targetId,
      confirm_name: confirmName,
      move_skills: options?.move_skills ?? true,
      move_subagents: options?.move_subagents ?? true,
      move_bindings: options?.move_bindings ?? true,
    }),
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'execute agent merge');
  }

  const json = await response.json();
  return json.data;
}

export async function getActiveSessions(): Promise<ActiveSessionsResponse> {
  const response = await fetch(`${getBackendUrl()}/api/v1/agents/active-sessions`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    await throwUserAgentFetchError(response, 'fetch active sessions');
  }

  const json = await response.json();
  return json.data;
}
