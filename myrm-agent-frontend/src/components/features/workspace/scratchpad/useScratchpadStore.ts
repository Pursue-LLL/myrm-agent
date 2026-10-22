import { create } from 'zustand';
import type {
  PromoteScratchpadPayload,
  PromotedProjectResponse,
  ScratchpadDraftState,
  ScratchpadStoreState,
} from './scratchpadTypes';

const STORAGE_KEY = 'myrm:scratchpad:draft';

function loadInitialDraft(): ScratchpadDraftState {
  if (typeof window === 'undefined') {
    return {
      title: '',
      content: '',
      temporaryTags: [],
      updatedAt: new Date().toISOString(),
    };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ScratchpadDraftState>;
      return {
        title: parsed.title ?? '',
        content: parsed.content ?? '',
        temporaryTags: Array.isArray(parsed.temporaryTags) ? parsed.temporaryTags : [],
        updatedAt: parsed.updatedAt ?? new Date().toISOString(),
      };
    }
  } catch {
    // Graceful fallback on storage access denial or malformed json
  }
  return {
    title: '',
    content: '',
    temporaryTags: [],
    updatedAt: new Date().toISOString(),
  };
}

function persistDraft(draft: ScratchpadDraftState): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  } catch {
    // Ignore storage quota errors
  }
}

export const useScratchpadStore = create<ScratchpadStoreState>((set, get) => ({
  isOpen: false,
  draft: loadInitialDraft(),
  isPromoting: false,
  promotionResult: null,
  error: null,

  openScratchpad: () => {
    set({ isOpen: true, error: null });
  },

  closeScratchpad: () => {
    set({ isOpen: false });
  },

  setTitle: (title: string) => {
    const current = get().draft;
    const next: ScratchpadDraftState = {
      ...current,
      title,
      updatedAt: new Date().toISOString(),
    };
    persistDraft(next);
    set({ draft: next });
  },

  setContent: (content: string) => {
    const current = get().draft;
    const next: ScratchpadDraftState = {
      ...current,
      content,
      updatedAt: new Date().toISOString(),
    };
    persistDraft(next);
    set({ draft: next });
  },

  setTags: (tags: string[]) => {
    const current = get().draft;
    const next: ScratchpadDraftState = {
      ...current,
      temporaryTags: tags,
      updatedAt: new Date().toISOString(),
    };
    persistDraft(next);
    set({ draft: next });
  },

  clearDraft: () => {
    const fresh: ScratchpadDraftState = {
      title: '',
      content: '',
      temporaryTags: [],
      updatedAt: new Date().toISOString(),
    };
    persistDraft(fresh);
    set({ draft: fresh, promotionResult: null, error: null });
  },

  promoteToProject: async (customProjectName?: string): Promise<PromotedProjectResponse> => {
    const { draft } = get();
    if (!draft.title.trim() && !draft.content.trim()) {
      const err = 'Cannot promote empty scratchpad';
      set({ error: err });
      throw new Error(err);
    }

    set({ isPromoting: true, error: null });

    const payload: PromoteScratchpadPayload = {
      title: draft.title.trim() || 'Untitled Scratchpad',
      content: draft.content.trim() || 'No initial content.',
      target_project_name: customProjectName?.trim() || null,
      init_readme: true,
      temporary_tags: draft.temporaryTags,
    };

    try {
      const res = await fetch('/api/v1/workspace/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errDetail = await res.text();
        throw new Error(errDetail || `Promotion failed with status ${res.status}`);
      }

      const data = (await res.json()) as PromotedProjectResponse;
      set({
        isPromoting: false,
        promotionResult: data,
        error: null,
      });
      return data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      set({ isPromoting: false, error: message });
      throw err;
    }
  },
}));
