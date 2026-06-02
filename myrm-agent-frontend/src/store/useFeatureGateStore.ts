import { create } from 'zustand';

interface FeatureStatusItem {
  id: string;
  enabled: boolean;
}

interface FeatureGateState {
  enabledFeatures: Set<string>;
  initialized: boolean;
  loadFeatures: () => Promise<void>;
  isEnabled: (featureId: string) => boolean;
}

export const useFeatureGateStore = create<FeatureGateState>((set, get) => ({
  enabledFeatures: new Set(),
  initialized: false,
  loadFeatures: async () => {
    try {
      const res = await fetch('/api/v1/features');
      if (res.ok) {
        const data = await res.json();
        const enabled = new Set<string>();
        if (data && Array.isArray(data.features)) {
          data.features.forEach((f: FeatureStatusItem) => {
            if (f.enabled) enabled.add(f.id);
          });
        }
        set({ enabledFeatures: enabled, initialized: true });
      }
    } catch (e) {
      console.warn('Failed to load feature gates:', e);
    }
  },
  isEnabled: (featureId: string) => {
    return get().enabledFeatures.has(featureId);
  },
}));
