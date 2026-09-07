'use client';

/**
 * [INPUT]
 * @/store/useProviderBalanceStore (POS: gauge state for current provider)
 * next-intl (POS: i18n copy)
 *
 * [OUTPUT]
 * ProviderBalanceIndicator: micro health status dot or badge next to active model
 *
 * [POS]
 * Visual indicator in BaseModelSelector showing whether the selected provider's
 * account balance is healthy, approaching warning thresholds, or critically low.
 */

import { memo, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import useProviderBalanceStore from '@/store/useProviderBalanceStore';
import { cn } from '@/lib/utils/classnameUtils';

interface ProviderBalanceIndicatorProps {
  providerId: string | null | undefined;
  className?: string;
}

export const ProviderBalanceIndicator = memo<ProviderBalanceIndicatorProps>(({ providerId, className }) => {
  const t = useTranslations('settings.providerBalance');
  const getGauge = useProviderBalanceStore((state) => state.getGauge);
  const fetchGauges = useProviderBalanceStore((state) => state.fetchGauges);

  useEffect(() => {
    // Proactively fetch balance gauges once on mount if empty
    fetchGauges();
  }, [fetchGauges]);

  if (!providerId) return null;

  const gauge = getGauge(providerId);
  if (!gauge) return null;

  const status = gauge.status;
  if (status === 'unsupported' && !gauge.details) {
    return null;
  }

  const getStatusBadge = () => {
    switch (status) {
      case 'healthy':
        return {
          dotClass: 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.5)]',
          badgeClass: 'text-emerald-600 dark:text-emerald-400 border-emerald-500/20 bg-emerald-500/10',
          label: t('statusHealthy'),
        };
      case 'warning':
        return {
          dotClass: 'bg-amber-500 animate-pulse shadow-[0_0_6px_rgba(245,158,11,0.5)]',
          badgeClass: 'text-amber-600 dark:text-amber-400 border-amber-500/20 bg-amber-500/10',
          label: t('statusWarning'),
        };
      case 'critical':
        return {
          dotClass: 'bg-rose-500 animate-ping shadow-[0_0_8px_rgba(244,63,94,0.7)]',
          badgeClass: 'text-rose-600 dark:text-rose-400 border-rose-500/20 bg-rose-500/10',
          label: t('statusCritical'),
        };
      default:
        return null;
    }
  };

  const badge = getStatusBadge();
  if (!badge) return null;

  const tooltipText = gauge.details || (gauge.balance !== null ? `${gauge.balance.toFixed(2)} ${gauge.currency}` : badge.label);

  return (
    <div
      className={cn('inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded text-[10px] font-medium border transition-colors', badge.badgeClass, className)}
      title={`${t('tooltipPrefix')}: ${tooltipText}`}
      data-testid="provider-balance-indicator"
    >
      <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', badge.dotClass)} />
      {gauge.balance !== null ? (
        <span className="tabular-nums font-mono text-[9px]">
          {gauge.currency === 'USD' ? '$' : ''}
          {gauge.balance.toFixed(gauge.currency === 'USD' ? 2 : 1)}
          {gauge.currency === 'CNY' ? '¥' : ''}
        </span>
      ) : (
        <span>{badge.label}</span>
      )}
    </div>
  );
});

ProviderBalanceIndicator.displayName = 'ProviderBalanceIndicator';
export default ProviderBalanceIndicator;
