'use client';

import { Globe, Image, Monitor, Video, MousePointerClick, type LucideIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import { useShallow } from 'zustand/react/shallow';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import { getActiveSearchServiceConfig, guardSearchServiceConfigured } from '@/store/config/searchService';
import type { BuiltinToolId } from '@/store/chat/types';

const toggleBtnClass = (active: boolean, unavailable?: boolean) =>
  cn(
    'p-1.5 rounded-full transition-all duration-200',
    unavailable
      ? 'text-muted-foreground/20 hover:text-muted-foreground/35 cursor-not-allowed'
      : active
        ? 'text-primary hover:text-primary/80'
        : 'text-muted-foreground/40 hover:text-muted-foreground/60',
  );

const TOOL_UI_CONFIG: ReadonlyArray<{
  id: BuiltinToolId;
  icon: LucideIcon;
  enableKey: string;
  disableKey: string;
}> = [
  { id: 'web_search', icon: Globe, enableKey: 'enableWebSearch', disableKey: 'disableWebSearch' },
  { id: 'browser', icon: Monitor, enableKey: 'enableBrowser', disableKey: 'disableBrowser' },
  { id: 'computer_use', icon: MousePointerClick, enableKey: 'enableComputerUse', disableKey: 'disableComputerUse' },
  {
    id: 'image_generation',
    icon: Image,
    enableKey: 'enableImageGeneration',
    disableKey: 'disableImageGeneration',
  },
  {
    id: 'video_generation',
    icon: Video,
    enableKey: 'enableVideoGeneration',
    disableKey: 'disableVideoGeneration',
  },
];

const AgentToolsToggle = () => {
  const t = useTranslations('chat');

  const { actionMode, currentBuiltinTools, toggleBuiltinTool } = useChatStore(
    useShallow((state) => ({
      actionMode: state.actionMode,
      currentBuiltinTools: state.currentBuiltinTools,
      toggleBuiltinTool: state.toggleBuiltinTool,
    })),
  );

  const searchConfigured = useConfigStore((state) => !!getActiveSearchServiceConfig(state.searchServiceConfigs));

  if (actionMode !== 'agent') {
    return null;
  }

  const handleToggle = (toolId: BuiltinToolId) => {
    if (toolId === 'web_search' && !currentBuiltinTools.includes(toolId)) {
      const { searchServiceConfigs } = useConfigStore.getState();
      if (!guardSearchServiceConfigured(searchServiceConfigs)) return;
    }
    toggleBuiltinTool(toolId);
  };

  return (
    <TooltipProvider delayDuration={300}>
      {TOOL_UI_CONFIG.map(({ id, icon: Icon, enableKey, disableKey }) => {
        const isActive = currentBuiltinTools.includes(id);
        const isUnavailable = id === 'web_search' && !searchConfigured;
        const tooltipText = isUnavailable ? t('searchNotConfiguredTooltip') : isActive ? t(disableKey) : t(enableKey);
        return (
          <Tooltip key={id}>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => handleToggle(id)}
                className={toggleBtnClass(isActive, isUnavailable)}
              >
                <Icon size={16} />
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-xs">
              {tooltipText}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </TooltipProvider>
  );
};

export default AgentToolsToggle;
