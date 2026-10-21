import { create } from 'zustand';
import {
  ElementAnnotationItem,
  StagedBatchPayload,
} from './elementPatchTypes';
import { createStagedBatchPayload } from './elementPatchEngine';

export interface ElementPatchStoreState {
  stagedAnnotations: ElementAnnotationItem[];
  activeBatch: StagedBatchPayload | null;
  isDrawerOpen: boolean;
  selectedAnnotationId: string | null;
  isPickingElement: boolean;

  // Actions
  startPicking: () => void;
  stopPicking: () => void;
  togglePicking: () => void;
  stageAnnotation: (
    item: Omit<ElementAnnotationItem, 'id' | 'createdAt' | 'status'>
  ) => void;
  updateAnnotationInstruction: (id: string, newInstruction: string) => void;
  removeAnnotation: (id: string) => void;
  clearStaged: () => void;
  packageAndDispatch: (artifactId: string) => StagedBatchPayload | null;
  markAnnotationResolved: (id: string) => void;
  markAnnotationFailed: (id: string) => void;
  toggleDrawer: (open?: boolean) => void;
  selectAnnotation: (id: string | null) => void;
  reset: () => void;
}

export const useElementPatchStore = create<ElementPatchStoreState>((set, get) => ({
  stagedAnnotations: [],
  activeBatch: null,
  isDrawerOpen: false,
  selectedAnnotationId: null,
  isPickingElement: false,

  startPicking: () => {
    set({ isPickingElement: true });
  },

  stopPicking: () => {
    set({ isPickingElement: false });
  },

  togglePicking: () => {
    set((state) => ({ isPickingElement: !state.isPickingElement }));
  },

  stageAnnotation: (item) => {
    const newAnnotation: ElementAnnotationItem = {
      ...item,
      id: `ann-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      createdAt: Date.now(),
      status: 'pending',
    };

    set((state) => ({
      stagedAnnotations: [...state.stagedAnnotations, newAnnotation],
      selectedAnnotationId: newAnnotation.id,
      isDrawerOpen: true,
      isPickingElement: false,
    }));
  },

  updateAnnotationInstruction: (id: string, newInstruction: string) => {
    set((state) => ({
      stagedAnnotations: state.stagedAnnotations.map((ann) => {
        if (ann.id === id) {
          return { ...ann, instruction: newInstruction };
        }
        return ann;
      }),
    }));
  },

  removeAnnotation: (id: string) => {
    set((state) => {
      const remaining = state.stagedAnnotations.filter((ann) => ann.id !== id);
      return {
        stagedAnnotations: remaining,
        selectedAnnotationId:
          state.selectedAnnotationId === id ? null : state.selectedAnnotationId,
        isDrawerOpen: remaining.length > 0 ? state.isDrawerOpen : false,
      };
    });
  },

  clearStaged: () => {
    set({
      stagedAnnotations: [],
      selectedAnnotationId: null,
      isDrawerOpen: false,
    });
  },

  packageAndDispatch: (artifactId: string) => {
    const { stagedAnnotations } = get();
    if (stagedAnnotations.length === 0) {
      return null;
    }

    const payload = createStagedBatchPayload(artifactId, stagedAnnotations);

    set({
      activeBatch: payload,
      stagedAnnotations: payload.annotations,
      isDrawerOpen: false,
      selectedAnnotationId: null,
    });

    return payload;
  },

  markAnnotationResolved: (id: string) => {
    set((state) => {
      const updateList = (list: ElementAnnotationItem[]) =>
        list.map((ann) => {
          if (ann.id === id) {
            return {
              ...ann,
              status: 'resolved' as const,
              resolvedAt: Date.now(),
            };
          }
          return ann;
        });

      const updatedStaged = updateList(state.stagedAnnotations);
      const updatedActiveBatch = state.activeBatch
        ? {
            ...state.activeBatch,
            annotations: updateList(state.activeBatch.annotations),
          }
        : null;

      return {
        stagedAnnotations: updatedStaged,
        activeBatch: updatedActiveBatch,
      };
    });
  },

  markAnnotationFailed: (id: string) => {
    set((state) => {
      const updateList = (list: ElementAnnotationItem[]) =>
        list.map((ann) => {
          if (ann.id === id) {
            return { ...ann, status: 'failed' as const };
          }
          return ann;
        });

      return {
        stagedAnnotations: updateList(state.stagedAnnotations),
        activeBatch: state.activeBatch
          ? {
              ...state.activeBatch,
              annotations: updateList(state.activeBatch.annotations),
            }
          : null,
      };
    });
  },

  toggleDrawer: (open?: boolean) => {
    set((state) => ({
      isDrawerOpen: typeof open === 'boolean' ? open : !state.isDrawerOpen,
    }));
  },

  selectAnnotation: (id: string | null) => {
    set({ selectedAnnotationId: id });
  },

  reset: () => {
    set({
      stagedAnnotations: [],
      activeBatch: null,
      isDrawerOpen: false,
      selectedAnnotationId: null,
      isPickingElement: false,
    });
  },
}));
