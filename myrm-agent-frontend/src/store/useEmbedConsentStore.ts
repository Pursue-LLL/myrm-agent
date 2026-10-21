import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type EmbedMode = 'always' | 'ask' | 'off';

interface EmbedConsentState {
  embedMode: EmbedMode;
  allowedProviders: string[];
  setEmbedMode: (mode: EmbedMode) => void;
  allowProvider: (provider: string) => void;
  revokeProvider: (provider: string) => void;
  clearAllowed: () => void;
}

const useEmbedConsentStore = create<EmbedConsentState>()(
  persist(
    (set, get) => ({
      embedMode: 'ask',
      allowedProviders: [],
      setEmbedMode: (mode) => set({ embedMode: mode }),
      allowProvider: (provider) => {
        const current = get().allowedProviders;
        if (!current.includes(provider)) {
          set({ allowedProviders: [...current, provider] });
        }
      },
      revokeProvider: (provider) => {
        set({ allowedProviders: get().allowedProviders.filter((p) => p !== provider) });
      },
      clearAllowed: () => set({ allowedProviders: [] }),
    }),
    { name: 'myrm-embed-consent' },
  ),
);

export default useEmbedConsentStore;
