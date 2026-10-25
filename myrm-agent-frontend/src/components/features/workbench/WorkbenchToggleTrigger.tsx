'use client';

/**
 * [INPUT]
 * - useWorkbenchStore from @/store/useWorkbenchStore
 * - useTranslations from next-intl (namespace: 'workbench')
 * - Global hotkey (Cmd+Shift+B / Ctrl+Shift+B)
 * - CustomEvent 'myrm:open-workbench'
 *
 * [OUTPUT]
 * - WorkbenchToggleTrigger: Floating HUD capsule button toggling MultiTabWorkbench
 *
 * [POS]
 * Trigger entrance for Auxiliary Workbench (Item 25).
 * Single file < 120 lines. Zero `any` types. Zero native emoji.
 */

import React, { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';

interface WorkbenchToggleTriggerProps {
  /** 菜单内使用时只保留快捷键监听，不再渲染悬浮胶囊。 */
  showTrigger?: boolean;
}

export function WorkbenchToggleTrigger({ showTrigger = true }: WorkbenchToggleTriggerProps = {}) {
  const t = useTranslations('workbench');
  const isOpen = useWorkbenchStore((s) => s.isOpen);
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
    window.addEventListener('myrm:open-workbench', handleCustomOpen);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('myrm:open-workbench', handleCustomOpen);
    };
  }, [toggleOpen, setOpen]);

  if (!showTrigger) {
    return null;
  }

  return (
    <aside
      data-workbench-trigger="true"
      aria-label={t('triggerAriaLabel')}
      className="fixed bottom-6 right-80 z-[9985] flex items-center select-none"
    >
      <button
        type="button"
        onClick={toggleOpen}
        className={`flex items-center gap-2 px-3 py-2 rounded-full text-xs font-medium shadow-xl backdrop-blur-md transition-all border ${
          isOpen
            ? 'bg-primary text-primary-foreground border-primary ring-2 ring-primary/40'
            : 'bg-card/90 text-foreground border-border/80 hover:bg-card hover:border-primary/50'
        }`}
        title={t('toggleHint')}
      >
        {isOpen ? (
          <PanelRightClose className="w-4 h-4 text-primary-foreground" />
        ) : (
          <PanelRightOpen className="w-4 h-4 text-primary" />
        )}
        <span>{isOpen ? t('hudActive') : t('hudTrigger')}</span>
        <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono rounded bg-background/60 border border-border/40 text-muted-foreground">
          {t('shortcutHint')}
        </kbd>
      </button>
    </aside>
  );
}
