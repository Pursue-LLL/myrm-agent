'use client';

/**
 * [INPUT]
 * @/services/budget (POS: Budget API service)
 *
 * [OUTPUT]
 * BudgetBadge: Compact inline budget indicator for the chat input area.
 *
 * [POS]
 * Displays real-time session/daily budget usage as a tiny progress indicator
 * next to the input area. Shows eco mode leaf icon when budget pressure is active.
 * Only visible when budget control is enabled.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconCreditCard, IconShield } from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { getBudgetStatus, type BudgetStatus } from '@/services/budget';

const STATUS_COLORS: Record<string, string> = {
  ok: 'text-muted-foreground',
  warning: 'text-amber-500',
  finalization: 'text-orange-500',
  exceeded: 'text-red-500',
};

const ECO_ACTIVE_STATUSES = new Set(['warning', 'finalization', 'exceeded']);

const BudgetBadge = memo(() => {
  const [status, setStatus] = useState<BudgetStatus | null>(null);
  const t = useTranslations('notifications');

  const refresh = useCallback(async () => {
    try {
      const s = await getBudgetStatus();
      setStatus(s);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    refresh();
    const handler = () => refresh();
    window.addEventListener('budget_updated', handler);
    window.addEventListener('budget_alert', handler);
    return () => {
      window.removeEventListener('budget_updated', handler);
      window.removeEventListener('budget_alert', handler);
    };
  }, [refresh]);

  if (!status || !status.enabled || status.status === 'disabled') return null;

  const colorClass = STATUS_COLORS[status.status] ?? STATUS_COLORS.ok;
  const ecoActive = ECO_ACTIVE_STATUSES.has(status.status);

  const tooltip = ecoActive
    ? `${t('ecoModeActive')}\nSession: $${status.session_cost_usd.toFixed(4)} / Daily: $${status.today_cost_usd.toFixed(4)}`
    : `Session: $${status.session_cost_usd.toFixed(4)} / Daily: $${status.today_cost_usd.toFixed(4)}`;

  return (
    <div
      className={cn('flex items-center gap-0.5 text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded', colorClass)}
      title={tooltip}
    >
      {ecoActive ? <IconShield className="w-2.5 h-2.5 text-green-500" /> : <IconCreditCard className="w-2.5 h-2.5" />}
      <span>{status.usage_pct.toFixed(0)}%</span>
    </div>
  );
});

BudgetBadge.displayName = 'BudgetBadge';

export default BudgetBadge;
