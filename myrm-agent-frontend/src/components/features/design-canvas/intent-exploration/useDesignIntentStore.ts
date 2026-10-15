'use client';

import { create } from 'zustand';
import {
  DesignElementKey,
  DesignDirectionVariant,
  FiveElementSpec,
} from './designIntentTypes';
import {
  analyzeFiveElements,
  assembleRefinedPrompt,
  generateInitial3Directions,
} from './fiveElementLinterEngine';

export interface DesignIntentState {
  draftPrompt: string;
  currentSpec: FiveElementSpec;
  activeCapsuleKey: DesignElementKey | null;
  variants: DesignDirectionVariant[];
  selectedVariantId: string | null;
  isExplorationOpen: boolean;

  setDraftPrompt: (prompt: string) => void;
  setElementValue: (key: DesignElementKey, value: string) => void;
  clearElementValue: (key: DesignElementKey) => void;
  setActiveCapsuleKey: (key: DesignElementKey | null) => void;
  applyAssembledPrompt: () => string;
  generateVariants: () => void;
  selectVariant: (variantId: string) => void;
  closeExploration: () => void;
  reset: () => void;
}

const INITIAL_PROMPT = '帮我做一张咖啡店周年庆海报，第二杯半价';
const INITIAL_SPEC = analyzeFiveElements(INITIAL_PROMPT);

export const useDesignIntentStore = create<DesignIntentState>((set, get) => ({
  draftPrompt: INITIAL_PROMPT,
  currentSpec: INITIAL_SPEC,
  activeCapsuleKey: null,
  variants: generateInitial3Directions(INITIAL_SPEC),
  selectedVariantId: 'direction-a-minimal',
  isExplorationOpen: false,

  setDraftPrompt: (prompt: string) => {
    const updatedSpec = analyzeFiveElements(prompt);
    set({
      draftPrompt: prompt,
      currentSpec: updatedSpec,
    });
  },

  setElementValue: (key: DesignElementKey, value: string) => {
    set((state) => {
      const updatedSpec: FiveElementSpec = {
        ...state.currentSpec,
        [key]: {
          ...state.currentSpec[key],
          value,
          isDetected: true,
        },
      };

      let count = 0;
      const keys: DesignElementKey[] = ['what', 'audience', 'style', 'content', 'format'];
      for (const k of keys) {
        if (updatedSpec[k].isDetected && updatedSpec[k].value) {
          count += 1;
        }
      }
      updatedSpec.completenessScore = Math.round((count / keys.length) * 100);

      return {
        currentSpec: updatedSpec,
        activeCapsuleKey: null,
      };
    });
  },

  clearElementValue: (key: DesignElementKey) => {
    set((state) => {
      const updatedSpec: FiveElementSpec = {
        ...state.currentSpec,
        [key]: {
          ...state.currentSpec[key],
          value: null,
          isDetected: false,
        },
      };

      let count = 0;
      const keys: DesignElementKey[] = ['what', 'audience', 'style', 'content', 'format'];
      for (const k of keys) {
        if (updatedSpec[k].isDetected && updatedSpec[k].value) {
          count += 1;
        }
      }
      updatedSpec.completenessScore = Math.round((count / keys.length) * 100);

      return {
        currentSpec: updatedSpec,
      };
    });
  },

  setActiveCapsuleKey: (key: DesignElementKey | null) => {
    set({ activeCapsuleKey: key });
  },

  applyAssembledPrompt: () => {
    const { currentSpec, draftPrompt } = get();
    const refined = assembleRefinedPrompt(currentSpec, draftPrompt);
    set({ draftPrompt: refined });
    return refined;
  },

  generateVariants: () => {
    const { currentSpec } = get();
    const newVariants = generateInitial3Directions(currentSpec);
    set({
      variants: newVariants,
      selectedVariantId: newVariants[0]?.id || null,
      isExplorationOpen: true,
    });
  },

  selectVariant: (variantId: string) => {
    set({ selectedVariantId: variantId });
  },

  closeExploration: () => {
    set({ isExplorationOpen: false });
  },

  reset: () => {
    const spec = analyzeFiveElements(INITIAL_PROMPT);
    set({
      draftPrompt: INITIAL_PROMPT,
      currentSpec: spec,
      activeCapsuleKey: null,
      variants: generateInitial3Directions(spec),
      selectedVariantId: 'direction-a-minimal',
      isExplorationOpen: false,
    });
  },
}));
