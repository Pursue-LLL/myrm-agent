'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { IconAlertTriangle } from '@/components/features/icons/PremiumIcons';
import type { TraceError } from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';

interface TraceErrorItemProps {
  error: TraceError;
  isFirstIrrecoverable: boolean;
}

/**
 * Error card in the execution trace timeline.
 *
 * Surfaces deterministic fault-side attribution (who owns the failure), the
 * localized recovery steps from the harness diagnostic, and marks the first
 * irrecoverable error so users can find the point the agent could not recover
 * from. Rendered per entry of ``ExecutionTrace.errors``.
 */
const TraceErrorItem = memo<TraceErrorItemProps>(({ error, isFirstIrrecoverable }) => {
  const t = useTranslations('settings.sessionAnalytics.trace');
  const tFault = useTranslations('progressSteps');
  const faultSide = error.fault_side && error.fault_side !== 'unknown' ? error.fault_side : null;

  return (
    <div
      className={cn(
        'rounded-lg border p-2.5',
        isFirstIrrecoverable
          ? 'bg-rose-500/10 border-rose-500/50 ring-1 ring-rose-500/30'
          : 'bg-rose-500/5 border-rose-500/20',
      )}
    >
      <div className="flex items-center gap-2">
        <IconAlertTriangle className="h-3.5 w-3.5 shrink-0 text-rose-500" />
        <span className="text-xs font-medium text-rose-600 dark:text-rose-400">{String(error.error_type)}</span>
        {faultSide && (
          <span className="inline-flex items-center rounded-full bg-rose-500/10 border border-rose-500/25 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-rose-600 dark:text-rose-400">
            {tFault(`faultSides.${faultSide}`)}
          </span>
        )}
        {isFirstIrrecoverable && (
          <span className="ml-auto inline-flex items-center rounded-full bg-rose-600/10 border border-rose-600/30 px-2 py-0.5 text-[10px] font-semibold text-rose-600 dark:text-rose-400">
            {t('firstIrrecoverable')}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground mt-1.5 break-words">{String(error.error)}</p>

      {error.diagnostic_result && error.diagnostic_result.resolution_steps?.length > 0 && (
        <div className="mt-2 border-t border-rose-500/10 pt-2 space-y-1">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
            {t('recoverySteps')}
          </div>
          {error.diagnostic_result.resolution_steps.slice(0, 4).map((step, i) => (
            <p key={i} className="text-[11px] text-foreground/80 leading-relaxed">
              {i + 1}. {step}
            </p>
          ))}
        </div>
      )}
    </div>
  );
});
TraceErrorItem.displayName = 'TraceErrorItem';

export default TraceErrorItem;
