'use client';

/**
 * [INPUT]
 * - localStorage ('myrm_workspace_layout_mode')
 * - Window custom event 'myrm:workspace-layout-changed' for cross-component sync
 *
 * [OUTPUT]
 * - PresetLayoutMode: 'copilot' | 'multi_agent' | 'remote_compute' | 'easy_minimal'
 * - useWorkspaceLayoutMode: Custom hook managing active workspace layout preset and persistence
 *
 * [POS]
 * State management hook for Four Preset Workspace Layout Switcher.
 * Strict typing: Zero `any`. File length < 100 lines.
 */

import { useState, useEffect, useCallback } from 'react';

export type PresetLayoutMode =
  | 'copilot'
  | 'multi_agent'
  | 'remote_compute'
  | 'easy_minimal';

export const WORKSPACE_LAYOUT_STORAGE_KEY = 'myrm_workspace_layout_mode';
export const DEFAULT_LAYOUT_MODE: PresetLayoutMode = 'easy_minimal';

const VALID_MODES: PresetLayoutMode[] = [
  'copilot',
  'multi_agent',
  'remote_compute',
  'easy_minimal',
];

export function useWorkspaceLayoutMode() {
  const [layoutMode, setLayoutModeState] = useState<PresetLayoutMode>(() => {
    if (typeof window === 'undefined') {
      return DEFAULT_LAYOUT_MODE;
    }
    const saved = localStorage.getItem(WORKSPACE_LAYOUT_STORAGE_KEY) as PresetLayoutMode | null;
    return saved && VALID_MODES.includes(saved) ? saved : DEFAULT_LAYOUT_MODE;
  });

  const setLayoutMode = useCallback((mode: PresetLayoutMode) => {
    setLayoutModeState(mode);
    if (typeof window !== 'undefined') {
      localStorage.setItem(WORKSPACE_LAYOUT_STORAGE_KEY, mode);
      window.dispatchEvent(
        new CustomEvent('myrm:workspace-layout-changed', { detail: { mode } }),
      );
    }
  }, []);

  // Listen to cross-component layout change events
  useEffect(() => {
    const handleSync = (e: Event) => {
      const customEvent = e as CustomEvent<{ mode: PresetLayoutMode }>;
      if (customEvent.detail?.mode && VALID_MODES.includes(customEvent.detail.mode)) {
        setLayoutModeState(customEvent.detail.mode);
      }
    };

    window.addEventListener('myrm:workspace-layout-changed', handleSync);
    return () => {
      window.removeEventListener('myrm:workspace-layout-changed', handleSync);
    };
  }, []);

  const resetLayout = useCallback(() => {
    setLayoutMode(DEFAULT_LAYOUT_MODE);
  }, [setLayoutMode]);

  return {
    layoutMode,
    setLayoutMode,
    resetLayout,
    isCopilot: layoutMode === 'copilot',
    isMultiAgent: layoutMode === 'multi_agent',
    isRemoteCompute: layoutMode === 'remote_compute',
    isEasyMinimal: layoutMode === 'easy_minimal',
  };
}
