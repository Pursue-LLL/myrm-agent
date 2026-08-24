'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import {
  IconBrain,
  IconCode,
  IconCpu,
  IconFileText,
  IconImage,
  IconZap,
} from '@/components/features/icons/PremiumIcons';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/primitives/hover-card';

interface ModelSpecialtyChipProps {
  specialty?: 'code' | 'long_doc' | 'reasoning' | 'multimodal' | 'casual' | 'general';
  modelName?: string;
}

export const ModelSpecialtyChip: React.FC<ModelSpecialtyChipProps> = ({ specialty, modelName }) => {
  const t = useTranslations('chat.specialtyRouting');

  if (!specialty || !modelName) {
    return null;
  }

  const getSpecialtyConfig = () => {
    switch (specialty) {
      case 'code':
        return {
          icon: <IconCode className="w-3.5 h-3.5 text-cyan-500" />,
          label: t('codeSpecialty'),
          desc: t('codeSpecialtyDesc'),
          badgeClass: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-600 dark:text-cyan-400',
        };
      case 'long_doc':
        return {
          icon: <IconFileText className="w-3.5 h-3.5 text-indigo-500" />,
          label: t('longDocSpecialty'),
          desc: t('longDocSpecialtyDesc'),
          badgeClass: 'bg-indigo-500/10 border-indigo-500/20 text-indigo-600 dark:text-indigo-400',
        };
      case 'reasoning':
        return {
          icon: <IconBrain className="w-3.5 h-3.5 text-purple-500" />,
          label: t('reasoningSpecialty'),
          desc: t('reasoningSpecialtyDesc'),
          badgeClass: 'bg-purple-500/10 border-purple-500/20 text-purple-600 dark:text-purple-400',
        };
      case 'multimodal':
        return {
          icon: <IconImage className="w-3.5 h-3.5 text-pink-500" />,
          label: t('multimodalSpecialty'),
          desc: t('multimodalSpecialtyDesc'),
          badgeClass: 'bg-pink-500/10 border-pink-500/20 text-pink-600 dark:text-pink-400',
        };
      case 'casual':
        return {
          icon: <IconZap className="w-3.5 h-3.5 text-amber-500" />,
          label: t('casualSpecialty'),
          desc: t('casualSpecialtyDesc'),
          badgeClass: 'bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400',
        };
      default:
        return {
          icon: <IconCpu className="w-3.5 h-3.5 text-blue-500" />,
          label: t('generalSpecialty'),
          desc: t('generalSpecialtyDesc'),
          badgeClass: 'bg-blue-500/10 border-blue-500/20 text-blue-600 dark:text-blue-400',
        };
    }
  };

  const config = getSpecialtyConfig();

  return (
    <HoverCard openDelay={200} closeDelay={100}>
      <HoverCardTrigger asChild>
        <div
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-xs font-medium cursor-help transition-all hover:opacity-80 select-none ${config.badgeClass}`}
        >
          {config.icon}
          <span>{config.label}</span>
          <span className="opacity-50">·</span>
          <span className="font-mono text-[11px] opacity-90 max-w-[140px] truncate">{modelName}</span>
        </div>
      </HoverCardTrigger>
      <HoverCardContent className="w-64 p-3 text-xs" align="start">
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 font-medium text-foreground">
            {config.icon}
            <span>{config.label}</span>
          </div>
          <p className="text-muted-foreground leading-relaxed">{config.desc}</p>
          <div className="pt-1 border-t border-border/50 text-[11px] text-muted-foreground">
            {t('actualModelLabel')}: <span className="font-mono text-foreground">{modelName}</span>
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
};
