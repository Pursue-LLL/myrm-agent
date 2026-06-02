/**
 * [INPUT]
 * - @/hooks/useEntitlements (POS: CP entitlements SWR)
 * - @/lib/deploy-mode::isSandbox (POS: 部署模式判定)
 *
 * [OUTPUT]
 * - WorkUnitBalanceBar: WU 余额胶囊链接
 *
 * [POS]
 * SaaS Sandbox 计费 UI。展示 CP 返回的 WU 余额，引导用户进入订阅页。
 */
'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { useEntitlements } from '@/hooks/useEntitlements';
import { isSandbox } from '@/lib/deploy-mode';
import { cn } from '@/lib/utils/classnameUtils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

interface WorkUnitBalanceBarProps {
  className?: string;
  compact?: boolean;
}

export default function WorkUnitBalanceBar({ className, compact = false }: WorkUnitBalanceBarProps) {
  const t = useTranslations('billing');
  const { entitlements, isLoading } = useEntitlements();

  if (!isSandbox() || isLoading || !entitlements) {
    return null;
  }

  const rollover = Math.max(0, entitlements.subscription_wu - entitlements.monthly_allowance_wu);
  const baseAvailable = Math.min(entitlements.subscription_wu, entitlements.monthly_allowance_wu);
  const hasDetails = rollover > 0 || entitlements.topup_wu > 0;

  const content = (
    <Link
      href="/subscription"
      className={cn(
        'inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground',
        className,
      )}
    >
      <span className="font-medium text-foreground">{t('wuBalance')}</span>
      <span>{entitlements.balance_wu.toLocaleString()} WU</span>
      {!compact && rollover > 0 ? (
        <span className="text-emerald-600 dark:text-emerald-400 font-medium">
          (+{rollover.toLocaleString()} Rollover)
        </span>
      ) : null}
    </Link>
  );

  if (!hasDetails) {
    return content;
  }

  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>{content}</TooltipTrigger>
        <TooltipContent side="bottom" align="end" className="flex flex-col gap-1.5 p-2.5">
          <div className="flex items-center justify-between gap-6">
            <span className="text-muted-foreground">Base Allowance</span>
            <span className="font-medium">{baseAvailable.toLocaleString()}</span>
          </div>
          {rollover > 0 && (
            <div className="flex items-center justify-between gap-6">
              <span className="text-emerald-600 dark:text-emerald-400">Rollover</span>
              <span className="font-medium text-emerald-600 dark:text-emerald-400">+{rollover.toLocaleString()}</span>
            </div>
          )}
          {entitlements.topup_wu > 0 && (
            <div className="flex items-center justify-between gap-6">
              <span className="text-blue-600 dark:text-blue-400">Top-up</span>
              <span className="font-medium text-blue-600 dark:text-blue-400">
                +{entitlements.topup_wu.toLocaleString()}
              </span>
            </div>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
