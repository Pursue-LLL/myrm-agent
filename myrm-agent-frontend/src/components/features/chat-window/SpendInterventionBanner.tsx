'use client';

/**
 * [INPUT]
 * @/services/budget (POS: Spend control API service)
 *
 * [OUTPUT]
 * SpendInterventionBanner: Floating soft-gate and progressive spend intervention banner.
 *
 * [POS]
 * Displays progressive spend alerts for Tier 1 (hints), Tier 2 (soft gate with self-confirm button),
 * Tier 3 (seamless downgrade notice), and Tier 4 (critical pause).
 */

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconShield, IconAlertTriangle, IconCheck, IconZap } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import {
  confirmSoftSpendGate,
  type SpendInterventionDecision,
} from '@/services/budget';

interface SpendInterventionBannerProps {
  decision: SpendInterventionDecision;
  sessionId: string;
  onBypassConfirmed?: () => void;
  className?: string;
}

export const SpendInterventionBanner = memo<SpendInterventionBannerProps>(
  ({ decision, sessionId, onBypassConfirmed, className }) => {
    const t = useTranslations('settings.budget');
    const [submitting, setSubmitting] = useState(false);
    const [confirmed, setConfirmed] = useState(false);

    const handleConfirmSoftGate = useCallback(async () => {
      if (!decision.bypassToken || submitting) return;
      setSubmitting(true);
      try {
        const res = await confirmSoftSpendGate({
          sessionId,
          bypassToken: decision.bypassToken,
        });
        if (res.confirmed) {
          setConfirmed(true);
          onBypassConfirmed?.();
        }
      } catch {
        // error handled by apiRequest
      } finally {
        setSubmitting(false);
      }
    }, [decision.bypassToken, submitting, sessionId, onBypassConfirmed]);

    if (confirmed || decision.action === 'allow') {
      return null;
    }

    const isSoftGate = decision.tier === 'tier_2_soft_gate';
    const isAutoDowngraded = decision.tier === 'tier_3_auto_downgrade';
    const isCriticalPause = decision.tier === 'tier_4_critical_pause';

    return (
      <div
        data-testid="spend-intervention-banner"
        className={cn(
          'p-3 rounded-xl border text-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-sm',
          isSoftGate && 'bg-amber-500/10 border-amber-500/30 text-amber-900 dark:text-amber-200',
          isAutoDowngraded && 'bg-purple-500/10 border-purple-500/30 text-purple-900 dark:text-purple-200',
          isCriticalPause && 'bg-red-500/10 border-red-500/30 text-red-900 dark:text-red-200',
          !isSoftGate && !isAutoDowngraded && !isCriticalPause && 'bg-sky-500/10 border-sky-500/30 text-sky-900 dark:text-sky-200',
          className,
        )}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="shrink-0 p-1.5 rounded-lg bg-background/50">
            {isCriticalPause ? (
              <IconAlertTriangle className="w-4 h-4 text-red-500" />
            ) : isAutoDowngraded ? (
              <IconZap className="w-4 h-4 text-purple-500" />
            ) : (
              <IconShield className="w-4 h-4 text-amber-500" />
            )}
          </div>
          <div className="min-w-0">
            <div className="font-semibold flex items-center gap-1.5">
              <span>
                {isCriticalPause
                  ? t('criticalPauseActive')
                  : isAutoDowngraded
                    ? t('autoDowngradedActive')
                    : isSoftGate
                      ? t('softGateActive')
                      : t('tier1Label')}
              </span>
              <span className="font-mono text-[10px] px-1.5 py-0.2 rounded bg-background/60 border border-border/40">
                ${decision.currentSpendUsd.toFixed(2)} / ${decision.quotaLimitUsd.toFixed(2)}
              </span>
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
              {decision.message}
            </div>
          </div>
        </div>

        {isSoftGate && decision.bypassToken && (
          <Button
            size="sm"
            variant="default"
            disabled={submitting}
            onClick={handleConfirmSoftGate}
            className="shrink-0 text-xs gap-1.5 bg-amber-600 hover:bg-amber-700 text-white dark:bg-amber-500 dark:hover:bg-amber-600"
          >
            <IconCheck className="w-3.5 h-3.5" />
            <span>{t('selfConfirmButton')}</span>
          </Button>
        )}
      </div>
    );
  },
);

SpendInterventionBanner.displayName = 'SpendInterventionBanner';
