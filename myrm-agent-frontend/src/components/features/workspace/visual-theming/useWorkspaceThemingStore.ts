import { create } from 'zustand';
import {
  WorkMode,
  WorkspaceItem,
  WorkspaceVisualTheme,
} from './workspaceThemingTypes';

interface WorkspaceThemingState {
  currentMode: WorkMode;
  activeWorkspaceId: string;
  workspaces: Record<string, WorkspaceItem>;
  isCustomizeThemeModalOpen: boolean;
  editingWorkspaceId: string | null;

  switchMode: (mode: WorkMode) => void;
  setActiveWorkspace: (id: string) => void;
  updateWorkspaceTheme: (id: string, theme: WorkspaceVisualTheme) => void;
  openCustomizeThemeModal: (id: string) => void;
  closeCustomizeThemeModal: () => void;
  reset: () => void;
}

export const INITIAL_PRESET_WORKSPACES: Record<string, WorkspaceItem> = {
  'ws-core-dev': {
    id: 'ws-core-dev',
    name: 'Myrm Agent 架构核心研发库',
    path: '~/projects/open-perplexity',
    defaultMode: 'coding',
    theme: {
      color: 'violet',
      icon: 'code',
      customLabel: '系统研发',
    },
    updatedAt: Date.now() - 3600000,
  },
  'ws-marketing-q4': {
    id: 'ws-marketing-q4',
    name: '2026 Q4 全球增长与商业化战役',
    path: '~/documents/marketing_campaign_q4',
    defaultMode: 'work',
    theme: {
      color: 'amber',
      icon: 'briefcase',
      customLabel: '商业企划',
    },
    updatedAt: Date.now() - 7200000,
  },
  'ws-legal-compliance': {
    id: 'ws-legal-compliance',
    name: '企业级数据安全与合规审计空间',
    path: '~/documents/legal_compliance_hub',
    defaultMode: 'work',
    theme: {
      color: 'emerald',
      icon: 'database',
      customLabel: '法务风控',
    },
    updatedAt: Date.now() - 86400000,
  },
};

export const useWorkspaceThemingStore = create<WorkspaceThemingState>((set) => ({
  currentMode: 'coding',
  activeWorkspaceId: 'ws-core-dev',
  workspaces: INITIAL_PRESET_WORKSPACES,
  isCustomizeThemeModalOpen: false,
  editingWorkspaceId: null,

  switchMode: (mode: WorkMode): void => {
    set({ currentMode: mode });
  },

  setActiveWorkspace: (id: string): void => {
    set((state) => {
      const target = state.workspaces[id];
      if (!target) {
        return state;
      }
      return {
        activeWorkspaceId: id,
        currentMode: target.defaultMode,
      };
    });
  },

  updateWorkspaceTheme: (id: string, theme: WorkspaceVisualTheme): void => {
    set((state) => {
      const existing = state.workspaces[id];
      if (!existing) {
        return state;
      }
      return {
        workspaces: {
          ...state.workspaces,
          [id]: {
            ...existing,
            theme,
            updatedAt: Date.now(),
          },
        },
      };
    });
  },

  openCustomizeThemeModal: (id: string): void => {
    set({
      isCustomizeThemeModalOpen: true,
      editingWorkspaceId: id,
    });
  },

  closeCustomizeThemeModal: (): void => {
    set({
      isCustomizeThemeModalOpen: false,
      editingWorkspaceId: null,
    });
  },

  reset: (): void => {
    set({
      currentMode: 'coding',
      activeWorkspaceId: 'ws-core-dev',
      workspaces: INITIAL_PRESET_WORKSPACES,
      isCustomizeThemeModalOpen: false,
      editingWorkspaceId: null,
    });
  },
}));
