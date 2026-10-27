'use client';

import * as React from 'react';
import { ClipboardText } from '@phosphor-icons/react';
import { useLocale, useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { SPILLOVER_MIN_CHARS } from '@/lib/utils/spillover';

interface ContextSpilloverBadgeProps {
  charCount: number;
  className?: string;
}

/** Composer notice for a text too long to send as is: it is kept with the chat and the assistant reads it from there. */
export const ContextSpilloverBadge: React.FC<ContextSpilloverBadgeProps> = ({ charCount, className }) => {
  const t = useTranslations('chat');
  const locale = useLocale();

  if (charCount <= SPILLOVER_MIN_CHARS) {
    return null;
  }

  return (
    <div
      data-testid="context-spillover-badge"
      className={cn(
        'mb-2 flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-xs text-foreground',
        'transition-all duration-200 animate-in fade-in-50 slide-in-from-bottom-1',
        className,
      )}
    >
      <ClipboardText size={16} weight="duotone" aria-hidden className="shrink-0 text-primary" />
      <span className="font-medium">
        {t('spillover.notice', { chars: new Intl.NumberFormat(locale).format(charCount) })}
      </span>
    </div>
  );
};
