/**
 * [INPUT] @/services/milestones
 * [OUTPUT] useMilestoneStore: 里程碑状态管理
 * [POS] 管理当前项目的里程碑列表和 CRUD 操作，驱动 ProjectRoadmapPanel 组件。
 */

import { create } from 'zustand';

import type { Milestone } from '@/services/milestones';
import {
  getMilestones,
  createMilestone,
  updateMilestone as apiUpdateMilestone,
  deleteMilestone as apiDeleteMilestone,
} from '@/services/milestones';

interface MilestoneState {
  milestones: Milestone[];
  loading: boolean;
  currentProjectId: string | null;
}

interface MilestoneActions {
  fetchMilestones: (projectId: string) => Promise<void>;
  addMilestone: (projectId: string, title: string, description?: string, acceptanceCriteria?: string) => Promise<Milestone>;
  updateMilestone: (projectId: string, milestoneId: string, updates: { title?: string; description?: string; acceptance_criteria?: string; status?: string }) => Promise<void>;
  removeMilestone: (projectId: string, milestoneId: string) => Promise<void>;
  completeMilestone: (projectId: string, milestoneId: string) => Promise<void>;
  reset: () => void;
}

export const useMilestoneStore = create<MilestoneState & MilestoneActions>()((set) => ({
  milestones: [],
  loading: false,
  currentProjectId: null,

  fetchMilestones: async (projectId) => {
    set({ loading: true, currentProjectId: projectId });
    try {
      const milestones = await getMilestones(projectId);
      set({ milestones, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  addMilestone: async (projectId, title, description, acceptanceCriteria) => {
    const milestone = await createMilestone(projectId, {
      title,
      description: description ?? '',
      acceptance_criteria: acceptanceCriteria ?? '',
    });
    set((s) => ({ milestones: [...s.milestones, milestone] }));
    return milestone;
  },

  updateMilestone: async (projectId, milestoneId, updates) => {
    const milestone = await apiUpdateMilestone(projectId, milestoneId, updates);
    set((s) => ({
      milestones: s.milestones.map((m) => (m.id === milestoneId ? milestone : m)),
    }));
  },

  removeMilestone: async (projectId, milestoneId) => {
    await apiDeleteMilestone(projectId, milestoneId);
    set((s) => ({
      milestones: s.milestones.filter((m) => m.id !== milestoneId),
    }));
  },

  completeMilestone: async (projectId, milestoneId) => {
    const milestone = await apiUpdateMilestone(projectId, milestoneId, { status: 'completed' });
    set((s) => ({
      milestones: s.milestones.map((m) => (m.id === milestoneId ? milestone : m)),
    }));
  },

  reset: () => set({ milestones: [], loading: false, currentProjectId: null }),
}));
