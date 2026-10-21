/**
 * useDualTrackStore.ts
 * 业务极简模式 vs 深度工程模式双轨视图状态管理
 */

import { create } from 'zustand';
import type {
  DualTrackViewMode,
  EngineeringTraceDetails,
} from './dualTrackTypes';

export interface DualTrackStoreState {
  viewMode: DualTrackViewMode;
  isTraceDrawerOpen: boolean;
  activeTraceDetails: EngineeringTraceDetails | null;
  agentDefaultViewPreferences: Record<string, DualTrackViewMode>;

  // Actions
  setViewMode: (mode: DualTrackViewMode) => void;
  toggleViewMode: () => void;
  openTraceDrawer: (trace: EngineeringTraceDetails) => void;
  closeTraceDrawer: () => void;
  setAgentPreference: (agentId: string, mode: DualTrackViewMode) => void;
  applyAgentPreference: (agentId: string) => void;
  resetAll: () => void;
}

export const useDualTrackStore = create<DualTrackStoreState>((set) => ({
  viewMode: 'business',
  isTraceDrawerOpen: false,
  activeTraceDetails: null,
  agentDefaultViewPreferences: {},

  setViewMode: (mode: DualTrackViewMode): void => {
    set({ viewMode: mode });
  },

  toggleViewMode: (): void => {
    set((state) => ({
      viewMode: state.viewMode === 'business' ? 'engineering' : 'business',
    }));
  },

  openTraceDrawer: (trace: EngineeringTraceDetails): void => {
    set({
      isTraceDrawerOpen: true,
      activeTraceDetails: trace,
    });
  },

  closeTraceDrawer: (): void => {
    set({
      isTraceDrawerOpen: false,
      activeTraceDetails: null,
    });
  },

  setAgentPreference: (agentId: string, mode: DualTrackViewMode): void => {
    set((state) => ({
      agentDefaultViewPreferences: {
        ...state.agentDefaultViewPreferences,
        [agentId]: mode,
      },
    }));
  },

  applyAgentPreference: (agentId: string): void => {
    set((state) => {
      const pref = state.agentDefaultViewPreferences[agentId];
      if (pref !== undefined) {
        return { viewMode: pref };
      }
      return state;
    });
  },

  resetAll: (): void => {
    set({
      viewMode: 'business',
      isTraceDrawerOpen: false,
      activeTraceDetails: null,
      agentDefaultViewPreferences: {},
    });
  },
}));
