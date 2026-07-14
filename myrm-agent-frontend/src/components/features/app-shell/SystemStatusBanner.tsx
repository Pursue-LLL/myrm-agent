'use client';

/**
 * [INPUT]
 * - `@/lib/backend-health` (`fetchBackendHealth`)
 * - `next-intl` (`notifications.*`, `common.close`)
 *
 * [OUTPUT]
 * - `SystemStatusBanner`: mount-time DB degrade/recover global banner + reset action
 *
 * [POS]
 * Root-level banner in `LocalizedProviders`. Checks `/api/v1/health` once on mount;
 * shows i18n copy when `system_status.database_degraded`; toast on `database_recovered`.
 */

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { AlertTriangle, Database, X } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { apiRequest } from '@/lib/api';
import { fetchBackendHealth } from '@/lib/backend-health';

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
    const checkStatus = async () => {
      const data = await fetchBackendHealth();
      const status = data?.system_status;
      if (!status) return;

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
    };
    checkStatus();
  }, [t]);

  const handleReset = async () => {
    if (!confirm(t('databaseResetConfirm'))) {
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

  if (!degraded || dismissed) return null;

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
