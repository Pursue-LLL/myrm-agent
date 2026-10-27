'use client';

import * as React from 'react';
import { ClipboardText } from '@phosphor-icons/react';
import { useLocale, useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { isLongPaste } from '@/lib/utils/spillover';

interface ContextSpilloverBadgeProps {
  text: string;
  className?: string;
}

/** Composer notice for a text too long to send as is: it is kept with the chat and the assistant reads it from there. */
export const ContextSpilloverBadge: React.FC<ContextSpilloverBadgeProps> = ({ text, className }) => {
  const t = useTranslations('chat');
  const locale = useLocale();

  if (!isLongPaste(text)) {
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
        {t('spillover.notice', { chars: new Intl.NumberFormat(locale).format(text.length) })}
      </span>
    </div>
  );
};
