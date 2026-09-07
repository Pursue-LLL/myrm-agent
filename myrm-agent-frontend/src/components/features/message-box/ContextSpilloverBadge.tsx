'use client';

import * as React from 'react';
import { FileText, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface ContextSpilloverBadgeProps {
  charCount: number;
  className?: string;
}

export const ContextSpilloverBadge: React.FC<ContextSpilloverBadgeProps> = ({
  charCount,
  className = '',
}) => {
  const t = useTranslations('chat');

  if (charCount <= 16000) {
    return null;
  }

  return (
    <div
      data-testid="context-spillover-badge"
      className={`mb-2 flex items-center justify-between gap-2 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-xs text-sky-800 dark:border-sky-400/30 dark:bg-sky-950/40 dark:text-sky-200 transition-all duration-200 animate-in fade-in-50 slide-in-from-bottom-1 ${className}`}
    >
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 shrink-0 text-sky-600 dark:text-sky-400" />
        <span className="font-medium">
          {t('spillover.notice', {
            chars: charCount.toLocaleString(),
            default: `Large text detected (${charCount.toLocaleString()} chars). Will automatically spill to workspace file to keep context clean.`,
          })}
        </span>
      </div>
      <div className="flex items-center gap-1 text-[11px] text-sky-600/80 dark:text-sky-400/80">
        <Sparkles className="h-3 w-3" />
        <span>{t('spillover.optimized', { default: 'Protected' })}</span>
      </div>
    </div>
  );
};
