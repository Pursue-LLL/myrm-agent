import { create } from 'zustand';
import {
  ClarificationAttachment,
  ClarificationQuestionnaireState,
  QuestionnaireQuestion,
  V1SpecContract,
} from './clarificationQuestionnaireTypes';
import {
  DEFAULT_CLARIFICATION_QUESTIONS,
  autoApplyAllRecommendations,
  synthesizeV1Spec,
} from './clarificationQuestionnaireEngine';

export interface ClarificationQuestionnaireActions {
  setQuestions: (questions: QuestionnaireQuestion[]) => void;
  selectOption: (questionId: string, optionId: string) => void;
  updateCustomText: (questionId: string, text: string) => void;
  addAttachment: (questionId: string, attachment: ClarificationAttachment) => void;
  updateAttachmentStatus: (
    questionId: string,
    attachmentId: string,
    status: 'uploading' | 'ready' | 'error',
    url?: string
  ) => void;
  removeAttachment: (questionId: string, attachmentId: string) => void;
  applyAllRecommendations: () => void;
  setCurrentQuestionIndex: (index: number) => void;
  synthesizeAndPreviewSpec: () => V1SpecContract;
  setSpecModalOpen: (open: boolean) => void;
  submitQuestionnaire: () => V1SpecContract;
  reset: () => void;
}

export type ClarificationQuestionnaireStore = ClarificationQuestionnaireState &
  ClarificationQuestionnaireActions;

const INITIAL_STATE: ClarificationQuestionnaireState = {
  status: 'draft',
  questions: DEFAULT_CLARIFICATION_QUESTIONS,
  currentQuestionIndex: 0,
  isSpecModalOpen: false,
  activeSpecContract: null,
  lastSubmittedTime: null,
};

export const useClarificationQuestionnaireStore = create<ClarificationQuestionnaireStore>(
  (set, get) => ({
    ...INITIAL_STATE,

    setQuestions: (questions: QuestionnaireQuestion[]) => {
      set({
        questions,
        currentQuestionIndex: 0,
        status: 'draft',
        activeSpecContract: null,
      });
    },

    selectOption: (questionId: string, optionId: string) => {
      const updated = get().questions.map((q) => {
        if (q.id !== questionId) {
          return q;
        }

        if (q.isMultiSelect) {
          const isAlreadySelected = q.selectedOptionIds.includes(optionId);
          const newSelected = isAlreadySelected
            ? q.selectedOptionIds.filter((id) => id !== optionId)
            : [...q.selectedOptionIds, optionId];
          return {
            ...q,
            selectedOptionIds: newSelected,
          };
        }

        // 单选逻辑：如果点击已选中的单选，保持选中；点击新项则切换
        return {
          ...q,
          selectedOptionIds: [optionId],
        };
      });

      set({ questions: updated });
    },

    updateCustomText: (questionId: string, text: string) => {
      const updated = get().questions.map((q) => {
        if (q.id !== questionId) {
          return q;
        }
        return {
          ...q,
          customTextAnswer: text,
        };
      });

      set({ questions: updated });
    },

    addAttachment: (questionId: string, attachment: ClarificationAttachment) => {
      const updated = get().questions.map((q) => {
        if (q.id !== questionId) {
          return q;
        }
        return {
          ...q,
          attachments: [...q.attachments, attachment],
        };
      });

      set({ questions: updated });
    },

    updateAttachmentStatus: (
      questionId: string,
      attachmentId: string,
      status: 'uploading' | 'ready' | 'error',
      url?: string
    ) => {
      const updated = get().questions.map((q) => {
        if (q.id !== questionId) {
          return q;
        }
        const updatedAttachments = q.attachments.map((att) => {
          if (att.id !== attachmentId) {
            return att;
          }
          return {
            ...att,
            uploadStatus: status,
            url: url !== undefined ? url : att.url,
          };
        });
        return {
          ...q,
          attachments: updatedAttachments,
        };
      });

      set({ questions: updated });
    },

    removeAttachment: (questionId: string, attachmentId: string) => {
      const updated = get().questions.map((q) => {
        if (q.id !== questionId) {
          return q;
        }
        return {
          ...q,
          attachments: q.attachments.filter((att) => att.id !== attachmentId),
        };
      });

      set({ questions: updated });
    },

    applyAllRecommendations: () => {
      const recommended = autoApplyAllRecommendations(get().questions);
      set({ questions: recommended });
    },

    setCurrentQuestionIndex: (index: number) => {
      const maxIdx = Math.max(0, get().questions.length - 1);
      const safeIdx = Math.min(Math.max(0, index), maxIdx);
      set({ currentQuestionIndex: safeIdx });
    },

    synthesizeAndPreviewSpec: () => {
      const spec = synthesizeV1Spec(get().questions);
      set({
        activeSpecContract: spec,
        isSpecModalOpen: true,
      });
      return spec;
    },

    setSpecModalOpen: (open: boolean) => {
      set({ isSpecModalOpen: open });
    },

    submitQuestionnaire: () => {
      const spec = synthesizeV1Spec(get().questions);
      set({
        status: 'submitted',
        activeSpecContract: spec,
        isSpecModalOpen: false,
        lastSubmittedTime: Date.now(),
      });
      return spec;
    },

    reset: () => {
      set(INITIAL_STATE);
    },
  })
);
