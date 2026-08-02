import { create } from 'zustand';

interface ThemePackagePendingState {
  pendingFile: File | null;
  setPendingFile: (file: File) => void;
  clearPendingFile: () => void;
}

const useThemePackagePendingStore = create<ThemePackagePendingState>((set) => ({
  pendingFile: null,
  setPendingFile: (file) => set({ pendingFile: file }),
  clearPendingFile: () => set({ pendingFile: null }),
}));

export default useThemePackagePendingStore;
