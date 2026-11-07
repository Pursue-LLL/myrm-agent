'use client';

/**
 * [INPUT] @/store/useRetrievalStore::embeddingApplied (POS: 向量模型是否已生效), @/components/primitives/tooltip (POS: 悬浮提示)
 * [OUTPUT] MemoryHeader: 记忆面板标题区（标题、使用指南入口、说明文案、关键词检索模式提示）
 * [POS] 记忆面板的头部展示组件：记忆开启但向量模型未生效时提示当前为关键词检索模式。
 */

import { useTranslations } from 'next-intl';
import { IconBook, IconSparkles } from '@/components/features/icons/PremiumIcons';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import useRetrievalStore from '@/store/useRetrievalStore';

interface MemoryHeaderProps {
  enableMemory: boolean;
  onOpenGuide: () => void;
}

export function MemoryHeader({ enableMemory, onOpenGuide }: MemoryHeaderProps) {
  const t = useTranslations('memory');
  const embeddingApplied = useRetrievalStore((state) => state.embeddingApplied);

  return (
    <div className="min-w-0 flex-1 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-xl font-semibold text-foreground">{t('title')}</h2>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onOpenGuide}
              aria-label={t('guide.openGuideHint')}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border border-border/60',
                'bg-accent/40 px-2.5 py-1 text-xs font-medium text-muted-foreground',
                'transition-colors duration-200',
                'hover:border-primary/30 hover:bg-primary/10 hover:text-foreground',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
              )}
            >
              <IconBook className="h-3.5 w-3.5 shrink-0" />
              <span className="hidden sm:inline">{t('guide.openGuide')}</span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="max-w-xs text-xs">
            {t('guide.openGuideHint')}
          </TooltipContent>
        </Tooltip>
      </div>
      <p className="text-sm text-muted-foreground">{t('description')}</p>
      {enableMemory && !embeddingApplied && (
        <p
          className={cn(
            'inline-flex max-w-full items-center gap-1.5 rounded-md border border-border/60 bg-muted/40',
            'px-2.5 py-1.5 text-xs text-muted-foreground',
          )}
        >
          <IconSparkles className="h-3.5 w-3.5 shrink-0" />
          <span>{t('keywordModeHint')}</span>
        </p>
      )}
    </div>
  );
}
