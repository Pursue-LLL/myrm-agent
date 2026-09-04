'use client';

/**
 * [INPUT]
 * - @/hooks/message-input/useComposerContextChips::ContextChipItem (POS: 上下文胶囊项数据契约)
 * - @/hooks/message-input/useComposerContextChips::ComposerContextSummary (POS: 上下文负载汇总)
 * - @/hooks/ui/useMediaQuery::useIsMobile (POS: 移动端视口检测)
 *
 * [OUTPUT]
 * - ComposerContextChipStrip: 聊天输入区统一内联上下文胶囊流与溢出抽屉/浮层
 *
 * [POS]
 * 输入区上下文可视化组件。在发送前向用户透明呈现所有激活的能力、模板与附加资产。
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Sparkles,
  GitBranch,
  SlidersHorizontal,
  AtSign,
  FileText,
  Image as ImageIcon,
  BookOpen,
  X,
  AlertTriangle,
  ChevronDown,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useIsMobile } from '@/hooks/ui/useMediaQuery';
import type { ContextChipItem, ComposerContextSummary } from '@/hooks/message-input/useComposerContextChips';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';

export interface ComposerContextChipStripProps {
  chips: ContextChipItem[];
  summary: ComposerContextSummary;
  className?: string;
  disabled?: boolean;
  onOpenCapabilityEditor?: () => void;
}

const renderChipIcon = (iconType: ContextChipItem['iconType']) => {
  switch (iconType) {
    case 'skill':
      return <Sparkles className="size-3 shrink-0 text-primary" />;
    case 'workflow':
      return <GitBranch className="size-3 shrink-0 text-amber-500 dark:text-amber-400" />;
    case 'capability':
      return <SlidersHorizontal className="size-3 shrink-0 text-indigo-500 dark:text-indigo-400" />;
    case 'knowledge':
      return <BookOpen className="size-3 shrink-0 text-violet-500 dark:text-violet-400" />;
    case 'mention':
      return <AtSign className="size-3 shrink-0 text-cyan-500 dark:text-cyan-400" />;
    case 'image':
      return <ImageIcon className="size-3 shrink-0 text-emerald-500 dark:text-emerald-400" />;
    case 'file':
    default:
      return <FileText className="size-3 shrink-0 text-muted-foreground" />;
  }
};

interface SingleChipProps {
  chip: ContextChipItem;
  disabled?: boolean;
  onRemoveLabel: string;
}

const SingleChip = ({ chip, disabled, onRemoveLabel }: SingleChipProps) => {
  const isClickable = Boolean(chip.onAction && !disabled);
  return (
    <div
      data-testid={chip.category === 'skill' ? 'skill-activation-chips' : `context-chip-${chip.id}`}
      data-context-chip-id={chip.id}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onClick={isClickable ? chip.onAction : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                chip.onAction?.();
              }
            }
          : undefined
      }
      className={cn(
        'group inline-flex h-6 max-w-[220px] items-center gap-1.5 rounded-md border border-border/70 bg-background/80 px-2 text-xs font-medium text-foreground shadow-xs transition-colors hover:border-primary/40 dark:bg-card/90',
        chip.category === 'workflow' && 'border-amber-500/30 bg-amber-500/[0.06] text-amber-900 dark:text-amber-200',
        chip.category === 'capability' &&
          'border-indigo-500/30 bg-indigo-500/[0.06] text-indigo-900 dark:text-indigo-200',
        chip.category === 'knowledge' &&
          'border-violet-500/30 bg-violet-500/[0.06] text-violet-900 dark:text-violet-200',
        isClickable && 'cursor-pointer hover:border-primary/60 dark:hover:border-primary/50',
      )}
      title={chip.tooltip || chip.label}
    >
      {renderChipIcon(chip.iconType)}
      <span className="truncate">{chip.label}</span>
      {chip.detail ? <span className="shrink-0 text-[10px] text-muted-foreground/80">({chip.detail})</span> : null}
      {chip.isRemovable && chip.onRemove && !disabled ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            chip.onRemove?.();
          }}
          className="inline-flex size-3.5 shrink-0 items-center justify-center rounded-xs text-muted-foreground/70 transition-colors hover:bg-destructive/15 hover:text-destructive focus:outline-hidden"
          aria-label={`${onRemoveLabel}: ${chip.label}`}
        >
          <X size={10} />
        </button>
      ) : null}
    </div>
  );
};

export function ComposerContextChipStrip({
  chips,
  summary,
  className,
  disabled = false,
  onOpenCapabilityEditor,
}: ComposerContextChipStripProps) {
  const t = useTranslations('chat.contextStrip');
  const isMobile = useIsMobile();
  const [isOverflowOpen, setIsOverflowOpen] = useState(false);

  if (chips.length === 0) {
    return null;
  }

  const maxVisible = isMobile ? 2 : 4;
  const visibleChips = chips.slice(0, maxVisible);
  const overflowChips = chips.slice(maxVisible);
  const hasOverflow = overflowChips.length > 0;

  return (
    <div
      data-testid="composer-context-chip-strip"
      className={cn(
        'mb-2 flex flex-wrap items-center justify-between gap-1.5 rounded-lg border border-border/50 bg-secondary/50 p-1.5 text-xs backdrop-blur-xs',
        summary.isOverloaded && 'border-amber-500/30 bg-amber-500/[0.04]',
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5 min-w-0">
        {visibleChips.map((chip) => (
          <SingleChip key={chip.id} chip={chip} disabled={disabled} onRemoveLabel={t('remove')} />
        ))}

        {hasOverflow ? (
          <Popover open={isOverflowOpen} onOpenChange={setIsOverflowOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="inline-flex h-6 items-center gap-1 rounded-md border border-border/60 bg-muted/60 px-2 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label={t('moreItems', { count: overflowChips.length })}
              >
                <span>+{overflowChips.length}</span>
                <ChevronDown size={10} className="opacity-70" />
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-72 p-2 shadow-md">
              <div className="mb-1.5 px-1 text-xs font-semibold text-muted-foreground">
                {t('attachedContextTitle')} ({chips.length})
              </div>
              <div className="flex max-h-48 flex-col gap-1.5 overflow-y-auto pr-1">
                {overflowChips.map((chip) => (
                  <div
                    key={chip.id}
                    data-testid={chip.category === 'skill' ? 'skill-activation-chips' : `context-chip-${chip.id}`}
                    data-context-chip-id={chip.id}
                    className="flex items-center justify-between gap-1 rounded-md p-1 hover:bg-muted/50"
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      {renderChipIcon(chip.iconType)}
                      <span className="truncate text-xs font-medium text-foreground">{chip.label}</span>
                    </div>
                    {chip.isRemovable && chip.onRemove && !disabled ? (
                      <button
                        type="button"
                        onClick={() => chip.onRemove?.()}
                        className="inline-flex size-5 shrink-0 items-center justify-center rounded-xs text-muted-foreground hover:bg-destructive/15 hover:text-destructive"
                        aria-label={`${t('remove')}: ${chip.label}`}
                      >
                        <X size={12} />
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            </PopoverContent>
          </Popover>
        ) : null}
      </div>

      {/* 负载提示与微徽章 */}
      <div className="ml-auto flex items-center gap-1.5 shrink-0">
        {summary.isOverloaded ? (
          onOpenCapabilityEditor && !disabled ? (
            <button
              type="button"
              onClick={onOpenCapabilityEditor}
              data-testid="composer-overload-nudge"
              className="inline-flex cursor-pointer items-center gap-1 rounded-xs bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 transition-colors hover:bg-amber-500/20 focus:outline-hidden dark:text-amber-300 dark:hover:bg-amber-500/25"
              title={t('overloadWarning')}
              aria-label={t('overloadAria')}
            >
              <AlertTriangle size={10} />
              <span>{t('heavyPayload')}</span>
            </button>
          ) : (
            <span
              className="inline-flex items-center gap-1 rounded-xs bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300"
              title={t('overloadWarning')}
            >
              <AlertTriangle size={10} />
              <span>{t('heavyPayload')}</span>
            </span>
          )
        ) : null}
        <span className="text-[10px] font-medium text-muted-foreground/70">
          {t('activeSummary', { count: summary.totalItems })}
        </span>
      </div>
    </div>
  );
}
