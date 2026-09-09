'use client';

/**
 * [INPUT]
 * @/store/useBrowserInspectorStore::useBrowserInspectorStore (POS: Browser Inspector state management; selectScopedBrowserViewData)
 * @/store/useChatStore::useChatStore (POS: Active chat session identification)
 *
 * [OUTPUT]
 * BrowserInspectorToggle: Floating toggle button with hover micro peek thumbnail.
 *
 * [POS]
 * Browser Inspector satellite control. Renders toggle button and desktop hover micro peek thumbnail.
 */

import React, { useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { ScanSearch } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useBrowserInspectorStore, { selectScopedBrowserViewData } from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';

const BrowserInspectorToggle: React.FC = () => {
  const t = useTranslations('chat.browserInspector');
  const { isBrowserActive, isOpen, togglePanel, viewData, terminalViewData } = useBrowserInspectorStore();
  const chatId = useChatStore((state) => state.chatId?.trim() ?? '');
  const [isHovered, setIsHovered] = useState(false);

  const effectiveViewData = viewData ?? terminalViewData;
  const scopedViewData = selectScopedBrowserViewData(effectiveViewData, chatId);
  const hasScopedView = Boolean(scopedViewData);

  if (!isBrowserActive && !hasScopedView) {
    return null;
  }

  return (
    <div
      className="fixed bottom-24 right-20 z-50 max-sm:bottom-20 max-sm:right-16 group"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Desktop Hover Micro Peek Thumbnail */}
      {isHovered && scopedViewData?.screenshotBase64 && !isOpen && (
        <div
          data-testid="browser-inspector-peek-thumbnail"
          className={cn(
            'absolute bottom-full right-0 mb-3 hidden sm:flex flex-col',
            'w-44 p-2 rounded-xl border border-border/80 bg-popover/95 text-popover-foreground shadow-2xl backdrop-blur-md',
            'transition-all duration-200 animate-in fade-in-50 zoom-in-95 pointer-events-none select-none',
          )}
        >
          <div className="flex items-center justify-between gap-1.5 mb-1.5 px-0.5">
            <div className="flex items-center gap-1 min-w-0">
              <span
                className={cn(
                  'w-1.5 h-1.5 rounded-full shrink-0',
                  isBrowserActive ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500',
                )}
              />
              <span className="text-[10px] font-medium tracking-wide uppercase text-muted-foreground">
                {isBrowserActive ? 'Live' : 'Snapshot'}
              </span>
            </div>
            {scopedViewData.pageTitle && (
              <span className="text-[10px] text-muted-foreground truncate max-w-[80px]" title={scopedViewData.pageTitle}>
                {scopedViewData.pageTitle}
              </span>
            )}
          </div>

          <div className="relative w-full aspect-video rounded-lg overflow-hidden border border-border/60 bg-muted/40">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:${scopedViewData.mimeType};base64,${scopedViewData.screenshotBase64}`}
              alt={scopedViewData.pageTitle || 'Live peek'}
              className="w-full h-full object-cover"
              draggable={false}
            />
          </div>

          {scopedViewData.pageUrl && (
            <span className="mt-1 text-[9px] font-mono text-muted-foreground/70 truncate block px-0.5">
              {scopedViewData.pageUrl}
            </span>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={togglePanel}
        data-testid="browser-inspector-toggle-button"
        className={cn(
          'p-3 rounded-full shadow-lg transition-all duration-200 hover:scale-105 active:scale-95',
          'flex items-center justify-center relative',
          isOpen
            ? 'bg-primary text-primary-foreground ring-2 ring-primary/30'
            : 'bg-secondary text-secondary-foreground hover:bg-secondary/90',
        )}
        title={t('toggleTitle')}
        aria-label={t('toggleTitle')}
      >
        <ScanSearch size={22} />
        {isBrowserActive && (
          <span className="absolute top-1 right-1 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-background animate-pulse" />
        )}
      </button>
    </div>
  );
};

export default React.memo(BrowserInspectorToggle);
