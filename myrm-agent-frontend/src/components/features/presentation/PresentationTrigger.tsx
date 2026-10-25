/**
 * [INPUT]
 * @/components/features/presentation/PresentationGeneratorModal (POS: Presentation generator modal)
 * react-i18next::useTranslation (POS: Internationalization hook)
 *
 * [OUTPUT]
 * - PresentationTrigger: HUD floating pill & shortcut trigger for Presentation generator
 *
 * [POS]
 * Presentation HUD Trigger Component (Item 16).
 * Single file < 90 lines. Zero `any` types.
 */

'use client';

import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { PresentationGeneratorModal } from './PresentationGeneratorModal';

interface PresentationTriggerProps {
  /** 菜单内使用时只保留快捷键/事件监听与生成器弹层。 */
  showTrigger?: boolean;
}

export const PresentationTrigger: React.FC<PresentationTriggerProps> = ({ showTrigger = true }) => {
  const t = useTranslations('presentation');
  const [isOpen, setIsOpen] = useState<boolean>(false);

  // Global keyboard shortcut: Option+Cmd+P (Mac) or Alt+Ctrl+P (Win/Linux)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isAltOrOption = e.altKey;
      const isMetaOrCtrl = e.metaKey || e.ctrlKey;
      if (isAltOrOption && isMetaOrCtrl && (e.key === 'p' || e.key === 'P')) {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };

    const handleCustomOpen = () => setIsOpen(true);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('myrm:open-presentation', handleCustomOpen);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('myrm:open-presentation', handleCustomOpen);
    };
  }, []);

  return (
    <>
      {showTrigger && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          aria-label={t('triggerAriaLabel')}
          title={t('triggerTooltip')}
          className="fixed bottom-20 right-6 z-40 flex items-center gap-2 px-3 py-2 rounded-full bg-slate-900/90 hover:bg-slate-800 text-slate-200 border border-blue-500/30 hover:border-blue-400 shadow-xl backdrop-blur-md transition-all group focus:outline-none focus:ring-2 focus:ring-blue-500/50"
        >
          <div className="w-5 h-5 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center group-hover:scale-110 transition-transform">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"
              />
            </svg>
          </div>
          <span className="text-xs font-semibold tracking-wide text-slate-100 hidden sm:inline">PPT</span>
          <span className="text-[10px] font-mono font-medium px-1.5 py-0.5 rounded bg-white/10 text-slate-400 group-hover:text-slate-200 hidden md:inline">
            ⌥⌘P
          </span>
        </button>
      )}

      <PresentationGeneratorModal isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
};
