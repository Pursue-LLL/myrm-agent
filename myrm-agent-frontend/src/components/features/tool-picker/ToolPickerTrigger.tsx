/**
 * [INPUT]
 * @/components/features/tool-picker/CategorizedToolPickerDrawer::CategorizedToolPickerDrawer
 * @/components/features/icons/PremiumIcons (IconWrench)
 * next-intl::useTranslations
 *
 * [OUTPUT]
 * - ToolPickerTrigger: Floating HUD trigger capsule and shortcut listener for tool picker
 *
 * [POS]
 * Trigger HUD for CategorizedToolPickerWithPinningAndInstantFilter (Item 15).
 * Single file < 120 lines. Zero `any` types.
 */

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { CategorizedToolPickerDrawer } from './CategorizedToolPickerDrawer';
import { IconWrench } from '@/components/features/icons/PremiumIcons';

interface ToolPickerTriggerProps {
  /** 菜单内使用时只保留快捷键/事件监听与抽屉。 */
  showTrigger?: boolean;
}

export const ToolPickerTrigger: React.FC<ToolPickerTriggerProps> = ({ showTrigger = true }) => {
  const t = useTranslations('toolPicker');
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
    window.addEventListener('myrm:open-tool-picker', handleCustomOpen);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('myrm:open-tool-picker', handleCustomOpen);
    };
  }, []);

  const handleOpen = useCallback(() => {
    setIsOpen(true);
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  return (
    <>
      {/* Floating HUD Capsule Bar */}
      {showTrigger && (
        <div className="fixed bottom-4 right-48 z-40 flex items-center">
          <button
            type="button"
            onClick={handleOpen}
            title={t('triggerTooltip')}
            aria-label={t('triggerAriaLabel')}
            className="group flex items-center gap-2 px-3 py-1.5 rounded-full border border-zinc-200/80 bg-white/90 shadow-md backdrop-blur-md transition-all hover:bg-zinc-50 hover:shadow-lg active:scale-95 dark:border-zinc-800/80 dark:bg-zinc-900/90 dark:hover:bg-zinc-800"
          >
            <IconWrench className="w-3.5 h-3.5 text-zinc-600 dark:text-zinc-400 group-hover:rotate-45 transition-transform" />
            <span className="text-xs font-mono font-medium text-zinc-700 dark:text-zinc-300">Tools</span>
            <span className="text-[10px] px-1 py-0.2 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-400 dark:text-zinc-500 font-mono">
              ⌘⇧T
            </span>
          </button>
        </div>
      )}

      {/* Categorized Tool Drawer */}
      <CategorizedToolPickerDrawer isOpen={isOpen} onClose={handleClose} />
    </>
  );
};
