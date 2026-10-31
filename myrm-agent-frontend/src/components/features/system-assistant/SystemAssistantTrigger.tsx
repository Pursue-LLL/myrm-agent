'use client';

/**
 * [INPUT]
 * - Keyboard events (Cmd+J / Ctrl+J)
 * - UTILITY_PANEL_EVENTS.assistant ('myrm:open-system-assistant') dispatched by the nav rail's Tools menu
 * - SystemAssistantModal from ./SystemAssistantModal
 *
 * [OUTPUT]
 * - SystemAssistantTrigger: global shortcut and open-event host of the XiaoMo assistant hub
 *
 * [POS]
 * Entrance for XiaoMo Unified Natural Language Control Center. The visible entrance is the Tools menu in the nav rail.
 * Strict typing: Zero `any`. File length < 120 lines.
 */

import { useState, useEffect, useCallback } from 'react';
import { SystemAssistantModal } from './SystemAssistantModal';
import { UTILITY_PANEL_EVENTS } from '@/lib/utilityPanelEvents';

export function SystemAssistantTrigger() {
  const [isOpen, setIsOpen] = useState<boolean>(false);

  // Global shortcut listener: Cmd+J / Ctrl+J
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };

    const handleCustomOpen = () => setIsOpen(true);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener(UTILITY_PANEL_EVENTS.assistant, handleCustomOpen);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener(UTILITY_PANEL_EVENTS.assistant, handleCustomOpen);
    };
  }, [isOpen]);

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  return <SystemAssistantModal isOpen={isOpen} onClose={handleClose} />;
}
