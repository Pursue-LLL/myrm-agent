import { create } from 'zustand';
import type { ThemeProfileRecipe } from '@/theme-engine/schema';

interface ThemeStudioDomPreviewPayload {
  profile: ThemeProfileRecipe;
  mediaUrl: string | null;
  posterUrl: string | null;
}

interface ThemeStudioDomPreviewState {
  enabled: boolean;
  profile: ThemeProfileRecipe | null;
  mediaUrl: string | null;
  posterUrl: string | null;
  setPreview: (payload: ThemeStudioDomPreviewPayload) => void;
  clearPreview: () => void;
}

const useThemeStudioDomPreviewStore = create<ThemeStudioDomPreviewState>((set) => ({
  enabled: false,
  profile: null,
  mediaUrl: null,
  posterUrl: null,
  setPreview: ({ profile, mediaUrl, posterUrl }) =>
    set({ enabled: true, profile, mediaUrl, posterUrl }),
  clearPreview: () => set({ enabled: false, profile: null, mediaUrl: null, posterUrl: null }),
}));

export default useThemeStudioDomPreviewStore;
