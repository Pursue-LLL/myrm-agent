/**
 * [INPUT]
 * @/components/features/presentation/PresentationGeneratorModal (POS: Presentation generator modal)
 * UTILITY_PANEL_EVENTS.presentation ('myrm:open-presentation') dispatched by the nav rail's Tools menu
 *
 * [OUTPUT]
 * - PresentationTrigger: global shortcut and open-event host of the Presentation generator dialog
 *
 * [POS]
 * Presentation entrance (Item 16). The visible entrance is the Tools menu in the nav rail.
 * Single file < 90 lines. Zero `any` types.
 */

'use client';

import React, { useState, useEffect } from 'react';
import { PresentationGeneratorModal } from './PresentationGeneratorModal';
import { UTILITY_PANEL_EVENTS } from '@/lib/utilityPanelEvents';

export const PresentationTrigger: React.FC = () => {
  const [isOpen, setIsOpen] = useState<boolean>(false);

  // Global keyboard shortcut: Option+Cmd+P (Mac) or Alt+Ctrl+P (Win/Linux)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isAltOrOption = e.altKey;
      const isMetaOrCtrl = e.metaKey || e.ctrlKey;
      // macOS rewrites `key` while Option is held (Option+P yields 'π'), so match the physical `code` first.
      // The modifier checks stay in front so `key` is only read for real shortcut presses.
      if (isAltOrOption && isMetaOrCtrl && (e.code === 'KeyP' || e.key.toLowerCase() === 'p')) {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };

    const handleCustomOpen = () => setIsOpen(true);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener(UTILITY_PANEL_EVENTS.presentation, handleCustomOpen);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener(UTILITY_PANEL_EVENTS.presentation, handleCustomOpen);
    };
  }, []);

  return <PresentationGeneratorModal isOpen={isOpen} onClose={() => setIsOpen(false)} />;
};
