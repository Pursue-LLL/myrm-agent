/**
 * Skill draft management store (for background review)
 */

import { create } from 'zustand';
import type { SkillDraft, SkillDraftListResponse, ApproveDraftResult } from '@/services/skill';
import { listSkillDrafts, getUnreviewedDraftCount, approveSkillDraft, rejectSkillDraft } from '@/services/skill';

interface SkillDraftState {
  drafts: SkillDraft[];
  unreviewedCount: number;
  isLoading: boolean;
  error: string | null;
}

interface SkillDraftActions {
  fetchDrafts: (status?: 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED') => Promise<void>;
  fetchUnreviewedCount: () => Promise<void>;
  approveDraft: (draftId: string, skillName?: string) => Promise<ApproveDraftResult>;
  rejectDraft: (draftId: string) => Promise<void>;
  incrementUnreviewedCount: () => void;
  decrementUnreviewedCount: () => void;
  reset: () => void;
}

type SkillDraftStore = SkillDraftState & SkillDraftActions;

const initialState: SkillDraftState = {
  drafts: [],
  unreviewedCount: 0,
  isLoading: false,
  error: null,
};

export const useSkillDraftStore = create<SkillDraftStore>((set, get) => ({
  ...initialState,

  fetchDrafts: async (status = 'PENDING_REVIEW') => {
    const { isLoading } = get();
    if (isLoading) return;

    set({ isLoading: true, error: null });
    try {
      const response: SkillDraftListResponse = await listSkillDrafts(status);
      set({ drafts: response.drafts, isLoading: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch skill drafts',
        isLoading: false,
      });
    }
  },

  fetchUnreviewedCount: async () => {
    try {
      const response = await getUnreviewedDraftCount();
      set({ unreviewedCount: response.unreviewed_count });
    } catch (error) {
      console.error('Failed to fetch unreviewed draft count:', error);
    }
  },

  approveDraft: async (draftId: string, skillName?: string) => {
    const { drafts, unreviewedCount } = get();
    try {
      const result = await approveSkillDraft(draftId, skillName);
      if (result.materialized !== false) {
        set({
          drafts: drafts.filter((d) => d.id !== draftId),
          unreviewedCount: Math.max(0, unreviewedCount - 1),
        });
      }
      return result;
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to approve draft' });
      throw error;
    }
  },

  rejectDraft: async (draftId: string) => {
    const { drafts, unreviewedCount } = get();
    try {
      await rejectSkillDraft(draftId);
      set({
        drafts: drafts.filter((d) => d.id !== draftId),
        unreviewedCount: Math.max(0, unreviewedCount - 1),
      });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to reject draft' });
      throw error;
    }
  },

  incrementUnreviewedCount: () => {
    set((state) => ({ unreviewedCount: state.unreviewedCount + 1 }));
  },

  decrementUnreviewedCount: () => {
    set((state) => ({ unreviewedCount: Math.max(0, state.unreviewedCount - 1) }));
  },

  reset: () => {
    set(initialState);
  },
}));
