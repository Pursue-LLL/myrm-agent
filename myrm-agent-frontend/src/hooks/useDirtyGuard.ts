import { useEffect, useRef } from 'react';

import type { SettingsTab } from '@/components/ui/settings/SettingsMenu';
import useSettingsDirtyStore from '@/store/useSettingsDirtyStore';

interface UseDirtyGuardOptions {
  isDirty: boolean;
  onSave: () => Promise<boolean>;
}

/**
 * Registers a settings section's dirty state with the global store.
 *
 * When `isDirty` is true the tab is marked dirty with the provided `onSave`.
 * When the component unmounts or `isDirty` flips to false the tab is cleaned.
 * Also registers a `beforeunload` handler to warn the user when closing
 * the browser tab with unsaved changes.
 */
export function useDirtyGuard(tab: SettingsTab, { isDirty, onSave }: UseDirtyGuardOptions): void {
  const saveFnRef = useRef(onSave);
  saveFnRef.current = onSave;

  const stableSave = useRef(async () => saveFnRef.current()).current;

  useEffect(() => {
    const { markDirty, markClean } = useSettingsDirtyStore.getState();
    if (isDirty) {
      markDirty(tab, stableSave);
    } else {
      markClean(tab);
    }
  }, [isDirty, tab, stableSave]);

  useEffect(() => {
    return () => useSettingsDirtyStore.getState().markClean(tab);
  }, [tab]);

  useEffect(() => {
    if (!isDirty) return;

    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };

    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);
}
