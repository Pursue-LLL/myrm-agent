'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, Circle, Shield } from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';
import { isTauriRuntime } from '@/lib/deploy-mode';
import {
  MYRM_LOCKED_USE_SETTINGS_ANCHOR,
  MYRM_PRIVACY_CURTAIN_SETTINGS_ANCHOR,
  scrollToDesktopSettingsAnchor,
} from '@/lib/desktop/desktopSettingsAnchors';

interface UnattendedDesktopGuideCardProps {
  privacyCurtainEnabled: boolean;
  lockedUseEnabled: boolean;
}

const UnattendedDesktopGuideCard = memo<UnattendedDesktopGuideCardProps>(
  ({ privacyCurtainEnabled, lockedUseEnabled }) => {
    const t = useTranslations('settings.system.unattendedDesktop');

    if (!isTauriRuntime()) {
      return null;
    }

    const steps = [
      {
        key: 'curtain',
        title: t('stepCurtainTitle'),
        body: t('stepCurtainBody'),
        action: t('stepCurtainAction'),
        done: privacyCurtainEnabled,
        onAction: () => scrollToDesktopSettingsAnchor(MYRM_PRIVACY_CURTAIN_SETTINGS_ANCHOR),
      },
      {
        key: 'lockedUse',
        title: t('stepLockedUseTitle'),
        body: t('stepLockedUseBody'),
        action: t('stepLockedUseAction'),
        done: lockedUseEnabled,
        optional: true,
        onAction: () => scrollToDesktopSettingsAnchor(MYRM_LOCKED_USE_SETTINGS_ANCHOR),
      },
      {
        key: 'approval',
        title: t('stepApprovalTitle'),
        body: t('stepApprovalBody'),
        informational: true as const,
      },
    ] as const;

    return (
      <div
        className={cn(
          'rounded-2xl border border-border/50 bg-gradient-to-br from-card/80 to-card/40 backdrop-blur-sm p-5 sm:p-6',
          'shadow-sm',
        )}
      >
        <div className="flex items-start gap-3 mb-5">
          <div className="p-2 rounded-xl bg-emerald-500/10 shrink-0">
            <Shield className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="min-w-0 space-y-1">
            <h3 className="text-base font-semibold text-foreground tracking-tight">{t('guideTitle')}</h3>
            <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">{t('guideIntro')}</p>
          </div>
        </div>

        <ol className="space-y-4">
          {steps.map((step, index) => {
            const informational = 'informational' in step && step.informational;
            const stepDone = 'done' in step ? step.done : false;
            const StatusIcon = informational ? null : stepDone ? CheckCircle2 : Circle;
            return (
              <li
                key={step.key}
                className="flex gap-3 sm:gap-4 rounded-xl border border-border/40 bg-background/60 p-3 sm:p-4"
              >
                <div className="flex flex-col items-center gap-1 pt-0.5 shrink-0">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70">
                    {index + 1}
                  </span>
                  {StatusIcon ? (
                    <StatusIcon
                      className={cn(
                        'h-4 w-4',
                        stepDone ? 'text-emerald-500' : 'text-muted-foreground/50',
                      )}
                      aria-hidden
                    />
                  ) : (
                    <span className="h-4 w-4" aria-hidden />
                  )}
                </div>
                <div className="min-w-0 flex-1 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{step.title}</span>
                    {informational ? null : 'optional' in step && step.optional ? (
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                        {t('statusOptional')}
                      </span>
                    ) : (
                      <span
                        className={cn(
                          'text-[10px] font-semibold uppercase tracking-wide',
                          stepDone ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400',
                        )}
                      >
                        {stepDone ? t('statusOn') : t('statusOff')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">{step.body}</p>
                  {'action' in step && step.action ? (
                    <button
                      type="button"
                      onClick={step.onAction}
                      className="text-xs font-semibold text-primary hover:underline underline-offset-2"
                    >
                      {step.action}
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    );
  },
);

UnattendedDesktopGuideCard.displayName = 'UnattendedDesktopGuideCard';

export default UnattendedDesktopGuideCard;
