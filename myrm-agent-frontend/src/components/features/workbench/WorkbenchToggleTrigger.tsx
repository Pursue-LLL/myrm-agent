'use client';

/**
 * [INPUT]
 * - useWorkbenchStore from @/store/useWorkbenchStore
 * - Global hotkey (Cmd+Shift+B / Ctrl+Shift+B)
 * - UTILITY_PANEL_EVENTS.workbench ('myrm:open-workbench') dispatched by the nav rail's Tools menu
 *
 * [OUTPUT]
 * - WorkbenchToggleTrigger: renders nothing; keeps the workbench hotkey and open event alive
 *
 * [POS]
 * Global entrance for the Auxiliary Workbench (Item 25). The visible entrance is the Tools menu in the nav rail.
 * Zero `any` types. Zero native emoji.
 */

import { useEffect } from 'react';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import { UTILITY_PANEL_EVENTS } from '@/lib/utilityPanelEvents';

export function WorkbenchToggleTrigger() {
  const toggleOpen = useWorkbenchStore((s) => s.toggleOpen);
  const setOpen = useWorkbenchStore((s) => s.setOpen);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+Shift+B or Ctrl+Shift+B to toggle workbench
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        toggleOpen();
      }
    };

    const handleCustomOpen = () => setOpen(true);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener(UTILITY_PANEL_EVENTS.workbench, handleCustomOpen);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener(UTILITY_PANEL_EVENTS.workbench, handleCustomOpen);
    };
  }, [toggleOpen, setOpen]);

  return null;
}
