/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 *
 * [OUTPUT]
 * - AgentState: Runtime status enum ('working' | 'ready' | 'waiting_input' | 'idle' | 'error')
 * - SessionNode: Representation of a chat session in the topology graph
 * - ProjectCluster: Project boundary grouping sessions with isolated workspace path & repo
 * - FleetCockpitSummary: Aggregate metrics for hundreds of concurrent agents
 * - SessionSearchHit / SessionSearchResponse: Instant multi-attribute search results
 * - fetchSessionMapProjects: Async query for project topology
 * - fetchFleetCockpitSummary: Async query for cockpit fleet statistics
 * - searchSessionMap: Async search across projects and session nodes
 *
 * [POS]
 * Client service layer for Project-Centric Session Map and Agent State Cockpit View.
 * Single file < 120 lines. Zero `any` types.
 */

import { apiClient } from './api';

export type AgentState = 'working' | 'ready' | 'waiting_input' | 'idle' | 'error';

export interface SessionNode {
  id: string;
  title: string;
  project_id?: string;
  agent_id?: string;
  agent_name: string;
  state: AgentState;
  current_task?: string;
  tokens_used: number;
  last_active_at: string;
  tags: string[];
  workspace_dir?: string;
  match_highlights?: string[];
}

export interface ProjectCluster {
  id: string;
  name: string;
  description: string;
  color: string;
  workspace_path?: string;
  git_repo_url?: string;
  sessions: SessionNode[];
  active_agent_count: number;
  total_tokens: number;
}

export interface FleetCockpitSummary {
  total_projects: number;
  total_sessions: number;
  total_agents: number;
  working_agents: number;
  ready_agents: number;
  waiting_input_agents: number;
  error_agents: number;
  total_tokens_consumed: number;
  top_active_sessions: SessionNode[];
}

export interface SessionSearchHit {
  session: SessionNode;
  project_name: string;
  relevance_score: number;
  matched_snippet: string;
}

export interface SessionSearchResponse {
  query: string;
  total_hits: number;
  hits: SessionSearchHit[];
}

const SESSION_MAP_BASE = '/api/v1/session-map';

export async function fetchSessionMapProjects(
  stateFilter?: AgentState,
): Promise<ProjectCluster[]> {
  const query = stateFilter ? `?state_filter=${encodeURIComponent(stateFilter)}` : '';
  return apiClient.get<ProjectCluster[]>(`${SESSION_MAP_BASE}/projects${query}`);
}

export async function fetchFleetCockpitSummary(): Promise<FleetCockpitSummary> {
  return apiClient.get<FleetCockpitSummary>(`${SESSION_MAP_BASE}/cockpit`);
}

export async function searchSessionMap(
  query: string,
  projectId?: string,
  state?: AgentState,
): Promise<SessionSearchResponse> {
  return apiClient.post<SessionSearchResponse>(`${SESSION_MAP_BASE}/search`, {
    query,
    project_id: projectId,
    state,
  });
}
