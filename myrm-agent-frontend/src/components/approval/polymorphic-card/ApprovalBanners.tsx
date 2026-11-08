'use client';

import { useTranslations } from 'next-intl';
import { AlertTriangle, ShieldCheck } from 'lucide-react';
import type { SpendConfig } from './approvalFlags';

/** The amount a spend approval would charge, and whether the approval is tied to this exact action. */
export function SpendProtectionBanner({ spendConfig }: { spendConfig: SpendConfig }) {
  const t = useTranslations('toolApproval');
  return (
    <div
      className="flex flex-col gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 dark:border-amber-500/30 dark:bg-amber-950/20"
      data-testid="spend-protection-banner"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
          <h4 className="font-semibold text-sm text-amber-800 dark:text-amber-200">{t('spendProtection.title')}</h4>
        </div>
        {spendConfig.actionDigest && (
          <span className="inline-flex items-center rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-mono text-amber-800 dark:text-amber-300">
            {t('spendProtection.tamperProtected')}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{t('spendProtection.description')}</p>
      {spendConfig.amount !== undefined && (
        <div className="flex items-baseline gap-2 mt-1 rounded bg-background/60 px-3 py-2 border border-border/50">
          <span className="text-xs text-muted-foreground">{t('spendProtection.amount')}:</span>
          <span className="text-base font-bold font-mono text-foreground">
            {spendConfig.amount.toFixed(2)} {spendConfig.currency}
          </span>
        </div>
      )}
    </div>
  );
}

/** Auto mode was turned off after the agent crossed a limit; `autoModeSuspendedBreach` says which one. */
export function AutoModeSuspendedBanner({ autoModeSuspendedBreach }: { autoModeSuspendedBreach: string }) {
  const t = useTranslations('toolApproval');
  return (
    <div className="flex items-center gap-2 rounded-lg border border-red-500/50 bg-red-500/10 px-4 py-3">
      <AlertTriangle className="h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" />
      <div>
        <h4 className="font-semibold text-sm text-red-700 dark:text-red-300">{t('autoModeSuspended.title')}</h4>
        <p className="text-xs text-red-600/80 dark:text-red-400/80 mt-0.5">
          {autoModeSuspendedBreach === 'consecutive'
            ? t('autoModeSuspended.consecutiveReason')
            : t('autoModeSuspended.totalReason')}
        </p>
      </div>
    </div>
  );
}

/** The action reaches people outside the workspace and cannot be taken back. */
export function SociallyIrreversibleBanner() {
  const t = useTranslations('toolApproval');
  return (
    <div className="flex items-center gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-4 py-3">
      <AlertTriangle className="h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
      <div>
        <h4 className="font-semibold text-sm text-amber-700 dark:text-amber-300">{t('sociallyIrreversible.title')}</h4>
        <p className="text-xs text-amber-600/80 dark:text-amber-400/80 mt-0.5">
          {t('sociallyIrreversible.description')}
        </p>
      </div>
    </div>
  );
}

/** The safety review refused the action; the user may still let it run once. */
export function SmartDeniedBanner() {
  const t = useTranslations('toolApproval');
  return (
    <div className="flex items-center gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-4 py-3">
      <AlertTriangle className="h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
      <h4 className="font-semibold text-sm text-amber-700 dark:text-amber-300">{t('smartDenied.title')}</h4>
    </div>
  );
}
