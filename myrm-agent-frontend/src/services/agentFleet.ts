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
