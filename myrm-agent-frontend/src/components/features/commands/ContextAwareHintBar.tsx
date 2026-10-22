/**
 * [INPUT]
 * - onInsertPrompt: Callback when user clicks a suggested command chip to prefill input
 * - useCommandMatrixStore: Zustand store for suggestedChips, dismissChip
 * - next-intl: useTranslations
 * - lucide-react icons: Lightbulb, Sparkles, X, ChevronRight
 *
 * [OUTPUT]
 * - ContextAwareHintBar: Non-intrusive floating suggestion chips above prompt input
 *
 * [POS]
 * Client-side component for Item 38 P0. Strictly under 220 lines. Zero `any`. Zero native emojis.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { Lightbulb, Sparkles, X } from 'lucide-react';
import { useCommandMatrixStore } from './useCommandMatrixStore';
import type { CapabilityHintChip } from './commandMatrixTypes';

export interface ContextAwareHintBarProps {
  onInsertPrompt?: (prompt: string) => void;
  className?: string;
}

export const ContextAwareHintBar: React.FC<ContextAwareHintBarProps> = ({
  onInsertPrompt,
  className = '',
}) => {
  const t = useTranslations('commandMatrix');
  const suggestedChips = useCommandMatrixStore((s) => s.suggestedChips);
  const dismissChip = useCommandMatrixStore((s) => s.dismissChip);
  const markCommandMastered = useCommandMatrixStore((s) => s.markCommandMastered);

  if (!suggestedChips || suggestedChips.length === 0) {
    return null;
  }

  const handleChipClick = (chip: CapabilityHintChip) => {
    markCommandMastered(chip.command);
    if (onInsertPrompt) {
      onInsertPrompt(chip.insert_prompt);
    }
  };

  const handleDismiss = (e: React.MouseEvent, chip: CapabilityHintChip) => {
    e.stopPropagation();
    dismissChip(chip.chip_id, chip.command);
  };

  return (
    <section
      aria-label={t('title')}
      className={`flex flex-wrap items-center gap-2 py-1.5 px-2 bg-background/80 backdrop-blur-sm rounded-lg border border-border/40 text-xs shadow-xs animate-in fade-in slide-in-from-bottom-1 duration-200 ${className}`}
    >
      <div className="flex items-center gap-1.5 text-primary font-medium text-[11px] select-none pl-0.5">
        <Sparkles className="w-3.5 h-3.5 text-amber-500 animate-pulse" />
        <span>建议：</span>
      </div>

      {suggestedChips.map((chip) => (
        <div
          key={chip.chip_id}
          className="group inline-flex items-center gap-1.5 pl-2 pr-1.5 py-1 bg-muted/60 hover:bg-muted/90 rounded-md border border-border/60 transition-all duration-150 text-foreground"
          title={`${chip.label_zh} - ${chip.reason_zh}`}
        >
          <button
            type="button"
            onClick={() => handleChipClick(chip)}
            className="flex items-center gap-1 text-[11px] font-medium text-left hover:text-primary transition-colors cursor-pointer"
          >
            <Lightbulb className="w-3 h-3 text-amber-500 flex-shrink-0" />
            <span className="font-mono text-primary font-semibold">{chip.command}</span>
            <span className="text-muted-foreground group-hover:text-foreground line-clamp-1 max-w-[140px]">
              {chip.label_zh}
            </span>
          </button>

          <button
            type="button"
            onClick={(e) => handleDismiss(e, chip)}
            className="p-0.5 text-muted-foreground hover:text-foreground rounded-sm transition-colors cursor-pointer ml-0.5"
            aria-label={t('dismissHint')}
            title={t('dismissHint')}
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      ))}
    </section>
  );
};
