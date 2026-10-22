/**
 * 个人私有空间与团队协同工作空间穿梭中枢及交互式微应用发现芯片契约定义
 */

export type WorkspaceScope = 'personal' | 'team';

export type TeamRole = 'owner' | 'admin' | 'member';

export interface TeamWorkspaceEntity {
  id: string;
  name: string;
  avatarUrl?: string;
  memberCount: number;
  role: TeamRole;
  enterpriseSandboxId: string;
  sharedProjectsCount: number;
}

export interface ScopeIsolationAudit {
  switchedAt: number;
  fromScope: WorkspaceScope;
  toScope: WorkspaceScope;
  activeSessionPurged: boolean;
  localSecretKeysHidden: boolean;
  isZeroLeakGuaranteed: boolean;
}

export type DiscoveryChipCategory = 'dashboard' | 'heatmap' | 'workflow';

export interface DiscoveryChipItem {
  id: string;
  label: string;
  description: string;
  iconName: string; // Lucide icon identifier
  templatePrompt: string;
  category: DiscoveryChipCategory;
}

export interface WorkspaceScopeState {
  currentScope: WorkspaceScope;
  activeTeamId: string;
  teams: TeamWorkspaceEntity[];
  lastIsolationAudit: ScopeIsolationAudit | null;
  isScopeDropdownOpen: boolean;
  discoveryChips: DiscoveryChipItem[];
  selectedChipResult: string | null;
}
