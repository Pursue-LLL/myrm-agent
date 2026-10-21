import { create } from 'zustand';
import { createStudioDraft } from '@/components/features/theme-studio/studio-profile';
import type { ThemeProfileRecipe } from '@/theme-engine';

const STORAGE_KEY = 'myrm-theme-studio-draft-v1';

interface PersistedDraft {
  draft: ThemeProfileRecipe;
  step: BuilderStep;
  previewAssetUrl: string | null;
  editingProfileId: string | null;
}

export type BuilderStep = 1 | 2 | 3 | 4;

interface ThemeStudioDraftState {
  draft: ThemeProfileRecipe;
  step: BuilderStep;
  previewAssetUrl: string | null;
  editingProfileId: string | null;
  dirty: boolean;
  setStep: (step: BuilderStep) => void;
  patchDraft: (patch: Partial<ThemeProfileRecipe>) => void;
  replaceDraft: (draft: ThemeProfileRecipe, editingProfileId?: string | null) => void;
  setPreviewAssetUrl: (url: string | null) => void;
  resetDraft: () => void;
  hydrateFromStorage: () => void;
  persistToStorage: () => void;
  clearStorage: () => void;
}

function readStorage(): PersistedDraft | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as PersistedDraft;
  } catch {
    return null;
  }
}

function writeStorage(payload: PersistedDraft): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Ignore quota errors — draft remains in memory.
  }
}

export const useThemeStudioDraftStore = create<ThemeStudioDraftState>((set, get) => ({
  draft: createStudioDraft(),
  step: 1,
  previewAssetUrl: null,
  editingProfileId: null,
  dirty: false,
  setStep: (step) => {
    set({ step });
    get().persistToStorage();
  },
  patchDraft: (patch) => {
    set((state) => ({
      draft: { ...state.draft, ...patch },
      dirty: true,
    }));
    get().persistToStorage();
  },
  replaceDraft: (draft, editingProfileId = null) => {
    set({
      draft,
      editingProfileId,
      dirty: false,
      step: draft.art.mediaKind === 'none' ? 1 : 2,
    });
    get().persistToStorage();
  },
  setPreviewAssetUrl: (previewAssetUrl) => {
    set({ previewAssetUrl });
    get().persistToStorage();
  },
  resetDraft: () => {
    set({
      draft: createStudioDraft(),
      step: 1,
      previewAssetUrl: null,
      editingProfileId: null,
      dirty: false,
    });
    get().clearStorage();
  },
  hydrateFromStorage: () => {
    const saved = readStorage();
    if (!saved) {
      return;
    }
    set({
      draft: saved.draft,
      step: saved.step,
      previewAssetUrl: saved.previewAssetUrl,
      editingProfileId: saved.editingProfileId,
      dirty: true,
    });
  },
  persistToStorage: () => {
    const { draft, step, previewAssetUrl, editingProfileId } = get();
    writeStorage({ draft, step, previewAssetUrl, editingProfileId });
  },
  clearStorage: () => {
    if (typeof window === 'undefined') {
      return;
    }
    window.sessionStorage.removeItem(STORAGE_KEY);
  },
}));

export default useThemeStudioDraftStore;
