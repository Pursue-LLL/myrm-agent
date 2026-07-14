'use client';

/**
 * [INPUT]
 * zustand (POS: State management)
 * zustand/middleware/immer (POS: Immutable state updates)
 *
 * [OUTPUT]
 * useResearchStore: Research mode state — selected resource IDs, active tab, panel visibility.
 *
 * [POS]
 * Research 工作台全局状态。管理资料勾选、面板切换和 Research session 上下文。
 */

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';

export type ResearchTab = 'resources' | 'chat' | 'output';

export interface ResearchResource {
  id: string;
  name: string;
  type: 'concept' | 'raw_file';
  summary?: string;
  selected: boolean;
}

interface ResearchState {
  resources: ResearchResource[];
  activeTab: ResearchTab;
}

interface ResearchActions {
  addResource: (resource: Omit<ResearchResource, 'selected'>) => void;
  removeResource: (id: string) => void;
  toggleResource: (id: string) => void;
  selectAll: () => void;
  deselectAll: () => void;
  setActiveTab: (tab: ResearchTab) => void;
  getSelectedResources: () => ResearchResource[];
  reset: () => void;
}

const initialState: ResearchState = {
  resources: [],
  activeTab: 'resources',
};

const useResearchStore = create<ResearchState & ResearchActions>()(
  immer((set, get) => ({
    ...initialState,

    addResource: (resource) =>
      set((state) => {
        if (state.resources.some((r) => r.id === resource.id)) return;
        state.resources.push({ ...resource, selected: true });
      }),

    removeResource: (id) =>
      set((state) => {
        state.resources = state.resources.filter((r) => r.id !== id);
      }),

    toggleResource: (id) =>
      set((state) => {
        const resource = state.resources.find((r) => r.id === id);
        if (resource) resource.selected = !resource.selected;
      }),

    selectAll: () =>
      set((state) => {
        for (const r of state.resources) r.selected = true;
      }),

    deselectAll: () =>
      set((state) => {
        for (const r of state.resources) r.selected = false;
      }),

    setActiveTab: (tab) => set({ activeTab: tab }),

    getSelectedResources: () => get().resources.filter((r) => r.selected),

    reset: () => set(initialState),
  })),
);

export default useResearchStore;
