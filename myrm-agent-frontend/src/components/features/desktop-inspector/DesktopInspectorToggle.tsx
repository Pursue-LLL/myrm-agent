'use client';

import React, { useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { LayoutGrid } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';

const DesktopInspectorToggle: React.FC = () => {
  const t = useTranslations('chat.desktopInspector');
  const computerUseEnabled = useChatStore((state) => state.currentBuiltinTools.includes('computer_use'));
  const { isDesktopActive, isOpen, togglePanel, closePanel } = useDesktopInspectorStore();

  const isVisible = computerUseEnabled || isDesktopActive;
  const isPending = !isDesktopActive;

  useEffect(() => {
    if (!computerUseEnabled && !isDesktopActive && isOpen) {
      closePanel();
    }
  }, [computerUseEnabled, isDesktopActive, isOpen, closePanel]);

  if (!isVisible) return null;

  const tooltipText = isPending ? t('enabledHint') : t('toggleTitle');

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={togglePanel}
            className={cn(
              'fixed bottom-24 right-36 p-3 rounded-full shadow-lg transition-colors z-50',
              'flex items-center justify-center',
              'max-sm:bottom-20 max-sm:right-28',
              isPending && 'opacity-70 ring-1 ring-dashed ring-muted-foreground/40',
              isOpen
                ? 'bg-primary text-primary-foreground ring-2 ring-primary/30'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/90',
            )}
            title={tooltipText}
            aria-label={tooltipText}
          >
            <LayoutGrid size={22} />
          </button>
        </TooltipTrigger>
        <TooltipContent side="left" className="text-xs max-w-[220px]">
          {tooltipText}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default React.memo(DesktopInspectorToggle);
