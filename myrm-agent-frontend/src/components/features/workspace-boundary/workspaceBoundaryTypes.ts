/**
 * [INPUT]
 * None
 * [OUTPUT]
 * Strongly typed TypeScript interfaces for Workspace Execution Boundary and 3-Currents state.
 * [POS]
 * src/components/features/workspace-boundary/workspaceBoundaryTypes.ts
 */

export type ExecutionHostType = 'local_host' | 'cloud_sandbox' | 'docker_container';

export type RiskLevel = 'safe' | 'warning' | 'blocked';

export interface ThreeCurrentsBoundary {
  session_id: string;
  project_id: string;
  project_name: string;
  session_goal: string;
  cwd: string;
  repo_name: string;
  git_branch: string;
  git_worktree?: string | null;
  git_is_clean: boolean;
  git_uncommitted_changes: number;
  execution_host_type: ExecutionHostType;
  execution_host_label: string;
  execution_host_id: string;
  inspected_at: number;
}

export interface ProjectSwitchHandshakeRequest {
  target_project_id: string;
  target_path: string;
  current_session_id?: string | null;
}

export interface ProjectSwitchHandshakeResponse {
  target_project_id: string;
  target_path: string;
  path_exists: boolean;
  is_git_repo: boolean;
  git_branch: string;
  git_worktree?: string | null;
  git_uncommitted_changes: number;
  risk_level: RiskLevel;
  warnings: string[];
  can_switch: boolean;
  handshake_token: string;
}

export interface MultiRepoWorktreeEntry {
  repo: string;
  worktree?: string | null;
  branch: string;
  path: string;
  is_active: boolean;
}
