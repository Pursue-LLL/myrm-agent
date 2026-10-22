import { create } from 'zustand';
import { resolvePositionalReference } from './presentationToolEngine';
import {
  PositionalResolutionResult,
  PresentationItem,
  PresentationPayload,
  SuggestionChipItem,
} from './presentationToolTypes';

interface PresentationToolState {
  activePresentations: Record<string, PresentationPayload>;
  selectedPositionalItem: {
    presentationId: string;
    item: PresentationItem;
  } | null;
  lastActionQuery: string | null;

  registerPresentation: (payload: PresentationPayload) => void;
  clickSuggestionChip: (chip: SuggestionChipItem) => string;
  resolveAndSelectItem: (
    utterance: string,
    presentationId: string,
  ) => PositionalResolutionResult;
  clear: () => void;
  reset: () => void;
}

export const usePresentationToolStore = create<PresentationToolState>(
  (set, get) => ({
    activePresentations: {},
    selectedPositionalItem: null,
    lastActionQuery: null,

    registerPresentation: (payload: PresentationPayload): void => {
      set((state) => ({
        activePresentations: {
          ...state.activePresentations,
          [payload.id]: payload,
        },
      }));
    },

    clickSuggestionChip: (chip: SuggestionChipItem): string => {
      set({ lastActionQuery: chip.actionQuery });
      return chip.actionQuery;
    },

    resolveAndSelectItem: (
      utterance: string,
      presentationId: string,
    ): PositionalResolutionResult => {
      const presentation = get().activePresentations[presentationId];
      if (!presentation) {
        return {
          matchedItem: null,
          position: null,
          confidence: 0,
          rationale: `未找到 ID 为 ${presentationId} 的展示负载`,
        };
      }

      const res = resolvePositionalReference(utterance, presentation);
      if (res.matchedItem) {
        set({
          selectedPositionalItem: {
            presentationId,
            item: res.matchedItem,
          },
        });
      }

      return res;
    },

    clear: (): void => {
      set({
        activePresentations: {},
        selectedPositionalItem: null,
        lastActionQuery: null,
      });
    },

    reset: (): void => {
      set({
        activePresentations: {},
        selectedPositionalItem: null,
        lastActionQuery: null,
      });
    },
  }),
);
