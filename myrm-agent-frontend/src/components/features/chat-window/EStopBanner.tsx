'use client';

import { useCallback, useEffect, useState } from 'react';
import { OctagonPause } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import { apiRequest } from '@/lib/api';
import { showI18nToast } from '@/services/i18nToastService';

type EStopStatus = {
  level: string;
  reason: string;
};

const ESTOP_CHANGED_EVENT = 'estop-changed';

export default function EStopBanner() {
  const t = useTranslations('estopBanner');
  const [status, setStatus] = useState<EStopStatus | null>(null);
  const [resuming, setResuming] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await apiRequest<EStopStatus>('/security/estop');
      if (data.level === 'none') {
        setStatus(null);
      } else {
        setStatus(data);
      }
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();

    const onChange = () => {
      void fetchStatus();
    };
    const onFocus = () => {
      void fetchStatus();
    };

    window.addEventListener(ESTOP_CHANGED_EVENT, onChange);
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener(ESTOP_CHANGED_EVENT, onChange);
      window.removeEventListener('focus', onFocus);
    };
  }, [fetchStatus]);

  const handleResume = useCallback(async () => {
    setResuming(true);
    try {
      await apiRequest<EStopStatus>('/security/estop', {
        method: 'POST',
        body: JSON.stringify({ action: 'resume' }),
      });
      setStatus(null);
      window.dispatchEvent(new Event(ESTOP_CHANGED_EVENT));
      showI18nToast('commands.builtin.freezeResumed', undefined, { type: 'success' });
    } catch {
      showI18nToast('commands.builtin.freezeFailed', undefined, { type: 'error' });
    } finally {
      setResuming(false);
    }
  }, []);

  if (!status) return null;

  const reasonText = status.reason.trim();

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cn(
        'relative overflow-hidden border-b border-destructive/20',
        'bg-gradient-to-r from-destructive/10 via-destructive/5 to-transparent',
        'backdrop-blur-md supports-[backdrop-filter]:bg-destructive/5',
      )}
    >
      <div className="absolute inset-y-0 left-0 w-[3px] bg-gradient-to-b from-destructive/80 via-destructive to-destructive/40" />
      <div
        className={cn(
          'flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between',
          'px-3 py-2.5 pl-4 sm:px-4 sm:py-2 sm:pl-5',
        )}
      >
        <div className="flex min-w-0 items-start gap-2.5 sm:items-center">
          <span
            className={cn(
              'flex h-7 w-7 shrink-0 items-center justify-center rounded-full',
              'bg-destructive/15 text-destructive ring-1 ring-destructive/25',
              'dark:bg-destructive/20 dark:text-destructive dark:ring-destructive/30',
            )}
          >
            <OctagonPause className="h-3.5 w-3.5" aria-hidden />
          </span>
          <div className="min-w-0 space-y-0.5">
            <p className="text-sm font-semibold leading-tight text-destructive dark:text-destructive">
              {t('message')}
            </p>
            <p className="text-xs leading-snug text-muted-foreground">
              {reasonText || t('hint')}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="destructive"
          size="sm"
          className={cn(
            'h-8 w-full shrink-0 rounded-full px-4 text-xs font-semibold sm:w-auto',
            'bg-destructive/90 hover:bg-destructive',
          )}
          onClick={() => void handleResume()}
          disabled={resuming}
        >
          {resuming ? t('resuming') : t('resume')}
        </Button>
      </div>
    </div>
  );
}
