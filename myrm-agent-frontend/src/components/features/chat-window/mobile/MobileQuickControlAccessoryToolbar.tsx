'use client';

/**
 * [INPUT]
 * - lucide-react (POS: Consistent SVG icons)
 * - next-intl::useTranslations (POS: Internationalization)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind class merger)
 *
 * [OUTPUT]
 * - MobileQuickControlAccessoryToolbar: Compact touch-first accessory toolbar for mobile chat.
 *
 * [POS]
 * Mobile input control surface. Positioned directly above the input box on mobile devices,
 * providing one-touch access to prompt history navigation, clipboard pasting, and side advisor Q&A.
 */

import { useCallback, useState } from 'react';
import { History, Clipboard, Sparkles, X, Check } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';

export interface MobileQuickControlAccessoryToolbarProps {
  chatId: string;
  historyCount: number;
  historyCurrentIndex: number;
  currentValue: string;
  onNavigateHistory: () => void;
  onPasteText: (text: string) => void;
  onOpenAdvisor: () => void;
  onClearInput: () => void;
  onRequestFocusInput?: () => void;
  className?: string;
}

export function MobileQuickControlAccessoryToolbar({
  historyCount,
  historyCurrentIndex,
  currentValue,
  onNavigateHistory,
  onPasteText,
  onOpenAdvisor,
  onClearInput,
  onRequestFocusInput,
  className,
}: MobileQuickControlAccessoryToolbarProps) {
  const t = useTranslations('agent.mobileCommand');
  const [pasteSuccess, setPasteSuccess] = useState(false);

  const handlePaste = useCallback(async () => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.readText) {
        const text = await navigator.clipboard.readText();
        if (text && text.trim()) {
          onPasteText(text);
          setPasteSuccess(true);
          setTimeout(() => setPasteSuccess(false), 1200);
          onRequestFocusInput?.();
        } else {
          toast.info(t('clipboardEmpty'));
        }
      } else {
        toast.error(t('pasteError'));
      }
    } catch {
      toast.error(t('pasteError'));
    }
  }, [onPasteText, onRequestFocusInput, t]);

  const handleHistoryClick = useCallback(() => {
    onNavigateHistory();
    onRequestFocusInput?.();
  }, [onNavigateHistory, onRequestFocusInput]);

  const handleClearClick = useCallback(() => {
    onClearInput();
    onRequestFocusInput?.();
  }, [onClearInput, onRequestFocusInput]);

  const isBrowsingHistory = historyCurrentIndex >= 0;
  const historyBadgeText = isBrowsingHistory
    ? `${historyCurrentIndex + 1}/${historyCount}`
    : historyCount > 0
      ? `${historyCount}`
      : null;

  return (
    <div
      data-testid="mobile-accessory-toolbar"
      className={cn('flex items-center gap-1.5 px-3 pt-2 pb-0.5 overflow-x-auto no-scrollbar', className)}
    >
      <button
        type="button"
        onClick={handleHistoryClick}
        onMouseDown={(e) => e.preventDefault()}
        disabled={historyCount === 0}
        aria-label={t('historyNav') ?? 'History'}
        className={cn(
          'inline-flex items-center gap-1 h-7 px-2.5 rounded-full text-xs font-medium border transition-colors touch-manipulation select-none shrink-0',
          isBrowsingHistory
            ? 'border-primary/60 bg-primary/10 text-primary'
            : historyCount > 0
              ? 'border-border/60 bg-secondary/40 text-muted-foreground hover:text-foreground hover:bg-secondary/80 active:scale-95'
              : 'border-border/30 bg-secondary/20 text-muted-foreground/40 cursor-not-allowed',
        )}
      >
        <History className="h-3.5 w-3.5" />
        <span>{t('history') ?? '历史'}</span>
        {historyBadgeText && (
          <span className="ml-0.5 text-[10px] tabular-nums font-mono opacity-80">{historyBadgeText}</span>
        )}
      </button>

      <button
        type="button"
        onClick={handlePaste}
        onMouseDown={(e) => e.preventDefault()}
        aria-label={t('paste') ?? 'Paste'}
        className={cn(
          'inline-flex items-center gap-1 h-7 px-2.5 rounded-full text-xs font-medium border border-border/60 bg-secondary/40 text-muted-foreground hover:text-foreground hover:bg-secondary/80 active:scale-95 transition-colors touch-manipulation select-none shrink-0',
          pasteSuccess && 'text-emerald-500 border-emerald-500/50 bg-emerald-500/10',
        )}
      >
        {pasteSuccess ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Clipboard className="h-3.5 w-3.5" />}
        <span>{t('paste') ?? '粘贴'}</span>
      </button>

      <button
        type="button"
        onClick={onOpenAdvisor}
        onMouseDown={(e) => e.preventDefault()}
        aria-label={t('advisorAsk') ?? 'Ask Advisor'}
        className="inline-flex items-center gap-1 h-7 px-2.5 rounded-full text-xs font-medium border border-border/60 bg-secondary/40 text-muted-foreground hover:text-foreground hover:bg-secondary/80 active:scale-95 transition-colors touch-manipulation select-none shrink-0"
      >
        <Sparkles className="h-3.5 w-3.5 text-amber-500/90" />
        <span>{t('advisorAsk') ?? '问顾问'}</span>
      </button>

      {currentValue.length > 0 && (
        <button
          type="button"
          onClick={handleClearClick}
          onMouseDown={(e) => e.preventDefault()}
          aria-label={t('clear') ?? 'Clear'}
          className="inline-flex items-center gap-1 h-7 px-2 rounded-full text-xs text-muted-foreground hover:text-foreground bg-secondary/30 hover:bg-secondary/60 active:scale-95 transition-colors touch-manipulation select-none ml-auto shrink-0"
        >
          <X className="h-3 w-3" />
          <span className="text-[11px]">{t('clear') ?? '清空'}</span>
        </button>
      )}
    </div>
  );
}
