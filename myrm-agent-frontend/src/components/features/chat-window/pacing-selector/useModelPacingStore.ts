/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/store/useChatStore (POS: Downstream connection to optimizationMode)
 * - @/components/features/chat-window/pacing-selector/modelPacingTypes
 * - @/components/features/chat-window/pacing-selector/modelPacingEngine
 *
 * [OUTPUT]
 * - useModelPacingStore (POS: Reactive store for tri-tier model execution pacing)
 *
 * [POS]
 * Central reactive dispatcher for Item 191.
 * Governs execution pacing (fast/balanced/smart) and synchronizes with downstream chat store optimizationMode.
 */

import { create } from 'zustand';
import useChatStore from '@/store/useChatStore';
import type {
  ModelPacingTier,
  ModelPacingStoreState,
} from './modelPacingTypes';
import { mapPacingTierToOptimizationMode } from './modelPacingEngine';

export interface ModelPacingStoreActions {
  readonly setPacingTier: (tier: ModelPacingTier, chatId?: string | null) => void;
  readonly togglePopover: (open?: boolean) => void;
  readonly loadChatOverride: (chatId: string) => void;
  readonly resetStore: () => void;
}

export type ModelPacingStore = ModelPacingStoreState & ModelPacingStoreActions;

export const useModelPacingStore = create<ModelPacingStore>((set, get) => ({
  activeTier: 'balanced',
  isPopoverOpen: false,
  perChatOverrides: {},

  setPacingTier: (tier: ModelPacingTier, chatId?: string | null) => {
    // Synchronize to useChatStore optimizationMode
    const mappedMode = mapPacingTierToOptimizationMode(tier);
    useChatStore.getState().setOptimizationMode(mappedMode);

    set((state) => {
      const overrides = { ...state.perChatOverrides };
      if (chatId) {
        overrides[chatId] = tier;
      }
      return {
        activeTier: tier,
        perChatOverrides: overrides,
        isPopoverOpen: false,
      };
    });
  },

  togglePopover: (open?: boolean) => {
    set((state) => ({
      isPopoverOpen: typeof open === 'boolean' ? open : !state.isPopoverOpen,
    }));
  },

  loadChatOverride: (chatId: string) => {
    const override = get().perChatOverrides[chatId];
    if (override) {
      get().setPacingTier(override, chatId);
    }
  },

  resetStore: () => {
    set({
      activeTier: 'balanced',
      isPopoverOpen: false,
      perChatOverrides: {},
    });
  },
}));
