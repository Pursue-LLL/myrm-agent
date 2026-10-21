/**
 * [INPUT] @/services/milestones (POS: 里程碑 REST API 封装)
 * [OUTPUT] useMilestoneStore: 里程碑状态管理（列表 + 批量进度）
 * [POS] 管理当前项目的里程碑列表、批量进度统计和 CRUD 操作，驱动 ProjectMilestonePanel 组件。
 */

import { create } from 'zustand';

import type { Milestone, MilestoneProgress } from '@/services/milestones';
import {
  type AssessmentImportReceipt,
  getMilestones,
  getBatchProgress,
  createMilestone,
  importAssessmentArtifact,
  updateMilestone as apiUpdateMilestone,
  deleteMilestone as apiDeleteMilestone,
} from '@/services/milestones';

interface MilestoneState {
  milestones: Milestone[];
  progressMap: Record<string, MilestoneProgress>;
  loading: boolean;
  currentProjectId: string | null;
}

interface MilestoneActions {
  fetchMilestones: (projectId: string) => Promise<void>;
  addMilestone: (
    projectId: string,
    title: string,
    description?: string,
    acceptanceCriteria?: string,
  ) => Promise<Milestone>;
  updateMilestone: (
    projectId: string,
    milestoneId: string,
    updates: { title?: string; description?: string; acceptance_criteria?: string; status?: string },
  ) => Promise<void>;
  removeMilestone: (projectId: string, milestoneId: string) => Promise<void>;
  completeMilestone: (projectId: string, milestoneId: string) => Promise<void>;
  importAssessment: (
    projectId: string,
    payload: {
      artifact_id: string;
      source_chat_id?: string;
      max_milestones?: number;
      max_tasks_per_milestone?: number;
    },
  ) => Promise<AssessmentImportReceipt>;
  reset: () => void;
}

export const useMilestoneStore = create<MilestoneState & MilestoneActions>()((set) => ({
  milestones: [],
  progressMap: {},
  loading: false,
  currentProjectId: null,

  fetchMilestones: async (projectId) => {
    set({ loading: true, currentProjectId: projectId });
    try {
      const [milestones, progressList] = await Promise.all([getMilestones(projectId), getBatchProgress(projectId)]);
      const progressMap: Record<string, MilestoneProgress> = {};
      for (const p of progressList) {
        progressMap[p.milestoneId] = p;
      }
      set({ milestones, progressMap, loading: false });
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

  importAssessment: async (projectId, payload) => {
    const receipt = await importAssessmentArtifact(projectId, payload);
    const [milestones, progressList] = await Promise.all([getMilestones(projectId), getBatchProgress(projectId)]);
    const progressMap: Record<string, MilestoneProgress> = {};
    for (const p of progressList) {
      progressMap[p.milestoneId] = p;
    }
    set({ milestones, progressMap, currentProjectId: projectId });
    return receipt;
  },

  reset: () => set({ milestones: [], progressMap: {}, loading: false, currentProjectId: null }),
}));
