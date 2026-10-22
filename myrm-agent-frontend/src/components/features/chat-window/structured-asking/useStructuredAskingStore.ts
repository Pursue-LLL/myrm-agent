/**
 * [INPUT]
 * - structuredAskingTypes: QuestionType, StructuredQuestionResponse
 *
 * [OUTPUT]
 * - useStructuredAskingStore: Zustand store for local structured asking selections and keyboard interaction
 *
 * [POS]
 * Store for managing structured question response draft states (Item 47 P0).
 * Strictly under 160 lines. Zero `any`.
 */

import { create } from 'zustand';
import type { QuestionType, StructuredQuestionResponse } from './structuredAskingTypes';

interface QuestionDraftState {
  selectedOptionIds: string[];
  textInput: string;
}

interface StructuredAskingState {
  drafts: Record<string, QuestionDraftState>;

  getDraft: (questionId: string) => QuestionDraftState;
  selectOption: (
    questionId: string,
    optionId: string,
    questionType: QuestionType
  ) => void;
  setTextInput: (questionId: string, text: string) => void;
  clearDraft: (questionId: string) => void;
  buildResponse: (
    questionId: string,
    isSkipped: boolean,
    defaultOptionId?: string
  ) => StructuredQuestionResponse;
  resetAll: () => void;
}

const DEFAULT_DRAFT: QuestionDraftState = {
  selectedOptionIds: [],
  textInput: '',
};

export const useStructuredAskingStore = create<StructuredAskingState>((set, get) => ({
  drafts: {},

  getDraft: (questionId: string) => {
    return get().drafts[questionId] ?? DEFAULT_DRAFT;
  },

  selectOption: (questionId: string, optionId: string, questionType: QuestionType) => {
    set((state) => {
      const current = state.drafts[questionId] ?? {
        selectedOptionIds: [],
        textInput: '',
      };

      if (questionType === 'single_choice' || questionType === 'boolean_confirm') {
        return {
          drafts: {
            ...state.drafts,
            [questionId]: {
              ...current,
              selectedOptionIds: [optionId],
            },
          },
        };
      }

      if (questionType === 'multi_choice') {
        const exists = current.selectedOptionIds.includes(optionId);
        const updated = exists
          ? current.selectedOptionIds.filter((id) => id !== optionId)
          : [...current.selectedOptionIds, optionId];
        return {
          drafts: {
            ...state.drafts,
            [questionId]: {
              ...current,
              selectedOptionIds: updated,
            },
          },
        };
      }

      return state;
    });
  },

  setTextInput: (questionId: string, text: string) => {
    set((state) => {
      const current = state.drafts[questionId] ?? {
        selectedOptionIds: [],
        textInput: '',
      };
      return {
        drafts: {
          ...state.drafts,
          [questionId]: {
            ...current,
            textInput: text,
          },
        },
      };
    });
  },

  clearDraft: (questionId: string) => {
    set((state) => {
      const next = { ...state.drafts };
      delete next[questionId];
      return { drafts: next };
    });
  },

  buildResponse: (
    questionId: string,
    isSkipped: boolean,
    defaultOptionId?: string
  ): StructuredQuestionResponse => {
    const draft = get().getDraft(questionId);

    if (isSkipped) {
      return {
        selectedOptionIds: defaultOptionId ? [defaultOptionId] : [],
        textValue: undefined,
        isSkipped: true,
        answeredAt: Date.now(),
      };
    }

    return {
      selectedOptionIds: draft.selectedOptionIds,
      textValue: draft.textInput.trim() || undefined,
      isSkipped: false,
      answeredAt: Date.now(),
    };
  },

  resetAll: () => {
    set({ drafts: {} });
  },
}));
