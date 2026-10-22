'use client';

/**
 * HonestyAuditBanner Component.
 * Top interaction banner warning users of unverified placeholder numbers.
 * Adheres to WorkBuddy controlled fabrication paradigm with zero emojis.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertTriangle,
  CheckCircle2,
  ListChecks,
  Sparkles,
} from 'lucide-react';

interface HonestyAuditBannerProps {
  pendingCount: number;
  totalCount: number;
  onOpenDrawer: () => void;
  onFinalize?: () => void;
  className?: string;
}

export const HonestyAuditBanner: React.FC<HonestyAuditBannerProps> = ({
  pendingCount,
  totalCount,
  onOpenDrawer,
  onFinalize,
  className = '',
}) => {
  let t = (key: string, values?: Record<string, string | number>): string => {
    if (key === 'bannerWarning' && values?.count !== undefined) {
      return `本篇草案包含 ${values.count} 处待实测占位数据，发布前建议替换为真实跑测结果`;
    }
    return key;
  };

  try {
    const translation = useTranslations('factCheck');
    t = (key: string, values?: Record<string, string | number>): string =>
      translation(key, values);
  } catch {
    // Fallback in test suites
  }

  const hasPending = pendingCount > 0;

  if (totalCount === 0) {
    return null;
  }

  return (
    <section
      aria-label={t('bannerTitle')}
      className={`flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 px-4 py-3 rounded-xl border transition-all ${
        hasPending
          ? 'bg-amber-950/20 border-amber-900/40 text-amber-200'
          : 'bg-emerald-950/20 border-emerald-900/40 text-emerald-200'
      } ${className}`}
    >
      <div className="flex items-center gap-2.5">
        <div
          className={`p-1.5 rounded-lg shrink-0 ${
            hasPending
              ? 'bg-amber-500/15 text-amber-400'
              : 'bg-emerald-500/15 text-emerald-400'
          }`}
        >
          {hasPending ? (
            <AlertTriangle className="w-4 h-4" />
          ) : (
            <CheckCircle2 className="w-4 h-4" />
          )}
        </div>
        <div className="text-xs">
          <span className="font-semibold block sm:inline mr-2">
            {t('bannerTitle')}:
          </span>
          <span className={hasPending ? 'text-amber-300/90' : 'text-emerald-300/90'}>
            {hasPending
              ? t('bannerWarning', { count: pendingCount })
              : t('bannerSuccess')}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
        <button
          type="button"
          onClick={onOpenDrawer}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            hasPending
              ? 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40'
              : 'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 border border-emerald-500/40'
          }`}
        >
          <ListChecks className="w-3.5 h-3.5" />
          <span>{t('viewCheckSheet')}</span>
          {hasPending && (
            <span className="px-1.5 py-0.2 rounded-full bg-amber-500/30 text-[10px] font-mono font-bold">
              {pendingCount}
            </span>
          )}
        </button>

        {!hasPending && onFinalize && (
          <button
            type="button"
            onClick={onFinalize}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white shadow transition-all"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>{t('finalizeDraft')}</span>
          </button>
        )}
      </div>
    </section>
  );
};
