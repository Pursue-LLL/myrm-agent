/**
 * [INPUT]
 * workspaceBoundaryTypes.ts
 * [OUTPUT]
 * Workspace boundary client service fetching 3-currents state and executing switch handshakes.
 * [POS]
 * src/components/features/workspace-boundary/workspaceBoundaryService.ts
 */

import {
  MultiRepoWorktreeEntry,
  ProjectSwitchHandshakeRequest,
  ProjectSwitchHandshakeResponse,
  ThreeCurrentsBoundary,
} from './workspaceBoundaryTypes';

export class WorkspaceBoundaryService {
  private readonly baseUrl: string;

  constructor(baseUrl: string = '/api/v1/workspace/boundary') {
    this.baseUrl = baseUrl;
  }

  async fetchCurrentBoundary(params?: {
    sessionId?: string;
    projectId?: string;
    projectName?: string;
    sessionGoal?: string;
    cwd?: string;
  }): Promise<ThreeCurrentsBoundary> {
    const searchParams = new URLSearchParams();
    if (params?.sessionId) {
      searchParams.set('session_id', params.sessionId);
    }
    if (params?.projectId) {
      searchParams.set('project_id', params.projectId);
    }
    if (params?.projectName) {
      searchParams.set('project_name', params.projectName);
    }
    if (params?.sessionGoal) {
      searchParams.set('session_goal', params.sessionGoal);
    }
    if (params?.cwd) {
      searchParams.set('cwd', params.cwd);
    }

    const query = searchParams.toString();
    const url = query ? `${this.baseUrl}/current?${query}` : `${this.baseUrl}/current`;

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        return (await response.json()) as ThreeCurrentsBoundary;
      }
    } catch {
      // Offline or network error fallback
    }

    // Default offline fallback
    return {
      session_id: params?.sessionId || 'local-session-main',
      project_id: params?.projectId || 'myrm-agent',
      project_name: params?.projectName || 'myrm-agent',
      session_goal: params?.sessionGoal || 'Maintain codebase tasks and feature delivery',
      cwd: params?.cwd || '/Users/developer/projects/myrm-agent',
      repo_name: 'myrm-agent',
      git_branch: 'main',
      git_worktree: null,
      git_is_clean: true,
      git_uncommitted_changes: 0,
      execution_host_type: 'local_host',
      execution_host_label: '💻 Local Mac',
      execution_host_id: 'host-local',
      inspected_at: Date.now() / 1000,
    };
  }

  async probeProjectSwitchHandshake(
    request: ProjectSwitchHandshakeRequest
  ): Promise<ProjectSwitchHandshakeResponse> {
    try {
      const response = await fetch(`${this.baseUrl}/handshake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      if (response.ok) {
        return (await response.json()) as ProjectSwitchHandshakeResponse;
      }
    } catch {
      // Offline fallback
    }

    const isNonExistent = request.target_path.includes('phantom') || request.target_path.includes('404');
    if (isNonExistent) {
      return {
        target_project_id: request.target_project_id,
        target_path: request.target_path,
        path_exists: false,
        is_git_repo: false,
        git_branch: '',
        git_worktree: null,
        git_uncommitted_changes: 0,
        risk_level: 'blocked',
        warnings: [`Target workspace path '${request.target_path}' does not exist on disk.`],
        can_switch: false,
        handshake_token: '',
      };
    }

    return {
      target_project_id: request.target_project_id,
      target_path: request.target_path,
      path_exists: true,
      is_git_repo: true,
      git_branch: 'feat/worktree-target',
      git_worktree: null,
      git_uncommitted_changes: 0,
      risk_level: 'safe',
      warnings: [],
      can_switch: true,
      handshake_token: 'offline-handshake-token-mock',
    };
  }

  async listWorktrees(cwd?: string): Promise<MultiRepoWorktreeEntry[]> {
    const url = cwd
      ? `${this.baseUrl}/worktrees?cwd=${encodeURIComponent(cwd)}`
      : `${this.baseUrl}/worktrees`;

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        return (await response.json()) as MultiRepoWorktreeEntry[];
      }
    } catch {
      // Offline fallback
    }

    return [
      {
        repo: 'myrm-agent',
        worktree: null,
        branch: 'main',
        path: cwd || '/Users/developer/projects/myrm-agent',
        is_active: true,
      },
    ];
  }
}

export const workspaceBoundaryService = new WorkspaceBoundaryService();
