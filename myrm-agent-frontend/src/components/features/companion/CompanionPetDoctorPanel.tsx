'use client';

/**
 * CompanionPetDoctorPanel — GUI health check for companion sprite setup.
 *
 * [INPUT]
 * - @/services/companion/petDoctor (POS: doctor API client)
 * - @/services/companion/companionDoctorCheckI18nCore (POS: doctor check i18n)
 * - useCompanionStore (POS: spriteEnabled + openCompanionHealthCheck)
 *
 * [OUTPUT]
 * - CompanionPetDoctorPanel: collapsible pass/warn/fail checks with fix actions
 *
 * [POS]
 * Embedded in PetGallery; server checks merge with local spriteEnabled state.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/primitives/button';
import {
  fetchCompanionDoctor,
  type CompanionDoctorCheck,
  type DoctorCheckStatus,
} from '@/services/companion/petDoctor';
import {
  localizeDoctorCheckMessage,
  type DoctorCheckMessageContext,
} from '@/services/companion/companionDoctorCheckI18nCore';
import { cn } from '@/lib/utils/classnameUtils';
import useCompanionStore from '@/store/useCompanionStore';

interface CompanionPetDoctorPanelProps {
  expanded: boolean;
  onExpandedChange: (open: boolean) => void;
}

function statusClass(status: DoctorCheckStatus): string {
  switch (status) {
    case 'pass':
      return 'text-primary';
    case 'warn':
      return 'text-amber-600 dark:text-amber-400';
    case 'fail':
      return 'text-destructive';
    default:
      return 'text-muted-foreground';
  }
}

export function CompanionPetDoctorPanel({
  expanded,
  onExpandedChange,
}: CompanionPetDoctorPanelProps) {
  const t = useTranslations('companion');
  const router = useRouter();
  const spriteEnabled = useCompanionStore((s) => s.spriteEnabled);
  const setSpriteEnabled = useCompanionStore((s) => s.setSpriteEnabled);
  const openCompanionHealthCheck = useCompanionStore((s) => s.openCompanionHealthCheck);

  const [loading, setLoading] = useState(false);
  const [checks, setChecks] = useState<CompanionDoctorCheck[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageContext, setMessageContext] = useState<DoctorCheckMessageContext>({});

  const runDoctor = useCallback(async (rescan = false) => {
    setLoading(true);
    setError(null);
    try {
      const report = await fetchCompanionDoctor(rescan);
      const clientChecks: CompanionDoctorCheck[] = [
        {
          id: 'ui.sprite_enabled',
          status: spriteEnabled ? 'pass' : 'fail',
          message: spriteEnabled
            ? t('doctor.checks.spriteEnabledPass')
            : t('doctor.checks.spriteEnabledFail'),
          fixAction: spriteEnabled ? null : 'enable_sprite_overlay',
        },
      ];
      setChecks([...report.checks, ...clientChecks]);
      setMessageContext({
        activeSlug: report.activeSlug,
        installedCount: report.installedCount,
      });
      setReady(report.ready && spriteEnabled);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
      setChecks([]);
      setReady(false);
    } finally {
      setLoading(false);
    }
  }, [spriteEnabled, t]);

  useEffect(() => {
    if (!expanded) {return;}
    void runDoctor(false);
  }, [expanded, runDoctor]);

  const handleFix = useCallback(
    (action: string | null) => {
      if (!action) {return;}
      if (action === 'open_experimental_companion') {
        router.push('/settings/developer?sub=experimental');
        return;
      }
      if (action === 'open_pet_gallery') {
        openCompanionHealthCheck();
        return;
      }
      if (action === 'enable_sprite_overlay') {
        setSpriteEnabled(true);
        void runDoctor(false);
        return;
      }
      if (action === 'doctor_rescan') {
        void runDoctor(true);
      }
    },
    [openCompanionHealthCheck, router, runDoctor, setSpriteEnabled],
  );

  const resolveCheckMessage = useCallback(
    (check: CompanionDoctorCheck) => {
      if (check.id === 'ui.sprite_enabled') {
        return check.message;
      }
      return localizeDoctorCheckMessage(t, check, messageContext);
    },
    [messageContext, t],
  );

  const failedCount = checks.filter((c) => c.status === 'fail').length;

  return (
    <div className="rounded-lg border border-border/60 bg-muted/20" data-testid="companion-pet-doctor">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
        onClick={() => onExpandedChange(!expanded)}
      >
        <span className="text-xs font-medium text-foreground">{t('doctor.title')}</span>
        <span className="text-[10px] text-muted-foreground">
          {ready ? t('doctor.ready') : failedCount > 0 ? t('doctor.issues', { count: failedCount }) : t('doctor.runHint')}
        </span>
      </button>

      {expanded && (
        <div className="space-y-2 border-t border-border/50 px-3 py-2">
          {loading && (
            <div className="flex items-center gap-2 py-1 text-xs text-muted-foreground">
              <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              {t('doctor.loading')}
            </div>
          )}

          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}

          {!loading && checks.length > 0 && (
            <ul className="space-y-1.5">
              {checks.map((check) => (
                <li key={check.id} className="flex items-start justify-between gap-2 text-[11px] leading-snug">
                  <span className={cn('min-w-0 flex-1', statusClass(check.status))}>
                    {resolveCheckMessage(check)}
                  </span>
                  {check.fixAction && check.status !== 'pass' && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 shrink-0 px-2 text-[10px]"
                      onClick={() => handleFix(check.fixAction)}
                    >
                      {t('doctor.fix')}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}

          <div className="flex gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-[10px]"
              disabled={loading}
              onClick={() => void runDoctor(false)}
            >
              {t('doctor.refresh')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-[10px]"
              disabled={loading}
              onClick={() => void runDoctor(true)}
            >
              {t('doctor.rescan')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
