import { create } from 'zustand';

export interface ScopedArtifactTarget {
  artifactId: string;
  artifactName: string;
  kind?: 'code' | 'document' | 'spreadsheet' | 'general';
  scopeLabel: string; // e.g. "L12-L35", "Sheet1!B2:E15", "§ 核心设计"
  selectedSnippet?: string;
}

interface ScopedArtifactState {
  target: ScopedArtifactTarget | null;
  setTarget: (target: ScopedArtifactTarget) => void;
  clearTarget: () => void;
}

export const useScopedArtifactStore = create<ScopedArtifactState>((set) => ({
  target: null,
  setTarget: (target) => set({ target }),
  clearTarget: () => set({ target: null }),
}));

export default useScopedArtifactStore;
