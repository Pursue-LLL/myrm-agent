/**
 * [INPUT]
 * @/components/features/tool-picker/CategorizedToolPickerDrawer::CategorizedToolPickerDrawer
 * UTILITY_PANEL_EVENTS.toolPicker ('myrm:open-tool-picker') dispatched by the nav rail's Tools menu
 *
 * [OUTPUT]
 * - ToolPickerTrigger: global shortcut and open-event host of the tool picker drawer
 *
 * [POS]
 * Entrance for CategorizedToolPickerWithPinningAndInstantFilter (Item 15). The visible entrance is the Tools menu in the nav rail.
 * Single file < 120 lines. Zero `any` types.
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { CategorizedToolPickerDrawer } from './CategorizedToolPickerDrawer';
import { UTILITY_PANEL_EVENTS } from '@/lib/utilityPanelEvents';

export const ToolPickerTrigger: React.FC = () => {
  const [isOpen, setIsOpen] = useState<boolean>(false);

  // Shortcut Cmd+Shift+T / Ctrl+Shift+T to toggle tool picker drawer
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 't') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };
    const handleCustomOpen = () => setIsOpen(true);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener(UTILITY_PANEL_EVENTS.toolPicker, handleCustomOpen);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener(UTILITY_PANEL_EVENTS.toolPicker, handleCustomOpen);
    };
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  return <CategorizedToolPickerDrawer isOpen={isOpen} onClose={handleClose} />;
};
