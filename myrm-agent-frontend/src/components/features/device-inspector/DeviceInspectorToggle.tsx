'use client';

import React, { useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Smartphone } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import useDeviceInspectorStore, { selectScopedDeviceViewData } from '@/store/useDeviceInspectorStore';
import { useClosePanelOnChatSwitch } from '@/hooks/inspector/useClosePanelOnChatSwitch';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';

export const DeviceInspectorToggle: React.FC = () => {
  const t = useTranslations('chat.deviceInspector');
  const chatId = useChatStore((state) => state.chatId?.trim() ?? '');
  const { isDeviceActive, isOpen, togglePanel, closePanel, viewData } = useDeviceInspectorStore();
  const hasScopedView = Boolean(selectScopedDeviceViewData(viewData, chatId));

  const isVisible = isDeviceActive || hasScopedView;
  const isPending = !isDeviceActive || !hasScopedView;

  useEffect(() => {
    if (!isDeviceActive && isOpen && !hasScopedView) {
      closePanel();
    }
  }, [isDeviceActive, isOpen, hasScopedView, closePanel]);

  useClosePanelOnChatSwitch(chatId, isOpen, closePanel);

  if (!isVisible) {
    return null;
  }

  const tooltipText = isPending ? t('enabledHint') : t('toggleTitle');

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={togglePanel}
            className={cn(
              'fixed bottom-24 right-48 p-3 rounded-full shadow-lg transition-colors z-50',
              'flex items-center justify-center',
              'max-sm:bottom-20 max-sm:right-40',
              isPending && 'opacity-70 ring-1 ring-dashed ring-muted-foreground/40',
              isOpen
                ? 'bg-emerald-600 text-white ring-2 ring-emerald-500/30'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/90',
            )}
            title={tooltipText}
            aria-label={tooltipText}
            data-testid="device-inspector-toggle"
          >
            <Smartphone size={22} className={cn(isOpen && 'text-white')} />
          </button>
        </TooltipTrigger>
        <TooltipContent side="left" className="text-xs max-w-[220px]">
          {tooltipText}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default DeviceInspectorToggle;
