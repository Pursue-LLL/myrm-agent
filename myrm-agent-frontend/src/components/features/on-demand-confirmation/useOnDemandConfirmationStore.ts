import { create } from 'zustand';
import {
  OptionLetterId,
  OnDemandDecisionInterrupt,
  ConfirmationDecisionResult,
  NineEntryId,
} from './onDemandConfirmationTypes';
import { buildDecisionResult } from './onDemandConfirmationEngine';

interface OnDemandConfirmationState {
  currentInterrupt: OnDemandDecisionInterrupt | null;
  selectedOptionId: OptionLetterId | null;
  customInput: string;
  isModalOpen: boolean;
  historyDecisions: ConfirmationDecisionResult[];
  activeNavEntryId: NineEntryId;

  setInterrupt: (interrupt: OnDemandDecisionInterrupt) => void;
  selectOption: (optionId: OptionLetterId) => void;
  setCustomInput: (input: string) => void;
  openModal: () => void;
  closeModal: () => void;
  confirmDecision: () => ConfirmationDecisionResult | null;
  setActiveNavEntryId: (entryId: NineEntryId) => void;
  clearHistory: () => void;
}

export const useOnDemandConfirmationStore = create<OnDemandConfirmationState>((set, get) => ({
  currentInterrupt: null,
  selectedOptionId: null,
  customInput: '',
  isModalOpen: false,
  historyDecisions: [],
  activeNavEntryId: 'main_chat',

  setInterrupt: (interrupt) => {
    // 默认高亮推荐选项，若无推荐则默认选中第一项
    const recommended = interrupt.options.find((o) => o.isRecommended);
    const initialSelected = recommended ? recommended.id : interrupt.options[0]?.id || null;
    set({
      currentInterrupt: interrupt,
      selectedOptionId: initialSelected,
      customInput: '',
      isModalOpen: true,
    });
  },

  selectOption: (optionId) => set({ selectedOptionId: optionId }),

  setCustomInput: (customInput) => set({ customInput }),

  openModal: () => set({ isModalOpen: true }),

  closeModal: () => set({ isModalOpen: false }),

  confirmDecision: () => {
    const { currentInterrupt, selectedOptionId, customInput, historyDecisions } = get();
    if (!currentInterrupt || !selectedOptionId) {
      return null;
    }

    const result = buildDecisionResult(currentInterrupt, selectedOptionId, customInput);
    set({
      isModalOpen: false,
      currentInterrupt: null,
      selectedOptionId: null,
      customInput: '',
      historyDecisions: [result, ...historyDecisions],
    });

    return result;
  },

  setActiveNavEntryId: (activeNavEntryId) => set({ activeNavEntryId }),

  clearHistory: () => set({ historyDecisions: [] }),
}));
