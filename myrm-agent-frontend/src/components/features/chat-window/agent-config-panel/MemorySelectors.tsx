'use client';

import { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import { IconBrain } from '@/components/features/icons/PremiumIcons';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';

/**
 * 记忆遗忘速度配置 (Memory Decay Selector)
 * 允许用户控制智能体长期记忆的衰减速度
 */
export const MemoryDecaySelector = memo(() => {
  const t = useTranslations('agent.configPanel');
  const agentConfig = useChatStore((state) => state.agentConfig);
  const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);

  const selected = agentConfig?.memoryDecayProfile || 'normal';

  const handleChange = useCallback(
    (value: string) => {
      updateAgentConfig({ memoryDecayProfile: value as 'permanent' | 'normal' | 'fast' });
    },
    [updateAgentConfig],
  );

  return (
    <div className="flex flex-col gap-2 mt-3">
      <div className="flex items-center gap-2">
        <IconBrain className="w-3.5 h-3.5 text-purple-500 flex-shrink-0" />
        <span className="text-xs text-muted-foreground whitespace-nowrap">{t('memoryDecay')}</span>
        <Select value={selected} onValueChange={handleChange}>
          <SelectTrigger
            className={cn(
              'flex-1 min-w-0 h-7 text-xs px-2 rounded-full border-border/50',
              selected !== 'normal' && 'border-purple-400/50 bg-purple-50/30 dark:bg-purple-950/20',
            )}
          >
            <SelectValue placeholder={t('memoryDecayNormal')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="permanent">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryDecayPermanent')}</span>
              </div>
            </SelectItem>
            <SelectItem value="normal">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryDecayNormal')}</span>
              </div>
            </SelectItem>
            <SelectItem value="fast">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryDecayFast')}</span>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
});
MemoryDecaySelector.displayName = 'MemoryDecaySelector';

export const MemoryExtractionPresetSelector = memo(() => {
  const t = useTranslations('agent.configPanel');
  const agentConfig = useChatStore((state) => state.agentConfig);
  const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);

  const selected = agentConfig?.memoryExtractionPreset || 'auto';

  const handleChange = useCallback(
    (value: string) => {
      updateAgentConfig({
        memoryExtractionPreset: value as 'none' | 'auto' | 'persona' | 'work_assistant' | 'research',
      });
    },
    [updateAgentConfig],
  );

  return (
    <div className="flex flex-col gap-2 mt-2">
      <div className="flex items-center gap-2">
        <IconBrain className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
        <span className="text-xs text-muted-foreground whitespace-nowrap">{t('memoryExtractionPreset')}</span>
        <Select value={selected} onValueChange={handleChange}>
          <SelectTrigger
            className={cn(
              'flex-1 min-w-0 h-7 text-xs px-2 rounded-full border-border/50',
              selected !== 'auto' && 'border-indigo-400/50 bg-indigo-50/30 dark:bg-indigo-950/20',
            )}
          >
            <SelectValue placeholder={t('memoryPresetAuto')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryPresetAuto')}</span>
              </div>
            </SelectItem>
            <SelectItem value="persona">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryPresetPersona')}</span>
              </div>
            </SelectItem>
            <SelectItem value="work_assistant">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryPresetWork')}</span>
              </div>
            </SelectItem>
            <SelectItem value="research">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryPresetResearch')}</span>
              </div>
            </SelectItem>
            <SelectItem value="none">
              <div className="flex flex-col py-0.5">
                <span>{t('memoryPresetNone')}</span>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
});
MemoryExtractionPresetSelector.displayName = 'MemoryExtractionPresetSelector';
