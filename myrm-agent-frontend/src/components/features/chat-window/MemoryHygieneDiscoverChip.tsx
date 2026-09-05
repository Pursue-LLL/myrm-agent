'use client';

/**
 * [INPUT]
 * - next/navigation::useRouter (POS: route navigation)
 * - next-intl::useTranslations (POS: i18n)
 * - lucide-react::Activity, ArrowRight, ShieldCheck, X (POS: refined UI icons)
 *
 * [OUTPUT]
 * - MemoryHygieneDiscoverChip: EmptyChat 5-minute memory hygiene discovery capsule.
 *
 * [POS]
 * EmptyChat monthly memory health discovery component. Prompts users (especially Hermes
 * migrants used to monthly cleanups) to run a 1-click health checkup and self-healing
 * in the Memory Command Center.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Activity, ArrowRight, ShieldCheck, X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

interface MemoryHygieneDiscoverChipProps {
  className?: string;
}

const DISMISS_KEY = 'myrm_memory_hygiene_chip_dismissed';

export const MemoryHygieneDiscoverChip = memo(function MemoryHygieneDiscoverChip({
  className,
}: MemoryHygieneDiscoverChipProps) {
  const t = useTranslations('chat.memoryHygieneChip');
  const router = useRouter();
  const [dismissed, setDismissed] = useState<boolean>(true);

  useEffect(() => {
    try {
      const isDismissed = sessionStorage.getItem(DISMISS_KEY) === 'true';
      setDismissed(isDismissed);
    } catch {
      setDismissed(false);
    }
  }, []);

  const handleNavigate = useCallback(() => {
    router.push('/settings/memory?sub=command-center&focus=doctor');
  }, [router]);

  const handleDismiss = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      sessionStorage.setItem(DISMISS_KEY, 'true');
    } catch {
      // Ignore sessionStorage failure
    }
    setDismissed(true);
  }, []);

  if (dismissed) {
    return null;
  }

  return (
    <div
      data-testid="memory-hygiene-discover-chip"
      onClick={handleNavigate}
      className={cn(
        'group relative w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl cursor-pointer select-none',
        'bg-gradient-to-r from-emerald-500/5 via-teal-500/5 to-cyan-500/5 dark:from-emerald-950/20 dark:via-teal-950/20 dark:to-cyan-950/20',
        'border border-emerald-500/20 dark:border-emerald-500/15 hover:border-emerald-500/35 dark:hover:border-emerald-500/30',
        'shadow-xs hover:shadow-sm transition-all duration-200',
        className,
      )}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 shrink-0 group-hover:scale-105 transition-transform">
          <Activity className="w-4 h-4" />
        </div>
        <div className="flex flex-col min-w-0 text-left">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-neutral-800 dark:text-neutral-200 truncate">{t('title')}</span>
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded-md bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20 shrink-0">
              <ShieldCheck className="w-2.5 h-2.5" />
              {t('hermesBadge')}
            </span>
          </div>
          <span className="text-[11px] text-neutral-500 dark:text-neutral-400 truncate">{t('subtitle')}</span>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <span className="hidden sm:inline-flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 group-hover:text-emerald-700 dark:group-hover:text-emerald-300 transition-colors">
          {t('action')}
          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
        </span>
        <button
          type="button"
          onClick={handleDismiss}
          className="p-1 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-200/50 dark:hover:bg-neutral-800/50 transition-colors"
          aria-label={t('dismiss')}
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
});

export default MemoryHygieneDiscoverChip;
