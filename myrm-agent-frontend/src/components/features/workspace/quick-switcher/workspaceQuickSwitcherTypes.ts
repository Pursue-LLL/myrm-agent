/**
 * 工作区快速切换器与多项目漫游实体契约
 */

export interface WorkspaceItem {
  id: string;
  name: string;
  path: string;
  gitBranch?: string;
  isDirty?: boolean;
  dirtyCount?: number;
  lastOpenedAt: number;
  isFavorite: boolean;
  activeSessionsCount: number;
  rulesLoaded: string[];
}

export type WorkspaceFilterTab = 'all' | 'recent' | 'favorites';

export interface WorkspaceSwitchEvent {
  previousWorkspaceId: string | null;
  currentWorkspaceId: string;
  workspace: WorkspaceItem;
  openInNewTab?: boolean;
}

export interface WorkspaceQuickSwitcherState {
  isOpen: boolean;
  searchQuery: string;
  activeTab: WorkspaceFilterTab;
  selectedIndex: number;
  workspaces: WorkspaceItem[];
  currentWorkspaceId: string | null;
  lastSwitchEvent: WorkspaceSwitchEvent | null;
}
