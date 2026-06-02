import { create } from 'zustand';

import type { SettingsTab } from '@/components/ui/settings/SettingsMenu';

type SaveFn = () => Promise<boolean>;

interface SettingsDirtyState {
  _dirtyTabs: Map<SettingsTab, SaveFn>;

  markDirty: (tab: SettingsTab, saveFn: SaveFn) => void;
  markClean: (tab: SettingsTab) => void;
  isDirty: (tab: SettingsTab) => boolean;
  isDirtyAny: () => boolean;
  autoSaveAll: () => Promise<boolean>;
}

const useSettingsDirtyStore = create<SettingsDirtyState>((set, get) => ({
  _dirtyTabs: new Map(),

  markDirty: (tab, saveFn) => {
    set((state) => {
      const next = new Map(state._dirtyTabs);
      next.set(tab, saveFn);
      return { _dirtyTabs: next };
    });
  },

  markClean: (tab) => {
    set((state) => {
      if (!state._dirtyTabs.has(tab)) return state;
      const next = new Map(state._dirtyTabs);
      next.delete(tab);
      return { _dirtyTabs: next };
    });
  },

  isDirty: (tab) => get()._dirtyTabs.has(tab),

  isDirtyAny: () => get()._dirtyTabs.size > 0,

  autoSaveAll: async () => {
    const entries = Array.from(get()._dirtyTabs.entries());
    if (entries.length === 0) return true;

    const results = await Promise.allSettled(
      entries.map(async ([tab, saveFn]) => {
        const ok = await saveFn();
        if (ok) get().markClean(tab);
        return ok;
      }),
    );

    return results.every((r) => r.status === 'fulfilled' && r.value === true);
  },
}));

export default useSettingsDirtyStore;
