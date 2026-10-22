import { create } from 'zustand';
import {
  CanvasInteractionMode,
  VisualCommentPin,
  ElementStylePatch,
  InSituInspectionTarget,
} from './insituAnnotationTypes';

interface InsituAnnotationState {
  artifactId: string;
  mode: CanvasInteractionMode;
  comments: VisualCommentPin[];
  stylePatches: ElementStylePatch[];
  activeCommentId: string | null;
  inspectionTarget: InSituInspectionTarget | null;
  isRailOpen: boolean;

  setArtifactId: (id: string) => void;
  setMode: (mode: CanvasInteractionMode) => void;
  setInspectionTarget: (target: InSituInspectionTarget | null) => void;
  upsertStylePatch: (patch: ElementStylePatch) => void;
  removeStylePatch: (selector: string) => void;
  addCommentPin: (
    pinData: Omit<VisualCommentPin, 'id' | 'index' | 'createdAt'>
  ) => VisualCommentPin;
  updateCommentPinText: (id: string, text: string) => void;
  removeCommentPin: (id: string) => void;
  setActiveCommentId: (id: string | null) => void;
  toggleRail: () => void;
  clearAll: () => void;
}

export const useInsituAnnotationStore = create<InsituAnnotationState>((set, get) => ({
  artifactId: 'artifact-default',
  mode: 'comment',
  comments: [],
  stylePatches: [],
  activeCommentId: null,
  inspectionTarget: null,
  isRailOpen: true,

  setArtifactId: (artifactId) => set({ artifactId }),

  setMode: (mode) =>
    set({
      mode,
      inspectionTarget: mode !== 'inspect' ? null : get().inspectionTarget,
    }),

  setInspectionTarget: (inspectionTarget) => set({ inspectionTarget }),

  upsertStylePatch: (patch) =>
    set((state) => {
      const filtered = state.stylePatches.filter((p) => p.selector !== patch.selector);
      return { stylePatches: [...filtered, patch] };
    }),

  removeStylePatch: (selector) =>
    set((state) => ({
      stylePatches: state.stylePatches.filter((p) => p.selector !== selector),
    })),

  addCommentPin: (pinData) => {
    const { comments } = get();
    const nextIndex = comments.length + 1;
    const newPin: VisualCommentPin = {
      ...pinData,
      id: `pin-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      index: nextIndex,
      createdAt: new Date().toLocaleTimeString(),
    };
    set({
      comments: [...comments, newPin],
      activeCommentId: newPin.id,
      isRailOpen: true,
    });
    return newPin;
  },

  updateCommentPinText: (id, text) =>
    set((state) => ({
      comments: state.comments.map((c) =>
        c.id === id ? { ...c, commentText: text } : c
      ),
    })),

  removeCommentPin: (id) =>
    set((state) => {
      const remaining = state.comments.filter((c) => c.id !== id);
      // 重新对序号从 1 开始整理
      const reindexed = remaining.map((c, idx) => ({
        ...c,
        index: idx + 1,
      }));
      return {
        comments: reindexed,
        activeCommentId:
          state.activeCommentId === id ? null : state.activeCommentId,
      };
    }),

  setActiveCommentId: (activeCommentId) => set({ activeCommentId }),

  toggleRail: () => set((state) => ({ isRailOpen: !state.isRailOpen })),

  clearAll: () =>
    set({
      comments: [],
      stylePatches: [],
      activeCommentId: null,
      inspectionTarget: null,
    }),
}));
