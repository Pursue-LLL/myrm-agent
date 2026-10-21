import { create } from 'zustand';
import {
  ChannelFootprintItem,
  ChannelType,
  DigestStylePreset,
  FootprintCategory,
  RefinementInstruction,
  WeeklyDigestSummary,
} from './weeklyDigestTypes';
import { INITIAL_CHANNEL_FOOTPRINTS } from './footprintAggregatorData';
import {
  applyRefinementInstruction,
  synthesizeWeeklyDigest,
} from './weeklyDigestSynthesizerEngine';

export interface WeeklyDigestState {
  footprints: ChannelFootprintItem[];
  selectedChannelFilter: ChannelType | 'all';
  selectedCategoryFilter: FootprintCategory | 'all';
  selectedWeekIdentifier: string;
  currentDigest: WeeklyDigestSummary | null;
  activeStylePreset: DigestStylePreset;
  isSynthesizerModalOpen: boolean;
  isSynthesizing: boolean;
  refinementInstructions: RefinementInstruction[];
  lastExportStatus: { target: string; success: boolean; timestamp: number } | null;

  // Actions
  setChannelFilter: (channel: ChannelType | 'all') => void;
  setCategoryFilter: (category: FootprintCategory | 'all') => void;
  toggleFootprintIncluded: (id: string) => void;
  setAllFootprintsIncluded: (included: boolean) => void;
  addFootprintItem: (
    item: Omit<ChannelFootprintItem, 'id' | 'timestamp' | 'includedInDigest'>
  ) => void;
  openSynthesizerModal: () => void;
  closeSynthesizerModal: () => void;
  synthesizeDigest: (style?: DigestStylePreset) => Promise<void>;
  refineDigest: (instruction: string) => Promise<void>;
  exportDigest: (target: 'clipboard' | 'markdown' | 'feishu') => Promise<boolean>;
  resetState: () => void;
}

export const useWeeklyDigestStore = create<WeeklyDigestState>((set, get) => ({
  footprints: INITIAL_CHANNEL_FOOTPRINTS,
  selectedChannelFilter: 'all',
  selectedCategoryFilter: 'all',
  selectedWeekIdentifier: '2026-W36',
  currentDigest: null,
  activeStylePreset: 'executive',
  isSynthesizerModalOpen: false,
  isSynthesizing: false,
  refinementInstructions: [],
  lastExportStatus: null,

  setChannelFilter: (channel) => {
    set({ selectedChannelFilter: channel });
  },

  setCategoryFilter: (category) => {
    set({ selectedCategoryFilter: category });
  },

  toggleFootprintIncluded: (id) => {
    set((state) => ({
      footprints: state.footprints.map((item) => {
        if (item.id === id) {
          return { ...item, includedInDigest: !item.includedInDigest };
        }
        return item;
      }),
    }));
  },

  setAllFootprintsIncluded: (included) => {
    set((state) => ({
      footprints: state.footprints.map((item) => ({
        ...item,
        includedInDigest: included,
      })),
    }));
  },

  addFootprintItem: (item) => {
    const newItem: ChannelFootprintItem = {
      ...item,
      id: `fp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      timestamp: Date.now(),
      includedInDigest: true,
    };
    set((state) => ({ footprints: [newItem, ...state.footprints] }));
  },

  openSynthesizerModal: () => {
    // 若当前尚未合成，则自动执行初次合成
    if (!get().currentDigest) {
      const digest = synthesizeWeeklyDigest(get().footprints, {
        weekIdentifier: get().selectedWeekIdentifier,
        stylePreset: get().activeStylePreset,
      });
      set({ currentDigest: digest });
    }
    set({ isSynthesizerModalOpen: true });
  },

  closeSynthesizerModal: () => {
    set({ isSynthesizerModalOpen: false });
  },

  synthesizeDigest: async (style) => {
    const targetStyle = style || get().activeStylePreset;
    set({ isSynthesizing: true, activeStylePreset: targetStyle });

    // 模拟微任务延迟，保证动画感知
    await new Promise((resolve) => setTimeout(resolve, 60));

    const digest = synthesizeWeeklyDigest(get().footprints, {
      weekIdentifier: get().selectedWeekIdentifier,
      stylePreset: targetStyle,
    });

    set({ currentDigest: digest, isSynthesizing: false });
  },

  refineDigest: async (instruction) => {
    if (!instruction.trim() || !get().currentDigest) {
      return;
    }
    set({ isSynthesizing: true });

    await new Promise((resolve) => setTimeout(resolve, 80));

    const current = get().currentDigest;
    if (current) {
      const refined = applyRefinementInstruction(current, instruction);
      const newRefinement: RefinementInstruction = {
        id: `ref-${Date.now()}`,
        prompt: instruction.trim(),
        appliedAt: Date.now(),
      };
      set((state) => ({
        currentDigest: refined,
        activeStylePreset: refined.stylePreset,
        refinementInstructions: [...state.refinementInstructions, newRefinement],
        isSynthesizing: false,
      }));
    } else {
      set({ isSynthesizing: false });
    }
  },

  exportDigest: async (target) => {
    const digest = get().currentDigest;
    if (!digest) {
      return false;
    }

    try {
      if (target === 'clipboard' && typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(digest.markdownContent);
      }

      set({
        lastExportStatus: {
          target,
          success: true,
          timestamp: Date.now(),
        },
      });

      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('myrm:weekly-digest-exported', {
            detail: {
              target,
              digestId: digest.id,
              weekIdentifier: digest.weekIdentifier,
            },
          })
        );
      }
      return true;
    } catch {
      set({
        lastExportStatus: {
          target,
          success: false,
          timestamp: Date.now(),
        },
      });
      return false;
    }
  },

  resetState: () => {
    set({
      footprints: INITIAL_CHANNEL_FOOTPRINTS,
      selectedChannelFilter: 'all',
      selectedCategoryFilter: 'all',
      currentDigest: null,
      activeStylePreset: 'executive',
      isSynthesizerModalOpen: false,
      isSynthesizing: false,
      refinementInstructions: [],
      lastExportStatus: null,
    });
  },
}));
