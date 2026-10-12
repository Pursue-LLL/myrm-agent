'use client';

/**
 * [INPUT]
 * - Keyboard events (Cmd+J / Ctrl+J)
 * - Translation strings from 'systemAssistant' namespace
 * - SystemAssistantModal from ./SystemAssistantModal
 *
 * [OUTPUT]
 * - SystemAssistantTrigger: Global floating trigger and shortcut listener for XiaoMo assistant hub
 *
 * [POS]
 * Trigger and HUD anchor for XiaoMo Unified Natural Language Control Center.
 * Strict typing: Zero `any`. File length < 120 lines.
 */

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconBrain,
  IconSparkles,
} from '@/components/features/icons/PremiumIcons';
import { SystemAssistantModal } from './SystemAssistantModal';

export function SystemAssistantTrigger() {
  const t = useTranslations('systemAssistant');
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

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  return (
    <>
      {/* Floating HUD Launcher Button */}
      <aside
        aria-label={t('launcherAriaLabel')}
        className="fixed bottom-6 left-6 z-[9990] flex items-center select-none"
      >
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-2 px-3.5 py-2 rounded-full text-xs font-medium shadow-lg backdrop-blur-md bg-card/90 text-foreground border border-border/80 hover:bg-card hover:border-primary/50 ring-1 ring-border/20 hover:ring-primary/30 transition-all"
          title={t('launcherTooltip')}
        >
          <div className="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold">
            <IconBrain className="w-3.5 h-3.5" />
          </div>
          <span>{t('assistantName')}</span>
          <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono rounded bg-background/60 border border-border/40 text-muted-foreground">
            {t('shortcutHint')}
          </kbd>
        </button>
      </aside>

      {/* XiaoMo Natural Language Hub Modal */}
      <SystemAssistantModal isOpen={isOpen} onClose={handleClose} />
    </>
  );
}
