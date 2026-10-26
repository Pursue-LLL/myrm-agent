'use client';

/**
 * [INPUT]
 * - `@/lib/backend-health` (`fetchBackendHealth`)
 * - `next-intl` (`notifications.*`, `common.close`)
 *
 * [OUTPUT]
 * - `SystemStatusBanner`: DB degrade/recover global banner + reset action, and a persistent
 *   dismissible toast when the memory store is not being saved (`system_status.vector_degraded`)
 *
 * [POS]
 * Root-level banner in `LocalizedProviders`. Reads `/api/v1/health` on mount: shows i18n copy when
 * `system_status.database_degraded`, toast on `database_recovered`. The vector store opens in the
 * backend's background warmup and can finish after the first read, so a few delayed rechecks
 * look for `vector_degraded` until it is reported once.
 */

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { AlertTriangle, Database, X } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { apiRequest } from '@/lib/api';
import { fetchBackendHealth } from '@/lib/backend-health';
import { confirmAction } from '@/lib/app-dialog';

const VECTOR_DEGRADED_TOAST_ID = 'vector-degraded';
/** Delays after mount (ms); covers the backend warmup that creates the vector store. */
const VECTOR_RECHECK_DELAYS_MS = [8_000, 30_000, 90_000] as const;

function resolveErrorMessage(error: unknown): string | undefined {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return undefined;
}

export default function SystemStatusBanner() {
  const t = useTranslations('notifications');
  const tCommon = useTranslations('common');
  const [degraded, setDegraded] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let vectorReported = false;

    const checkStatus = async (isInitial: boolean) => {
      const data = await fetchBackendHealth();
      const status = data?.system_status;
      if (cancelled || !status) {
        return;
      }

      if (isInitial) {
        if (status.database_recovered) {
          toast.success(t('databaseRecoveredTitle'), {
            description: t('databaseRecoveredDesc'),
            icon: <Database className="w-4 h-4" />,
            duration: 5000,
          });
        }
        if (status.database_degraded) {
          setDegraded(true);
        }
      }
      if (status.vector_degraded && !vectorReported) {
        vectorReported = true;
        toast.warning(t('vectorDegradedTitle'), {
          id: VECTOR_DEGRADED_TOAST_ID,
          description: t('vectorDegradedDesc'),
          duration: Number.POSITIVE_INFINITY,
          dismissible: true,
        });
      }
    };

    void checkStatus(true);
    const recheckTimers = VECTOR_RECHECK_DELAYS_MS.map((delay) =>
      setTimeout(() => {
        if (!vectorReported) {
          void checkStatus(false);
        }
      }, delay),
    );

    return () => {
      cancelled = true;
      recheckTimers.forEach(clearTimeout);
    };
  }, [t]);

  const handleReset = async () => {
    const confirmed = await confirmAction({
      variant: 'destructive',
      description: t('databaseResetConfirm'),
      confirmText: t('databaseResetNow'),
    });
    if (!confirmed) {
      return;
    }

    setIsResetting(true);
    try {
      await apiRequest('/health/database/reset', {
        method: 'POST',
        silent: true,
      });

      toast.success(t('databaseResetSuccessTitle'), {
        description: t('databaseResetSuccessDesc'),
      });
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } catch (error: unknown) {
      console.error(error);
      const message = resolveErrorMessage(error) ?? t('databaseResetFailedNetwork');
      toast.error(t('databaseResetFailedTitle'), {
        description: t('databaseResetFailedDesc', { message }),
      });
      setIsResetting(false);
    }
  };

  if (!degraded || dismissed) {
    return null;
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-destructive text-destructive-foreground px-4 py-3 myrm-safe-top-banner shadow-md flex items-center justify-between animate-in slide-in-from-top">
      <div className="flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 flex-shrink-0" />
        <div className="text-sm">
          <span className="font-bold mr-2">{t('databaseDegradedTitle')}</span>
          {t('databaseDegradedBody')}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="secondary" size="sm" className="h-8 text-xs" onClick={handleReset} disabled={isResetting}>
          {isResetting ? t('databaseResetting') : t('databaseResetNow')}
        </Button>
        <button
          onClick={() => setDismissed(true)}
          className="p-1 hover:bg-black/10 rounded-full transition-colors"
          aria-label={tCommon('close')}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
