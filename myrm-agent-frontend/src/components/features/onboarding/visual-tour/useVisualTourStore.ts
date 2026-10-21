import { create } from 'zustand';
import {
  DEFAULT_CHECKLIST_ITEMS,
  DEFAULT_PLAYGROUND_TEMPLATES,
  DEFAULT_TOUR_STEPS,
  getNextStepIndex,
  getPrevStepIndex,
} from './visualTourEngine';
import type {
  ChecklistItem,
  PlaygroundTemplate,
  TourStep,
} from './visualTourTypes';

const STORAGE_KEY = 'myrm_onboarding_tour_state_v1';

export interface VisualTourState {
  readonly isTourActive: boolean;
  readonly currentStepIndex: number;
  readonly isTourDismissed: boolean;
  readonly steps: readonly TourStep[];
  readonly checklistItems: readonly ChecklistItem[];
  readonly isChecklistCollapsed: boolean;
  readonly isChecklistDismissed: boolean;
  readonly templates: readonly PlaygroundTemplate[];
  readonly selectedTemplate: PlaygroundTemplate | null;

  startTour: () => void;
  nextTourStep: () => void;
  prevTourStep: () => void;
  skipTour: () => void;
  finishTour: () => void;
  toggleChecklistItem: (id: string) => void;
  setChecklistItemCompleted: (id: string, completed: boolean) => void;
  setChecklistCollapsed: (collapsed: boolean) => void;
  setChecklistDismissed: (dismissed: boolean) => void;
  resetOnboardingState: () => void;
  selectTemplate: (template: PlaygroundTemplate | null) => void;
}

function loadPersistedState(): {
  isTourDismissed: boolean;
  isChecklistDismissed: boolean;
  checklistItems?: readonly ChecklistItem[];
} {
  if (typeof window === 'undefined') {
    return { isTourDismissed: false, isChecklistDismissed: false };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { isTourDismissed: false, isChecklistDismissed: false };
    }
    const parsed = JSON.parse(raw);
    return {
      isTourDismissed: Boolean(parsed.isTourDismissed),
      isChecklistDismissed: Boolean(parsed.isChecklistDismissed),
      checklistItems: Array.isArray(parsed.checklistItems) ? parsed.checklistItems : undefined,
    };
  } catch {
    return { isTourDismissed: false, isChecklistDismissed: false };
  }
}

function savePersistedState(data: {
  isTourDismissed: boolean;
  isChecklistDismissed: boolean;
  checklistItems: readonly ChecklistItem[];
}): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // 忽略存储写入异常
  }
}

const initialPersisted = loadPersistedState();

export const useVisualTourStore = create<VisualTourState>((set, get) => {
  return {
    isTourActive: false,
    currentStepIndex: 0,
    isTourDismissed: initialPersisted.isTourDismissed,
    steps: DEFAULT_TOUR_STEPS,
    checklistItems: initialPersisted.checklistItems ?? DEFAULT_CHECKLIST_ITEMS,
    isChecklistCollapsed: false,
    isChecklistDismissed: initialPersisted.isChecklistDismissed,
    templates: DEFAULT_PLAYGROUND_TEMPLATES,
    selectedTemplate: null,

    startTour: () => {
      set({
        isTourActive: true,
        currentStepIndex: 0,
      });
    },

    nextTourStep: () => {
      const { currentStepIndex, steps } = get();
      if (currentStepIndex >= steps.length - 1) {
        get().finishTour();
      } else {
        set({
          currentStepIndex: getNextStepIndex(currentStepIndex, steps.length),
        });
      }
    },

    prevTourStep: () => {
      const { currentStepIndex } = get();
      set({
        currentStepIndex: getPrevStepIndex(currentStepIndex),
      });
    },

    skipTour: () => {
      set({
        isTourActive: false,
        isTourDismissed: true,
      });
      const { isChecklistDismissed, checklistItems } = get();
      savePersistedState({ isTourDismissed: true, isChecklistDismissed, checklistItems });
    },

    finishTour: () => {
      set({
        isTourActive: false,
        isTourDismissed: true,
      });
      const { isChecklistDismissed, checklistItems } = get();
      savePersistedState({ isTourDismissed: true, isChecklistDismissed, checklistItems });
    },

    toggleChecklistItem: (id: string) => {
      set((state) => {
        const nextItems = state.checklistItems.map((item) => {
          if (item.id === id) {
            return { ...item, completed: !item.completed };
          }
          return item;
        });
        savePersistedState({
          isTourDismissed: state.isTourDismissed,
          isChecklistDismissed: state.isChecklistDismissed,
          checklistItems: nextItems,
        });
        return { checklistItems: nextItems };
      });
    },

    setChecklistItemCompleted: (id: string, completed: boolean) => {
      set((state) => {
        const nextItems = state.checklistItems.map((item) => {
          if (item.id === id) {
            return { ...item, completed };
          }
          return item;
        });
        savePersistedState({
          isTourDismissed: state.isTourDismissed,
          isChecklistDismissed: state.isChecklistDismissed,
          checklistItems: nextItems,
        });
        return { checklistItems: nextItems };
      });
    },

    setChecklistCollapsed: (collapsed: boolean) => {
      set({ isChecklistCollapsed: collapsed });
    },

    setChecklistDismissed: (dismissed: boolean) => {
      set((state) => {
        savePersistedState({
          isTourDismissed: state.isTourDismissed,
          isChecklistDismissed: dismissed,
          checklistItems: state.checklistItems,
        });
        return { isChecklistDismissed: dismissed };
      });
    },

    resetOnboardingState: () => {
      const resetChecklist = DEFAULT_CHECKLIST_ITEMS.map((item) => {
        return { ...item, completed: false };
      });
      set({
        isTourActive: true,
        currentStepIndex: 0,
        isTourDismissed: false,
        checklistItems: resetChecklist,
        isChecklistCollapsed: false,
        isChecklistDismissed: false,
        selectedTemplate: null,
      });
      savePersistedState({
        isTourDismissed: false,
        isChecklistDismissed: false,
        checklistItems: resetChecklist,
      });
    },

    selectTemplate: (template: PlaygroundTemplate | null) => {
      set({ selectedTemplate: template });
    },
  };
});
