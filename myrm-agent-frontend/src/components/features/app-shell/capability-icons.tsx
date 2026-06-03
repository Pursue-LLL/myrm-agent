'use client';

import { Eye, Wrench, Brain, Headphones, Video } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import type { ModelCapabilities } from '@/services/llm-config';

interface CapabilityIconsProps {
  capabilities: ModelCapabilities;
  size?: number;
}

const CapabilityIcons = ({ capabilities, size = 10 }: CapabilityIconsProps) => {
  const t = useTranslations('settings.modelCapabilities');

  const icons = [
    {
      key: 'function',
      show: capabilities.supports_function_calling,
      icon: Wrench,
      label: t('functionCalling'),
    },
    { key: 'vision', show: capabilities.supports_vision, icon: Eye, label: t('vision') },
    {
      key: 'audio',
      show: capabilities.supports_audio_input,
      icon: Headphones,
      label: t('audioInput'),
    },
    { key: 'video', show: capabilities.supports_video_input, icon: Video, label: t('videoInput') },
    { key: 'reasoning', show: capabilities.supports_reasoning, icon: Brain, label: t('reasoning') },
  ];

  const visibleIcons = icons.filter((i) => i.show);
  if (visibleIcons.length === 0) return null;

  return (
    <TooltipProvider>
      <div className="flex items-center gap-0.5">
        {visibleIcons.map(({ key, icon: Icon, label }) => (
          <Tooltip key={key}>
            <TooltipTrigger asChild>
              <div
                className="flex items-center justify-center w-5 h-5 rounded transition-colors"
                style={{ backgroundColor: '#d7e1e1' }}
              >
                <Icon size={size} className="text-foreground" />
              </div>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-xs">
              {label}
            </TooltipContent>
          </Tooltip>
        ))}
      </div>
    </TooltipProvider>
  );
};

export default CapabilityIcons;
